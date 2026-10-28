"""Native guests cannot read private catalogue, stock or capacity planning data."""

import pytest
from test_store import store as store

import tools


def context(store, role):
    return {"store": store, "role": role, "actor": "test", "evidence": "fixture"}


@pytest.mark.parametrize(
    ("name", "arguments"),
    [
        ("catalog_find", {"query": "A"}),
        ("catalog_read", {"item_id": "A"}),
        ("stock_read", {}),
        ("quote_ready", {"lines": [{"item_id": "A", "quantity": 1}]}),
    ],
)
def test_public_company_planning_tools_fail_closed(store, name, arguments):
    with pytest.raises(PermissionError, match="role"):
        tools.read(context(store, "public"), name, arguments)


def test_operator_catalogue_supply_and_ready_reads_retain_planning_detail(store):
    store.record_stock("A", 12, "operator", "private count")
    store.capacity_event("workshop", "2026-10-13", 90, "operator", "private schedule")

    operator_item = tools.read(context(store, "operator"), "catalog_read", {"item_id": "A"})
    operator_supply = tools.read(context(store, "operator"), "stock_read", {})
    operator_ready = tools.read(
        context(store, "operator"),
        "quote_ready",
        {"lines": [{"item_id": "A", "quantity": 1}], "now": "2026-10-12T09:00:00+03:00"},
    )

    assert operator_item["stock"]["quantity"] == 12
    assert operator_item["stock"]["evidence"] == "private count"
    assert operator_supply["items"]["A"]["quantity"] == 12
    assert operator_supply["capacity_events"] == [
        {"resource_id": "workshop", "day": "2026-10-13", "minutes": 90.0}
    ]
    assert operator_ready["stock"][0]["available"] == 12
    assert "allocation" in operator_ready and "assumptions" in operator_ready
