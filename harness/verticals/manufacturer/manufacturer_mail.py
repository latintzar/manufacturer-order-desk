"""Owned-domain customer email, isolated from workspace membership and agent authority.

Hosts supply private commissioning evidence, a current-authority callback and the
shared CapabilitySpend grant. These synchronous methods belong in a worker thread.
No provider call occurs at construction or without current commissioning.

Provider contracts verified 2026-10-16:
https://resend.com/docs/api-reference/emails/retrieve-received-email
https://resend.com/changelog/message-id-for-sent-emails
https://resend.com/docs/dashboard/emails/idempotency-keys
https://docs.svix.com/receiving/verifying-payloads/how-manual
"""

from __future__ import annotations

import base64
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from email.utils import getaddresses
import fcntl
import hashlib
import hmac
from html import escape
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import stat
import time
from urllib.parse import urlsplit

import httpx

from capability_spend import CapabilitySpend, CapabilitySpendHeld
from messaging import Messaging
from manufacturer_conversations import EmailReceipt, _email
from manufacturer_store import Conflict, Invalid

MAX_BODY = 256 * 1024
RETRY_WINDOW = 23 * 3600  # Resend retains idempotency keys for 24 hours.
UUID = re.compile(r"[a-fA-F0-9]{8}(?:-[a-fA-F0-9]{4}){3}-[a-fA-F0-9]{12}")
CONFIG_FIELDS = {
    "schema_version",
    "environment_id",
    "company_id",
    "account_id",
    "sender_name",
    "sender_email",
    "reply_domain",
    "portal_origin",
    "commissioned",
    "sending_verified",
    "receiving_verified",
    "webhook_verified",
    "evidence_id",
    "commissioned_until",
    "daily_send_limit",
    "reply_ttl_days",
}


class MailHeld(ValueError):
    """A safe, non-secret error suitable for a host to map to a held delivery."""


def _require(value, message="Review the commissioned email connection."):
    if not value:
        raise MailHeld(message)


def _json(value):
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    _require(len(encoded.encode()) <= MAX_BODY, "Keep the email within its size limit.")
    return encoded


def _sha(value):
    return hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()


def _bounded(value, maximum=200):
    return isinstance(value, str) and 0 < len(value) <= maximum and not any(ord(c) < 32 for c in value)


def _address(value):
    _require(_bounded(value, 320))
    try:
        addresses = getaddresses([value])
        _require(len(addresses) == 1)
        return _email(addresses[0][1])
    except (ValueError, TypeError):
        raise MailHeld("Use the recorded customer email address.") from None


def _addresses(values):
    _require(isinstance(values, list) and 0 < len(values) <= 50)
    return [_address(value) for value in values]


def _message_id(value):
    return value if isinstance(value, str) and re.fullmatch(r"<[^<>\s]{1,990}>", value) else ""


def _event_time(value):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        _require(parsed.tzinfo is not None)
        return parsed.timestamp()
    except (AttributeError, ValueError, OverflowError):
        raise MailHeld("Use the provider event timestamp.") from None


def verify_webhook(raw, headers, secret, *, now):
    """Verify exact bytes before JSON parsing, with rotating Svix v1 signatures."""
    _require(isinstance(raw, bytes) and 0 < len(raw) <= MAX_BODY)
    _require(isinstance(secret, str) and secret.startswith("whsec_"))
    values = {str(key).lower(): value for key, value in headers.items()}
    identifier, timestamp = values.get("svix-id"), values.get("svix-timestamp")
    signatures = values.get("svix-signature", "")
    _require(
        isinstance(identifier, str)
        and re.fullmatch(r"[A-Za-z0-9_-]{1,128}", identifier)
        and isinstance(timestamp, str)
        and re.fullmatch(r"\d{1,12}", timestamp)
    )
    _require(abs(now - int(timestamp)) <= 300, "Use a current signed email event.")
    _require(_bounded(signatures, 4096))
    try:
        key = base64.b64decode(secret[6:] + "=" * (-len(secret[6:]) % 4), validate=True)
        _require(len(key) >= 16)
    except (ValueError, TypeError):
        raise MailHeld("Verify the email webhook connection.") from None
    digest = base64.b64encode(
        hmac.new(key, f"{identifier}.{timestamp}.".encode() + raw, hashlib.sha256).digest()
    ).decode()
    _require(
        any(hmac.compare_digest(part.encode(), ("v1," + digest).encode()) for part in signatures.split()),
        "Verify the email webhook signature.",
    )
    try:
        value = json.loads(raw)
        _require(
            isinstance(value, dict) and isinstance(value.get("data"), dict) and _bounded(value.get("type"))
        )
        return value
    except (ValueError, TypeError, RecursionError):
        raise MailHeld("Use a complete provider email event.") from None


