"""Human correspondence, exact customer review and pending transport effects."""

from __future__ import annotations

import copy
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "verticals/manufacturer"))
from manufacturer_conversations import ManufacturerConversations
from manufacturer_store import Conflict, Invalid, Missing


def CURRENT():
    return True


def customer(store, identifier="buyer"):
    return store.ensure_customer(
        identifier,
        contacts=[{"email": "buyer@example.test", "name": "Buyer"}],
        actor="peter",
        current=CURRENT,
    )


def order(identifier="order-1", customer_id="buyer", status="requested"):
    return {
        "id": identifier,
        "customer_id": customer_id,
        "number": "#1001",
        "status": status,
        "currency": "EUR",
        "lines": [{"code": "101037", "name": "Handle", "quantity": 2, "unit": "pc"}],
    }


def proposal(store, *, expected_revision=0, key="proposal-1", quantity=3):
    document = order()
    document["lines"][0]["quantity"] = quantity
    return store.propose_request(
        "buyer",
        "order-1",
        proposal=document,
        recipient="buyer@example.test",
        actor="peter",
        expected_revision=expected_revision,
        idempotency_key=key,
        current=CURRENT,
    )


@pytest.fixture
def store(tmp_path):
    value = ManufacturerConversations(tmp_path, "company-a")
    customer(value)
    value.record_source_order("buyer", order(), actor="peter", current=CURRENT)
    return value


def test_tenant_binding_and_customer_conversation_identity(tmp_path):
    store = ManufacturerConversations(tmp_path, "company-a")
    first = customer(store)
    assert customer(store)["id"] == first["id"]
    assert ManufacturerConversations(tmp_path, "company-a").conversation("buyer")["id"] == first["id"]
    with pytest.raises(Invalid):
        ManufacturerConversations(tmp_path, "company-b")
    other = ManufacturerConversations(tmp_path / "other", "company-b")
    assert customer(other)["id"] != first["id"]
    with pytest.raises(Missing):
        store.conversation("unknown")


def test_human_message_is_pending_email_not_agent_execution(store):
    result = store.send_message(
        "buyer",
        text="Please check the finish.",
        recipient="buyer@example.test",
        actor="peter",
        idempotency_key="message-1",
        current=CURRENT,
    )
    assert result["message"]["kind"] == "human_message"
    assert result["message"]["author_type"] == "staff"
    assert result["delivery"]["status"] == "pending"
    assert result["delivery"]["provider_message_id"] is None
    assert result["delivery"]["recipient"] == "buyer@example.test"
    assert store.pending_deliveries()[0]["id"] == result["delivery"]["id"]
    assert "agent" not in result
    again = store.send_message(
        "buyer",
        text="Please check the finish.",
        recipient="buyer@example.test",
        actor="peter",
        idempotency_key="message-1",
        current=CURRENT,
    )
    assert again == result
    with pytest.raises(Conflict):
        store.send_message(
            "buyer",
            text="Different",
            recipient="buyer@example.test",
            actor="peter",
            idempotency_key="message-1",
            current=CURRENT,
        )


def test_recipient_and_current_authority_are_checked_before_commit(store):
    with pytest.raises(Invalid):
        store.send_message(
            "buyer",
            text="Hi",
            recipient="outsider@example.test",
            actor="peter",
            idempotency_key="bad-address",
            current=CURRENT,
        )
    with pytest.raises(Invalid):
        store.ensure_customer(
            "bad", contacts=["buyer@example.test\nBcc: other@example.test"], actor="peter", current=CURRENT
        )
    with pytest.raises(Invalid):
        store.send_message(
            "buyer",
            text="Hi",
            recipient="buyer@example.test",
            actor="peter",
            idempotency_key="revoked",
            current=lambda: False,
        )
    assert store.pending_deliveries() == []


def test_source_order_cards_are_immutable_idempotent_and_bound(store):
    original = order()
    source_before = copy.deepcopy(original)
    store.record_source_order("buyer", original, actor="peter", current=CURRENT)
    assert original == source_before
    assert len(store.conversation("buyer")["messages"]) == 1
    customer(store, "other")
    with pytest.raises(Conflict):
        store.record_source_order("other", order(customer_id="other"), actor="peter", current=CURRENT)
    updated = order(status="accepted")
    store.record_source_order("buyer", updated, actor="peter", current=CURRENT)
    thread = store.conversation("buyer")
    assert len(thread["messages"]) == 2
    assert thread["messages"][0]["data"]["order"]["status"] == "requested"
    assert thread["orders"][0]["source_status"] == "accepted"
    assert thread["orders"][0]["review_status"] == "requested"
    assert thread["orders"][0]["status"] == "accepted"


