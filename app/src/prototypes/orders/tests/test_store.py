import sqlite3

import pytest
from store import CompanyStore


@pytest.fixture
def store(tmp_path):
    store = CompanyStore(tmp_path / "private" / "company.db")
    catalog = {
        "company": {"en": "Example"},
        "source": "https://example.test/prices",
        "services": [],
        "rules": {"vat": 0.2},
        "cats": [
            {
                "code": "tube",
                "en": "Tubes",
                "items": [{"c": "A", "p": 12.345, "cut": 0.42, "L": 6, "r": {"k": "len", "l": [3, 6]}}],
            }
        ],
    }
    store.ingest_catalog(
        catalog,
        {
            "slug": "example",
            "hours": {str(i): [510, 1050, 1020] for i in range(1, 6)},
            "shop": {"backlog": 0, "perLine": 6, "perCut": 2},
        },
        "test",
        "fixture",
    )
    yield store
    store.close()


def test_roundtrip_and_price_history(store):
    original = store.export_catalog()
    store.set_price("A", 13.777, "operator", "new supplier list", idempotency_key="price-1")
    assert store.export_catalog()["cats"][0]["items"][0]["p"] == 13.777
    assert original["cats"][0]["items"][0]["p"] == 12.345
    assert [r["amount"] for r in store.rows("SELECT amount FROM prices WHERE basis='p' ORDER BY id")] == [
        12.345,
        13.777,
    ]
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        store.db.execute("DELETE FROM prices")


def test_ingest_is_atomic(store):
    catalog = store.export_catalog()
    catalog["cats"][0]["items"].append(catalog["cats"][0]["items"][0])
    with pytest.raises(ValueError, match="duplicate"):
        store.ingest_catalog(catalog, {"slug": "example"}, "reader", "broken list")
    assert store.one("SELECT COUNT(*) n FROM items WHERE active=1")["n"] == 1


def test_idempotency(store):
    first = store.set_price("A", 20, "operator", "list", idempotency_key="once")
    assert store.set_price("A", 20, "operator", "list", idempotency_key="once") == first
    with pytest.raises(ValueError, match="different input"):
        store.set_price("A", 21, "operator", "list", idempotency_key="once")
    assert store.item("A")["item"]["p"] == 20


def test_unknown_is_never_inventory(store):
    stock = store.supply_projection()["items"]["A"]
    assert stock["state"] == "listed" and stock["quantity"] is None
    with pytest.raises(ValueError, match="must be null"):
        store.record_stock("A", 100, "operator", "guess", state="listed")


def test_public_supply_exposes_selling_rules_without_inventory_or_capacity(store):
    store.record_stock("A", 12, "operator", "counted")
    public = store.public_supply_projection()
    assert public["items"]["A"]["selling"] == {
        "minimum": 1,
        "step": 1,
        "pack": 1,
        "status": "assumed",
    }
    assert set(public) == {"timezone", "items"}
    assert not {"state", "quantity", "reserved"} & set(public["items"]["A"])


def test_moq_step_and_pack(store):
    store.set_selling("A", 4, 2, 4, "owner", "confirmed by owner")
    store.validate_lines([{"item_id": "A", "quantity": 8}])
    for quantity in [0, 2, 5, 6, float("nan"), float("inf"), True]:
        with pytest.raises(ValueError):
            store.validate_lines([{"item_id": "A", "quantity": quantity}])


def test_claim_does_not_grant_membership(store):
    first = store.request_claim("owner@example.test", "Owner", "public", "claim form", "claim-1")
    assert first["status"] == "pending"
    assert store.request_claim("owner@example.test", "Owner", "public", "claim form", "claim-1") == first
    assert store.rows("SELECT * FROM members") == []


def submit(store, key="order-1", quantity=2):
    return store.submit_order(
        {"name": "Buyer", "email": "buyer@example.test"},
        [{"item_id": "A", "quantity": quantity, "cuts": 2}],
        {"gross": 20},
        key,
        "web",
        "server recomputed price",
        now="2026-10-12T09:00:00+03:00",
    )