class ResendHTTPProvider:
    """Bounded fixed-origin transport; send and inbound-read keys are distinct inputs."""

    channel = "email"

    def __init__(self, account_id, company_id, *, send_key, receive_key, webhook_secret, client=None):
        self.account_id, self.company_id = account_id, company_id
        self._send_key, self._receive_key = send_key, receive_key
        self.webhook_secret = webhook_secret
        self._client = client

    @property
    def ready(self):
        return all(
            _bounded(value, 1024) for value in (self._send_key, self._receive_key, self.webhook_secret)
        )

    def units(self, prepared):
        return 1

    def _request(self, method, path, *, key, payload=None, idempotency_key=None):
        _require(self.ready)
        headers = {"Authorization": "Bearer " + key, "Accept": "application/json"}
        if idempotency_key is not None:
            _require(_bounded(idempotency_key, 256))
            headers["Idempotency-Key"] = idempotency_key
        if payload is not None:
            _json(payload)
        client = self._client or httpx.Client(timeout=10, follow_redirects=False, trust_env=False)
        try:
            with client.stream(
                method,
                "https://api.resend.com" + path,
                headers=headers,
                json=payload,
                timeout=10,
                follow_redirects=False,
            ) as response:
                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    _require(len(body) <= MAX_BODY, "Review the provider response size.")
                # Never expose provider error bodies, credentials or request headers.
                _require(200 <= response.status_code < 300, "Review the provider delivery receipt.")
                value = json.loads(body)
                _require(isinstance(value, dict))
                return value
        except (httpx.HTTPError, ValueError) as exc:
            if isinstance(exc, MailHeld):
                raise
            raise MailHeld("Review the provider delivery receipt.") from None
        finally:
            if self._client is None:
                client.close()

    def send(self, payload, key):
        return self._request("POST", "/emails", key=self._send_key, payload=payload, idempotency_key=key)

    def receive(self, identifier):
        _require(isinstance(identifier, str) and UUID.fullmatch(identifier))
        return self._request("GET", "/emails/receiving/" + identifier, key=self._receive_key)


