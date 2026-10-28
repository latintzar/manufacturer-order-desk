import json

import pytest
from customer_mail import CustomerMail
from reviewed_orders import (
    assent_reviewed_quote,
    commercially_resolved,
    confirm_operation_capacity,
    review_order,
    reviewed_price_is_firm,
)
from test_store import store as store

import tools

NOW = "2026-10-12T09:00:00+03:00"


def confirm_workshop(store):
    return confirm_operation_capacity(
        store,
        "cut",
        "workshop",
        6,
        2,
        480,
        "owner",
        "measured workshop process",
        "confirm-workshop",
    )


def make_held_item(store):
    item = json.loads(store.one("SELECT data FROM items WHERE id='A'")["data"])
    item["r"]["l"] = [6]
    store.db.execute("UPDATE items SET data=? WHERE id='A'", (json.dumps({**item, "q": True}),))


def confirm_prices(store, prefix="review"):
    store.set_price("A", 15, "owner", "reviewed material rate", idempotency_key=prefix + "-p")
    store.set_price("A", 2, "owner", "reviewed cutting rate", "cut", prefix + "-cut")


def custom_order(store, key="custom-review"):
    return store.submit_order(
        {"name": "Buyer", "email": "buyer@example.test"},
        [
            {
                "kind": "custom",
                "item_id": None,
                "quantity": 1,
                "description": "Cut the supplied drawing into one 3 metre section",
            }
        ],
        {"gross": 0, "currency": "EUR", "confirmation": True, "fulfilment": "pickup"},
        key,
        "web",
        "customer request",
        now=NOW,
    )


def replacement(description="Cut the supplied drawing into one 3 metre section"):
    return [
        {
            "line_index": 0,
            "requests": [{"code": "A", "rows": [{"x": 3000, "n": 2}]}],
            "operation": {"id": "cut", "description": description},
        }
    ]


def test_custom_review_preserves_order_history_and_requires_exact_customer_assent(store):
    make_held_item(store)
    confirm_workshop(store)
    confirm_prices(store)
    store.record_stock("A", 5, "owner", "physical count", status="confirmed")
    original = custom_order(store)
    customer_id = store.one("SELECT customer_id FROM orders WHERE id=?", (original["id"],))["customer_id"]

    result = review_order(
        store,
        original["id"],
        replacement(),
        "owner",
        "drawing and reviewed rates",
        "review-custom-1",
        now=NOW,
    )
    assert result["id"] == original["id"] and result["assent_required"] is True
    assert store.one("SELECT customer_id FROM orders WHERE id=?", (original["id"],))["customer_id"] == customer_id
    assert store.one("SELECT COUNT(*) n FROM customers")["n"] == 1
    order = store.read_order(original["id"])
    assert order["state"] == "requested" and order["quote"]["confirmation"] is True
    assert order["quote"]["review"]["state"] == "awaiting_customer"
    assert len(order["lines"]) == 1 and order["lines"][0]["item_id"] == "A"
    assert order["lines"][0]["quantity"] == 1 and order["lines"][0]["cuts"] == 1
    assert reviewed_price_is_firm(store, order["lines"][0])
    assert {row["basis"] for row in order["lines"][0]["review"]["prices"]} == {"p", "cut"}
    assert order["estimates"][-1]["data"]["stock"][0] == {
        "item_id": "A",
        "required": 1.0,
        "available": 5.0,
        "state": "known",
    }
    event = store.one("SELECT data FROM order_events WHERE event='quote_reviewed'")
    history = json.loads(event["data"])
    assert history["replacements"][0]["original_line"]["description"].startswith("Cut the supplied")
    assert history["replacements"][0]["operation"]["description"].startswith("Cut the supplied")
    assert store.item("A")["stock"]["reserved"] == 0
    assert commercially_resolved(store, order) is False

    with pytest.raises(ValueError, match="current reviewed quote"):
        assent_reviewed_quote(
            store, original["id"], "superseded", "customer:buyer", "private link", "wrong-assent"
        )
    assented = assent_reviewed_quote(
        store,
        original["id"],
        result["review_id"],
        "customer:buyer",
        "private order link",
        "assent-custom-1",
    )
    assert assented["quote"]["confirmation"] is False
    assert assented["quote"]["review"]["state"] == "assented"
    assert commercially_resolved(store, store.read_order(original["id"]))
    assert store.one("SELECT COUNT(*) n FROM order_events WHERE event='quote_assented'")["n"] == 1