def test_request_is_not_promise_and_acceptance_rolls_back(store):
    order = submit(store)
    assert order["state"] == "requested" and order["ready"]["kind"] == "estimate"
    assert store.rows("SELECT * FROM capacity_load") == []
    with pytest.raises(ValueError, match="confirmed stock"):
        store.accept_order(order["id"], "owner", "accepted", "accept-1", now="2026-10-12T09:00:00+03:00")
    assert store.read_order(order["id"])["state"] == "requested"
    assert store.rows("SELECT * FROM capacity_load") == []
    assert store.item("A")["stock"]["reserved"] == 0


def test_accept_reserves_and_cancellation_releases(store):
    store.record_stock("A", 10, "owner", "counted")
    order = submit(store)
    first = store.accept_order(order["id"], "owner", "accepted", "accept-1", now="2026-10-12T09:00:00+03:00")
    assert first["ready"]["kind"] == "promise"
    assert store.accept_order(order["id"], "owner", "accepted", "accept-1") == first
    assert store.item("A")["stock"]["reserved"] == 2
    assert store.one("SELECT SUM(minutes) n FROM capacity_load")["n"] == 10
    store.mark_order(order["id"], "cancelled", "owner", "buyer cancelled", "cancel-1")
    assert store.item("A")["stock"]["reserved"] == 0
    assert store.one("SELECT SUM(minutes) n FROM capacity_load")["n"] == 0


def test_issued_invoice_is_an_immutable_operator_record(store):
    order = submit(store)
    with pytest.raises(ValueError, match="accept"):
        store.record_invoice(
            order["id"], "MM-2026-14", "2026-10-12T09:00:00+03:00", "EUR", 20,
            "https://invoices.example.test/MM-2026-14.pdf", "owner", "issued in ledger", "invoice-1",
        )
    store.record_stock("A", 10, "owner", "counted")
    store.accept_order(order["id"], "owner", "accepted", "accept-invoice")
    invoice = store.record_invoice(
        order["id"], "MM-2026-14", "2026-10-12T09:00:00+03:00", "EUR", 20,
        "https://invoices.example.test/MM-2026-14.pdf", "owner", "issued in ledger", "invoice-1",
    )
    assert store.record_invoice(
        order["id"], "MM-2026-14", "2026-10-12T09:00:00+03:00", "EUR", 20,
        "https://invoices.example.test/MM-2026-14.pdf", "owner", "issued in ledger", "invoice-1",
    ) == invoice
    row = store.one("SELECT number,issued_at,currency,amount,document_url,actor,evidence FROM invoices")
    assert row == {
        "number": "MM-2026-14", "issued_at": "2026-10-12T09:00:00+03:00", "currency": "EUR",
        "amount": 20.0, "document_url": "https://invoices.example.test/MM-2026-14.pdf",
        "actor": "owner", "evidence": "issued in ledger",
    }
    assert store.one("SELECT event FROM order_events WHERE event='invoice_issued'")["event"] == "invoice_issued"
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        store.db.execute("UPDATE invoices SET number='changed'")


@pytest.mark.parametrize("issued_at,currency,url", [
    ("2026-10-12T09:00:00", "EUR", "https://invoices.example.test/MM-14.pdf"),
    ("2026-10-12T09:00:00+03:00", "eur", "https://invoices.example.test/MM-14.pdf"),
    ("2026-10-12T09:00:00+03:00", "EUR", "http://invoices.example.test/MM-14.pdf"),
    ("2026-10-12T09:00:00+03:00", "EUR", "https://user:pass@invoices.example.test/MM-14.pdf"),
])
def test_invoice_record_requires_issued_time_currency_and_safe_document_url(store, issued_at, currency, url):
    order = submit(store)
    with pytest.raises(ValueError):
        store.record_invoice(order["id"], "MM-14", issued_at, currency, 20, url, "owner", "ledger", "bad")


def test_acceptance_holds_unresolved_commercial_terms(store):
    store.record_stock('A', 10, 'owner', 'counted')
    order = store.submit_order(
        {'name': 'Buyer', 'email': 'buyer@example.test'},
        [{'item_id': 'A', 'quantity': 1, 'confirmation': True, 'plan': {'pending': True}}],
        {'gross': 20, 'confirmation': True}, 'pending-order', 'web', 'server quote',
    )
    with pytest.raises(ValueError, match='commercial terms'):
        store.accept_order(order['id'], 'owner', 'accept', 'pending-accept')
    assert store.item('A')['stock']['reserved'] == 0
    assert store.rows('SELECT * FROM capacity_load') == []
    assert store.item("A")["stock"]["quantity"] == 10


