"""Narrow customer review and phone capabilities, separate from workspace access."""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from manufacturer_conversations import ManufacturerConversations, _email, _id, _json, _text
from manufacturer_store import Conflict, Invalid, Missing
from starlette.concurrency import run_in_threadpool

from origin_config import configured_origin

REVIEW_TTL = 7 * 86400
PHONE_TTL = 600
MAX_BODY = 16384
TOKEN = re.compile(r"[A-Za-z0-9_-]{43}")
ENVIRONMENT = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")
PUBLIC_PREFIX = "/api/manufacturer/customer-portal/"
ASSETS = {
    "/static/manufacturer/manufacturer-customer-portal.js": (
        "manufacturer-customer-portal.js",
        "application/javascript",
    ),
    "/static/manufacturer/manufacturer-customer-portal.css": ("manufacturer-customer-portal.css", "text/css"),
}
HEADERS = {
    "Cache-Control": "private, no-store",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Content-Security-Policy": "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; "
    f"img-src 'self' {configured_origin()}; base-uri 'none'; "
    "form-action 'none'; frame-ancestors 'none'",
}


def portal_error(status, detail=None):
    return HTTPException(status, detail, headers=HEADERS)


def commercial_proposal(document):
    """Project only the saved customer-facing commercial fields; never source metadata."""

    def scalar(value):
        return value is None or type(value) in {str, int, float, bool}

    fields = (
        "number",
        "display_number",
        "currency",
        "subtotal",
        "tax",
        "shipping",
        "total",
        "notes",
        "terms",
        "fulfilment",
        "pricing_state",
    )
    result = {key: document[key] for key in fields if key in document and scalar(document[key])}
    line_fields = (
        "code",
        "name",
        "quantity",
        "unit",
        "unit_price",
        "line_total",
        "total",
        "image_url",
        "finish",
        "size",
        "description",
        "pricing_state",
    )
    result["lines"] = [
        {key: line[key] for key in line_fields if key in line and scalar(line[key])}
        for line in document["lines"]
    ]
    delivery = document.get("delivery")
    if isinstance(delivery, dict):
        result["delivery"] = {
            key: delivery[key]
            for key in ("address", "method", "date", "notes")
            if key in delivery and scalar(delivery[key])
        }
    elif isinstance(delivery, str):
        result["delivery"] = {"notes": delivery}
    return result


def qr_svg(url):
    """Encode the private URL locally; its contents never reach a QR service."""
    from reportlab.graphics import renderSVG
    from reportlab.graphics.barcode.qr import QrCodeWidget
    from reportlab.graphics.shapes import Drawing

    code = QrCodeWidget(url)
    x, y, right, bottom = code.getBounds()
    size = 240
    drawing = Drawing(size, size, transform=[size / (right - x), 0, 0, size / (bottom - y), 0, 0])
    drawing.add(code)
    # Keep the standalone SVG element for safe insertion into the first-party drawer.
    result = renderSVG.drawToString(drawing)
    return result[result.index("<svg") :]


def phone_number(value):
    value = _text(value, 64)
    compact = re.sub(r"[\s().-]", "", value)
    if compact.startswith("00"):
        compact = "+" + compact[2:]
    if not re.fullmatch(r"\+[1-9][0-9]{6,14}", compact):
        raise Invalid("Използвайте телефон с международен код.")
    return compact


def _digest(token):
    if not isinstance(token, str) or not TOKEN.fullmatch(token):
        raise Missing("Отворете актуалния личен линк.")
    return hashlib.sha256(token.encode()).hexdigest()


