"""Physical observations remain true when accepted reservations exceed counted stock."""

import json

import pytest
from supply import quote_ready
from test_store import store as store
from test_store import submit


def accept(store, key="first", quantity=2):
    order = submit(store, key, quantity)
    store.accept_order(order["id"], "owner", "accepted", "accept-" + key, now="2026-10-12T09:00:00+03:00")
    return order["id"]


def test_lower_actual_count_is_saved_and_all_affected_orders_are_flagged(store):
    store.record_stock("A", 10, "owner", "initial count")
    ids = [accept(store, "first"), accept(store, "second")]
    promises = {oid: store.read_order(oid)["estimates"] for oid in ids}
    capacity = store.rows("SELECT * FROM capacity_load")
    observed = store.record_stock("A", 1, "owner", "physical recount", idempotency_key="recount")
    assert observed["quantity"] == 1 and observed["reserved"] == 4
    assert quote_ready(store, [{"item_id": "A", "quantity": 1}])["stock"][0]["available"] == 0
    assert store.supply_projection()["items"]["A"]["quantity"] == 1
    question = json.loads(store.one("SELECT data FROM questions ORDER BY id DESC")["data"])
    assert question["kind"] == "stock_shortage"
    assert set(question["order_ids"]) == set(ids)
    assert question["observed_quantity"] == 1 and question["reserved_quantity"] == 4
    assert question["shortage_quantity"] == 3
    for oid in ids:
        assert store.read_order(oid)["state"] == "accepted"
        assert store.read_order(oid)["estimates"] == promises[oid]
        assert (
            store.one(
                "SELECT COUNT(*) n FROM order_events WHERE order_id=? AND event='stock_shortage'", (oid,)
            )["n"]
            == 1
        )
    assert store.rows("SELECT * FROM capacity_load") == capacity
    store.record_stock("A", 1, "owner", "physical recount", idempotency_key="recount")
    assert store.one("SELECT COUNT(*) n FROM questions")["n"] == 1


def test_recount_blocks_new_acceptance_against_stale_available_stock(store):
    store.record_stock("A", 10, "owner", "initial count")
    accept(store)
    store.record_stock("A", 1, "owner", "physical recount")
    pending = submit(store, "new", 1)
    before = store.rows("SELECT * FROM capacity_load")
    with pytest.raises(ValueError, match="sufficient confirmed stock"):
        store.accept_order(pending["id"], "owner", "new request", "accept-new")
    assert store.read_order(pending["id"])["state"] == "requested"
    assert store.item("A")["stock"]["reserved"] == 2
    assert store.rows("SELECT * FROM capacity_load") == before


@pytest.mark.parametrize(("state", "quantity"), [("known", 1), ("out", 0), ("unknown", None)])
def test_completion_rolls_back_on_physical_shortage_or_unknown_count(store, state, quantity):
    store.record_stock("A", 10, "owner", "initial count")
    oid = accept(store)
    store.mark_order(oid, "in_progress", "owner", "started")
    store.mark_order(oid, "ready", "owner", "cut and bundled")
    store.record_stock("A", quantity, "owner", "physical recount", state=state)
    before = {
        table: store.rows(f"SELECT * FROM {table}")
        for table in (
            "orders",
            "stock",
            "stock_events",
            "order_events",
            "capacity_load",
            "audit",
            "idempotency",
        )
    }
    with pytest.raises(ValueError, match="sufficient confirmed physical stock"):
        store.mark_order(oid, "completed", "owner", "collection", "complete")
    for table, rows in before.items():
        assert store.rows(f"SELECT * FROM {table}") == rows
    store.record_stock("A", 2, "owner", "reconciled bundle count")
    assert store.mark_order(oid, "completed", "owner", "collection", "complete")["state"] == "completed"
    assert store.item("A")["stock"]["quantity"] == 0
    assert store.item("A")["stock"]["reserved"] == 0


@pytest.mark.parametrize(("state", "quantity"), [("known", 1), ("unknown", None)])
def test_cancellation_releases_reservations_after_shortage_or_unknown_count(store, state, quantity):
    store.record_stock("A", 10, "owner", "initial count")
    oid = accept(store)
    store.record_stock("A", quantity, "owner", "physical recount", state=state)
    store.mark_order(oid, "cancelled", "owner", "customer cancelled")
    assert store.item("A")["stock"]["quantity"] == quantity
    assert store.item("A")["stock"]["reserved"] == 0
    assert store.one("SELECT SUM(minutes) n FROM capacity_load")["n"] == 0


def test_completion_checks_total_demand_across_repeated_item_lines(store):
    store.record_stock("A", 10, "owner", "initial count")
    order = store.submit_order(
        {"name": "Buyer", "email": "buyer@example.test"},
        [{"item_id": "A", "quantity": 2}, {"item_id": "A", "quantity": 2}],
        {"gross": 50},
        "repeat-item",
        "web",
        "server quote",
    )
    oid = order["id"]
    store.accept_order(oid, "owner", "accepted", "accept-repeated")
    store.mark_order(oid, "in_progress", "owner", "started")
    store.mark_order(oid, "ready", "owner", "bundled")
    store.record_stock("A", 3, "owner", "recount")
    with pytest.raises(ValueError, match="sufficient confirmed physical stock"):
        store.mark_order(oid, "completed", "owner", "collection")
    assert store.item("A")["stock"]["quantity"] == 3
    assert store.item("A")["stock"]["reserved"] == 4