def test_two_orders_cannot_reserve_same_stock(store):
    store.record_stock("A", 3, "owner", "counted")
    one = submit(store, "one")
    two = submit(store, "two")
    store.accept_order(one["id"], "owner", "accepted", "accept-one")
    with pytest.raises(ValueError):
        store.accept_order(two["id"], "owner", "accepted", "accept-two")
    assert store.item("A")["stock"]["reserved"] == 2
    assert store.read_order(two["id"])["state"] == "requested"


def test_custom_request_is_held_for_pricing(store):
    order = store.submit_order(
        {"name": "Buyer", "phone": "123"},
        [{"kind": "custom", "item_id": None, "quantity": 1, "description": "Cut a drawing"}],
        {"confirmation": True},
        "custom",
        "web",
        "custom request",
    )
    assert order["ready"]["kind"] == "estimate"
    with pytest.raises(ValueError, match="commercial terms"):
        store.accept_order(order["id"], "owner", "accept", "custom-accept")


def test_messages_are_held(store):
    order = submit(store)
    assert store.draft_message(order["id"], "Order ready", "agent", "owner review")["status"] == "held"
    with pytest.raises(sqlite3.IntegrityError):
        store.db.execute("UPDATE messages SET status='sent'")


def test_simultaneous_acceptance_serializes_stock(store):
    from concurrent.futures import ThreadPoolExecutor

    store.record_stock("A", 3, "owner", "counted")
    orders = [submit(store, "race-a"), submit(store, "race-b")]

    def accept(order):
        connection = CompanyStore(store.path)
        try:
            return connection.accept_order(order["id"], "owner", "race check", "race-" + order["id"])["state"]
        except ValueError:
            return "insufficient"
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(accept, orders)) == ["accepted", "insufficient"]
    assert store.item("A")["stock"]["reserved"] == 2


def test_reschedule_updates_capacity_and_failure_rolls_back(store):
    store.record_stock("A", 10, "owner", "counted")
    order = submit(store)
    store.accept_order(order["id"], "owner", "accept", "accept", now="2026-10-12T09:00:00+03:00")
    store.change_time(
        order["id"],
        "2026-10-13T09:00:00+03:00",
        "2026-10-13T12:00:00+03:00",
        "owner",
        "customer agreed",
        "reschedule",
    )
    assert store.one("SELECT SUM(minutes) n FROM capacity_load WHERE day='2026-10-12'")["n"] == 0
    assert store.one("SELECT SUM(minutes) n FROM capacity_load WHERE day='2026-10-13'")["n"] == 10
    with pytest.raises(ValueError, match="insufficient capacity"):
        store.change_time(
            order["id"],
            "2026-10-14T09:00:00+03:00",
            "2026-10-14T09:01:00+03:00",
            "owner",
            "too short",
            "failed-reschedule",
        )
    assert store.item("A")["stock"]["reserved"] == 2
    assert store.one("SELECT SUM(minutes) n FROM capacity_load WHERE day='2026-10-13'")["n"] == 10


@pytest.mark.parametrize("delivery", [None, "confirmation", "estimated"])
def test_delivery_terms_hold_acceptance_atomically(store, delivery):
    store.record_stock("A", 10, "owner", "counted")
    order = store.submit_order(
        {"name": "Buyer", "email": "buyer@example.test"},
        [{"item_id": "A", "quantity": 1}],
        {"gross": 12.345, "confirmation": False, "fulfilment": "delivery", "delivery": delivery},
        "delivery-request", "web", "server quote",
    )
    with pytest.raises(ValueError, match="confirm delivery terms"):
        store.accept_order(order["id"], "owner", "accepted", "delivery-accept")
    assert store.read_order(order["id"])["state"] == "requested"
    assert store.item("A")["stock"]["reserved"] == 0
    assert store.rows("SELECT * FROM capacity_load") == []
    assert store.rows("SELECT * FROM estimates WHERE kind='promise'") == []