def test_exact_proposal_confirmation_keeps_source_status_and_full_snapshot(store, tmp_path):
    original = order()
    first = proposal(store)
    assert first["review"]["review_status"] == "review_pending"
    version = first["proposal"]
    assert version["version"] == 1 and len(version["sha256"]) == 64
    assert store.proposal("buyer", "order-1", version["id"])["document"]["lines"][0]["quantity"] == 3
    confirmed = store.confirm_proposal(
        "buyer",
        "order-1",
        version_id=version["id"],
        customer_actor="buyer-token",
        evidence={"method": "review_link", "event_id": "accept-1"},
        current=CURRENT,
    )
    assert confirmed["review_status"] == "customer_confirmed"
    assert confirmed["source_status"] == "requested"
    assert confirmed["source"]["lines"] == original["lines"]
    assert confirmed["confirmed_version_id"] == version["id"]
    assert ManufacturerConversations(tmp_path, "company-a").order_review("buyer", "order-1") == confirmed
    assert (
        store.confirm_proposal(
            "buyer",
            "order-1",
            version_id=version["id"],
            customer_actor="buyer-token",
            evidence={"method": "review_link", "event_id": "accept-1"},
            current=CURRENT,
        )
        == confirmed
    )


def test_stale_confirmation_and_change_requests_preserve_previous_confirmation(store):
    first = proposal(store)["proposal"]
    confirmed = store.confirm_proposal(
        "buyer",
        "order-1",
        version_id=first["id"],
        customer_actor="buyer",
        evidence={"method": "review_link"},
        current=CURRENT,
    )
    second = proposal(store, expected_revision=confirmed["revision"], key="proposal-2", quantity=4)[
        "proposal"
    ]
    with pytest.raises(Conflict):
        store.confirm_proposal(
            "buyer",
            "order-1",
            version_id=first["id"],
            customer_actor="buyer",
            evidence={"method": "review_link"},
            current=CURRENT,
        )
    changed = store.request_customer_change(
        "buyer",
        "order-1",
        version_id=second["id"],
        text="Use satin.",
        patch={"finish": "satin"},
        customer_actor="buyer",
        evidence={"method": "review_link"},
        idempotency_key="change-1",
        current=CURRENT,
    )
    assert changed["review_status"] == "changes_requested"
    assert changed["confirmed_version_id"] == first["id"]
    assert store.proposal("buyer", "order-1", second["id"])["document"]["lines"][0]["quantity"] == 4
    with pytest.raises(Conflict):
        store.confirm_proposal(
            "buyer",
            "order-1",
            version_id=second["id"],
            customer_actor="buyer",
            evidence={"method": "review_link"},
            current=CURRENT,
        )


def test_review_revision_compare_and_swap_is_atomic(store):
    def create(index):
        try:
            return proposal(store, key=f"parallel-{index}", quantity=3 + index)
        except Conflict:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        values = list(pool.map(create, [0, 1]))
    assert sum(value is not None for value in values) == 1
    assert len(store.pending_deliveries()) == 1


def test_human_service_is_separate_and_sends_no_default_email(store):
    service = store.ensure_service(actor="peter", current=CURRENT)
    assert service["id"] != store.conversation("buyer")["id"]
    store.send_service_message(
        text="Please adjust our setup.",
        actor="client-operator",
        side="client",
        idempotency_key="support-1",
        current=CURRENT,
    )
    store.send_service_message(
        text="I will review the setup.",
        actor="peter",
        side="provider",
        idempotency_key="support-2",
        current=CURRENT,
    )
    messages = store.service_conversation()["messages"]
    assert [message["author_type"] for message in messages] == ["client", "provider"]
    assert all(message["kind"] == "human_message" for message in messages)
    assert store.pending_deliveries() == []
    assert len(store.conversation("buyer")["messages"]) == 1


def test_email_classification_records_evidence_without_confirming_or_sending(store):
    version = proposal(store)["proposal"]
    received = store.record_customer_message(
        "buyer",
        text="Looks good, perhaps satin instead.",
        sender="buyer@example.test",
        provider="resend",
        provider_event_id="incoming-1",
        provenance={"signature_verified": True, "email_id": "email-1"},
        current=CURRENT,
    )
    result = store.record_email_intent(
        "buyer",
        message_id=received["id"],
        intent="confirmation",
        confidence=0.7,
        ambiguous=True,
        evidence={"classifier": "review-helper", "text": "perhaps satin instead"},
        actor="research-helper",
        idempotency_key="classification-1",
        current=CURRENT,
    )
    assert result["data"]["ambiguous"] is True and result["data"]["authority"] == "suggestion"
    assert store.order_review("buyer", "order-1")["review_status"] == "review_pending"
    assert store.order_review("buyer", "order-1")["current_version_id"] == version["id"]
    assert len(store.pending_deliveries()) == 1
    assert (
        store.record_customer_message(
            "buyer",
            text="Looks good, perhaps satin instead.",
            sender="buyer@example.test",
            provider="resend",
            provider_event_id="incoming-1",
            provenance={"signature_verified": True, "email_id": "email-1"},
            current=CURRENT,
        )["id"]
        == received["id"]
    )


