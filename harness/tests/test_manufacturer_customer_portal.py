"""Capability isolation, explicit exact-version review and safe public HTTP admission."""

from __future__ import annotations

import copy
import hashlib
import json
import sqlite3
import sys
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "verticals/manufacturer"))
from manufacturer_conversations import ManufacturerConversations
from manufacturer_customer_portal import (
    PHONE_TTL,
    REVIEW_TTL,
    CustomerPortal,
    existing_portal,
    is_public_portal_request,
    phone_number,
    qr_svg,
    register_customer_portal,
)
from manufacturer_store import Conflict, Invalid, Missing


def current():
    return True


def document():
    return {
        "id": "order-1",
        "customer_id": "buyer",
        "number": "#1001",
        "status": "requested",
        "currency": "EUR",
        "lines": [
            {
                "code": "101037",
                "name": "Дръжка за врата",
                "quantity": 12,
                "unit": "pc",
                "unit_price": 15.5,
                "total": 186,
                "description": "Сатен · розетка",
                "internal_margin": 42,
            }
        ],
        "delivery": {
            "address": "София, ул. Примерна 12",
            "date": "30 октомври 2026",
            "internal_route": "Private",
        },
        "total": 186,
        "enrichment": {"private": True},
        "customer": {"email": "buyer@example.test"},
        "internal_notes": "Private sales strategy",
    }


@pytest.fixture
def prepared(tmp_path):
    store = ManufacturerConversations(tmp_path, "company-a")
    contacts = [{"name": "Иван Петров", "email": "buyer@example.test", "phone": "+359 888 123 456"}]
    store.ensure_customer("buyer", contacts=contacts, actor="peter", current=current)
    store.record_source_order("buyer", document(), actor="peter", current=current)
    proposal = store.propose_request(
        "buyer",
        "order-1",
        proposal=document(),
        recipient="buyer@example.test",
        actor="peter",
        expected_revision=0,
        idempotency_key="proposal-1",
        current=current,
    )["proposal"]
    clock = [1000000.0]
    portal = CustomerPortal(tmp_path, "company-a", "demo", clock=lambda: clock[0])
    display = {"company": "Sample Hardware", "customer": "Примерен клиент", "order_number": "#1001"}
    return SimpleNamespace(
        store=store,
        portal=portal,
        proposal=proposal,
        clock=clock,
        display=display,
        contacts=contacts,
        root=tmp_path,
    )


def review_link(p):
    return p.portal.mint_review(
        "buyer",
        "order-1",
        p.proposal["id"],
        recipient="buyer@example.test",
        actor="peter",
        display=p.display,
        current=current,
    )


def review_session(p):
    return p.portal.redeem(review_link(p)["token"])["session_token"]


def test_link_tokens_are_hashed_and_session_is_separate(prepared):
    p = prepared
    link = review_link(p)
    assert link["expires_at"] == p.clock[0] + REVIEW_TTL
    session = p.portal.redeem(link["token"])
    assert session["session_token"] != link["token"]
    with p.portal.connect() as db:
        rows = [dict(row) for row in db.execute("SELECT * FROM capabilities")]
    raw = json.dumps(rows)
    assert link["token"] not in raw and session["session_token"] not in raw
    assert rows[0]["token_hash"] == hashlib.sha256(link["token"].encode()).hexdigest()
    assert rows[1]["parent_id"] == link["id"]
    with pytest.raises(Missing):
        p.portal.read(link["token"])
    with pytest.raises(Missing):
        p.portal.redeem(session["session_token"])


def test_exact_commercial_projection_and_explicit_confirmation(prepared):
    p = prepared
    token = review_session(p)
    before = p.store.order_review("buyer", "order-1")
    data = p.portal.read(token)
    assert data["can_confirm"] and data["is_current"]
    saved = data["proposal"]["document"]
    assert saved["lines"][0]["total"] == 186 and saved["delivery"]["date"] == "30 октомври 2026"
    assert "enrichment" not in saved and "customer" not in saved and "internal_notes" not in saved
    assert "internal_margin" not in saved["lines"][0] and "internal_route" not in saved["delivery"]
    assert data["proposal"]["sha256"] == p.proposal["sha256"]
    assert p.store.order_review("buyer", "order-1") == before
    p.portal.confirm(token, version_id=p.proposal["id"])
    after = p.store.order_review("buyer", "order-1")
    assert after["review_status"] == "customer_confirmed"
    assert after["source_status"] == before["source_status"] == "requested"
    assert after["source"] == before["source"]
    assert p.portal.read(token)["confirmed"]