def test_review_requires_confirmed_price_operation_and_resource_without_partial_write(store):
    make_held_item(store)
    order = custom_order(store)
    with pytest.raises(ValueError, match="confirm the operation"):
        review_order(
            store, order["id"], replacement(), "owner", "review", "review-missing-operation", now=NOW
        )
    assert store.read_order(order["id"])["lines"][0]["kind"] == "custom"
    assert store.rows("SELECT * FROM order_events WHERE event='quote_reviewed'") == []

    confirmed = confirm_workshop(store)
    assert confirm_workshop(store) == confirmed
    assert store.one(
        "SELECT COUNT(*) n FROM audit WHERE action='orders.confirm_operation_capacity'"
    )["n"] == 1
    with pytest.raises(ValueError, match="confirmed p price override"):
        review_order(
            store, order["id"], replacement(), "owner", "review", "review-missing-price", now=NOW
        )
    assert store.read_order(order["id"])["lines"][0]["kind"] == "custom"
    assert store.rows("SELECT * FROM order_events WHERE event='quote_reviewed'") == []


def test_review_is_idempotent_and_requires_every_held_line(store):
    make_held_item(store)
    confirm_workshop(store)
    confirm_prices(store)
    order = store.submit_order(
        {"name": "Buyer", "email": "buyer@example.test"},
        [
            {"kind": "custom", "item_id": None, "quantity": 1, "description": "First drawing"},
            {"kind": "custom", "item_id": None, "quantity": 1, "description": "Second drawing"},
        ],
        {"gross": 0, "currency": "EUR", "confirmation": True},
        "two-custom-lines",
        "web",
        "customer request",
        now=NOW,
    )
    with pytest.raises(ValueError, match="every unresolved"):
        review_order(
            store, order["id"], replacement("First drawing"), "owner", "review", "incomplete-review", now=NOW
        )
    complete = replacement("First drawing") + [
        {
            "line_index": 1,
            "requests": [{"code": "A", "rows": [{"x": 6000, "n": 1}]}],
            "operation": {"id": "cut", "description": "Second drawing"},
        }
    ]
    first = review_order(store, order["id"], complete, "owner", "review", "complete-review", now=NOW)
    replay = review_order(store, order["id"], complete, "owner", "review", "complete-review", now=NOW)
    assert replay == first
    assert store.one("SELECT COUNT(*) n FROM order_events WHERE event='quote_reviewed'")["n"] == 1


def test_delivery_only_review_keeps_firm_total_without_price_assent(store):
    order = store.submit_order(
        {"name": "Buyer", "email": "buyer@example.test"},
        [{"item_id": "A", "quantity": 1, "cuts": 0}],
        {"gross": 20, "currency": "EUR", "confirmation": False, "fulfilment": "delivery"},
        "delivery-review",
        "web",
        "server quote",
        now=NOW,
    )
    result = review_order(
        store,
        order["id"],
        [],
        "owner",
        "confirmed delivery record",
        "delivery-only-review",
        now=NOW,
    )
    assert result["assent_required"] is False
    reviewed = store.read_order(order["id"])
    assert reviewed["quote"]["gross"] == 20
    assert reviewed["quote"]["review"]["state"] == "not_required"
    assert commercially_resolved(store, reviewed)

    store.confirm_delivery(
        order["id"],
        "2026-10-16T09:00:00+03:00",
        "2026-10-16T12:00:00+03:00",
        "Delivered to the recorded address",
        "owner",
        "carrier booking",
        "confirm-delivery",
        included=True,
    )
    confirmed = store.read_order(order["id"])
    assert confirmed["quote"]["review"]["state"] == "not_required"
    assert confirmed["quote"]["confirmation"] is False
    store.record_stock("A", 10, "owner", "physical count", status="confirmed")
    accepted = store.accept_order(order["id"], "owner", "delivery confirmed", "accept-reviewed", now=NOW)
    assert accepted["state"] == "accepted"


