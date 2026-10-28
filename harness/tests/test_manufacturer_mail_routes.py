"""Mail host boundary proof; provider writes and reads are replaced with traps."""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
import sys
import time
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "verticals/manufacturer"))
from manufacturer_conversations import ManufacturerConversations
from manufacturer_mail import ResendHTTPProvider
from manufacturer_mail_routes import configuration_for, install_mail, register_mail
from signal_chain import SignalLedger
from workspace_identity import workspace_scope
from test_manufacturer_mail import SECRET, PROVIDER_ID, config, signed


class NativeStore:
    def __init__(self, root):
        self.path = root / "background-agents.sqlite"
        self.signals = SignalLedger(self)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()


class Extension:
    def __init__(self, selected, company):
        self.selected, self.company_id = selected, company
        self.conversations = ManufacturerConversations(selected["state"], company)
        self.roles = {"peter": "owner", "staff": "operator", "viewer": "browse"}
        self.conversations.ensure_customer(
            "buyer", contacts=[{"email": "buyer@example.test"}], actor="peter", current=lambda: True
        )
        self.ticks, self.closes = 0, 0

    def member(self, actor, *, owner=False, write=False):
        role = self.roles.get(actor)
        if role is None or owner and role != "owner" or write and role == "browse":
            raise ValueError("Use current company authority.")
        return {"id": actor, "role": role}

    def authorized(self, actor):
        return self.roles.get(actor) in {"owner", "operator"}

    def customer(self, actor, identifier):
        self.member(actor)
        return {"customer": {"display_name": "Example Buyer", "contacts": [{"email": "buyer@example.test"}]}}

    async def tick(self):
        self.ticks += 1

    async def close(self):
        self.closes += 1


@pytest.fixture
def boundary(tmp_path, monkeypatch):
    company = workspace_scope(tmp_path)
    agents = NativeStore(tmp_path)
    with agents.connect() as db:
        db.execute("CREATE TABLE environments (id TEXT PRIMARY KEY)")
        db.execute("INSERT INTO environments VALUES('demo')")
    app = FastAPI()
    selected = {
        "state": tmp_path,
        "environment_id": "demo",
        "agents": agents,
        "business_scope": SimpleNamespace(members=lambda: [{"id": "peter", "role": "owner"}]),
    }
    extension = Extension(selected, company)
    selected["vertical"] = extension
    calls = []
    host = SimpleNamespace(
        state=tmp_path,
        access=agents,
        app=app,
        options={},
        public_origin="https://manufacturer.example.test",
        workspaces={"demo": selected},
    )

    def workspace(environment):
        calls.append(environment)
        return selected

    host.workspace = workspace
    install_mail(host, selected, extension)

    def context(request, writable=False):
        actor = request.headers.get("x-actor", "peter")
        try:
            extension.member(actor, write=writable)
        except ValueError:
            raise HTTPException(403)
        return actor, extension

    def invoke(function, *args, **kwargs):
        try:
            return function(*args, **kwargs)
        except ValueError as error:
            raise HTTPException(403, str(error))

    register_mail(app, host, context=context, invoke=invoke)

    def external_trap(*args, **kwargs):
        pytest.fail("An external provider operation occurred at the host boundary.")

    monkeypatch.setattr(ResendHTTPProvider, "send", external_trap)
    monkeypatch.setattr(ResendHTTPProvider, "receive", external_trap)
    monkeypatch.delenv("ROCOTO_CAPABILITY_SPEND_CONFIG", raising=False)
    return host, extension, TestClient(app), calls


def commission(host, extension):
    cfg = config()
    cfg.update(company_id=extension.company_id, commissioned_until=int(time.time()) + 86400)
    path = Path(host.state) / "manufacturer-mail-secret.json"
    secrets = {key: cfg[key] for key in ("schema_version", "environment_id", "company_id", "account_id")}
    secrets.update(send_key="re_offline-send", receive_key="re_offline-read", webhook_secret=SECRET)
    path.write_text(json.dumps(secrets))
    path.chmod(0o600)
    cfg["credentials_path"] = str(path)
    settings = Path(host.state) / "manufacturer-mail.json"
    settings.write_text(json.dumps(cfg))
    settings.chmod(0o600)
    return settings, path


def event():
    return signed(
        {"type": "email.sent", "created_at": "2026-10-16T00:00:00Z", "data": {"email_id": PROVIDER_ID}},
        now=int(time.time()),
    )