def test_history_pagination_has_no_gaps_and_keeps_chronology(store):
    for index in range(5):
        store.send_message(
            "buyer",
            text=f"Message {index}",
            recipient="buyer@example.test",
            actor="peter",
            idempotency_key=f"message-{index}",
            current=CURRENT,
        )
    latest = store.conversation("buyer", limit=2)
    prior = store.conversation("buyer", limit=2, before=latest["next_before"])
    earliest = store.conversation("buyer", limit=2, before=prior["next_before"])
    combined = earliest["messages"] + prior["messages"] + latest["messages"]
    assert len(combined) == len({message["id"] for message in combined}) == 6
    assert [message["sequence"] for message in combined] == sorted(
        message["sequence"] for message in combined
    )
    with pytest.raises(Invalid):
        store.conversation("buyer", limit=1001)


def test_authority_revocation_rolls_back_whole_message_and_intent(store):
    checks = iter([True, False])
    with pytest.raises(Invalid):
        store.send_message(
            "buyer",
            text="Review this.",
            recipient="buyer@example.test",
            actor="peter",
            idempotency_key="revoked-before-commit",
            current=lambda: next(checks),
        )
    with pytest.raises(Invalid):
        store.send_message(
            "buyer",
            text="Review this.",
            recipient="buyer@example.test",
            actor="peter",
            idempotency_key="missing-authority",
            current=None,
        )
    assert store.pending_deliveries() == []
    assert len(store.conversation("buyer")["messages"]) == 1


def test_source_contacts_support_phone_only_and_plus_address_without_granting_extra_recipient(store):
    store.ensure_customer(
        "buyer",
        contacts=[
            {"name": "Phone contact", "phone": "+359 888 123 456", "email": ""},
            {"name": "Buyer", "email": "buyer+orders@example.test", "phone": ""},
        ],
        actor="peter",
        current=CURRENT,
    )
    received = store.record_customer_message(
        "buyer",
        text="Thanks",
        sender="buyer+orders@example.test",
        provider="resend",
        provider_event_id="plus-address",
        provenance={"signature_verified": True},
        current=CURRENT,
    )
    assert received["author_id"] == "buyer+orders@example.test"
    with pytest.raises(Invalid):
        store.send_message(
            "buyer",
            text="Hi",
            recipient="buyer@example.test",
            actor="peter",
            idempotency_key="old-contact",
            current=CURRENT,
        )


def test_research_refresh_does_not_create_duplicate_order_cards(store):
    snapshot = order()
    snapshot["enrichment"] = {"status": "researching", "updated_at": "2026-10-16T10:00:00Z"}
    store.record_source_order("buyer", snapshot, actor="peter", current=CURRENT)
    assert len(store.conversation("buyer")["messages"]) == 1
    snapshot["enrichment"] = {"status": "enriched", "updated_at": "2026-10-16T10:01:00Z"}
    store.record_source_order("buyer", snapshot, actor="peter", current=CURRENT)
    assert len(store.conversation("buyer")["messages"]) == 1


def test_changes_and_proposals_never_fabricate_source_fulfillment(store):
    store.record_source_order("buyer", order(status="in_progress"), actor="peter", current=CURRENT)
    proposed = proposal(store)
    confirmed = store.confirm_proposal(
        "buyer",
        "order-1",
        version_id=proposed["proposal"]["id"],
        customer_actor="buyer",
        evidence={"method": "review_link"},
        current=CURRENT,
    )
    assert confirmed["source_status"] == "in_progress"
    assert confirmed["fulfillment_status"] == confirmed["status"] == "preparing"
    assert confirmed["review_status"] == "customer_confirmed"


@pytest.mark.parametrize('origin', [{'is_demo': True}, {'customer': {'is_demo': True}}])
def test_original_demo_origin_fences_later_proposals_and_messages(store, origin):
    # The first immutable source event, rather than a new proposal's fields, owns delivery eligibility.
    store.ensure_customer('demo-buyer', contacts=[{'email': 'buyer@example.test'}], actor='peter', current=CURRENT)
    source = {**order('demo-order', 'demo-buyer'), **origin}
    store.record_source_order('demo-buyer', source, actor='peter', current=CURRENT)
    source.pop('is_demo', None)
    source.pop('customer', None)
    store.record_source_order('demo-buyer', source, actor='peter', current=CURRENT)
    for revision in range(2):
        result = store.propose_request('demo-buyer', 'demo-order', proposal={**source, 'is_demo': False},
            recipient='buyer@example.test', actor='peter', expected_revision=revision,
            idempotency_key='demo-review-'+str(revision), current=CURRENT)
        assert result['delivery']['status'] == 'demo'
        assert result['delivery']['provider'] == 'demo-fixture'
        assert result['message']['delivery']['status'] == 'demo'
    message = store.send_message('demo-buyer', text='Demonstration reply', recipient='buyer@example.test',
        actor='peter', idempotency_key='demo-message', current=CURRENT)
    assert message['delivery']['status'] == 'demo'
    assert store.pending_deliveries() == []
    real = store.propose_request('buyer', 'order-1', proposal={**order(), 'is_demo': True},
        recipient='buyer@example.test', actor='peter', expected_revision=0,
        idempotency_key='real-review', current=CURRENT)
    assert real['delivery']['status'] == 'pending'
    assert [row['id'] for row in store.pending_deliveries()] == [real['delivery']['id']]
