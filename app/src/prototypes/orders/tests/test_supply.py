import pytest
from supply import public_ready, quote_ready
from test_store import store as store

LINES = [{"item_id": "A", "quantity": 2, "cuts": 2}]


def test_unknown_stock_moves_window_and_marks_assumptions(store):
    unknown = quote_ready(store, LINES, "2026-10-12T09:00:00+03:00")
    store.record_stock("A", 10, "owner", "counted")
    known = quote_ready(store, LINES, "2026-10-12T09:00:00+03:00")
    assert unknown["earliest"] > known["earliest"]
    assert any(a["kind"] == "stock" for a in unknown["assumptions"])
    assert unknown["kind"] == "estimate"


def test_public_dates_wait_for_confirmed_stock_and_capacity_inputs(store):
    internal = quote_ready(store, LINES, "2026-10-12T09:00:00+03:00")
    assert internal["earliest"] and internal["latest"]
    assert public_ready(internal) == {"kind": "confirmation", "timezone": "Europe/Sofia"}

    store.record_stock("A", 10, "owner", "physical count", status="confirmed")
    store.set_supply_plan(
        "workshop",
        480,
        6,
        2,
        3,
        2,
        "confirmed",
        "owner",
        "measured workshop plan",
        "confirmed-public-ready",
    )
    confirmed = quote_ready(store, LINES, "2026-10-12T09:00:00+03:00")
    assert public_ready(confirmed) == {
        key: confirmed[key] for key in ("kind", "earliest", "latest", "timezone")
    }

    promised = {**internal, "kind": "promise"}
    assert public_ready(promised)["earliest"] == internal["earliest"]


def test_sunday_and_exception(store):
    store.record_stock("A", 10, "owner", "counted")
    store.set_exception("2026-10-12", True, "owner", "closed for maintenance")
    quote = quote_ready(store, LINES, "2026-10-11T09:00:00+03:00")
    assert quote["earliest"].startswith("2026-10-13T08:40:")
    assert all(a["day"] != "2026-10-12" for a in quote["allocation"])


def test_capacity_scarcity_changes_ready_window(store):
    store.record_stock("A", 10, "owner", "counted")
    first = quote_ready(store, LINES, "2026-10-12T09:00:00+03:00")
    store.capacity_event("workshop", "2026-10-12", 540, "owner", "saw down")
    second = quote_ready(store, LINES, "2026-10-12T09:00:00+03:00")
    assert second["earliest"] > first["earliest"]
    assert second["allocation"][0]["day"] == "2026-10-13"


def test_restock_date_and_dst(store):
    store.record_stock("A", 0, "owner", "supplier", state="out", restock_date="2026-10-26")
    quote = quote_ready(store, LINES, "2026-10-23T09:00:00+03:00")
    assert quote["earliest"].startswith("2026-10-26T")
    assert quote["earliest"].endswith("+02:00")


def test_timezone_required(store):
    with pytest.raises(ValueError, match="timezone"):
        quote_ready(store, LINES, "2026-10-12T09:00:00")