def test_install_missing_configuration_status_and_worker_do_zero_external_work(boundary):
    host, extension, client, calls = boundary
    assert client.get("/api/manufacturer/email/status").json()["state"] == "setup"
    response = client.post("/api/manufacturer/email/drain")
    assert response.status_code == 200 and response.json()["held"] is True
    body, headers = event()
    assert client.post("/hooks/manufacturer-email/demo", content=body, headers=headers).status_code == 403
    assert calls == []


def test_missing_credentials_or_allowance_remain_unready(boundary):
    host, extension, client, calls = boundary
    _, credentials = commission(host, extension)
    assert client.get("/api/manufacturer/email/status").json()["state"] == "allowance"
    assert client.post("/api/manufacturer/email/drain").json()["held"] is True
    credentials.unlink()
    assert client.get("/api/manufacturer/email/status").json()["state"] == "setup"
    assert client.post("/api/manufacturer/email/drain").json()["held"] is True
    assert calls == []


def test_webhook_validates_signature_before_any_workspace_initialization(boundary):
    host, extension, client, calls = boundary
    commission(host, extension)
    body, headers = event()
    headers["svix-signature"] = "v1,invalid"
    response = client.post("/hooks/manufacturer-email/demo", content=body, headers=headers)
    assert response.status_code == 403
    assert calls == []
    assert client.post("/hooks/manufacturer-email/unknown", content=body, headers=headers).status_code == 403
    assert calls == []


def test_valid_webhook_only_persists_bounded_metadata_and_duplicate_is_stable(boundary):
    host, extension, client, calls = boundary
    commission(host, extension)
    body, headers = event()
    response = client.post("/hooks/manufacturer-email/demo", content=body, headers=headers)
    assert response.status_code == 200 and response.json()["status"] == "queued"
    assert calls == ["demo"]
    assert (
        client.post("/hooks/manufacturer-email/demo", content=body, headers=headers).json() == response.json()
    )
    with extension.mail._db() as db:
        assert db.execute("SELECT count(*) FROM events").fetchone()[0] == 1
    assert (
        client.post(
            "/hooks/manufacturer-email/demo", content=b"x" * (256 * 1024 + 1), headers=headers
        ).status_code
        == 413
    )
    assert len(calls) == 2


def test_private_configuration_binds_company_account_and_has_no_browser_editor(boundary):
    host, extension, client, calls = boundary
    settings, credentials = commission(host, extension)
    cfg, secret = configuration_for(host.state, "demo", extension.company_id)
    assert cfg["company_id"] == extension.company_id and secret["account_id"] == cfg["account_id"]
    value = json.loads(credentials.read_text())
    value["account_id"] = "foreign-account"
    credentials.write_text(json.dumps(value))
    assert client.get("/api/manufacturer/email/status").json()["ready"] is False
    assert client.post("/api/manufacturer/email/config", json={}).status_code == 404
    settings.chmod(0o644)
    assert client.get("/api/manufacturer/email/status").json()["state"] == "setup"
    assert calls == []


def test_only_owner_can_drain_or_inspect_review_items(boundary):
    host, extension, client, calls = boundary
    for actor in ["staff", "viewer"]:
        assert client.get("/api/manufacturer/email/status", headers={"x-actor": actor}).status_code == 200
        assert client.get("/api/manufacturer/email/review", headers={"x-actor": actor}).status_code == 403
        assert client.post("/api/manufacturer/email/drain", headers={"x-actor": actor}).status_code == 403
    assert client.get("/api/manufacturer/email/review").json() == {"items": []}


def test_worker_shares_native_two_hundred_send_counter(boundary):
    host, extension, client, calls = boundary
    agents = extension.selected["agents"]
    with agents.connect() as db:
        assert agents.signals.reserve(db, "send", "earlier-effects", amount=199)
    context = {
        "id": "mail-1",
        "company_id": extension.company_id,
        "conversation_id": "customer-conversation",
        "customer_id": "buyer",
        "recipient": "buyer@example.test",
        "actor": "peter",
    }
    assert extension.mail_worker.allowance(context) is True
    assert extension.mail_worker.allowance(context) is True
    context["id"] = "mail-2"
    assert extension.mail_worker.allowance(context) is False
    assert agents.signals.usage()["send"]["used"] == 200


def test_lifecycle_composes_and_current_member_revocation_stops_background_work(boundary):
    host, extension, client, calls = boundary

    async def exercise():
        await extension.tick()
        await extension.close()

    asyncio.run(exercise())
    assert extension.ticks == extension.closes == 1
    assert extension.mail_worker.closed is True
    assert extension.mail_worker.current({"company_id": extension.company_id, "actor": "peter"}) is False
