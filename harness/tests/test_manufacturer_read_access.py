"""Current browse membership may hydrate/read CRM; human mutations require write membership."""

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "verticals/manufacturer"))

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from manufacturer_conversation_routes import register_conversations
from manufacturer_conversations import ManufacturerConversations
from manufacturer_fulfillment import register_fulfillment
from manufacturer_store import Conflict, Invalid, Missing


@pytest.fixture
def boundary(tmp_path):
    store = ManufacturerConversations(tmp_path, "company-a")
    source = {
        "id": "order-1",
        "customer_id": "buyer",
        "display_number": "#1001",
        "status": "requested",
        "currency": "EUR",
        "lines": [{"code": "101937", "quantity": 2, "name": "Брава"}],
    }
    profile = {"id": "buyer", "display_name": "Buyer", "contacts": [{"email": "buyer@example.test"}]}

    class Extension:
        conversations = store
        company_id = "company-a"
        selected = {
            "state": tmp_path,
            "environment_id": "demo",
            "business_scope": SimpleNamespace(members=lambda: []),
        }
        role = "browse"

        def member(self, actor, *, write=False):
            if actor != "reader" or self.role not in (
                {"owner", "operator"} if write else {"owner", "operator", "browse"}
            ):
                raise ValueError("Continue with current company access.")
            return {"role": self.role}

        def actor(self, actor):
            return {"id": actor, **self.member(actor)}

        def authorized(self, actor):
            try:
                return bool(self.member(actor, write=True))
            except ValueError:
                return False

        def customer(self, actor, customer_id):
            self.member(actor)
            if customer_id != "buyer":
                raise Missing("Choose this company customer.")
            return {"customer": profile}

        def order(self, actor, order_id):
            self.member(actor)
            if order_id != "order-1":
                raise Missing("Choose this company order.")
            return {"order": source}

        def _customer_snapshot(self, actor):
            self.member(actor)
            return [{**profile, "orders": [source]}], None, None

    extension = Extension()

    def context(request, writable=False):
        try:
            extension.member("reader", write=writable)
        except ValueError as exc:
            raise HTTPException(403, str(exc)) from None
        return "reader", extension

    def invoke(fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except (Invalid, Missing, Conflict, ValueError) as exc:
            status = (
                404
                if isinstance(exc, Missing)
                else 409
                if isinstance(exc, Conflict)
                else 403
                if isinstance(exc, ValueError)
                else 400
            )
            raise HTTPException(status, str(exc)) from None

    app = FastAPI()
    register_conversations(app, context=context, body=lambda request: request.json(), invoke=invoke)
    register_fulfillment(app, context=context, body=lambda request: request.json(), invoke=invoke)
    with TestClient(app) as client:
        yield client, store, extension


@pytest.mark.parametrize(
    "path",
    [
        "/api/manufacturer/service-conversation",
        "/api/manufacturer/conversations/buyer",
        "/api/manufacturer/orders/order-1/review",
        "/api/manufacturer/orders/order-1/fulfillment",
    ],
)
def test_browse_member_reads_and_repeat_hydration_is_idempotent(boundary, path):
    client, store, extension = boundary
    assert extension.authorized("reader") is False
    first = client.get(path)
    assert first.status_code == 200, first.text
    second = client.get(path)
    assert second.status_code == 200, second.text
    assert first.json() == second.json()
    assert store.pending_deliveries() == []


@pytest.mark.parametrize(
    "path",
    [
        "/api/manufacturer/service-conversation/messages",
        "/api/manufacturer/conversations/buyer/messages",
        "/api/manufacturer/orders/order-1/review",
        "/api/manufacturer/orders/order-1/fulfillment",
    ],
)
def test_browse_cannot_post_human_mutations(boundary, path):
    client, store, _ = boundary
    assert client.post(path, json={}).status_code == 403
    with store._transaction() as db:
        assert db.execute("SELECT count(*) FROM messages").fetchone()[0] == 0
    assert store.pending_deliveries() == []


def test_read_hydration_rechecks_membership_at_commit(boundary, monkeypatch):
    client, store, extension = boundary
    original = store.record_source_order

    def revoke_at_commit(customer_id, order, *, actor, current):
        checks = 0

        def admitted():
            nonlocal checks
            checks += 1
            if checks == 2:
                extension.role = None
            return current()

        return original(customer_id, order, actor=actor, current=admitted)

    monkeypatch.setattr(store, "record_source_order", revoke_at_commit)
    assert client.get("/api/manufacturer/orders/order-1/review").status_code in {400, 403}
    with store._transaction() as db:
        assert db.execute("SELECT count(*) FROM orders").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM messages").fetchone()[0] == 0


@pytest.mark.parametrize(
    ("quantity", "unit_price", "expected"),
    [
        (0.5, 0.29, 0.15),
        (1, 2.675, 2.68),
        (3, 19.99, 59.97),
    ],
)
def test_review_money_uses_decimal_rounding_and_replays_exact_receipt(
    boundary, quantity, unit_price, expected
):
    client, store, extension = boundary
    extension.role = "operator"
    payload = {
        "lines": [{"quantity": quantity, "unit_price": unit_price}],
        "delivery": {},
        "notes": "",
        "expected_revision": 0,
        "idempotency_key": "price-check",
    }
    first = client.post("/api/manufacturer/orders/order-1/review", json=payload)
    assert first.status_code == 200, first.text
    document = first.json()["proposal"]["document"]
    assert document["lines"][0]["line_total"] == expected
    assert document["subtotal"] == expected
    repeated = client.post("/api/manufacturer/orders/order-1/review", json=payload)
    assert repeated.status_code == 200 and repeated.json() == first.json()
    assert len(store.pending_deliveries()) == 1