def test_reviewed_delivery_quote_can_be_accepted(store):
    store.record_stock("A", 10, "owner", "counted")
    order = store.submit_order(
        {"name": "Buyer", "email": "buyer@example.test"},
        [{"item_id": "A", "quantity": 1}],
        {"gross": 22.345, "confirmation": False, "fulfilment": "delivery"},
        "delivery-reviewed", "owner", "reviewed material and delivery quote",
    )
    delivery = store.confirm_delivery(
        order["id"], "2030-10-14T10:00:00+03:00", "2030-10-14T12:00:00+03:00",
        "Delivery to the recorded address.", "owner", "carrier booking", "delivery-confirm", included=True,
    )
    assert delivery["state"] == "requested"
    assert store.rows("SELECT * FROM estimates WHERE kind='promise'") == []
    result = store.accept_order(order["id"], "owner", "reviewed terms", "delivery-accept")
    assert result["state"] == "accepted"
    assert store.item("A")["stock"]["reserved"] == 1


def test_delivery_confirmation_is_immutable_evidence_and_rejects_arrival_before_ready_promise(store):
    store.record_stock("A", 10, "owner", "counted")
    order = store.submit_order(
        {"name": "Buyer", "email": "buyer@example.test"}, [{"item_id": "A", "quantity": 1}],
        {"gross": 22.345, "currency": "EUR", "fulfilment": "delivery"}, "delivery-window", "web", "quote",
        now="2026-10-12T09:00:00+03:00",
    )
    original = store.read_order(order["id"])["quote"]
    confirmed = store.confirm_delivery(
        order["id"], "2026-10-13T10:00:00+03:00", "2026-10-13T12:00:00+03:00",
        "Forklift unloading at the recorded address.", "operator", "carrier booking", "delivery-window-1",
        fee=24.5, currency="EUR", vat_rate=0.2,
    )
    assert store.confirm_delivery(
        order["id"], "2026-10-13T10:00:00+03:00", "2026-10-13T12:00:00+03:00",
        "Forklift unloading at the recorded address.", "operator", "carrier booking", "delivery-window-1",
        fee=24.5, currency="EUR", vat_rate=0.2,
    ) == confirmed
    quote = store.read_order(order["id"])["quote"]
    assert quote["gross"] == 46.85 and quote["breakdown"]["delivery"] == {
        "net": 20.42, "vat": 4.08, "gross": 24.5, "vat_rate": 0.2, "currency": "EUR",
    }
    assert quote["review"]["state"] == "awaiting_customer" and quote["gross"] != original["gross"]
    assert store.one("SELECT event FROM order_events WHERE event='delivery_confirmed'")["event"] == "delivery_confirmed"
    from reviewed_orders import assent_reviewed_quote
    assent_reviewed_quote(
        store, order["id"], quote["review"]["id"], "customer-link", "private order link", "delivery-assent"
    )
    with pytest.raises(ValueError, match="workshop ready promise"):
        store.accept_order(order["id"], "owner", "accept", "delivery-window-accept", now="2026-10-12T09:00:00+03:00")
    assert store.read_order(order["id"])["state"] == "requested"


@pytest.mark.parametrize("kwargs", [
    {"fee": 2, "currency": "eur"}, {"fee": float("nan"), "currency": "EUR"},
    {"included": True, "fee": 2, "currency": "EUR"}, {"fee": 2, "currency": "EUR", "vat_rate": 1.1}, {},
])
def test_delivery_confirmation_requires_a_real_fee_or_confirmed_inclusion(store, kwargs):
    order = store.submit_order(
        {"name": "Buyer", "email": "buyer@example.test"}, [{"item_id": "A", "quantity": 1}],
        {"gross": 22.345, "currency": "EUR", "fulfilment": "delivery"}, "delivery-fee-" + str(kwargs), "web", "quote",
    )
    with pytest.raises(ValueError):
        store.confirm_delivery(
            order["id"], "2030-10-14T10:00:00+03:00", "2030-10-14T12:00:00+03:00", "Carrier booking",
            "operator", "booking", "delivery-fee-key-" + str(kwargs), **kwargs,
        )