def test_old_version_readable_but_cannot_confirm_or_change(prepared):
    p = prepared
    token = review_session(p)
    revision = p.store.order_review("buyer", "order-1")["revision"]
    changed = copy.deepcopy(document())
    changed["lines"][0]["quantity"] = 20
    latest = p.store.propose_request(
        "buyer",
        "order-1",
        proposal=changed,
        recipient="buyer@example.test",
        actor="peter",
        expected_revision=revision,
        idempotency_key="proposal-2",
        current=current,
    )["proposal"]
    data = p.portal.read(token)
    assert not data["is_current"] and not data["can_confirm"]
    assert data["proposal"]["document"]["lines"][0]["quantity"] == 12
    with pytest.raises(Conflict):
        p.portal.confirm(token, version_id=p.proposal["id"])
    with pytest.raises(Invalid):
        p.portal.confirm(token, version_id=latest["id"])
    with pytest.raises(Conflict):
        p.portal.change(token, version_id=p.proposal["id"], text="Промяна", idempotency_key="old-change")


def test_change_request_keeps_snapshot_and_confirmed_previous(prepared):
    p = prepared
    token = review_session(p)
    p.portal.confirm(token, version_id=p.proposal["id"])
    p.portal.change(token, version_id=p.proposal["id"], text="Моля, 15 броя.", idempotency_key="change-1")
    review = p.store.order_review("buyer", "order-1")
    assert review["review_status"] == "changes_requested"
    assert review["confirmed_version_id"] == p.proposal["id"]
    assert p.store.proposal("buyer", "order-1", p.proposal["id"])["document"] == document()


def test_scope_recipient_and_phone_validation(prepared):
    p = prepared
    with pytest.raises(Invalid):
        CustomerPortal(p.root, "company-b", "demo")
    with pytest.raises(Invalid):
        CustomerPortal(p.root, "company-a", "other")
    with pytest.raises(Invalid):
        CustomerPortal(p.root, "company-a", "../demo")
    with pytest.raises(Invalid):
        p.portal.mint_review(
            "buyer",
            "order-1",
            p.proposal["id"],
            recipient="outsider@example.test",
            actor="peter",
            display=p.display,
            current=current,
        )
    with pytest.raises(Invalid):
        p.portal.mint_phone("buyer", phone="+359999999999", actor="peter", display=p.display, current=current)
    with pytest.raises(Invalid):
        p.portal.mint_phone(
            "buyer", phone="+359888123456", actor="peter", display=p.display, current=lambda: False
        )
    assert phone_number("00359 (888) 123-456") == "+359888123456"
    for value in ["0888123456", "+359888123456;ext=12", "+359888123456?x=y"]:
        with pytest.raises(Invalid):
            phone_number(value)


def test_phone_grant_only_exposes_exact_contact_and_expiry(prepared):
    p = prepared
    link = p.portal.mint_phone(
        "buyer", phone="+359888123456", actor="peter", display=p.display, current=current
    )
    assert link["expires_at"] == p.clock[0] + PHONE_TTL
    token = p.portal.redeem(link["token"])["session_token"]
    data = p.portal.read(token)
    assert data["phone"] == "+359888123456" and data["purpose"] == "phone"
    assert set(data) == {"phone", "display", "purpose", "expires_at"}
    with pytest.raises(Invalid):
        p.portal.confirm(token, version_id=p.proposal["id"])
    p.clock[0] += PHONE_TTL
    with pytest.raises(Missing):
        p.portal.read(token)


def test_parent_revoke_and_contact_removal_invalidate_sessions(prepared):
    p = prepared
    link = review_link(p)
    token = p.portal.redeem(link["token"])["session_token"]
    p.portal.revoke(link["id"], actor="peter", current=current)
    with pytest.raises(Missing):
        p.portal.read(token)
    with pytest.raises(Missing):
        p.portal.redeem(link["token"])
    token = review_session(p)
    p.store.ensure_customer("buyer", contacts=[{"email": "new@example.test"}], actor="peter", current=current)
    with pytest.raises(Missing):
        p.portal.read(token)


