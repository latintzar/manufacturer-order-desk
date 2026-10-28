"""Exact-snapshot staff commitment without stock/capacity/provider effects."""

from __future__ import annotations

import copy
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "verticals/manufacturer"))
from manufacturer_conversations import ManufacturerConversations
from manufacturer_fulfillment import ManufacturerFulfillment
from manufacturer_store import Conflict, Invalid, Missing


def current():
    return True


def order():
    return {
        "id": "order-1",
        "customer_id": "buyer",
        "status": "requested",
        "number": "#1001",
        "currency": "EUR",
        "lines": [{"code": "101037", "quantity": 12, "unit_price": 10, "total": 120}],
        "total": 120,
    }


@pytest.fixture
def workflow(tmp_path):
    store = ManufacturerConversations(tmp_path, "company-a")
    store.ensure_customer("buyer", contacts=[{"email": "buyer@example.test"}], actor="peter", current=current)
    store.record_source_order("buyer", order(), actor="peter", current=current)
    return ManufacturerFulfillment(store)


def change(workflow, status, *, key=None, **overrides):
    before = workflow.read("buyer", "order-1")
    value = {
        "status": status,
        "version_id": before["current_version_id"],
        "expected_revision": before["revision"],
        "actor": "peter",
        "evidence": {"method": "staff_action"},
        "idempotency_key": key or status,
        "current": current,
    }
    value.update(overrides)
    return workflow.transition("buyer", "order-1", **value)


def propose(workflow, *, key="proposal", quantity=12):
    store = workflow.conversations
    review = store.order_review("buyer", "order-1")
    snapshot = copy.deepcopy(order())
    snapshot["lines"][0]["quantity"] = quantity
    return store.propose_request(
        "buyer",
        "order-1",
        proposal=snapshot,
        recipient="buyer@example.test",
        actor="peter",
        expected_revision=review["revision"],
        idempotency_key=key,
        current=current,
    )["proposal"]


def confirm(workflow, proposal):
    workflow.conversations.confirm_proposal(
        "buyer",
        "order-1",
        version_id=proposal["id"],
        customer_actor="customer",
        evidence={"method": "review_link"},
        current=current,
    )


def test_original_source_can_be_accepted_then_prepared_and_dispatched(workflow, tmp_path):
    original = workflow.conversations.order_review("buyer", "order-1")
    first = workflow.read("buyer", "order-1")
    assert first["allowed_actions"] == ["accepted"] and first["revision"] == 0
    assert first["current_version_id"] == "source:" + original["source_sha256"]
    accepted = change(workflow, "accepted")
    assert accepted["basis"] == "staff_reported" and accepted["allowed_actions"] == ["preparing"]
    preparing = change(workflow, "preparing")
    assert preparing["allowed_actions"] == ["dispatched"]
    dispatched = change(
        workflow, "dispatched", evidence={"method": "staff_action", "note": "Предадена на куриер."}
    )
    assert dispatched["allowed_actions"] == [] and dispatched["revision"] == 3
    assert [event["status"] for event in dispatched["events"]] == ["accepted", "preparing", "dispatched"]
    assert all(event["document_sha256"] == original["source_sha256"] for event in dispatched["events"])
    assert workflow.conversations.order_review("buyer", "order-1") == original
    assert workflow.conversations.pending_deliveries() == []
    restored = ManufacturerFulfillment(ManufacturerConversations(tmp_path, "company-a"))
    assert restored.read("buyer", "order-1") == dispatched
    messages = workflow.conversations.conversation("buyer")["messages"]
    assert [message["data"]["status"] for message in messages if message["kind"] == "fulfillment_update"] == [
        "accepted",
        "preparing",
        "dispatched",
    ]


