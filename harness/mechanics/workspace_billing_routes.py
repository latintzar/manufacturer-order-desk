"""Shared workspace billing HTTP boundary and private per-workspace commissioning."""
import json
import os
import re
import stat
import threading
import time
from pathlib import Path
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from workspace_identity import workspace_scope
from workspace_billing import (WorkspaceBilling, StripeHTTPProvider, BillingError,
                               BillingUnavailable, MAX_BODY, usage_credit_callback)

class WorkspaceBillingHost:
    def __init__(self, state, access):
        self.state, self.access = Path(state), access
        self.cache = {}
        self.refresh_after = {}
        self.refresh_lock = threading.Lock()

    def get(self, environment):
        if not isinstance(environment, str) or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}', environment):
            raise BillingError('Choose a commissioned workspace.')
        with self.access.connect() as db:
            if not db.execute('SELECT 1 FROM environments WHERE id=?', (environment,)).fetchone():
                raise BillingError('Choose a commissioned workspace.')
        root = self.state if environment == 'demo' else self.state / 'environments' / environment
        path = root / 'workspace-billing.json'
        config = None
        fingerprint = None
        if path.exists() or path.is_symlink():
            info = path.lstat()
            if (not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077
                    or info.st_uid != os.getuid() or info.st_size > 16384):
                raise BillingError('Use a private workspace billing configuration.')
            try:
                config = json.loads(path.read_text())
            except (ValueError, UnicodeError):
                raise BillingError('Use a valid workspace billing configuration.') from None
            # Only an absent file is uncommissioned. A present broken/empty file
            # must never silently restore the legacy permissive billing mode.
            if not isinstance(config, dict) or not config:
                raise BillingError('Use a complete workspace billing configuration.')
            fingerprint = (info.st_mtime_ns, info.st_size)
        cached = self.cache.get(environment)
        if cached and cached[0] == fingerprint:
            return cached[1]
        provider = None
        try:
            if config and config.get('account_id') and os.environ.get('ROCOTO_STRIPE_SECRET_KEY'):
                provider = StripeHTTPProvider(os.environ['ROCOTO_STRIPE_SECRET_KEY'],
                    account_id=config['account_id'], livemode=config.get('livemode'))
            billing = WorkspaceBilling(root, environment_id=environment, company_id=workspace_scope(root),
                config=config, provider=provider, webhook_secret=os.environ.get('ROCOTO_STRIPE_WEBHOOK_SECRET'),
                credit_receipt=usage_credit_callback(root))
        except (ValueError, TypeError):
            raise BillingError('Use a valid workspace billing configuration.') from None
        self.cache[environment] = (fingerprint, billing)
        return billing

    def reconcile_due(self, environment):
        billing = self.get(environment)
        if not billing.config or billing.provider is None:
            return billing
        now = time.monotonic()
        with self.refresh_lock:
            if now < self.refresh_after.get(environment, 0):
                return billing
            self.refresh_after[environment] = now + 60
        try:
            billing.reconcile()
        except (BillingError, OSError):
            # Cached canonical evidence expires normally; an outage never extends it.
            return billing
        with self.refresh_lock:
            self.refresh_after[environment] = time.monotonic() + 3600
        return billing

    def admission(self, environment):
        billing = self.reconcile_due(environment)
        # Existing verticals adopt billing through an explicit commissioning file.
        return not billing.config or billing.status()['operational']


def register_workspace_billing(app, billing_host):
    def selected(request):
        session = request.state.session
        if not session:
            raise HTTPException(401, 'Sign in to your workspace.')
        try:
            return billing_host.get(session['environment']['id']), session
        except (ValueError, OSError):
            raise HTTPException(503, 'Billing setup is in progress.') from None

    def owner(session):
        return not session.get('viewing_as') and (session.get('role') == 'owner' or session.get('workspace_admin') is True)

    async def invoke(function, *args, **kwargs):
        try:
            return await run_in_threadpool(function, *args, **kwargs)
        except BillingUnavailable:
            raise HTTPException(503, 'Billing setup is in progress.') from None
        except BillingError:
            raise HTTPException(400, 'Review the workspace billing details.') from None

    @app.get('/api/billing/status')
    async def status(request: Request):
        billing, session = selected(request)
        billing = await invoke(billing_host.reconcile_due, session['environment']['id'])
        value = await invoke(billing.status)
        if not billing.config:
            value.update(mode='uncommissioned', operational=True, reason='setup_required')
        if not owner(session):
            value.update(checkout_available=False, portal_available=False, credit_checkout_available=False)
        value['credit_checkout_available'] = owner(session) and value.get('credits_available', False)
        value['can_manage'] = owner(session)
        return JSONResponse(value, headers={'Cache-Control':'private, no-store'})

    async def request_id(request):
        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > 4096:
                raise HTTPException(413, 'Use the billing controls.')
        try:
            value = json.loads(raw)
            if not isinstance(value, dict) or set(value) != {'request_id'}:
                raise ValueError()
            key = value['request_id']
            if not isinstance(key, str) or not re.fullmatch(r'[A-Za-z0-9_-]{8,100}', key):
                raise ValueError()
            return key
        except (ValueError, TypeError):
            raise HTTPException(400, 'Use the billing controls.') from None

    async def action(request, kind):
        billing, session = selected(request)
        if not owner(session):
            raise HTTPException(403, 'Use workspace administrator access.')
        key = await request_id(request)
        result = await invoke(billing.portal, owner=True, request_id=key) if kind == 'portal' else await invoke(
            billing.checkout, owner=True, request_id=key, kind=kind)
        return JSONResponse(result, headers={'Cache-Control':'private, no-store'})

    @app.post('/api/billing/checkout')
    async def checkout(request: Request):
        return await action(request, 'subscription')

    @app.post('/api/billing/credits')
    async def credits(request: Request):
        return await action(request, 'credits')

    @app.post('/api/billing/portal')
    async def portal(request: Request):
        return await action(request, 'portal')

    @app.post('/hooks/stripe/{environment}')
    async def webhook(environment: str, request: Request):
        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > MAX_BODY:
                raise HTTPException(413, 'Use a bounded billing event.')
        try:
            billing = billing_host.get(environment)
            result = await run_in_threadpool(billing.handle_webhook, bytes(raw), request.headers.get('stripe-signature', ''))
        except BillingUnavailable:
            raise HTTPException(503, 'Billing reconciliation will retry.') from None
        except (BillingError, ValueError, OSError):
            raise HTTPException(400, 'Use a verified billing event.') from None
        return JSONResponse(result, headers={'Cache-Control':'no-store'})