def test_environment_resolution_never_creates_workspace(prepared):
    p = prepared
    access_path = p.root / "access.sqlite"
    with sqlite3.connect(access_path) as db:
        db.execute("CREATE TABLE environments(id TEXT PRIMARY KEY)")
        db.executemany("INSERT INTO environments VALUES(?)", [("demo",), ("empty",)])

    @contextmanager
    def connect():
        with sqlite3.connect(access_path) as db:
            yield db

    host = SimpleNamespace(
        state=p.root,
        access=SimpleNamespace(connect=connect),
        workspace=lambda *_: pytest.fail("Public access constructed a workspace"),
    )
    assert existing_portal(host, "demo").company_id == "company-a"
    for environment in ["empty", "unknown", "../demo"]:
        with pytest.raises(Missing):
            existing_portal(host, environment)
    assert not (p.root / "environments").exists()


@pytest.fixture
def web(prepared):
    p = prepared
    # HTTP operations use wall time; leave the deterministic expiry tests on their own clock.
    import time

    p.clock[0] = time.time()
    access_path = p.root / "access.sqlite"
    with sqlite3.connect(access_path) as db:
        db.execute("CREATE TABLE environments(id TEXT PRIMARY KEY)")
        db.execute("INSERT INTO environments VALUES('demo')")

    @contextmanager
    def connect():
        with sqlite3.connect(access_path) as db:
            yield db

    app = FastAPI()
    host = SimpleNamespace(
        state=p.root, access=SimpleNamespace(connect=connect), public_origin="http://testserver", options={}
    )

    def context(*_):
        pytest.fail("Public route attempted workspace authentication")

    register_customer_portal(app, host, context=context, invoke=lambda function: function())
    return TestClient(app), host, p


def post(client, action, payload, token=None, **extra):
    headers = {"Origin": "http://testserver", "X-Rocoto-Page": "1", **extra}
    if token:
        headers["Authorization"] = "Bearer " + token
    return client.post("/api/manufacturer/customer-portal/demo/" + action, json=payload, headers=headers)


def test_public_get_is_empty_private_and_never_consumes(web):
    client, host, p = web
    link = review_link(p)
    with p.portal.connect() as db:
        before = db.execute("SELECT count(*) FROM capabilities").fetchone()[0]
    for path in ["/customer/review", "/customer/phone"]:
        response = client.get(path + "#demo." + link["token"])
        assert response.status_code == 200
        assert "buyer@example.test" not in response.text and "#1001" not in response.text
        assert response.headers["Cache-Control"] == "private, no-store"
        assert response.headers["Referrer-Policy"] == "no-referrer"
        assert response.cookies == {}
    with p.portal.connect() as db:
        assert db.execute("SELECT count(*) FROM capabilities").fetchone()[0] == before
    response = client.get("/static/manufacturer/manufacturer-customer-portal.js?filename=../../server.py")
    assert response.status_code == 200 and "A customer capability" in response.text
    assert not is_public_portal_request(
        SimpleNamespace(method="GET", url=SimpleNamespace(path="/api/orders"))
    )


def test_public_posts_require_same_origin_bounded_json_and_exact_scope(web):
    client, _, p = web
    link = review_link(p)
    response = client.post("/api/manufacturer/customer-portal/demo/redeem", json={"token": link["token"]})
    assert response.status_code == 403 and response.headers["Cache-Control"] == "private, no-store"
    assert post(client, "redeem", {"token": link["token"]}, Origin="https://outside.test").status_code == 403
    assert (
        post(client, "redeem", {"token": link["token"]}, **{"Sec-Fetch-Site": "cross-site"}).status_code
        == 403
    )
    assert post(client, "redeem", {"token": "a" * 17000}).status_code == 413
    assert post(client, "redeem", {"token": link["token"], "customer": "someone"}).status_code == 400
    session = post(client, "redeem", {"token": link["token"]}).json()["session_token"]
    response = post(client, "read", {}, session)
    assert response.status_code == 200 and response.json()["proposal"]["id"] == p.proposal["id"]
    assert response.cookies == {}
    assert post(client, "confirm", {"version_id": "other"}, session).status_code == 403
    assert post(client, "confirm", {"version_id": p.proposal["id"]}, session).status_code == 200
    assert p.store.order_review("buyer", "order-1")["source_status"] == "requested"


def test_qr_is_standalone_local_svg():
    svg = qr_svg("https://example.test/customer/phone#demo." + "a" * 43)
    assert svg.startswith("<svg") and "</svg>" in svg
    assert "<script" not in svg and "<image" not in svg and "href=" not in svg