def test_custom_order_end_to_end_uses_same_bg_customer_link_and_exact_payable_revisions(store):
    make_held_item(store)
    confirm_prices(store, "end-to-end")
    owner = {"store": store, "role": "owner", "actor": "owner", "evidence": "reviewed records"}
    tools.call(
        owner,
        "orders_confirm_operation_capacity",
        {
            "operation_id": "cut",
            "resource_id": "workshop",
            "setup_minutes": 6,
            "minutes_per_unit": 2,
            "minutes_per_day": 480,
            "idempotency_key": "end-to-end-capacity",
        },
    )
    store.record_stock("A", 5, "owner", "physical count", status="confirmed")
    order = store.submit_order(
        {"name": "Купувач", "email": "buyer@example.test", "language": "bg"},
        [{"kind": "custom", "item_id": None, "quantity": 1, "description": "Рязане по чертеж"}],
        {"gross": 0, "currency": "EUR", "confirmation": True, "fulfilment": "delivery"},
        "end-to-end-order",
        "public-order-page",
        "company order form",
        now=NOW,
    )
    mail = CustomerMail(store)
    receipt = mail.queue(order["id"])
    link = mail.link(order["id"])
    token = link.rsplit(".", 1)[1]

    reviewed = tools.call(
        owner,
        "orders_review_quote",
        {
            "order_id": order["id"],
            "replacements": replacement("Рязане по чертеж"),
            "now": NOW,
            "idempotency_key": "end-to-end-review",
        },
    )
    assert reviewed["assent_required"] is True
    mail.change(
        order["id"], token, "assent", "", "customer-assent-price-01", reviewed["review_id"]
    )

    delivery = tools.call(
        owner,
        "orders_confirm_delivery",
        {
            "order_id": order["id"],
            "earliest": "2030-10-14T10:00:00+03:00",
            "latest": "2030-10-14T12:00:00+03:00",
            "terms": "Доставка до записания адрес.",
            "fee": 24,
            "currency": "EUR",
            "vat_rate": 0.2,
            "idempotency_key": "end-to-end-delivery",
        },
    )
    assert delivery["commercial_change"] is True
    current = mail.projection(order["id"], token)
    assert current["quote"]["breakdown"]["delivery"] == {
        "net": 20,
        "vat": 4,
        "gross": 24,
        "vat_rate": 0.2,
        "currency": "EUR",
    }
    second_review = current["quote"]["review"]["id"]
    with pytest.raises(ValueError, match="current reviewed quote"):
        mail.change(
            order["id"], token, "assent", "", "customer-stale-assent-01", reviewed["review_id"]
        )
    mail.change(order["id"], token, "assent", "", "customer-assent-fee-001", second_review)

    accepted = tools.call(
        owner,
        "orders_accept",
        {"order_id": order["id"], "now": NOW, "idempotency_key": "end-to-end-accept"},
    )
    assert accepted["state"] == "accepted"
    payable = store.read_order(order["id"])["quote"]
    tools.call(
        owner,
        "orders_record_invoice",
        {
            "order_id": order["id"],
            "invoice_number": "MM-2026-200",
            "issued_at": "2026-10-12T12:00:00+03:00",
            "currency": payable["currency"],
            "amount": payable["gross"],
            "document_url": "https://invoices.example.test/MM-2026-200.pdf",
            "idempotency_key": "end-to-end-invoice",
        },
    )
    mail.sync_events()

    final = mail.projection(order["id"], token)
    assert final["state"] == "accepted" and final["invoice"]["amount"] == payable["gross"]
    assert store.one("SELECT COUNT(*) n FROM customer_links WHERE order_id=?", (order["id"],))["n"] == 1
    assert mail.link(order["id"]) == link
    kinds = {row["kind"] for row in store.rows("SELECT kind FROM mail_outbox WHERE order_id=?", (order["id"],))}
    assert {"received", "reviewed", "delivery", "accepted", "invoice"}.issubset(kinds)
    assert store.one("SELECT language FROM mail_threads WHERE order_id=?", (order["id"],))["language"] == "bg"
    for queued in store.rows("SELECT id FROM mail_outbox WHERE order_id=?", (order["id"],)):
        rendered = CustomerMail(store).render(queued["id"])
        assert 'lang="bg"' in rendered["html"]
        assert "Поръчка" in rendered["subject"]
    assert receipt["event_key"] == order["id"] + ":received"