class _PlainHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.hidden = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "head"}:
            self.hidden += 1
        elif not self.hidden and tag in {"br", "p", "div", "tr", "li"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style", "head"}:
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def _plain(body):
    text = body.get("text")
    if not isinstance(text, str) or not text.strip():
        parser = _PlainHTML()
        parser.feed(body.get("html") or "")
        text = "".join(parser.parts)
    text = "".join(c for c in text if ord(c) >= 32 or c in "\n\r\t").strip()
    if not text:
        text = "Прикачен файл" if body.get("attachments") else "Имейл от клиента"
    return text[:8000], len(text) > 8000


def _money(value, currency):
    try:
        amount = Decimal(str(value))
        if not amount.is_finite() or amount < 0 or amount > 10**12:
            return ""
        return f"{amount:,.2f}".replace(",", " ").replace(".", ",") + " " + currency
    except (InvalidOperation, ValueError):
        return ""


class ManufacturerMail:
    def __init__(
        self,
        state,
        *,
        environment_id,
        company_id,
        conversations,
        config=None,
        provider=None,
        spend=None,
        current=lambda context: False,
        review_link=None,
        classify=None,
        send_admission=None,
        clock=time.time,
    ):
        _require(conversations.company_id == company_id)
        self.environment_id, self.company_id, self.conversations = environment_id, company_id, conversations
        self.config, self.provider, self.current = config, provider, current
        self.review_link, self.classify, self.clock = review_link, classify, clock
        self.send_admission = send_admission
        root = Path(state)
        root.mkdir(parents=True, exist_ok=True)
        self.path, self.lock_path = root / "manufacturer-mail.sqlite", root / "manufacturer-mail.lock"
        self.spend = spend or CapabilitySpend(root, environment_id, company_id)
        # Only the shared ledger transaction is reused; buyers are never enrolled as members.
        self.money_store = Messaging(root, company_id=company_id, channel_names=("email",))
        self._private_file(self.path)
        with self._locked(), self._db() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS scope (singleton INTEGER PRIMARY KEY, environment TEXT, company TEXT, account TEXT)"
            )
            scope = db.execute("SELECT * FROM scope WHERE singleton=1").fetchone()
            _require(
                scope is None or (scope["environment"], scope["company"]) == (environment_id, company_id)
            )
            db.execute("INSERT OR IGNORE INTO scope VALUES(1,?,?,NULL)", (environment_id, company_id))
            for statement in (
                """CREATE TABLE IF NOT EXISTS outgoing (intent TEXT PRIMARY KEY, account TEXT NOT NULL,
                   context TEXT NOT NULL, payload TEXT NOT NULL, payload_sha TEXT NOT NULL, key TEXT NOT NULL,
                   first_attempt REAL, last_attempt REAL, attempts INTEGER NOT NULL DEFAULT 0,
                   status TEXT NOT NULL DEFAULT 'prepared', provider_id TEXT, message_id TEXT,
                   event_at REAL NOT NULL DEFAULT 0, projected INTEGER NOT NULL DEFAULT 0)""",
                """CREATE UNIQUE INDEX IF NOT EXISTS outgoing_provider_id ON outgoing(provider_id) WHERE provider_id IS NOT NULL""",
                """CREATE TABLE IF NOT EXISTS reply_tokens (hash TEXT PRIMARY KEY, intent TEXT NOT NULL,
                   expires_at REAL NOT NULL, revoked INTEGER NOT NULL DEFAULT 0)""",
                """CREATE TABLE IF NOT EXISTS events (id TEXT PRIMARY KEY, hash TEXT NOT NULL,
                   payload TEXT NOT NULL, result TEXT, created_at REAL NOT NULL)""",
                """CREATE TABLE IF NOT EXISTS incoming (id TEXT PRIMARY KEY, intent TEXT NOT NULL,
                   event_id TEXT NOT NULL, body TEXT NOT NULL, classification TEXT, status TEXT NOT NULL DEFAULT 'pending', result TEXT)""",
                """CREATE TABLE IF NOT EXISTS message_refs (sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                   conversation TEXT NOT NULL, order_id TEXT NOT NULL, message_id TEXT NOT NULL,
                   UNIQUE(conversation,order_id,message_id))""",
            ):
                db.execute(statement)
        os.chmod(self.path, 0o600)

    @staticmethod
    def _private_file(path):
        _require(not path.is_symlink())
        try:
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
            os.close(descriptor)
        except FileExistsError:
            pass
        info = path.stat()
        _require(stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid() and not info.st_mode & 0o077)

    @contextmanager
    def _db(self):
        self._private_file(self.path)
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @contextmanager
    def _locked(self):
        self._private_file(self.lock_path)
        descriptor = os.open(self.lock_path, os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)

    def _configuration(self):
        cfg = self.config() if callable(self.config) else self.config
        _require(isinstance(cfg, dict) and set(cfg) == CONFIG_FIELDS)
        _require(
            type(cfg["schema_version"]) is int
            and cfg["schema_version"] == 1
            and cfg["environment_id"] == self.environment_id
            and cfg["company_id"] == self.company_id
        )
        _require(
            all(
                cfg[key] is True
                for key in ("commissioned", "sending_verified", "receiving_verified", "webhook_verified")
            )
        )
        _require(
            _bounded(cfg["evidence_id"])
            and type(cfg["commissioned_until"]) in {int, float}
            and self.clock() < cfg["commissioned_until"] < 4_102_444_800
        )
        _require(type(cfg["daily_send_limit"]) is int and 1 <= cfg["daily_send_limit"] <= 200)
        _require(type(cfg["reply_ttl_days"]) is int and 1 <= cfg["reply_ttl_days"] <= 365)
        _require(_bounded(cfg["sender_name"], 120) and not any(c in cfg["sender_name"] for c in '<>"'))
        _require(_address(cfg["sender_email"]) == cfg["sender_email"])
        _require(
            _bounded(cfg["reply_domain"])
            and re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?\.[a-z]{2,63}", cfg["reply_domain"])
            and ".." not in cfg["reply_domain"]
        )
        origin = urlsplit(cfg["portal_origin"])
        _require(
            origin.scheme == "https"
            and origin.hostname
            and not origin.username
            and not origin.password
            and origin.path in {"", "/"}
            and not origin.query
            and not origin.fragment
        )
        _require(callable(self.send_admission), "Connect the shared workspace email allowance.")
        _require(
            self.provider
            and self.provider.ready
            and self.provider.account_id == cfg["account_id"]
            and self.provider.company_id == self.company_id
        )
        return dict(cfg)

    def _bind(self, db, cfg):
        account = db.execute("SELECT account FROM scope WHERE singleton=1").fetchone()[0]
        _require(
            account is None or account == cfg["account_id"], "Use the original email account for this ledger."
        )
        db.execute("UPDATE scope SET account=? WHERE singleton=1", (cfg["account_id"],))

    def sender_status(self):
        result = {"ready": False, "state": "setup", "sender": None, "daily_send_limit": None}
        try:
            cfg = self._configuration()
            result.update(sender=cfg["sender_email"], daily_send_limit=cfg["daily_send_limit"])
            with self._db() as db:
                self._bind(db, cfg)
            ready = self.spend.ready(self.provider, self.clock())
            if ready:
                grant = self.spend.grant(self.provider, self.clock())
                today = datetime.fromtimestamp(self.clock(), timezone.utc).strftime("%Y-%m-%d")
                with self.money_store._db() as db:
                    if db is not None:
                        daily, total = db.execute(
                            "SELECT coalesce(sum(CASE WHEN day=? THEN amount ELSE 0 END),0),coalesce(sum(amount),0) FROM capability_spend_holds WHERE channel='email' AND account=? AND returned=0",
                            (today, cfg["account_id"]),
                        ).fetchone()
                        ready = (
                            daily + grant["unit_cost_microusd"] <= grant["daily_microusd"]
                            and total + grant["unit_cost_microusd"] <= grant["total_microusd"]
                        )
            result.update(ready=ready, state="ready")
            if not result["ready"]:
                result["state"] = "allowance"
        except (MailHeld, ValueError, TypeError):
            pass
        return result

    def _admit(self, context, *, spending=False):
        cfg = self._configuration()
        _require(
            context.get("company_id") == self.company_id and self.current(context),
            "Review the current customer communication permission.",
        )
        # Contact removal or reassignment immediately stops both sends and replies.
        if context.get("direction") == "receipt":
            return cfg
        fresh = self.conversations.delivery_context(context["id"])
        _require(
            all(
                fresh.get(key) == context.get(key)
                for key in (
                    "company_id",
                    "customer_id",
                    "conversation_id",
                    "recipient",
                    "proposal_version_id",
                    "order_id",
                )
            )
        )
        if spending:
            _require(self.spend.ready(self.provider, self.clock()), "Review the email spending allowance.")
        return cfg

    def _reference(self, db, context, message_id):
        if _message_id(message_id):
            db.execute(
                "INSERT OR IGNORE INTO message_refs(conversation,order_id,message_id) VALUES(?,?,?)",
                (context["conversation_id"], context.get("order_id") or "", message_id),
            )

    def _prepare(self, intent, cfg):
        context = self.conversations.delivery_context(intent["id"])
        self._admit(context, spending=True)
        with self._db() as db:
            if db.execute("SELECT 1 FROM outgoing WHERE intent=?", (intent["id"],)).fetchone():
                return
        alias_token = base64.b32encode(secrets.token_bytes(32)).decode().rstrip("=").lower()
        alias = "r." + alias_token + "@" + cfg["reply_domain"]
        _require(_bounded(context["subject"], 200), "Use a single email subject line.")
        text = context["body"]
        html = '<div style="font-family:Arial,sans-serif;max-width:640px;margin:auto;line-height:1.6">'
        html += "<p>" + escape(text).replace("\n", "<br>") + "</p>"
        proposal = context.get("proposal")
        if proposal:
            _require(callable(self.review_link), "Connect the customer proposal review page.")
            review_url = self.review_link(dict(context))
            _require(_bounded(review_url, 2048))
            parsed, origin = urlsplit(review_url), urlsplit(cfg["portal_origin"])
            _require(
                parsed.scheme == "https"
                and parsed.netloc == origin.netloc
                and parsed.path == "/customer/review"
                and parsed.fragment
                and not parsed.query
            )
            number = str(proposal.get("display_number") or proposal.get("number") or context["order_id"])
            title = "Поръчка " + number + " · Версия " + str(context["proposal_version"])
            text += "\n\n" + title
            html += "<h2>" + escape(title) + '</h2><table style="width:100%;border-collapse:collapse">'
            currency = proposal.get("currency", "EUR")
            _require(isinstance(currency, str) and re.fullmatch("[A-Z]{3}", currency))
            lines = proposal.get("lines", [])
            for line in lines[:20]:
                name = str(line.get("name") or line.get("description") or line.get("code") or "")
                quantity = str(line.get("quantity", "")) + " " + str(line.get("unit") or "")
                price = _money(line.get("line_total"), currency) or "По оферта"
                text += "\n" + name + " — " + quantity + " · " + price
                html += '<tr><td style="padding:8px 0;border-bottom:1px solid #ddd">' + escape(name)
                html += (
                    '</td><td style="padding:8px 0;text-align:right;border-bottom:1px solid #ddd">'
                    + escape(quantity)
                    + '</td><td style="padding:8px 0;text-align:right;border-bottom:1px solid #ddd">'
                    + escape(price)
                    + "</td></tr>"
                )
            html += "</table>"
            if len(lines) > 20:
                text += "\nОще " + str(len(lines) - 20) + " артикула в прегледа на поръчката."
                html += "<p>Още " + str(len(lines) - 20) + " артикула в прегледа на поръчката.</p>"
            subtotal = _money(proposal.get("subtotal"), currency)
            if subtotal:
                text += "\nОбщо артикули: " + subtotal
                html += "<p><strong>Общо артикули: " + escape(subtotal) + "</strong></p>"
            delivery = proposal.get("delivery")
            if isinstance(delivery, dict):
                values = [
                    str(delivery[key]) for key in ("address", "method", "date", "notes") if delivery.get(key)
                ]
                if values:
                    text += "\nДоставка: " + ", ".join(values)
                    html += "<p>Доставка: " + escape(", ".join(values)) + "</p>"
            html += '<p><a href="' + escape(review_url, quote=True) + '">Преглед на поръчката</a></p>'
            text += "\n\nПреглед на поръчката: " + review_url
        html += "<p>" + escape(cfg["sender_name"]) + "</p></div>"
        with self._db() as db:
            self._bind(db, cfg)
            headers = {}
            reference = db.execute(
                "SELECT message_id FROM message_refs WHERE conversation=? AND order_id=? ORDER BY sequence DESC LIMIT 1",
                (context["conversation_id"], context.get("order_id") or ""),
            ).fetchone()
            if reference:
                headers = {"In-Reply-To": reference[0], "References": reference[0]}
            payload = {
                "from": f"{cfg['sender_name']} <{cfg['sender_email']}>",
                "to": [context["recipient"]],
                "subject": context["subject"],
                "text": text,
                "html": html,
                "reply_to": alias,
                "tags": [{"name": "delivery_id", "value": context["id"]}],
            }
            if headers:
                payload["headers"] = headers
            encoded = _json(payload)
            key = "manufacturer/" + _sha(cfg["account_id"] + ":" + context["id"])
            db.execute(
                "INSERT INTO outgoing(intent,account,context,payload,payload_sha,key) VALUES(?,?,?,?,?,?)",
                (context["id"], cfg["account_id"], _json(context), encoded, _sha(encoded), key),
            )
            db.execute(
                "INSERT INTO reply_tokens VALUES(?,?,?,0)",
                (_sha(alias), context["id"], self.clock() + cfg["reply_ttl_days"] * 86400),
            )

    def _project(self, row, evidence):
        context = {**json.loads(row["context"]), "direction": "receipt"}
        self._admit(context)
        receipt = EmailReceipt("resend", row["provider_id"] or "", row["status"], evidence)
        self.conversations.record_delivery(
            row["intent"], receipt, current=lambda: bool(self.current(context))
        )
        with self._db() as db:
            db.execute("UPDATE outgoing SET projected=1 WHERE intent=?", (row["intent"],))

    def _send(self, identifier):
        with self._db() as db:
            row = dict(db.execute("SELECT * FROM outgoing WHERE intent=?", (identifier,)).fetchone())
        context, now = json.loads(row["context"]), self.clock()
        cfg = self._admit(context, spending=True)
        if row["first_attempt"] is not None and now - row["first_attempt"] >= RETRY_WINDOW:
            return {"id": identifier, "status": "uncertain", "review_required": True}
        if row["last_attempt"] is not None and now - row["last_attempt"] < 10:
            return {"id": identifier, "status": row["status"], "retry_after": 10}
        with self._db() as db:
            self._bind(db, cfg)
            day_start = (
                datetime.fromtimestamp(now, timezone.utc)
                .replace(hour=0, minute=0, second=0, microsecond=0)
                .timestamp()
            )
            used = db.execute(
                "SELECT count(*) FROM outgoing WHERE first_attempt>=? AND intent<>?", (day_start, identifier)
            ).fetchone()[0]
            _require(used < cfg["daily_send_limit"], "Review the daily email allowance.")
        _require(self.send_admission(context) is True, "Review the shared workspace send allowance.")
        with self.money_store._db(write=True) as db:
            self.spend.reserve(
                db,
                {"id": "manufacturer:" + identifier, "channel": "email", "account": cfg["account_id"]},
                self.provider,
                json.loads(row["payload"]),
                now,
            )
        self.conversations.begin_delivery(identifier, current=lambda: bool(self.current(context)))
        with self._db() as db:
            # A crash from this point is ambiguous; retry only the frozen key inside its window.
            db.execute(
                "UPDATE outgoing SET status='uncertain', first_attempt=coalesce(first_attempt,?),last_attempt=?,attempts=attempts+1,projected=0 WHERE intent=?",
                (now, now, identifier),
            )
        self._admit(context, spending=True)
        result, status = {}, "uncertain"
        try:
            result = self.provider.send(json.loads(row["payload"]), row["key"])
            _require(
                isinstance(result, dict)
                and isinstance(result.get("id"), str)
                and UUID.fullmatch(result["id"])
            )
            status = "accepted"
        except (MailHeld, httpx.HTTPError, ValueError, TypeError):
            result = {}
        with self._db() as db:
            db.execute(
                "UPDATE outgoing SET status=?,provider_id=? WHERE intent=?",
                (status, result.get("id"), identifier),
            )
            updated = dict(db.execute("SELECT * FROM outgoing WHERE intent=?", (identifier,)).fetchone())
        self._project(updated, "send-" + identifier + "-" + str(updated["attempts"]))
        return {"id": identifier, "status": status}

    def drain(self, *, limit=20):
        _require(type(limit) is int and 1 <= limit <= 20)
        status = self.sender_status()
        if status["state"] == "setup":
            return {"held": True, "state": status["state"], "deliveries": []}
        deliveries = []
        with self._locked():
            cfg = self._configuration()
            for intent in self.conversations.pending_deliveries(limit=limit) if status["ready"] else []:
                try:
                    self._prepare(intent, cfg)
                except (MailHeld, Invalid, Conflict):
                    deliveries.append({"id": intent["id"], "status": "pending", "held": True})
            with self._db() as db:
                rows = [
                    dict(row)
                    for row in db.execute(
                        "SELECT * FROM outgoing WHERE projected=0 AND status IN ('accepted','sent','delivered','failed') LIMIT ?",
                        (limit,),
                    )
                ]
            for row in rows:
                self._project(
                    row,
                    "recover-"
                    + row["intent"]
                    + "-"
                    + _sha(str(row["event_at"]) + row["status"] + str(row["attempts"]))[:16],
                )
            with self._db() as db:
                rows = db.execute(
                    "SELECT intent FROM outgoing WHERE status IN ('prepared','uncertain') ORDER BY first_attempt,intent LIMIT ?",
                    (limit,),
                ).fetchall()
            for row in rows if status["ready"] else []:
                try:
                    deliveries.append(self._send(row["intent"]))
                except (MailHeld, CapabilitySpendHeld, Invalid, Conflict):
                    deliveries.append({"id": row["intent"], "status": "held", "held": True})
            # Replay admitted callbacks that raced ahead of the send receipt or a transient body fetch.
            with self._db() as db:
                pending = db.execute(
                    "SELECT id,payload FROM events WHERE result IS NULL ORDER BY created_at LIMIT ?", (limit,)
                ).fetchall()
            for event in pending:
                try:
                    self._process_event(event["id"], json.loads(event["payload"]))
                except (MailHeld, Invalid, Conflict, httpx.HTTPError):
                    pass
        return {
            "held": not status["ready"] or any(row.get("held") for row in deliveries),
            "state": status["state"],
            "deliveries": deliveries,
        }

    def handle_webhook(self, raw, headers):
        self.accept_webhook(raw, headers)
        event_id = next(value for key, value in headers.items() if key.lower() == "svix-id")
        with self._locked():
            with self._db() as db:
                row = db.execute("SELECT payload,result FROM events WHERE id=?", (event_id,)).fetchone()
            return (
                json.loads(row["result"])
                if row["result"]
                else self._process_event(event_id, json.loads(row["payload"]))
            )

    def accept_webhook(self, raw, headers):
        """Durably admit signed metadata; the bounded worker performs body retrieval later."""
        cfg = self._configuration()
        event = verify_webhook(raw, headers, self.provider.webhook_secret, now=self.clock())
        event_id = next(value for key, value in headers.items() if key.lower() == "svix-id")
        with self._locked():
            with self._db() as db:
                self._bind(db, cfg)
                prior = db.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
                _require(prior is None or prior["hash"] == _sha(raw), "Keep the original provider event.")
                if prior and prior["result"]:
                    return json.loads(prior["result"])
                if prior is None:
                    count = db.execute(
                        "SELECT count(*) FROM events WHERE created_at>=?",
                        (int(self.clock() // 86400) * 86400,),
                    ).fetchone()[0]
                    pending = db.execute("SELECT count(*) FROM events WHERE result IS NULL").fetchone()[0]
                    _require(count < 1000 and pending < 100, "Review the email callback allowance.")
                db.execute(
                    "INSERT OR IGNORE INTO events VALUES(?,?,?,NULL,?)",
                    (event_id, _sha(raw), _json(event), self.clock()),
                )
            return {"status": "queued", "id": event_id}

    def _process_event(self, event_id, event):
        if event["type"] == "email.received":
            result = self._incoming(event_id, event["data"])
        else:
            result = self._delivery_event(event_id, event)
        if result["status"] != "pending":
            with self._db() as db:
                db.execute("UPDATE events SET result=? WHERE id=?", (_json(result), event_id))
        return result

    def _delivery_event(self, event_id, event):
        mapping = {
            "email.sent": "sent",
            "email.delivered": "delivered",
            "email.failed": "failed",
            "email.bounced": "failed",
        }
        if event["type"] not in mapping:
            return {"status": "ignored"}
        data = event["data"]
        _require(isinstance(data.get("email_id"), str) and UUID.fullmatch(data["email_id"]))
        event_at = _event_time(event.get("created_at"))
        with self._db() as db:
            row = db.execute("SELECT * FROM outgoing WHERE provider_id=?", (data["email_id"],)).fetchone()
            if row is None:
                # A signed provider callback can resolve an uncertain POST before its response.
                tags = data.get("tags")
                tag = tags.get("delivery_id") if isinstance(tags, dict) else None
                if tag:
                    candidate = db.execute(
                        "SELECT * FROM outgoing WHERE intent=? AND first_attempt IS NOT NULL", (tag,)
                    ).fetchone()
                    if candidate and candidate["provider_id"] is None:
                        frozen = json.loads(candidate["payload"])
                        _require(
                            _address(data.get("from")) == _address(frozen["from"])
                            and _addresses(data.get("to")) == frozen["to"]
                        )
                        db.execute(
                            "UPDATE outgoing SET provider_id=? WHERE intent=?", (data["email_id"], tag)
                        )
                        row = db.execute("SELECT * FROM outgoing WHERE intent=?", (tag,)).fetchone()
                if row is None:
                    return {"status": "ignored"}
            context = {**json.loads(row["context"]), "direction": "receipt"}
            self._admit(context)
            status = mapping[event["type"]]
            if event_at < row["event_at"] or row["status"] in {"delivered", "failed"} and status == "sent":
                status = row["status"]
            message_id = _message_id(data.get("message_id")) or row["message_id"]
            db.execute(
                "UPDATE outgoing SET status=?,message_id=?,event_at=max(event_at,?),projected=0 WHERE intent=?",
                (status, message_id, event_at, row["intent"]),
            )
            self._reference(db, context, message_id)
            updated = dict(db.execute("SELECT * FROM outgoing WHERE intent=?", (row["intent"],)).fetchone())
        self._project(updated, "event-" + event_id)
        return {"id": row["intent"], "status": status}

    def _incoming(self, event_id, data):
        cfg = self._configuration()
        identifier = data.get("email_id")
        _require(isinstance(identifier, str) and UUID.fullmatch(identifier))
        addresses = _addresses(data.get("to"))
        with self._db() as db:
            bindings = []
            for address in addresses:
                if address.split("@")[1] != cfg["reply_domain"]:
                    continue
                row = db.execute(
                    "SELECT outgoing.* FROM reply_tokens JOIN outgoing ON outgoing.intent=reply_tokens.intent WHERE reply_tokens.hash=? AND revoked=0 AND expires_at>?",
                    (_sha(address), self.clock()),
                ).fetchone()
                if row:
                    bindings.append((address, row))
            if len(bindings) != 1:
                return {"status": "ignored"}
            alias, outgoing = bindings[0]
            context = {**json.loads(outgoing["context"]), "direction": "incoming"}
            self._admit(context)
            saved = db.execute("SELECT * FROM incoming WHERE id=?", (identifier,)).fetchone()
            _require(saved is None or saved["intent"] == context["id"])
            if saved and saved["result"]:
                return json.loads(saved["result"])
        if saved:
            body = json.loads(saved["body"])
        else:
            self._admit(context)
            body = self.provider.receive(identifier)
            _require(isinstance(body, dict) and body.get("id") == identifier)
            _json(body)
            with self._db() as db:
                db.execute(
                    "INSERT INTO incoming(id,intent,event_id,body) VALUES(?,?,?,?)",
                    (identifier, context["id"], event_id, _json(body)),
                )
                saved = db.execute("SELECT * FROM incoming WHERE id=?", (identifier,)).fetchone()
        try:
            sender = _address(body.get("from"))
            exact = (
                alias in _addresses(body.get("to"))
                and sender == _address(data.get("from")) == context["recipient"]
            )
            authenticated = (
                isinstance(body.get("authentication"), dict) and body["authentication"].get("dmarc") == "pass"
            )
        except (MailHeld, Invalid):
            exact, authenticated, sender = False, False, ""
        if not exact or not authenticated:
            result = {
                "status": "review",
                "id": identifier,
                "reason": "sender" if not exact else "authentication",
            }
        else:
            self._admit(context)
            text, truncated = _plain(body)
            provenance = {
                "signature_verified": True,
                "provider_event_id": saved["event_id"],
                "provider_email_id": identifier,
                "body_sha256": _sha(_json(body)),
                "authentication": body.get("authentication"),
                "conversation_id": context["conversation_id"],
                "order_id": context.get("order_id"),
                "proposal_version_id": context.get("proposal_version_id"),
                "truncated": truncated,
                "message_id": _message_id(body.get("message_id")),
            }
            message = self.conversations.record_customer_message(
                context["customer_id"],
                text=text,
                sender=sender,
                provider="resend",
                provider_event_id=identifier,
                provenance=provenance,
                current=lambda: bool(self.current(context)),
            )
            # Classification is evidence for a human. It never confirms a proposal or admits an agent turn.
            classification = json.loads(saved["classification"]) if saved["classification"] else None
            if classification is None:
                classification = {"intent": "unknown", "confidence": 0, "ambiguous": True}
                # The host callback owns model budget admission; it receives untrusted reference data.
                if self.classify:
                    current_review = (
                        self.conversations.order_review(context["customer_id"], context["order_id"])
                        if context.get("order_id")
                        else None
                    )
                    candidate = self.classify(
                        {
                            "text": text,
                            "message": message,
                            "context": dict(context),
                            "provenance": provenance,
                            "current_review": current_review,
                        }
                    )
                    _require(isinstance(candidate, dict), "Изследването на имейла изчаква своя ресурс.")
                    classification = {key: candidate.get(key) for key in classification}
                    if isinstance(candidate.get("evidence"), dict):
                        classification["evidence"] = candidate["evidence"]
                    if current_review and context.get("proposal_version_id") != current_review.get(
                        "current_version_id"
                    ):
                        classification["ambiguous"] = True
                with self._db() as db:
                    db.execute(
                        "UPDATE incoming SET classification=? WHERE id=?", (_json(classification), identifier)
                    )
            evidence = {
                **classification.pop("evidence", {}),
                "provider_email_id": identifier,
                "body_sha256": provenance["body_sha256"],
            }
            self.conversations.record_email_intent(
                context["customer_id"],
                message_id=message["id"],
                **classification,
                evidence=evidence,
                actor="email-classifier",
                idempotency_key="resend-" + identifier,
                current=lambda: bool(self.current(context)),
            )
            with self._db() as db:
                self._reference(db, context, provenance["message_id"])
            result = {"status": "received", "id": identifier, "message_id": message["id"]}
        with self._db() as db:
            db.execute(
                "UPDATE incoming SET status=?,result=? WHERE id=?",
                (result["status"], _json(result), identifier),
            )
        return result

    def review_items(self, *, limit=50):
        _require(type(limit) is int and 1 <= limit <= 50)
        with self._db() as db:
            rows = db.execute(
                "SELECT incoming.id,incoming.body,incoming.result,outgoing.context FROM incoming JOIN outgoing ON outgoing.intent=incoming.intent WHERE incoming.status='review' LIMIT ?",
                (limit,),
            ).fetchall()
        result = []
        for row in rows:
            body, context = json.loads(row["body"]), json.loads(row["context"])
            result.append(
                {
                    "id": row["id"],
                    "customer_id": context["customer_id"],
                    "conversation_id": context["conversation_id"],
                    "order_id": context.get("order_id"),
                    "proposal_version_id": context.get("proposal_version_id"),
                    "sender": body.get("from"),
                    "text": _plain(body)[0],
                    "reason": json.loads(row["result"])["reason"],
                }
            )
        return result

    def revoke_reply(self, intent_id):
        context = self.conversations.delivery_context(intent_id)
        self._admit(context)
        with self._locked(), self._db() as db:
            db.execute("UPDATE reply_tokens SET revoked=1 WHERE intent=?", (intent_id,))
