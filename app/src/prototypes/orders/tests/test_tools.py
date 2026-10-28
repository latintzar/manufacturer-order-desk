import json

import pytest
from test_store import store as store
from test_store import submit

import tools


def context(store, role="operator"):
    return {"store": store, "role": role, "actor": "test", "evidence": "fixture"}


def test_registry_and_schema_validation(store):
    assert set(tools.READ_NAMES).isdisjoint(tools.WRITE_NAMES)
    assert all(s["type"] == "function" for s in tools.openai_specs(True))
    with pytest.raises(ValueError, match="unexpected"):
        tools.read(context(store), "catalog_read", {"item_id": "A", "surprise": True})
    with pytest.raises(ValueError, match="required"):
        tools.call(context(store), "catalog_set_price", {"item_id": "A", "amount": 5})


def test_private_order_read_and_owner_acceptance(store):
    order = submit(store)
    with pytest.raises(PermissionError):
        tools.read(context(store, "public"), "orders_read", {"order_id": order["id"]})
    with pytest.raises(PermissionError):
        tools.call(context(store), "orders_accept", {"order_id": order["id"], "idempotency_key": "accept"})
    with pytest.raises(PermissionError):
        tools.call(
            context(store, "public"),
            "orders_submit",
            {"customer": {}, "lines": [], "quote": {}, "idempotency_key": "x"},
        )
    assert tools.read(context(store), "orders_read", {"order_id": order["id"]})["customer"]["name"] == "Buyer"


def test_invoice_tool_requires_an_operator_and_records_an_issued_document(store):
    order = submit(store)
    store.record_stock("A", 10, "owner", "counted")
    store.accept_order(order["id"], "owner", "accepted", "accept-invoice")
    args = {
        "order_id": order["id"], "invoice_number": "MM-2026-14", "issued_at": "2026-10-12T09:00:00+03:00",
        "currency": "EUR", "amount": 20, "document_url": "https://invoices.example.test/MM-2026-14.pdf",
        "idempotency_key": "issued-invoice",
    }
    with pytest.raises(PermissionError):
        tools.call(context(store, "public"), "orders_record_invoice", args)
    recorded = tools.call(context(store), "orders_record_invoice", args)
    assert recorded["number"] == "MM-2026-14" and recorded["document_url"].startswith("https://")
    assert tools.read(context(store), "orders_read", {"order_id": order["id"]})["invoice"]["actor"] == "test"


def test_delivery_confirmation_tool_requires_a_trusted_operator(store):
    order = store.submit_order(
        {"name": "Buyer", "email": "buyer@example.test"}, [{"item_id": "A", "quantity": 1}],
        {"gross": 20, "currency": "EUR", "fulfilment": "delivery"}, "delivery-tool", "web", "quote",
    )
    args = {
        "order_id": order["id"], "earliest": "2030-10-14T10:00:00+03:00",
        "latest": "2030-10-14T12:00:00+03:00", "terms": "Carrier delivery to the recorded address.",
        "included": True, "idempotency_key": "delivery-tool-1",
    }
    with pytest.raises(PermissionError):
        tools.call(context(store, "public"), "orders_confirm_delivery", args)
    confirmed = tools.call(context(store, "operator"), "orders_confirm_delivery", args)
    assert confirmed["delivery"]["arrival"]["timezone"] == "Europe/Sofia"


def test_public_company_planning_is_private_and_claim_stays_public(store):
    with pytest.raises(PermissionError):
        tools.read(context(store, "public"), "catalog_read", {"item_id": "A"})
    assert (
        tools.call(
            context(store, "public"),
            "claim_request",
            {"email": "owner@example.test", "name": "Owner", "idempotency_key": "claim"},
        )["status"]
        == "pending"
    )
    assert store.rows("SELECT * FROM members") == []


def test_catalogue_read_explains_price_basis_currency_and_measurement_units(store):
    company = store.one("SELECT config FROM company")
    config = json.loads(company["config"])
    config["currency"] = "EUR"
    store.db.execute("UPDATE company SET config=?", (json.dumps(config),))
    item = json.loads(store.one("SELECT data FROM items WHERE id='A'")["data"])
    item["d"] = [40, 40, 4]
    store.db.execute("UPDATE items SET data=? WHERE id='A'", (json.dumps(item),))

    result = tools.read(context(store), "catalog_read", {"item_id": "A"})

    assert result["measurements"] == {"dimensions_unit": "mm", "stock_length_unit": "m"}
    assert result["price"] == {
        "amount": 12.345,
        "currency": "EUR",
        "basis": "stock_length",
        "status": "current",
        "basis_quantity": 6,
        "basis_unit": "m",
    }
    assert result["cutting_price"] == {"amount": 0.42, "currency": "EUR", "basis": "cut"}


def test_real_gates_and_run_record(store):
    result = tools.call(
        context(store),
        "run_gate",
        {"gate": "catalog_counts", "expected": {"types": 1, "items": 1}, "idempotency_key": "gate"},
    )
    assert result["passed"]
    result = tools.call(
        context(store),
        "run_gate",
        {"gate": "stock_truth", "expected": {"invalid": 0}, "idempotency_key": "stock-gate"},
    )
    assert result["passed"]
    tools.call(
        context(store),
        "run_start_stage",
        {"data": {"stage": "read", "model": "test", "api_calls": None}, "idempotency_key": "start"},
    )
    assert len(tools.read(context(store), "run_read", {"table": "stage_runs"})) == 3


def test_claim_verification_is_privileged_and_separate(store):
    claim = tools.call(
        context(store, "public"),
        "claim_request",
        {"email": "owner@example.test", "name": "Owner", "idempotency_key": "claim"},
    )
    args = {"claim_id": claim["id"], "role": "owner", "verified": True, "idempotency_key": "grant"}
    for role in ["public", "operator", "owner"]:
        with pytest.raises(PermissionError):
            tools.call(context(store, role), "claim_grant", args)
    result = tools.call(context(store, "admin"), "claim_grant", args)
    assert result["role"] == "owner"
    assert store.one("SELECT role FROM members")["role"] == "owner"


def test_operator_catalogue_retains_stock_evidence(store):
    store.record_stock("A", 3, "private-person", "private customer email")
    result = tools.read(context(store, "operator"), "catalog_read", {"item_id": "A"})
    assert result["stock"]["actor"] == "private-person"
    assert result["stock"]["evidence"] == "private customer email"
    found = tools.read(context(store, "operator"), "catalog_find", {"query": "A"})
    assert found[0]["stock"]["evidence"] == "private customer email"


def test_stage_plan_is_scoped_read_only_and_loads_one_stage(store):
    before = store.db.total_changes
    index = tools.read(context(store), "run_stage_plan", {})
    assert [s["id"] for s in index["stages"]][:2] == ["discover", "catalogue"]
    assert all("goal" not in s for s in index["stages"])
    stage = tools.read(context(store), "run_stage_plan", {"stage": "pictures"})
    assert stage["stage"]["id"] == "pictures"
    assert "one angled product image" in stage["stage"]["goal"]
    assert stage["model_profile"]["session_model"] == "gpt-5.6-terra"
    assert stage["model_selection"] == "planning_only"
    assert store.db.total_changes == before
    with pytest.raises(ValueError, match="Unknown manufacturer stage"):
        tools.read(context(store), "run_stage_plan", {"stage": "../../secret"})
    with pytest.raises(PermissionError):
        tools.read(context(store, "public"), "run_stage_plan", {})
    with pytest.raises(ValueError, match="unexpected"):
        tools.read(context(store), "run_stage_plan", {"path": "/tmp/other"})
