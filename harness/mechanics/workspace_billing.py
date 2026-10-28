"""Workspace subscriptions and settled credit receipts, separate from agent spending.

The host supplies commissioned company/account bindings and credentials. HTTP routes
must authenticate owners and run these bounded synchronous methods off the event loop.
Stripe evidence: https://docs.stripe.com/webhooks and
https://docs.stripe.com/api/subscriptions/retrieve?api-version=2025-03-31.basil
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from decimal import Decimal, InvalidOperation
import fcntl
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import time
from urllib.parse import urlencode, urlsplit

import httpx

from company_usage import CompanyUsage
from workspace_identity import workspace_scope

API_VERSION = '2025-03-31.basil'
MAX_BODY = 256 * 1024
STATUSES = {'active', 'trialing', 'past_due', 'unpaid', 'canceled', 'incomplete', 'incomplete_expired', 'paused'}


class BillingError(ValueError):
    pass


class BillingUnavailable(BillingError):
    pass


def _require(value, message='Use the commissioned workspace billing configuration.'):
    if not value:
        raise BillingError(message)


def _id(value, prefix):
    _require(isinstance(value, str) and re.fullmatch(re.escape(prefix) + r'[A-Za-z0-9_]{1,180}', value),
             'Use the exact bound billing identifier.')
    return value


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _sha(value):
    return hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()


def _time(value):
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
            _require(parsed.tzinfo is not None)
            value = parsed.timestamp()
        except (ValueError, OverflowError):
            raise BillingError('Supply a billing expiry with its timezone.') from None
    _require(type(value) in {int, float} and 0 < value < 4_102_444_800)
    return int(value)


def _url(value, host=None):
    _require(isinstance(value, str) and len(value) <= 2048)
    parsed = urlsplit(value)
    _require(parsed.scheme == 'https' and parsed.hostname and not parsed.username and not parsed.password
             and not parsed.fragment and (host is None or parsed.hostname == host), 'Use the hosted billing URL.')
    return value


def _object_id(value):
    return value.get('id') if isinstance(value, dict) else value


def _form(value, parent=''):
    result = []
    if isinstance(value, dict):
        for key, item in value.items():
            result.extend(_form(item, f'{parent}[{key}]' if parent else key))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            result.extend(_form(item, f'{parent}[{index}]'))
    elif value is not None:
        result.append((parent, str(value).lower() if type(value) is bool else str(value)))
    return result


class StripeHTTPProvider:
    """Fixed Stripe origin, explicit account/mode, bounded bodies and no redirects."""
    def __init__(self, secret_key, *, account_id, livemode, transport=None):
        _id(account_id, 'acct_')
        _require(type(livemode) is bool and isinstance(secret_key, str)
                 and re.fullmatch(r'(?:sk|rk)_' + ('live' if livemode else 'test') + r'_[A-Za-z0-9_]+', secret_key))
        self._key = secret_key
        self.account_id, self.livemode, self.transport = account_id, livemode, transport
        self._verified = False

    def _request(self, method, path, payload=None, *, idempotency_key=None, verify=True):
        if verify and not self._verified:
            account = self._request('GET', '/v1/account', verify=False)
            _require(account.get('id') == self.account_id, 'Connect the commissioned Stripe account.')
            self._verified = True
        headers = {'Authorization': 'Bearer ' + self._key, 'Stripe-Version': API_VERSION}
        if idempotency_key:
            headers['Idempotency-Key'] = idempotency_key
        arguments = {}
        if payload is not None:
            headers['Content-Type'] = 'application/x-www-form-urlencoded'
            arguments['content'] = urlencode(_form(payload)).encode()
        try:
            with httpx.Client(timeout=httpx.Timeout(10, connect=5), follow_redirects=False,
                              trust_env=False, transport=self.transport) as client:
                with client.stream(method, 'https://api.stripe.com' + path, headers=headers, **arguments) as response:
                    raw = bytearray()
                    for chunk in response.iter_bytes():
                        raw.extend(chunk)
                        if len(raw) > MAX_BODY:
                            raise BillingUnavailable('Retry billing verification.')
                    if response.status_code < 200 or response.status_code >= 300:
                        raise BillingUnavailable('Retry billing verification.')
            result = json.loads(raw)
            _require(isinstance(result, dict), 'Verify the billing provider response.')
            if 'livemode' in result:
                _require(result['livemode'] is self.livemode, 'Use the commissioned Stripe mode.')
            return result
        except (httpx.HTTPError, UnicodeError, json.JSONDecodeError):
            raise BillingUnavailable('Retry billing verification.') from None

    def retrieve_subscription(self, identifier):
        return self._request('GET', '/v1/subscriptions/' + _id(identifier, 'sub_'))

    def retrieve_checkout(self, identifier):
        return self._request('GET', '/v1/checkout/sessions/' + _id(identifier, 'cs_') + '?expand[]=line_items')

    def retrieve_payment(self, identifier):
        return self._request('GET', '/v1/payment_intents/' + _id(identifier, 'pi_') + '?expand[]=latest_charge')

    def create_checkout(self, payload, *, idempotency_key):
        return self._request('POST', '/v1/checkout/sessions', payload, idempotency_key=idempotency_key)

    def create_portal(self, payload, *, idempotency_key):
        return self._request('POST', '/v1/billing_portal/sessions', payload, idempotency_key=idempotency_key)


def usage_credit_callback(state):
    """Host-only sink for this module's verified receipts; reuse the existing ledger.

    Keep this callback private to webhook processing. CompanyUsage retains its rule
    separating operator allowances from real prepaid funds. It creates no new balance.
    """
    company = workspace_scope(state)

    def apply(receipt):
        _require(receipt.get('company_id') == company and receipt.get('settled') is True
                 and receipt.get('livemode') is True, 'Fund usage from a live settled payment receipt.')
        amount = Decimal(receipt['amount_usd'])
        _require(amount.is_finite() and 0 < amount <= 1_000_000 and amount * 1_000_000 == int(amount * 1_000_000))
        pool = CompanyUsage.agent_pool(state)
        with pool.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            binding = pool._openai_binding(db)
            _require(binding['parent_company_scope'] == company)
            pool._fund(db, receipt['key'], int(amount * 1_000_000), 'prepaid_customer_funds', _sha(_json(receipt)),
                       receipt_reference=receipt['checkout_id'], stripe_account=receipt['account_id'],
                       stripe_customer=receipt['customer_id'], payment_intent=receipt['payment_intent'],
                       verified_by='stripe_signed_webhook_and_canonical_checkout')
        return pool.summary()
    return apply


class WorkspaceBilling:
    def __init__(self, state, *, environment_id, company_id, config=None, provider=None,
                 webhook_secret=None, clock=time.time, credit_receipt=None):
        self.state = Path(state).resolve()
        _require(company_id == workspace_scope(self.state), 'Use this workspace’s billing identity.')
        _require(isinstance(environment_id, str) and re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}', environment_id))
        self.environment_id, self.company_id = environment_id, company_id
        self.provider, self.webhook_secret, self.clock = provider, webhook_secret, clock
        self.credit_receipt = credit_receipt
        self.config = json.loads(_json(config)) if config is not None else {}
        self._validate()
        self.path = self.state / 'workspace-billing.sqlite'
        _require(not self.path.is_symlink())
        with self._connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS identity(singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                    environment TEXT NOT NULL,company TEXT NOT NULL,account TEXT,customer TEXT,livemode INTEGER);
                CREATE TABLE IF NOT EXISTS subscription(singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                    id TEXT NOT NULL,snapshot TEXT,checked_at REAL,past_due_since REAL);
                CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY,sha256 TEXT NOT NULL,payload TEXT NOT NULL,
                    state TEXT NOT NULL,received_at REAL NOT NULL,processed_at REAL);
                CREATE TABLE IF NOT EXISTS requests(key TEXT PRIMARY KEY,kind TEXT NOT NULL,payload TEXT NOT NULL,
                    response TEXT,created_at REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS checkouts(id TEXT PRIMARY KEY,kind TEXT NOT NULL,
                    request_key TEXT NOT NULL UNIQUE,price TEXT NOT NULL,credit_usd TEXT);
                CREATE TABLE IF NOT EXISTS credit_receipts(id TEXT PRIMARY KEY,receipt TEXT NOT NULL,state TEXT NOT NULL,
                    payment_id TEXT NOT NULL UNIQUE);
                CREATE TABLE IF NOT EXISTS observations(sequence INTEGER PRIMARY KEY,snapshot TEXT NOT NULL,
                    source TEXT NOT NULL,checked_at REAL NOT NULL);
            ''')
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM identity').fetchone()
            account = self.config.get('account_id')
            customer = self.config.get('customer_id')
            live = self.config.get('livemode')
            if row:
                _require(row['environment'] == environment_id and row['company'] == company_id)
                if account and row['account']:
                    _require((row['account'], row['customer'], row['livemode']) == (account, customer, live))
                elif account:
                    db.execute('UPDATE identity SET account=?,customer=?,livemode=? WHERE singleton=1', (account, customer, live))
            else:
                db.execute('INSERT INTO identity VALUES(1,?,?,?,?,?)', (environment_id, company_id, account, customer, live))
            identifier = self.config.get('subscription_id')
            prior = db.execute('SELECT id FROM subscription').fetchone()
            if identifier:
                _require(prior is None or prior['id'] == identifier, 'Reconcile the bound subscription first.')
                db.execute('INSERT OR IGNORE INTO subscription(singleton,id) VALUES(1,?)', (identifier,))
        self.path.chmod(0o600)

    def _validate(self):
        value = self.config
        if not value:
            return
        fields = {'schema_version', 'environment_id', 'company_id', 'mode', 'demo_expires_at',
                  'account_id', 'livemode', 'customer_id', 'subscription_id', 'price_id', 'allowed_price_ids',
                  'return_url', 'grace_seconds', 'max_staleness_seconds', 'credit_pack', 'portal_configuration_id'}
        _require(set(value) <= fields and value.get('schema_version') == 1
                 and value.get('environment_id') == self.environment_id and value.get('company_id') == self.company_id
                 and value.get('mode') in {'demo', 'subscription'})
        if value['mode'] == 'demo':
            value['demo_expires_at'] = _time(value.get('demo_expires_at'))
        else:
            _require(value.get('demo_expires_at') is None)
        for key, default, maximum in [('grace_seconds', 0, 30 * 86400), ('max_staleness_seconds', 86400, 7 * 86400)]:
            number = value.get(key, default)
            _require(type(number) is int and 0 <= number <= maximum and (key != 'max_staleness_seconds' or number > 0))
            value[key] = number
        if value['mode'] == 'subscription' or value.get('account_id'):
            for field, prefix in [('account_id', 'acct_'), ('customer_id', 'cus_'), ('price_id', 'price_')]:
                _id(value.get(field), prefix)
            _require(type(value.get('livemode')) is bool)
            _url(value.get('return_url'))
            allowed = value.get('allowed_price_ids')
            _require(isinstance(allowed, list) and 1 <= len(allowed) <= 20 and value['price_id'] in allowed)
            for identifier in allowed:
                _id(identifier, 'price_')
            if value.get('subscription_id'):
                _id(value['subscription_id'], 'sub_')
            if value.get('portal_configuration_id'):
                _id(value['portal_configuration_id'], 'bpc_')
            pack = value.get('credit_pack')
            if pack is not None:
                _require(isinstance(pack, dict) and set(pack) == {'price_id', 'amount_usd'})
                _id(pack['price_id'], 'price_')
                try:
                    _require(isinstance(pack['amount_usd'], str))
                    amount = Decimal(pack['amount_usd'])
                    _require(amount.is_finite() and 0 < amount <= 1_000_000
                             and amount * 1_000_000 == int(amount * 1_000_000))
                except (InvalidOperation, ValueError):
                    raise BillingError('Set the commissioned credit pack amount.') from None
                pack['amount_usd'] = f'{amount:.6f}'
        else:
            _require(not (set(value) & {'customer_id', 'subscription_id', 'price_id', 'credit_pack', 'livemode'}))

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        return db

    @contextmanager
    def _locked(self):
        descriptor = os.open(self.state / '.workspace-billing.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            info = os.fstat(descriptor)
            _require(stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid() and info.st_mode & 0o077 == 0)
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield
        finally:
            os.close(descriptor)

    def _ready(self):
        _require(self.provider is not None and self.config.get('account_id'), 'Connect workspace billing.')

    def _metadata(self):
        return {'environment_id': self.environment_id, 'company_id': self.company_id}

    def status(self):
        now = self.clock()
        with self._connect() as db:
            row = db.execute('SELECT * FROM subscription').fetchone()
        subscription = {'id': row['id'] if row else None, 'status': 'unverified', 'checked_at': None,
                        'current_period_end': None, 'cancel_at_period_end': False, 'grace_until': None}
        operational, reason = False, 'subscription_required'
        if row and row['snapshot']:
            subscription.update(json.loads(row['snapshot']), checked_at=row['checked_at'])
            status = subscription['status']
            fresh = now < row['checked_at'] + self.config.get('max_staleness_seconds', 86400)
            if status in {'active', 'trialing'}:
                end = subscription['current_period_end']
                operational = fresh and now < end
                reason = 'subscription' if operational else 'verification_required'
            elif status == 'past_due':
                deadline = row['past_due_since'] + self.config.get('grace_seconds', 0)
                subscription['grace_until'] = deadline
                operational = fresh and now < deadline
                reason = 'payment_grace' if operational else 'payment_required'
            else:
                reason = status
        expiry = self.config.get('demo_expires_at') if self.config.get('mode') == 'demo' else None
        if not operational and expiry and now < expiry:
            operational, reason = True, 'demo'
        elif not operational and expiry and reason == 'subscription_required':
            reason = 'demo_expired'
        credits = CompanyUsage.agent_pool(self.state).summary()
        funded = Decimal(credits['available_usd']) > 0 and Decimal(credits['monthly_available_usd']) > 0
        ready = self.provider is not None and bool(self.config.get('account_id'))
        return {'mode': self.config.get('mode', 'unconfigured'), 'operational': operational, 'reason': reason,
                'demo_expires_at': expiry, 'subscription': subscription, 'checkout_available': ready and row is None,
                'portal_available': ready, 'credits_available': ready and bool(self.config.get('credit_pack'))
                and self.credit_receipt is not None and self.config.get('livemode') is True
                and credits['funding_kind'] == 'prepaid_customer_funds',
                'credits': credits, 'agent_work': operational and funded}

    def access(self):
        return self.status()

    def require_operational(self):
        # Admission checks entitlement; existing per-turn reservations own spending.
        if self.config and not self.status()['operational']:
            raise BillingError('Update workspace billing to continue agent work.')
        return True

    def _reconcile(self, source, identifier=None):
        self._ready()
        with self._connect() as db:
            prior = db.execute('SELECT * FROM subscription').fetchone()
        identifier = identifier or (prior['id'] if prior else None)
        if identifier is None:
            return
        _id(identifier, 'sub_')
        _require(prior is None or prior['id'] == identifier, 'Reconcile the bound subscription first.')
        value = self.provider.retrieve_subscription(identifier)
        try:
            snapshot = self._subscription_snapshot(value, identifier)
        except BillingError:
            with self._connect() as db:
                db.execute('UPDATE subscription SET checked_at=0 WHERE singleton=1')
            raise
        status = snapshot['status']
        now = self.clock()
        previous_status = json.loads(prior['snapshot'])['status'] if prior and prior['snapshot'] else None
        overdue = prior['past_due_since'] if previous_status == 'past_due' and status == 'past_due' else now if status == 'past_due' else None
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('INSERT INTO subscription VALUES(1,?,?,?,?) ON CONFLICT(singleton) DO UPDATE SET '
                       'id=excluded.id,snapshot=excluded.snapshot,checked_at=excluded.checked_at,past_due_since=excluded.past_due_since',
                       (identifier, _json(snapshot), now, overdue))
            db.execute('INSERT INTO observations(snapshot,source,checked_at) VALUES(?,?,?)', (_json(snapshot), source, now))

    def _subscription_snapshot(self, value, identifier):
        _require(isinstance(value, dict))
        _require(value.get('id') == identifier and _object_id(value.get('customer')) == self.config['customer_id']
                 and value.get('livemode') is self.config['livemode'], 'Verify this workspace’s subscription.')
        items = value.get('items')
        _require(isinstance(items, dict) and items.get('has_more') is not True)
        rows = items.get('data')
        _require(isinstance(rows, list) and len(rows) == 1 and isinstance(rows[0], dict) and type(rows[0].get('quantity')) is int and rows[0]['quantity'] == 1
                 and _object_id(rows[0].get('price')) in self.config['allowed_price_ids'])
        status = value.get('status')
        _require(status in STATUSES)
        end = _time(rows[0].get('current_period_end', value.get('current_period_end')))
        if status == 'trialing':
            end = min(end, _time(value.get('trial_end')))
        cancel = value.get('cancel_at_period_end')
        _require(type(cancel) is bool)
        if value.get('cancel_at'):
            end = min(end, _time(value['cancel_at']))
        return {'id': identifier, 'status': status, 'current_period_end': end,
                'cancel_at_period_end': cancel, 'price_id': _object_id(rows[0]['price'])}

    def reconcile(self):
        with self._locked():
            self._reconcile('reconcile')
        return self.status()

    def _request_key(self, request_id, kind):
        _require(isinstance(request_id, str) and re.fullmatch(r'[A-Za-z0-9_-]{1,100}', request_id),
                 'Supply a stable billing request identifier.')
        return 'billing-' + _sha(self.company_id + '\0' + kind + '\0' + request_id)

    def checkout(self, *, owner, request_id, kind='subscription'):
        if owner is not True:
            raise PermissionError('An owner can manage workspace billing.')
        self._ready()
        _require(kind in {'subscription', 'credits'})
        key = self._request_key(request_id, kind)
        with self._locked(), self._connect() as db:
            old = db.execute('SELECT * FROM requests WHERE key=?', (key,)).fetchone()
            if old and old['response']:
                return json.loads(old['response'])
            if old:
                _require(self.clock() - old['created_at'] < 23 * 3600,
                         'Reconcile the previous checkout before creating another.')
                payload = json.loads(old['payload'])
            else:
                if kind == 'subscription':
                    _require(db.execute('SELECT id FROM subscription').fetchone() is None,
                             'Manage the current subscription through billing.')
                    pending = db.execute("SELECT c.id,r.response FROM checkouts c JOIN requests r ON r.key=c.request_key WHERE c.kind='subscription' ORDER BY r.created_at DESC LIMIT 1").fetchone()
                    if pending:
                        session = self.provider.retrieve_checkout(pending['id'])
                        _require(session.get('id') == pending['id']
                                 and _object_id(session.get('customer')) == self.config['customer_id']
                                 and session.get('livemode') is self.config['livemode'])
                        if session.get('status') == 'open':
                            return json.loads(pending['response'])
                        _require(session.get('status') == 'expired', 'Complete billing verification before a new subscription.')
                    # An uncertain creation has no session receipt yet: retain its idempotency identity.
                    _require(db.execute("SELECT 1 FROM requests WHERE kind='subscription' AND response IS NULL").fetchone() is None,
                             'Retry the original checkout request before creating another.')
                    price = self.config['price_id']
                else:
                    _require(self.config.get('credit_pack') and self.credit_receipt is not None,
                             'Connect the commissioned credit pack and receipt ledger.')
                    if self.config['livemode']:
                        _require(CompanyUsage.agent_pool(self.state).summary()['funding_kind'] == 'prepaid_customer_funds',
                                 'Reconcile the operator allowance before accepting customer credit payments.')
                    price = self.config['credit_pack']['price_id']
                payload = {'mode': 'subscription' if kind == 'subscription' else 'payment',
                           'customer': self.config['customer_id'], 'line_items': [{'price': price, 'quantity': 1}],
                           'success_url': self.config['return_url'], 'cancel_url': self.config['return_url'],
                           'metadata': {**self._metadata(), 'billing_kind': kind}}
                if kind == 'credits':
                    payload['metadata']['credit_amount_usd'] = self.config['credit_pack']['amount_usd']
                if kind == 'subscription':
                    payload['subscription_data'] = {'metadata': self._metadata()}
                db.execute('INSERT INTO requests VALUES(?,?,?,?,?)', (key, kind, _json(payload), None, self.clock()))
                db.commit()
            result = self.provider.create_checkout(payload, idempotency_key=key)
            _id(result.get('id'), 'cs_')
            _require(_object_id(result.get('customer')) == self.config['customer_id']
                     and result.get('livemode') is self.config['livemode'])
            receipt = {'id': result['id'], 'url': _url(result.get('url'), 'checkout.stripe.com')}
            db.execute('INSERT OR IGNORE INTO checkouts VALUES(?,?,?,?,?)', (result['id'], kind, key,
                       payload['line_items'][0]['price'], payload['metadata'].get('credit_amount_usd')))
            db.execute('UPDATE requests SET response=? WHERE key=?', (_json(receipt), key))
            return receipt

    def portal(self, *, owner, request_id):
        if owner is not True:
            raise PermissionError('An owner can manage workspace billing.')
        self._ready()
        key = self._request_key(request_id, 'portal')
        payload = {'customer': self.config['customer_id'], 'return_url': self.config['return_url']}
        if self.config.get('portal_configuration_id'):
            payload['configuration'] = self.config['portal_configuration_id']
        result = self.provider.create_portal(payload, idempotency_key=key)
        return {'url': _url(result.get('url'), 'billing.stripe.com')}

    def _verify_event(self, raw, signature):
        _require(isinstance(raw, bytes) and len(raw) <= MAX_BODY and isinstance(signature, str) and len(signature) <= 4096,
                 'Supply a bounded signed billing event.')
        secret = self.webhook_secret() if callable(self.webhook_secret) else self.webhook_secret
        _require(isinstance(secret, str) and secret.startswith('whsec_'), 'Connect the billing webhook secret.')
        parts = signature.split(',')
        timestamps = [part[2:] for part in parts if part.startswith('t=')]
        signatures = [part[3:] for part in parts if part.startswith('v1=')]
        _require(len(timestamps) == 1 and timestamps[0].isdigit() and signatures, 'Verify the billing event signature.')
        _require(abs(self.clock() - int(timestamps[0])) <= 300, 'Verify the billing event timestamp.')
        expected = hmac.new(secret.encode(), timestamps[0].encode() + b'.' + raw, hashlib.sha256).hexdigest()
        _require(any(hmac.compare_digest(expected, candidate) for candidate in signatures), 'Verify the billing event signature.')
        try:
            event = json.loads(raw)
        except (ValueError, UnicodeError):
            raise BillingError('Supply a complete billing event.') from None
        _require(isinstance(event, dict))
        _id(event.get('id'), 'evt_')
        _require(event.get('livemode') is self.config.get('livemode')
                 and event.get('account', self.config.get('account_id')) == self.config.get('account_id'),
                 'Use this account’s billing event.')
        _require(isinstance(event.get('type'), str) and isinstance(event.get('data'), dict)
                 and isinstance(event['data'].get('object'), dict))
        return event

    def _credit(self, row, session):
        if session.get('status') != 'complete' or session.get('payment_status') != 'paid':
            return
        items = session.get('line_items')
        _require(isinstance(items, dict) and items.get('has_more') is not True)
        rows = items.get('data')
        _require(session.get('mode') == 'payment' and isinstance(rows, list) and len(rows) == 1
                 and isinstance(rows[0], dict) and type(rows[0].get('quantity')) is int and rows[0]['quantity'] == 1 and _object_id(rows[0].get('price')) == row['price'])
        _require(type(session.get('amount_total')) is int and session['amount_total'] > 0
                 and isinstance(session.get('currency'), str) and re.fullmatch('[a-z]{3}', session['currency']))
        payment = _id(_object_id(session.get('payment_intent')), 'pi_')
        paid = self.provider.retrieve_payment(payment)
        _require(isinstance(paid, dict) and paid.get('id') == payment and paid.get('status') == 'succeeded'
                 and _object_id(paid.get('customer')) == self.config['customer_id']
                 and paid.get('livemode') is self.config['livemode']
                 and paid.get('currency') == session['currency']
                 and type(paid.get('amount_received')) is int and paid['amount_received'] >= session['amount_total'])
        charge = paid.get('latest_charge')
        _require(isinstance(charge, dict) and charge.get('paid') is True and charge.get('refunded') is False
                 and charge.get('amount_refunded') == 0 and charge.get('disputed') is False,
                 'Review this credit payment before applying funds.')
        receipt = {'key': 'stripe:' + self.config['account_id'] + ':' + session['id'], 'settled': True,
                   'company_id': self.company_id, 'environment_id': self.environment_id,
                   'account_id': self.config['account_id'], 'customer_id': self.config['customer_id'],
                   'livemode': self.config['livemode'], 'checkout_id': session['id'], 'payment_intent': payment, 'price_id': row['price'],
                   'amount_usd': row['credit_usd'], 'paid_amount_minor': session['amount_total'],
                   'paid_currency': session['currency']}
        with self._connect() as db:
            prior = db.execute('SELECT * FROM credit_receipts WHERE id=?', (session['id'],)).fetchone()
            if prior:
                _require(prior['receipt'] == _json(receipt), 'Reconcile the original credit payment receipt.')
                if prior['state'] == 'applied':
                    return
            else:
                _require(db.execute('SELECT id FROM credit_receipts WHERE payment_id=?', (payment,)).fetchone() is None,
                         'Reconcile the existing receipt for this payment.')
                db.execute('INSERT INTO credit_receipts VALUES(?,?,?,?)', (session['id'], _json(receipt), 'pending', payment))
        if self.credit_receipt is None:
            raise BillingUnavailable('Connect the settled usage credit ledger.')
        self.credit_receipt(receipt)  # callback must be idempotent on receipt.key, including crash recovery
        with self._connect() as db:
            db.execute("UPDATE credit_receipts SET state='applied' WHERE id=?", (session['id'],))

    def handle_webhook(self, raw, signature):
        self._ready()
        event = self._verify_event(raw, signature)
        with self._locked():
            with self._connect() as db:
                prior = db.execute('SELECT * FROM events WHERE id=?', (event['id'],)).fetchone()
                if prior:
                    _require(prior['sha256'] == _sha(raw), 'Reconcile the original billing event.')
                    if prior['state'] != 'pending':
                        return {'id': event['id'], 'state': prior['state'], 'duplicate': True}
                else:
                    db.execute('INSERT INTO events VALUES(?,?,?,?,?,NULL)',
                               (event['id'], _sha(raw), raw.decode(), 'pending', self.clock()))
            state = 'ignored'
            value, kind = event['data']['object'], event['type']
            if _object_id(value.get('customer')) == self.config['customer_id']:
                if kind.startswith('customer.subscription.'):
                    with self._connect() as db:
                        row = db.execute('SELECT id FROM subscription').fetchone()
                    if row and value.get('id') == row['id']:
                        self._reconcile(event['id'])
                        state = 'processed'
                elif kind.startswith('invoice.'):
                    with self._connect() as db:
                        row = db.execute('SELECT id FROM subscription').fetchone()
                    subscription = _object_id(value.get('subscription'))
                    if subscription is None:
                        subscription = _object_id(((value.get('parent') or {}).get('subscription_details') or {}).get('subscription'))
                    if row and subscription == row['id']:
                        self._reconcile(event['id'])
                        state = 'processed'
                elif kind in {'checkout.session.completed', 'checkout.session.async_payment_succeeded'}:
                    with self._connect() as db:
                        row = db.execute('SELECT * FROM checkouts WHERE id=?', (value.get('id'),)).fetchone()
                    if row:
                        session = self.provider.retrieve_checkout(row['id'])
                        _require(session.get('id') == row['id'] and _object_id(session.get('customer')) == self.config['customer_id']
                                 and session.get('livemode') is self.config['livemode'])
                        metadata = session.get('metadata')
                        _require(isinstance(metadata, dict) and all(metadata.get(key) == expected
                                 for key, expected in self._metadata().items())
                                 and metadata.get('billing_kind') == row['kind'])
                        if row['kind'] == 'credits':
                            self._credit(row, session)
                        elif session.get('mode') == 'subscription' and session.get('status') == 'complete':
                            self._reconcile(event['id'], _id(_object_id(session.get('subscription')), 'sub_'))
                        state = 'processed'
            with self._connect() as db:
                db.execute('UPDATE events SET state=?,processed_at=? WHERE id=?', (state, self.clock(), event['id']))
            return {'id': event['id'], 'state': state, 'duplicate': False}