class CustomerPortal:
    """Only hashed tokens persist. Link/session grants retain exact immutable scope."""

    def __init__(self, state, company_id, environment_id, *, clock=time.time, existing=False):
        if not isinstance(environment_id, str) or not ENVIRONMENT.fullmatch(environment_id):
            raise Invalid("Изберете съществуващото работно пространство.")
        self.company_id, self.environment_id, self.clock = _id(company_id), environment_id, clock
        self.root = Path(state)
        self.path = self.root / "manufacturer-customer-portal.sqlite"
        if existing and (
            not self.path.is_file() or not (self.root / "manufacturer-conversations.sqlite").is_file()
        ):
            raise Missing("Отворете актуалния личен линк.")
        if self.path.is_symlink() or self.root.is_symlink():
            raise Invalid("Използвайте частното фирмено хранилище.")
        self.root.mkdir(parents=True, exist_ok=True)
        self.conversations = ManufacturerConversations(self.root, company_id)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                "CREATE TABLE IF NOT EXISTS scope (singleton INTEGER PRIMARY KEY, "
                "company_id TEXT, environment_id TEXT)"
            )
            row = db.execute("SELECT * FROM scope WHERE singleton=1").fetchone()
            if row and (row["company_id"], row["environment_id"]) != (company_id, environment_id):
                raise Invalid("Използвайте личния линк за тази фирма.")
            db.execute("INSERT OR IGNORE INTO scope VALUES(1,?,?)", (company_id, environment_id))
            db.execute("""CREATE TABLE IF NOT EXISTS capabilities (
                id TEXT PRIMARY KEY, token_hash TEXT UNIQUE NOT NULL,
                kind TEXT NOT NULL, purpose TEXT NOT NULL,
                parent_id TEXT, customer_id TEXT NOT NULL, contact TEXT NOT NULL,
                order_id TEXT, version_id TEXT,
                issuer TEXT NOT NULL, display TEXT NOT NULL, expires REAL NOT NULL,
                revoked INTEGER NOT NULL DEFAULT 0,
                created REAL NOT NULL)""")
            db.commit()
        os.chmod(self.path, 0o600)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15, isolation_level=None)
        db.row_factory = sqlite3.Row
        try:
            yield db
        finally:
            db.close()

    def _audience_current(self, row):
        try:
            contacts = self.conversations.conversation(row["customer_id"], limit=1)["contacts"]
            if row["purpose"] == "review":
                return row["contact"] in {contact["email"] for contact in contacts}
            for contact in contacts:
                try:
                    if phone_number(contact.get("phone", "")) == row["contact"]:
                        return True
                except Invalid:
                    pass
            return False
        except (Invalid, Missing):
            return False

    def _valid(self, db, row):
        if not row or row["revoked"] or row["expires"] <= self.clock():
            return False
        scope = db.execute("SELECT * FROM scope WHERE singleton=1").fetchone()
        if not scope or (scope["company_id"], scope["environment_id"]) != (
            self.company_id,
            self.environment_id,
        ):
            return False
        if row["parent_id"]:
            parent = db.execute("SELECT * FROM capabilities WHERE id=?", (row["parent_id"],)).fetchone()
            if not parent or parent["revoked"] or parent["expires"] <= self.clock():
                return False
        return self._audience_current(row)

    def _insert(
        self,
        db,
        *,
        purpose,
        customer_id,
        contact,
        issuer,
        display,
        expires,
        order_id=None,
        version_id=None,
        parent_id=None,
    ):
        raw = secrets.token_urlsafe(32)
        identifier = "cap-" + secrets.token_hex(16)
        db.execute(
            """INSERT INTO capabilities(id,token_hash,kind,purpose,parent_id,customer_id,contact,
            order_id,version_id,issuer,display,expires,created) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                identifier,
                _digest(raw),
                "session" if parent_id else "link",
                purpose,
                parent_id,
                customer_id,
                contact,
                order_id,
                version_id,
                issuer,
                _json(display, maximum=16384),
                expires,
                self.clock(),
            ),
        )
        return {"id": identifier, "token": raw, "expires_at": expires, "purpose": purpose}

    def mint_review(self, customer_id, order_id, version_id, *, recipient, actor, display, current):
        recipient = _email(recipient)
        if not callable(current) or current() is not True:
            raise Invalid("Продължете с текущия фирмен достъп.")
        self.conversations.proposal(customer_id, order_id, version_id)
        candidate = {"purpose": "review", "customer_id": customer_id, "contact": recipient}
        if not self._audience_current(candidate):
            raise Invalid("Изберете контакт от текущия клиентски профил.")
        return self._mint(
            candidate, actor, display, REVIEW_TTL, current, order_id=order_id, version_id=version_id
        )

    def mint_phone(self, customer_id, *, phone, actor, display, current):
        candidate = {"purpose": "phone", "customer_id": customer_id, "contact": phone_number(phone)}
        if not self._audience_current(candidate):
            raise Invalid("Изберете телефон от текущия клиентски профил.")
        return self._mint(candidate, actor, display, PHONE_TTL, current)

    def _mint(self, candidate, actor, display, ttl, current, **scope):
        if not callable(current) or current() is not True:
            raise Invalid("Продължете с текущия фирмен достъп.")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            result = self._insert(
                db, **candidate, issuer=_id(actor), display=display, expires=self.clock() + ttl, **scope
            )
            if current() is not True:
                db.rollback()
                raise Invalid("Продължете с текущия фирмен достъп.")
            db.commit()
            return result

    @contextmanager
    def admitted(self, token, kind):
        digest = _digest(token)
        with self.connect() as db:
            # Revoke waits until this one narrow operation completes, including its review transaction.
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT * FROM capabilities WHERE token_hash=? AND kind=?", (digest, kind)
            ).fetchone()
            if not self._valid(db, row):
                db.rollback()
                raise Missing("Отворете актуалния личен линк.")
            try:
                yield db, row
                if not self._valid(db, row):
                    raise Missing("Отворете актуалния личен линк.")
                db.commit()
            except BaseException:
                db.rollback()
                raise

    def redeem(self, token):
        with self.admitted(token, "link") as (db, row):
            active = db.execute(
                "SELECT count(*) FROM capabilities WHERE parent_id=? AND expires>? AND revoked=0",
                (row["id"], self.clock()),
            ).fetchone()[0]
            if active >= 20:
                raise Invalid("Отворете личния линк отново след малко.")
            result = self._insert(
                db,
                purpose=row["purpose"],
                customer_id=row["customer_id"],
                contact=row["contact"],
                issuer=row["issuer"],
                display=json.loads(row["display"]),
                expires=min(row["expires"], self.clock() + 3600),
                order_id=row["order_id"],
                version_id=row["version_id"],
                parent_id=row["id"],
            )
            return {
                "session_token": result["token"],
                "expires_at": result["expires_at"],
                "purpose": row["purpose"],
            }

    def revoke(self, capability_id, *, actor, current):
        _id(actor)
        if not callable(current) or current() is not True:
            raise Invalid("Продължете с текущия фирмен достъп.")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            changed = db.execute(
                "UPDATE capabilities SET revoked=1 WHERE id=? OR parent_id=?",
                (_id(capability_id), capability_id),
            ).rowcount
            if current() is not True:
                db.rollback()
                raise Invalid("Продължете с текущия фирмен достъп.")
            db.commit()
            return {"revoked": bool(changed)}

    def read(self, token):
        with self.admitted(token, "session") as (_, row):
            display = json.loads(row["display"])
            if row["purpose"] == "phone":
                return {
                    "purpose": "phone",
                    "display": display,
                    "phone": row["contact"],
                    "expires_at": row["expires"],
                }
            proposal = self.conversations.proposal(row["customer_id"], row["order_id"], row["version_id"])
            review = self.conversations.order_review(row["customer_id"], row["order_id"])
            # Do not expose internal source snapshots, the email audience or customer correspondence.
            return {
                "purpose": "review",
                "display": display,
                "order_id": row["order_id"],
                "proposal": {
                    **{key: proposal[key] for key in ("id", "version", "sha256", "created_at")},
                    "document": commercial_proposal(proposal["document"]),
                },
                "review_status": review["review_status"],
                "source_status": review["source_status"],
                "is_current": review["current_version_id"] == row["version_id"],
                "can_confirm": review["current_version_id"] == row["version_id"]
                and review["review_status"] == "review_pending",
                "confirmed": review["confirmed_version_id"] == row["version_id"],
                "expires_at": row["expires"],
            }

    def confirm(self, token, *, version_id):
        with self.admitted(token, "session") as (db, row):
            if row["purpose"] != "review" or version_id != row["version_id"]:
                raise Invalid("Потвърдете версията от личния линк.")
            result = self.conversations.confirm_proposal(
                row["customer_id"],
                row["order_id"],
                version_id=version_id,
                customer_actor=row["id"],
                evidence={"method": "review_link", "capability_id": row["id"], "contact": row["contact"]},
                current=lambda: self._valid(db, row),
            )
            return {"review_status": result["review_status"], "version_id": version_id}

    def change(self, token, *, version_id, text, idempotency_key):
        with self.admitted(token, "session") as (db, row):
            if row["purpose"] != "review" or version_id != row["version_id"]:
                raise Invalid("Посочете промяната към версията от личния линк.")
            result = self.conversations.request_customer_change(
                row["customer_id"],
                row["order_id"],
                version_id=version_id,
                text=_text(text),
                customer_actor=row["id"],
                evidence={"method": "review_link", "capability_id": row["id"]},
                idempotency_key=idempotency_key,
                current=lambda: self._valid(db, row),
            )
            return {"review_status": result["review_status"], "version_id": version_id}


def is_public_portal_request(request):
    path = request.url.path
    if request.method in {"GET", "HEAD"}:
        return path in ASSETS or path in {"/customer/review", "/customer/phone"}
    return (
        request.method == "POST"
        and re.fullmatch(
            r"/api/manufacturer/customer-portal/[a-z0-9][a-z0-9-]{0,63}/(redeem|read|confirm|change)", path
        )
        is not None
    )


def existing_portal(host, environment):
    """Resolve existing private records only; public input never constructs a workspace/agent."""
    if not ENVIRONMENT.fullmatch(environment):
        raise Missing("Отворете актуалния личен линк.")
    with host.access.connect() as db:
        if not db.execute("SELECT 1 FROM environments WHERE id=?", (environment,)).fetchone():
            raise Missing("Отворете актуалния личен линк.")
    root = Path(host.state) if environment == "demo" else Path(host.state) / "environments" / environment
    path = root / "manufacturer-customer-portal.sqlite"
    if not path.is_file() or path.is_symlink() or root.is_symlink():
        raise Missing("Отворете актуалния личен линк.")
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as db:
        row = db.execute("SELECT company_id,environment_id FROM scope WHERE singleton=1").fetchone()
    if not row or row[1] != environment:
        raise Missing("Отворете актуалния личен линк.")
    return CustomerPortal(root, row[0], environment, existing=True)


def register_customer_portal(app, host, *, context, invoke):
    old_public = host.options.get("public_request", lambda request: False)
    old_limit = host.options.get("request_body_limit", lambda request: None)
    host.options["public_request"] = lambda request: is_public_portal_request(request) or old_public(request)
    host.options["request_body_limit"] = lambda request: (
        MAX_BODY if request.url.path.startswith(PUBLIC_PREFIX) else old_limit(request)
    )
    buckets, lock = {}, threading.Lock()

    def protected_call(function, *args, **kwargs):
        try:
            return function(*args, **kwargs)
        except Conflict:
            raise portal_error(409, "Отворете последната версия за потвърждение.") from None
        except (Invalid, Missing, ValueError):
            raise portal_error(403, "Отворете актуалния личен линк.") from None

    async def bounded_body(request, *, public=False):
        if public:
            expected = (host.public_origin or str(request.base_url)).rstrip("/")
            if (
                request.headers.get("origin") != expected
                or request.headers.get("x-rocoto-page") != "1"
                or request.headers.get("sec-fetch-site", "same-origin") not in {"same-origin", "none"}
            ):
                raise portal_error(403, "Отворете страницата от личния линк.")
            now = time.monotonic()
            key = request.client.host if request.client else "unknown"
            with lock:
                start, count = buckets.get(key, (now, 0))
                if now - start >= 60:
                    start, count = now, 0
                if count >= 120:
                    raise portal_error(429, "Опитайте отново след малко.")
                if len(buckets) > 2048:
                    buckets.clear()
                buckets[key] = (start, count + 1)
        if request.headers.get("content-type", "").split(";")[0].strip() != "application/json":
            raise portal_error(415, "Изпратете формуляра от страницата.")
        raw = bytearray()
        async for part in request.stream():
            raw.extend(part)
            if len(raw) > MAX_BODY:
                raise portal_error(413, "Използвайте кратко съобщение.")
        try:
            value = json.loads(raw)
        except (ValueError, UnicodeError):
            raise portal_error(400, "Изпратете попълнения формуляр.") from None
        if not isinstance(value, dict):
            raise portal_error(400, "Изпратете попълнения формуляр.")
        return value

    def shell():
        return HTMLResponse(
            """<!doctype html><html lang="bg"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="referrer" content="no-referrer">
<title>Вашата поръчка</title><link rel="stylesheet" href="/theme.css">
<link rel="stylesheet" href="/static/manufacturer/manufacturer-customer-portal.css">
<script defer src="/static/manufacturer/manufacturer-customer-portal.js"></script></head>
<body><main id="portal" aria-busy="true"><div class="portal-loading" aria-label="Зареждане">
<div class="skeleton short"></div><div class="skeleton title"></div><div class="skeleton block"></div>
<div class="skeleton block"></div></div></main></body></html>""",
            headers=HEADERS,
        )

    app.add_api_route("/customer/review", shell, methods=["GET", "HEAD"])
    app.add_api_route("/customer/phone", shell, methods=["GET", "HEAD"])

    def asset_handler(filename, mime):
        def asset():
            return FileResponse(Path(__file__).parent / "web" / filename, media_type=mime, headers=HEADERS)

        return asset

    for url, (filename, mime) in ASSETS.items():
        app.add_api_route(url, asset_handler(filename, mime), methods=["GET", "HEAD"])

    def prepare(request, actor, extension, customer_id):
        profile = extension.customer(actor, customer_id)["customer"]
        extension.conversations.ensure_customer(
            customer_id,
            contacts=profile["contacts"],
            actor=actor,
            current=lambda: extension.authorized(actor),
        )
        environment = request.state.session["environment"]["id"]
        portal = CustomerPortal(extension.selected["state"], extension.company_id, environment)
        company = extension.source.company()
        name = company.get("name", "Вашата фирма")
        if isinstance(name, dict):
            name = name.get("bg") or name.get("en") or "Вашата фирма"
        return portal, profile, {"company": _text(name, 200), "customer": _text(profile["display_name"], 200)}

    def link(portal, value):
        origin = host.public_origin.rstrip("/")
        if not origin:
            raise Invalid("Настройте точния адрес на клиентската страница.")
        url = (
            origin + "/customer/" + value["purpose"] + "#" + portal.environment_id + "." + value.pop("token")
        )
        return {**value, "url": url, **({"qr_svg": qr_svg(url)} if value["purpose"] == "phone" else {})}

    @app.post("/api/manufacturer/customers/{customer_id}/review-links")
    async def mint_review(customer_id: str, request: Request):
        actor, extension = context(request, True)
        value = await bounded_body(request)
        if set(value) != {"order_id", "version_id", "recipient"}:
            raise portal_error(400, "Изберете поръчка, версия и контакт.")

        def mint():
            portal, _, display = prepare(request, actor, extension, customer_id)
            source = extension.order(actor, value["order_id"])["order"]
            if source["customer_id"] != customer_id:
                raise Missing("Изберете поръчка на този клиент.")
            display["order_number"] = source.get("display_number") or source.get("number") or source["id"]
            return link(
                portal,
                portal.mint_review(
                    customer_id,
                    value["order_id"],
                    value["version_id"],
                    recipient=value["recipient"],
                    actor=actor,
                    display=display,
                    current=lambda: extension.authorized(actor),
                ),
            )

        return JSONResponse(await run_in_threadpool(invoke, mint), headers=HEADERS)

    @app.post("/api/manufacturer/customers/{customer_id}/phone-links")
    async def mint_phone(customer_id: str, request: Request):
        actor, extension = context(request, True)
        value = await bounded_body(request)
        if set(value) != {"contact_index"} or type(value["contact_index"]) is not int:
            raise portal_error(400, "Изберете телефон за връзка.")

        def mint():
            portal, profile, display = prepare(request, actor, extension, customer_id)
            index = value["contact_index"]
            if not 0 <= index < len(profile["contacts"]):
                raise Invalid("Изберете контакт от клиентския профил.")
            contact = profile["contacts"][index]
            display["contact_name"] = contact.get("name") or display["customer"]
            return link(
                portal,
                portal.mint_phone(
                    customer_id,
                    phone=contact.get("phone"),
                    actor=actor,
                    display=display,
                    current=lambda: extension.authorized(actor),
                ),
            )

        return JSONResponse(await run_in_threadpool(invoke, mint), headers=HEADERS)

    @app.post("/api/manufacturer/customer-links/{capability_id}/revoke")
    async def revoke_link(capability_id: str, request: Request):
        actor, extension = context(request, True)
        value = await bounded_body(request)
        if value:
            raise portal_error(400, "Изберете личния линк.")

        def revoke():
            environment = request.state.session["environment"]["id"]
            portal = CustomerPortal(extension.selected["state"], extension.company_id, environment)
            return portal.revoke(capability_id, actor=actor, current=lambda: extension.authorized(actor))

        return JSONResponse(await run_in_threadpool(invoke, revoke), headers=HEADERS)

    @app.post("/api/manufacturer/customer-portal/{environment}/{action}")
    async def operation(environment: str, action: str, request: Request):
        if action not in {"redeem", "read", "confirm", "change"}:
            raise portal_error(404)
        value = await bounded_body(request, public=True)
        expected = (
            {"token"}
            if action == "redeem"
            else set()
            if action == "read"
            else {"version_id"}
            if action == "confirm"
            else {"version_id", "text", "idempotency_key"}
        )
        if set(value) != expected:
            raise portal_error(400, "Изпратете попълнения формуляр.")
        bearer = request.headers.get("authorization", "")
        token = (
            value.get("token")
            if action == "redeem"
            else bearer.removeprefix("Bearer ")
            if bearer.startswith("Bearer ")
            else ""
        )

        def run():
            portal = existing_portal(host, environment)
            return getattr(portal, action)(token, **({} if action in {"redeem", "read"} else value))

        return JSONResponse(await run_in_threadpool(protected_call, run), headers=HEADERS)
