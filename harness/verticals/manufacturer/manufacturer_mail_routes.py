"""Private per-workspace email commissioning, signed ingress and bounded delivery worker.

Commissioning files live in the selected private workspace, outside product UI:
manufacturer-mail.json = manufacturer_mail.CONFIG_FIELDS + credentials_path.
The separate credentials document has schema_version/environment_id/company_id/
account_id plus send_key, receive_key and webhook_secret. Both use the existing
private regular-file reader. The shared ROCOTO_CAPABILITY_SPEND_CONFIG remains
mandatory; its account caps and the native 200/day counter are reused.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
import re
import threading
import time
from types import SimpleNamespace

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from manufacturer_mail import (
    CONFIG_FIELDS,
    MAX_BODY,
    MailHeld,
    ManufacturerMail,
    ResendHTTPProvider,
    verify_webhook,
)
from messaging_signals import reserve_send
from registered_oauth import read_private_configuration

ENVIRONMENT = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")
SECRET_FIELDS = {
    "schema_version",
    "environment_id",
    "company_id",
    "account_id",
    "send_key",
    "receive_key",
    "webhook_secret",
}
HOOK_PREFIX = "/hooks/manufacturer-email/"


def _read(path):
    try:
        return read_private_configuration(Path(path), max_bytes=32768)
    except (ValueError, OSError, TypeError):
        raise MailHeld("Завършете настройката на фирмения имейл.") from None


def configuration_for(root, environment, company_id=None):
    """Read an existing commissioning record only; create neither identity nor workspace."""
    root = Path(root)
    path = root / "manufacturer-mail.json"
    if not path.exists() and not path.is_symlink():
        return None, None
    value = _read(path)
    if not isinstance(value, dict) or set(value) != CONFIG_FIELDS | {"credentials_path"}:
        raise MailHeld("Прегледайте настройката на фирмения имейл.")
    identity = _read(root / ".workspace-identity.json")
    expected = identity.get("company_scope") if isinstance(identity, dict) else None
    if (
        not expected
        or company_id is not None
        and expected != company_id
        or value.get("company_id") != expected
        or value.get("environment_id") != environment
    ):
        raise MailHeld("Изберете имейла на тази фирма.")
    location = value["credentials_path"]
    if not isinstance(location, str) or not Path(location).is_absolute():
        raise MailHeld("Прегледайте частната имейл връзка.")
    secret = _read(location)
    binding = {key: value[key] for key in ("schema_version", "environment_id", "company_id", "account_id")}
    if (
        not isinstance(secret, dict)
        or set(secret) != SECRET_FIELDS
        or any(secret.get(key) != item for key, item in binding.items())
    ):
        raise MailHeld("Прегледайте частната имейл връзка.")
    config = {key: value[key] for key in CONFIG_FIELDS}
    return config, secret


class _ConfiguredProvider:
    channel = "email"

    def __init__(self, root, environment, company_id):
        self.root, self.environment, self.company_id = root, environment, company_id

    def _provider(self):
        config, secret = configuration_for(self.root, self.environment, self.company_id)
        if config is None:
            raise MailHeld("Завършете настройката на фирмения имейл.")
        return ResendHTTPProvider(
            config["account_id"],
            self.company_id,
            send_key=secret["send_key"],
            receive_key=secret["receive_key"],
            webhook_secret=secret["webhook_secret"],
        )

    @property
    def account_id(self):
        return self._provider().account_id

    @property
    def ready(self):
        return self._provider().ready

    @property
    def webhook_secret(self):
        return self._provider().webhook_secret

    def units(self, payload):
        return 1

    def send(self, payload, key):
        return self._provider().send(payload, key)

    def receive(self, identifier):
        return self._provider().receive(identifier)


class _MailWorker:
    """One bounded batch per workspace; shared host semaphore keeps other views responsive."""

    def __init__(self, host, selected, extension):
        self.host, self.selected, self.extension = host, selected, extension
        self.closed, self.task, self.next_run = False, None, 0
        self.slots = host.options.setdefault("manufacturer_mail_slots", asyncio.Semaphore(2))

    def current(self, context):
        if self.closed or context.get("company_id") != self.extension.company_id:
            return False
        try:
            actor = context.get("notification_actor") or context.get("actor")
            incoming = context.get("direction") in {"incoming", "receipt"}
            if incoming and not self.extension.authorized(actor):
                actor = next(
                    (
                        member["id"]
                        for member in self.selected["business_scope"].members()
                        if member.get("role") in {"owner", "operator"}
                    ),
                    None,
                )
            if not actor or not self.extension.authorized(actor):
                return False
            if not incoming:
                billing = getattr(getattr(self.host.app, "state", None), "billing_host", None)
                if billing and not billing.get(self.selected["environment_id"]).require_operational():
                    return False
            if context.get("direction") == "receipt":
                return True
            profile = self.extension.customer(actor, context["customer_id"])["customer"]
            return context["recipient"] in {
                person.get("email", "").lower() for person in profile.get("contacts", [])
            }
        except (ValueError, KeyError, OSError):
            return False

    def allowance(self, context):
        if not self.current(context):
            return False
        actor = SimpleNamespace(chat_id=context["conversation_id"])
        return reserve_send(
            self.selected["agents"], actor, {"id": "manufacturer:" + context["id"], "channel": "email"}
        )

    def review_link(self, context):
        from manufacturer_customer_portal import CustomerPortal

        if not self.current(context):
            raise MailHeld("Прегледайте текущия фирмен достъп.")
        cfg, _ = configuration_for(
            self.selected["state"], self.selected["environment_id"], self.extension.company_id
        )
        origin = self.host.public_origin.rstrip("/")
        if not cfg or cfg["portal_origin"].rstrip("/") != origin:
            raise MailHeld("Настройте точния адрес на клиентската страница.")
        actor = context.get("notification_actor") or context["actor"]
        profile = self.extension.customer(actor, context["customer_id"])["customer"]
        portal = CustomerPortal(
            self.selected["state"], self.extension.company_id, self.selected["environment_id"]
        )
        value = portal.mint_review(
            context["customer_id"],
            context["order_id"],
            context["proposal_version_id"],
            recipient=context["recipient"],
            actor=actor,
            display={
                "company": cfg["sender_name"],
                "customer": profile["display_name"],
                "order_number": str(context["proposal"].get("number") or context["order_id"]),
            },
            current=lambda: self.current(context),
        )
        return origin + "/customer/review#" + self.selected["environment_id"] + "." + value["token"]

    async def run(self):
        async with self.slots:
            if not self.closed:
                await asyncio.to_thread(self.extension.mail.drain, limit=4)

    async def tick(self):
        if self.closed or self.task and not self.task.done() or time.monotonic() < self.next_run:
            return
        if self.task:
            # Retrieve failures without exposing customer content in worker logs.
            try:
                self.task.result()
            except Exception:
                pass
        self.next_run = time.monotonic() + 15
        self.task = asyncio.create_task(self.run())

    async def close(self):
        self.closed = True
        if self.task:
            # The current callback fences later sends; retain ambiguous started effects.
            await asyncio.gather(self.task, return_exceptions=True)


def install_mail(host, selected, extension):
    """Attach .mail and compose tick/close with the existing workspace lifecycle."""
    if hasattr(extension, "mail"):
        return extension.mail
    worker = _MailWorker(host, selected, extension)
    environment, company = selected["environment_id"], extension.company_id
    extension.mail = ManufacturerMail(
        selected["state"],
        environment_id=environment,
        company_id=company,
        conversations=extension.conversations,
        config=lambda: configuration_for(selected["state"], environment, company)[0],
        provider=_ConfiguredProvider(selected["state"], environment, company),
        current=worker.current,
        review_link=worker.review_link,
        send_admission=worker.allowance,
    )
    extension.mail_worker = worker
    previous_tick, previous_close = extension.tick, extension.close

    async def tick():
        await previous_tick()
        await worker.tick()

    async def close():
        await worker.close()
        await previous_close()

    extension.tick, extension.close = tick, close
    return extension.mail


def _existing_configuration(host, environment):
    if not ENVIRONMENT.fullmatch(environment):
        raise MailHeld("Изберете текущата имейл връзка.")
    with host.access.connect() as db:
        if not db.execute("SELECT 1 FROM environments WHERE id=?", (environment,)).fetchone():
            raise MailHeld("Изберете текущата имейл връзка.")
    root = Path(host.state) if environment == "demo" else Path(host.state) / "environments" / environment
    if root.is_symlink() or not root.is_dir():
        raise MailHeld("Изберете текущата имейл връзка.")
    config, secret = configuration_for(root, environment)
    if (
        config is None
        or any(
            config.get(key) is not True
            for key in ("commissioned", "sending_verified", "receiving_verified", "webhook_verified")
        )
        or type(config.get("commissioned_until")) not in {int, float}
        or config["commissioned_until"] <= time.time()
    ):
        raise MailHeld("Завършете настройката на фирмения имейл.")
    return config, secret


def register_mail(app, host, *, context, invoke):
    """Mount settings status, owner review/drain and signature-first public ingress."""
    old_public = host.options.get("public_request", lambda request: False)
    old_limit = host.options.get("request_body_limit", lambda request: None)
    host.options["public_request"] = lambda request: (
        (
            request.method == "POST"
            and re.fullmatch(re.escape(HOOK_PREFIX) + ENVIRONMENT.pattern, request.url.path)
        )
        or old_public(request)
    )
    host.options["request_body_limit"] = lambda request: (
        MAX_BODY if request.url.path.startswith(HOOK_PREFIX) else old_limit(request)
    )
    buckets, bucket_lock = {}, threading.Lock()

    @app.get("/api/manufacturer/email/status")
    async def status(request: Request):
        actor, extension = context(request)
        extension.member(actor)
        return JSONResponse(
            await run_in_threadpool(extension.mail.sender_status),
            headers={"Cache-Control": "private, no-store"},
        )

    @app.get("/api/manufacturer/email/review")
    async def reviews(request: Request):
        actor, extension = context(request)
        invoke(extension.member, actor, owner=True)
        return JSONResponse(
            {"items": await run_in_threadpool(invoke, extension.mail.review_items)},
            headers={"Cache-Control": "private, no-store"},
        )

    @app.post("/api/manufacturer/email/drain")
    async def drain(request: Request):
        actor, extension = context(request, True)
        invoke(extension.member, actor, owner=True)
        return JSONResponse(
            await run_in_threadpool(invoke, extension.mail.drain, limit=4),
            headers={"Cache-Control": "private, no-store"},
        )

    @app.post(HOOK_PREFIX + "{environment}")
    async def webhook(environment: str, request: Request):
        # This route must be in the shared host signed-callback path allowlist.
        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > MAX_BODY:
                raise HTTPException(413, "Изпратете имейл събитие до 256 KB.")
        try:
            config, secret = await run_in_threadpool(_existing_configuration, host, environment)
            await run_in_threadpool(
                verify_webhook, bytes(raw), dict(request.headers), secret["webhook_secret"], now=time.time()
            )
        except (MailHeld, ValueError, OSError):
            raise HTTPException(403, "Потвърдете подписа на имейл събитието.") from None
        with bucket_lock:
            minute = int(time.time() // 60)
            key = (environment, minute)
            for old in list(buckets):
                if old[1] < minute:
                    del buckets[old]
            if buckets.get(key, 0) >= 120:
                raise HTTPException(429, "Повторете имейл събитието след малко.")
            buckets[key] = buckets.get(key, 0) + 1
        # A valid provider signature, configured company and registered environment precede recovery.
        try:
            selected = host.workspace(environment)
            extension = selected["vertical"]
            if extension.company_id != config["company_id"]:
                raise MailHeld("Изберете текущата фирмена връзка.")
            result = await run_in_threadpool(extension.mail.accept_webhook, bytes(raw), dict(request.headers))
            extension.mail_worker.next_run = 0
        except (ValueError, OSError):
            raise HTTPException(503, "Имейл събитието ще бъде повторено.") from None
        return JSONResponse(result, headers={"Cache-Control": "no-store"})