def test_review_pending_and_changes_requested_require_customer_confirmation(workflow):
    proposal = propose(workflow)
    assert workflow.read("buyer", "order-1")["allowed_actions"] == []
    with pytest.raises(Conflict):
        change(workflow, "accepted")
    confirm(workflow, proposal)
    result = change(workflow, "accepted")
    assert result["version_id"] == proposal["id"] and result["document_sha256"] == proposal["sha256"]
    workflow.conversations.request_customer_change(
        "buyer",
        "order-1",
        version_id=proposal["id"],
        text="15 броя.",
        customer_actor="customer",
        evidence={"method": "review_link"},
        idempotency_key="change",
        current=current,
    )
    assert workflow.read("buyer", "order-1")["allowed_actions"] == []
    with pytest.raises(Conflict):
        change(workflow, "preparing")


def test_stale_source_and_proposal_bindings_block_advance_and_require_reacceptance(workflow):
    original = workflow.read("buyer", "order-1")
    change(workflow, "accepted")
    updated = order()
    updated["lines"][0]["quantity"] = 15
    workflow.conversations.record_source_order("buyer", updated, actor="peter", current=current)
    progress = workflow.read("buyer", "order-1")
    assert progress["version_id"] != progress["current_version_id"] and progress["allowed_actions"] == [
        "accepted"
    ]
    with pytest.raises(Conflict):
        change(workflow, "preparing", version_id=original["current_version_id"])
    change(workflow, "accepted", key="accept-updated")
    proposal = propose(workflow)
    confirm(workflow, proposal)
    assert workflow.read("buyer", "order-1")["allowed_actions"] == ["accepted"]
    change(workflow, "accepted", key="accept-proposal")
    change(workflow, "preparing")


def test_skip_reverse_and_terminal_actions_are_blocked(workflow):
    with pytest.raises(Conflict):
        change(workflow, "preparing")
    with pytest.raises(Conflict):
        change(workflow, "dispatched")
    change(workflow, "accepted")
    with pytest.raises(Conflict):
        change(workflow, "accepted", key="again")
    change(workflow, "preparing")
    change(workflow, "dispatched")
    with pytest.raises(Conflict):
        change(workflow, "accepted", key="after-dispatch")
    with pytest.raises(Invalid):
        change(workflow, "completed")


def test_source_cancellation_blocks_and_is_kept_separate(workflow):
    change(workflow, "accepted")
    cancelled = order()
    cancelled["status"] = "cancelled"
    workflow.conversations.record_source_order("buyer", cancelled, actor="peter", current=current)
    progress = workflow.read("buyer", "order-1")
    assert progress["source_status"] == "cancelled" and progress["status"] == "accepted"
    assert progress["allowed_actions"] == []
    with pytest.raises(Conflict):
        change(workflow, "preparing")


def test_idempotency_cas_and_withdrawn_authority(workflow):
    first = workflow.read("buyer", "order-1")
    payload = {"version_id": first["current_version_id"], "expected_revision": 0, "key": "same"}
    accepted = change(workflow, "accepted", **payload)
    assert change(workflow, "accepted", **payload) == accepted
    with pytest.raises(Conflict):
        change(workflow, "preparing", **payload)
    with pytest.raises(Conflict):
        change(workflow, "preparing", expected_revision=0)
    with pytest.raises(Invalid):
        change(workflow, "preparing", current=lambda: False)
    calls = []

    def revoked_at_commit():
        calls.append(True)
        return len(calls) == 1

    with pytest.raises(Invalid):
        change(workflow, "preparing", current=revoked_at_commit)
    assert workflow.read("buyer", "order-1") == accepted
    with pytest.raises(Invalid):
        change(workflow, "preparing", evidence={"method": "email_classification"})


def test_concurrent_actions_one_revision_wins(workflow):
    before = workflow.read("buyer", "order-1")

    def run(key):
        try:
            return change(
                workflow, "accepted", key=key, expected_revision=0, version_id=before["current_version_id"]
            )
        except Conflict:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, ["first", "second"]))
    assert sum(result is not None for result in results) == 1
    assert len(workflow.read("buyer", "order-1")["events"]) == 1
    with pytest.raises(Missing):
        workflow.read("other-customer", "order-1")
