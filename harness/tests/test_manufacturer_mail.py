"""Offline proof of exact customer routing, bounded effects and delivery evidence."""

from __future__ import annotations

import base64
import copy
import hashlib
import hmac
import json
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "verticals/manufacturer"))
from capability_spend import CapabilitySpend
from manufacturer_conversations import ManufacturerConversations
from manufacturer_mail import ManufacturerMail, MailHeld, ResendHTTPProvider, verify_webhook

NOW = 1_800_000_000
SECRET = "whsec_" + base64.b64encode(b"x" * 32).decode()
PROVIDER_ID = "11111111-1111-4111-8111-111111111111"
INBOUND_ID = "22222222-2222-4222-8222-222222222222"


def config():
    return dict(
        schema_version=1,
        environment_id="demo",
        company_id="company-a",
        account_id="resend-a",
        sender_name="Sample Hardware",
        sender_email="orders@service.example.test",
        reply_domain="reply.example.test",
        portal_origin="https://manufacturer.example.test",
        commissioned=True,
        sending_verified=True,
        receiving_verified=True,
        webhook_verified=True,
        evidence_id="commission-1",
        commissioned_until=NOW + 86400 * 30,
        daily_send_limit=20,
        reply_ttl_days=90,
    )


def grant():
    return dict(
        grant_id="email-1",
        channel="email",
        account_id="resend-a",
        expires_at=NOW + 86400,
        stopped=False,
        unit_cost_microusd=1000,
        maximum_request_microusd=1000,
        daily_microusd=20000,
        total_microusd=200000,
    )


def signed(value, event_id="evt-1", now=NOW):
    body = json.dumps(value, separators=(",", ":")).encode()
    headers = {"svix-id": event_id, "svix-timestamp": str(now)}
    signature = hmac.new(b"x" * 32, f"{event_id}.{now}.".encode() + body, hashlib.sha256).digest()
    headers["svix-signature"] = "v1," + base64.b64encode(signature).decode()
    return body, headers


class FakeProvider:
    channel = "email"
    company_id = "company-a"
    account_id = "resend-a"
    webhook_secret = SECRET
    ready = True

    def __init__(self):
        self.sent, self.received = [], []
        self.fail = False
        self.body = {}

    def units(self, prepared):
        return 1

    def send(self, payload, key):
        self.sent.append((copy.deepcopy(payload), key))
        if self.fail:
            raise httpx.ReadTimeout("ambiguous")
        return {
            "id": PROVIDER_ID
            if len(self.sent) == 1 or self.sent[-1][1] == self.sent[0][1]
            else "33333333-3333-4333-8333-333333333333"
        }

    def receive(self, identifier):
        self.received.append(identifier)
        return copy.deepcopy(self.body)


@pytest.fixture
def setup(tmp_path):
    conversations = ManufacturerConversations(tmp_path, "company-a")
    conversations.ensure_customer(
        "buyer", contacts=[{"email": "buyer@example.test"}], actor="peter", current=lambda: True
    )
    cfg, allowance, provider, clock = config(), grant(), FakeProvider(), [NOW]
    mail = ManufacturerMail(
        tmp_path,
        environment_id="demo",
        company_id="company-a",
        conversations=conversations,
        config=lambda: cfg,
        provider=provider,
        spend=CapabilitySpend(tmp_path, "demo", "company-a", reader=lambda: [allowance]),
        current=lambda ctx: True,
        send_admission=lambda ctx: True,
        review_link=lambda ctx: "https://manufacturer.example.test/customer/review#demo.token",
        clock=lambda: clock[0],
    )
    return mail, conversations, provider, cfg, allowance, clock


def intent(store, key="message-1"):
    return store.send_message(
        "buyer",
        text="Здравейте <script>bad()</script>",
        recipient="buyer@example.test",
        actor="peter",
        idempotency_key=key,
        current=lambda: True,
    )["delivery"]


def incoming(provider, alias, *, sender="buyer@example.test", dmarc="pass"):
    provider.body = dict(
        id=INBOUND_ID,
        to=[alias],
        received_for=[alias],
        **{"from": sender},
        text="Потвърждавам тази версия.",
        html=None,
        message_id="<incoming@customer.test>",
        headers={"in-reply-to": "<outgoing@resend.test>"},
        authentication={"dmarc": dmarc, "spf": "pass", "dkim": "pass"},
        attachments=[],
    )
    return dict(
        type="email.received",
        created_at="2027-01-15T08:00:00Z",
        data={"email_id": INBOUND_ID, "to": [alias], "from": sender},
    )


def test_missing_commission_or_money_admits_zero_external_effects(setup):
    mail, store, provider, cfg, allowance, clock = setup
    intent(store)
    cfg["commissioned"] = False
    assert not mail.sender_status()["ready"]
    assert mail.drain()["held"]
    assert provider.sent == []
    cfg["commissioned"] = True
    allowance["stopped"] = True
    assert mail.drain()["held"]
    assert provider.sent == []
    assert store.pending_deliveries()[0]["status"] == "pending"


def test_send_freezes_human_payload_and_actual_receipt(setup):
    mail, store, provider, cfg, allowance, clock = setup
    item = intent(store)
    result = mail.drain()
    assert result["deliveries"][0]["status"] == "accepted"
    payload, key = provider.sent[0]
    assert payload["from"] == "Sample Hardware <orders@service.example.test>"
    assert payload["to"] == ["buyer@example.test"]
    assert payload["reply_to"].startswith("r.") and payload["reply_to"].endswith("@reply.example.test")
    assert "<script>" not in payload["html"] and "&lt;script&gt;" in payload["html"]
    assert "Message-ID" not in payload.get("headers", {})
    assert store.delivery_context(item["id"])["provider_message_id"] == PROVIDER_ID
    assert mail.drain()["deliveries"] == []
    assert len(provider.sent) == 1
    assert "whsec_" not in json.dumps(mail.sender_status())


def test_timeout_retries_exact_payload_inside_window_then_stops(setup):
    mail, store, provider, cfg, allowance, clock = setup
    intent(store)
    provider.fail = True
    assert mail.drain()["deliveries"][0]["status"] == "uncertain"
    first = copy.deepcopy(provider.sent[0])
    clock[0] += 30
    assert mail.drain()["deliveries"][0]["status"] == "uncertain"
    assert provider.sent[1] == first
    clock[0] += 24 * 3600
    allowance["expires_at"] = clock[0] + 86400
    assert mail.drain()["deliveries"][0]["status"] == "uncertain"
    assert len(provider.sent) == 2


def test_webhook_signature_raw_body_freshness_and_rotation():
    payload, headers = signed({"type": "email.sent", "data": {"email_id": PROVIDER_ID}})
    assert verify_webhook(payload, headers, SECRET, now=NOW)["type"] == "email.sent"
    headers["svix-signature"] = "v1,wrong " + headers["svix-signature"]
    assert verify_webhook(payload, headers, SECRET, now=NOW)
    for body, hdrs, secret, now in [
        (payload + b" ", headers, SECRET, NOW),
        (payload, headers, SECRET, NOW + 301),
        (payload, headers, "", NOW),
        (b"x" * (256 * 1024 + 1), headers, SECRET, NOW),
    ]:
        with pytest.raises(MailHeld):
            verify_webhook(body, hdrs, secret, now=now)


def test_known_sender_and_exact_alias_join_customer_and_only_suggest_acceptance(setup):
    mail, store, provider, cfg, allowance, clock = setup
    intent(store)
    mail.drain()
    alias = provider.sent[0][0]["reply_to"]
    body, headers = signed(incoming(provider, alias))
    result = mail.handle_webhook(body, headers)
    assert result["status"] == "received"
    assert mail.handle_webhook(body, headers) == result
    assert provider.received == [INBOUND_ID]
    messages = store.conversation("buyer")["messages"]
    customers = [m for m in messages if m["author_type"] == "customer"]
    assert len(customers) == 1 and customers[0]["text"] == "Потвърждавам тази версия."
    suggestions = [m for m in messages if m["kind"] == "email_intent"]
    assert suggestions[0]["data"]["authority"] == "suggestion"
    assert suggestions[0]["data"]["ambiguous"] is True
    assert all(m["kind"] != "customer_confirmation" for m in messages)


@pytest.mark.parametrize("sender,dmarc", [("outsider@example.test", "pass"), ("buyer@example.test", "fail")])
def test_sender_or_authentication_mismatch_goes_to_review(setup, sender, dmarc):
    mail, store, provider, cfg, allowance, clock = setup
    intent(store)
    mail.drain()
    body, headers = signed(incoming(provider, provider.sent[0][0]["reply_to"], sender=sender, dmarc=dmarc))
    assert mail.handle_webhook(body, headers)["status"] == "review"
    assert len(mail.review_items()) == 1
    assert all(m["author_type"] != "customer" for m in store.conversation("buyer")["messages"])


def test_unknown_alias_never_fetches_unrelated_customer_email(setup):
    mail, store, provider, cfg, allowance, clock = setup
    event = incoming(provider, "r.unknown@reply.example.test")
    assert mail.handle_webhook(*signed(event))["status"] == "ignored"
    assert provider.received == []


def test_delivery_events_store_actual_message_id_and_ignore_late_events(setup):
    mail, store, provider, cfg, allowance, clock = setup
    item = intent(store)
    mail.drain()
    event = {
        "type": "email.delivered",
        "created_at": "2027-01-15T08:00:00Z",
        "data": {"email_id": PROVIDER_ID, "message_id": "<actual@resend.test>"},
    }
    assert mail.handle_webhook(*signed(event))["status"] == "delivered"
    event["type"] = "email.sent"
    event["created_at"] = "2027-01-15T07:59:00Z"
    assert mail.handle_webhook(*signed(event, "evt-2"))["status"] == "delivered"
    assert store.delivery_context(item["id"])["status"] == "delivered"
    intent(store, "message-2")
    mail.drain()
    assert provider.sent[1][0]["headers"]["In-Reply-To"] == "<actual@resend.test>"


def test_fixed_http_endpoints_separate_keys_and_bounded_response():
    calls = []

    def transport(request):
        calls.append(request)
        assert str(request.url).startswith("https://api.resend.com/")
        return httpx.Response(200, json={"id": PROVIDER_ID})

    provider = ResendHTTPProvider(
        "resend-a",
        "company-a",
        send_key="re_send",
        receive_key="re_read",
        webhook_secret=SECRET,
        client=httpx.Client(transport=httpx.MockTransport(transport)),
    )
    provider.send({"to": ["buyer@example.test"]}, "frozen-key")
    provider.receive(INBOUND_ID)
    assert calls[0].headers["authorization"] == "Bearer re_send"
    assert calls[0].headers["idempotency-key"] == "frozen-key"
    assert calls[1].headers["authorization"] == "Bearer re_read"
    assert calls[1].url.path == "/emails/receiving/" + INBOUND_ID
    with pytest.raises(MailHeld):
        provider.receive("../../evil.test")


def test_exact_proposal_card_and_reply_revision_survive_later_revision(setup):
    mail, store, provider, cfg, allowance, clock = setup
    document = {
        "id": "order-1",
        "customer_id": "buyer",
        "number": "#1001",
        "status": "requested",
        "currency": "EUR",
        "lines": [
            {"code": "10", "name": "Дръжка", "quantity": 2, "unit": "бр.", "unit_price": 4.5, "line_total": 9}
        ],
        "subtotal": 9,
        "delivery": {"address": "София"},
    }
    store.record_source_order("buyer", document, actor="peter", current=lambda: True)
    first = store.propose_request(
        "buyer",
        "order-1",
        proposal=document,
        recipient="buyer@example.test",
        actor="peter",
        expected_revision=0,
        idempotency_key="proposal-1",
        current=lambda: True,
    )
    mail.drain()
    payload = provider.sent[0][0]
    assert "#1001" in payload["html"] and "Версия 1" in payload["html"]
    assert "/customer/review#demo.token" in payload["html"]
    document["lines"][0]["quantity"] = 3
    store.propose_request(
        "buyer",
        "order-1",
        proposal=document,
        recipient="buyer@example.test",
        actor="peter",
        expected_revision=1,
        idempotency_key="proposal-2",
        current=lambda: True,
    )
    result = mail.handle_webhook(*signed(incoming(provider, payload["reply_to"])))
    assert result["status"] == "received"
    message = next(m for m in store.conversation("buyer")["messages"] if m["author_type"] == "customer")
    assert message["data"]["provenance"]["proposal_version_id"] == first["proposal"]["id"]
    assert store.order_review("buyer", "order-1")["confirmed_version_id"] is None


def test_current_contact_and_permission_revocation_stop_send(setup):
    mail, store, provider, cfg, allowance, clock = setup
    intent(store)
    mail.current = lambda ctx: False
    assert mail.drain()["held"]
    assert provider.sent == []
    mail.current = lambda ctx: True
    store.ensure_customer(
        "buyer", contacts=[{"email": "replacement@example.test"}], actor="peter", current=lambda: True
    )
    assert mail.drain()["held"]
    assert provider.sent == []


def test_shared_account_money_and_workspace_count_are_enforced(setup):
    mail, store, provider, cfg, allowance, clock = setup
    item = intent(store)
    with mail.money_store._db(write=True) as db:
        mail.spend.reserve(
            db, {"id": "native-otp", "channel": "email", "account": "resend-a"}, provider, {}, NOW
        )
    allowance["total_microusd"] = 1000
    assert mail.drain()["held"]
    assert provider.sent == []
    allowance["total_microusd"] = 200000
    mail.send_admission = lambda ctx: False
    assert mail.drain()["held"]
    assert provider.sent == []
    mail.send_admission = lambda ctx: True
    assert mail.drain()["deliveries"][0]["status"] == "accepted"
    with mail.money_store._db() as db:
        holds = list(db.execute("SELECT outbox FROM capability_spend_holds"))
    assert {r[0] for r in holds} == {"native-otp", "manufacturer:" + item["id"]}


def test_daily_count_is_durable_and_money_hold_is_idempotent(setup):
    mail, store, provider, cfg, allowance, clock = setup
    cfg["daily_send_limit"] = 1
    first = intent(store)
    mail.drain()
    intent(store, "second")
    assert mail.drain()["held"]
    assert len(provider.sent) == 1
    with mail.money_store._db() as db:
        assert db.execute("SELECT count(*) FROM capability_spend_holds").fetchone()[0] == 1
    assert store.delivery_context(first["id"])["status"] == "accepted"


def test_revoked_alias_and_wrong_domain_stay_out_of_customer_history(setup):
    mail, store, provider, cfg, allowance, clock = setup
    item = intent(store)
    mail.drain()
    alias = provider.sent[0][0]["reply_to"]
    mail.revoke_reply(item["id"])
    assert mail.handle_webhook(*signed(incoming(provider, alias)))["status"] == "ignored"
    assert (
        mail.handle_webhook(*signed(incoming(provider, alias.replace("@reply.", "@foreign.")), "evt-2"))[
            "status"
        ]
        == "ignored"
    )
    assert provider.received == []


def test_changed_event_and_cross_company_or_account_binding_fail_closed(setup, tmp_path):
    mail, store, provider, cfg, allowance, clock = setup
    event = incoming(provider, "r.unknown@reply.example.test")
    mail.handle_webhook(*signed(event))
    event["data"]["from"] = "different@example.test"
    with pytest.raises(MailHeld):
        mail.handle_webhook(*signed(event))
    cfg["company_id"] = "company-b"
    assert mail.drain()["held"]
    cfg["company_id"] = "company-a"
    cfg["account_id"] = provider.account_id = "resend-b"
    assert not mail.sender_status()["ready"]
    with pytest.raises(MailHeld):
        ManufacturerMail(tmp_path, environment_id="other", company_id="company-a", conversations=store)


def test_html_only_incoming_is_plain_and_attachment_metadata_stays_private(setup):
    mail, store, provider, cfg, allowance, clock = setup
    intent(store)
    mail.drain()
    event = incoming(provider, provider.sent[0][0]["reply_to"])
    provider.body.update(
        text=None,
        html="<script>bad()</script><p>Промяна <b>моля</b></p>",
        attachments=[
            {"id": "file-1", "filename": "plan.pdf", "content_type": "application/pdf", "size": 250}
        ],
        raw={"download_url": "https://private.example.test/signed-secret"},
    )
    mail.handle_webhook(*signed(event))
    message = next(m for m in store.conversation("buyer")["messages"] if m["author_type"] == "customer")
    assert message["text"] == "Промяна моля"
    assert "signed-secret" not in json.dumps(message)
    assert provider.received == [INBOUND_ID]


def test_duplicate_inbound_after_crash_retains_original_provenance(setup, monkeypatch):
    mail, store, provider, cfg, allowance, clock = setup
    intent(store)
    mail.drain()
    event = incoming(provider, provider.sent[0][0]["reply_to"])
    original = store.record_email_intent
    monkeypatch.setattr(
        store, "record_email_intent", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("crash"))
    )
    with pytest.raises(RuntimeError):
        mail.handle_webhook(*signed(event))
    monkeypatch.setattr(store, "record_email_intent", original)
    assert mail.handle_webhook(*signed(event, "different-retry-event"))["status"] == "received"
    assert len([m for m in store.conversation("buyer")["messages"] if m["author_type"] == "customer"]) == 1
    assert provider.received == [INBOUND_ID]


def test_classification_confirmation_is_only_a_suggestion(setup):
    mail, store, provider, cfg, allowance, clock = setup
    intent(store)
    mail.drain()
    mail.classify = lambda payload: {
        "intent": "confirmation",
        "confidence": 1.0,
        "ambiguous": False,
        "execute": "accept_all_orders",
    }
    mail.handle_webhook(*signed(incoming(provider, provider.sent[0][0]["reply_to"])))
    suggestion = next(m for m in store.conversation("buyer")["messages"] if m["kind"] == "email_intent")
    assert suggestion["data"]["intent"] == "confirmation" and suggestion["data"]["authority"] == "suggestion"
    assert "execute" not in suggestion["data"]


def test_http_transport_holds_redirect_and_oversized_response():
    for response in [
        httpx.Response(302, headers={"location": "https://elsewhere.test/secret"}),
        httpx.Response(200, content=b"x" * (256 * 1024 + 1)),
    ]:
        calls = []

        def transport(request):
            calls.append(request)
            return response

        provider = ResendHTTPProvider(
            "resend-a",
            "company-a",
            send_key="re_send",
            receive_key="re_read",
            webhook_secret=SECRET,
            client=httpx.Client(transport=httpx.MockTransport(transport)),
        )
        with pytest.raises(MailHeld):
            provider.receive(INBOUND_ID)
        assert len(calls) == 1


def test_queued_webhook_fetches_in_worker_even_with_send_allowance_stopped(setup):
    mail, store, provider, cfg, allowance, clock = setup
    intent(store)
    mail.drain()
    payload = signed(incoming(provider, provider.sent[0][0]["reply_to"]))
    assert mail.accept_webhook(*payload)["status"] == "queued"
    assert provider.received == []
    allowance["stopped"] = True
    assert mail.drain()["held"]
    assert provider.received == [INBOUND_ID]
    assert mail.handle_webhook(*payload)["status"] == "received"


def test_unfunded_classifier_stays_pending_without_losing_customer_message(setup):
    mail, store, provider, cfg, allowance, clock = setup
    intent(store)
    mail.drain()
    mail.classify = lambda payload: None
    event = signed(incoming(provider, provider.sent[0][0]["reply_to"]))
    with pytest.raises(MailHeld):
        mail.handle_webhook(*event)
    assert len([m for m in store.conversation("buyer")["messages"] if m["author_type"] == "customer"]) == 1
    mail.classify = lambda payload: {
        "intent": "question",
        "confidence": 0.9,
        "ambiguous": False,
        "evidence": {"model": "offline-model", "revision": "v1"},
    }
    assert mail.handle_webhook(*event)["status"] == "received"
    assert provider.received == [INBOUND_ID]
    suggestion = next(m for m in store.conversation("buyer")["messages"] if m["kind"] == "email_intent")
    assert suggestion["data"]["evidence"]["model"] == "offline-model"


def test_signed_receipt_recovers_ambiguous_post_by_exact_frozen_delivery_tag(setup):
    mail, store, provider, cfg, allowance, clock = setup
    item = intent(store)
    provider.fail = True
    mail.drain()
    payload = provider.sent[0][0]
    event = {
        "type": "email.delivered",
        "created_at": "2027-01-15T08:00:00Z",
        "data": {
            "email_id": PROVIDER_ID,
            "message_id": "<actual@resend.test>",
            "tags": {"delivery_id": item["id"]},
            "from": payload["from"],
            "to": payload["to"],
        },
    }
    assert mail.handle_webhook(*signed(event))["status"] == "delivered"
    assert store.delivery_context(item["id"])["status"] == "delivered"
    clock[0] += 30
    assert mail.drain()["deliveries"] == []
    assert len(provider.sent) == 1


def test_acceptance_notification_uses_one_existing_timeline_event(setup):
    from manufacturer_fulfillment import ManufacturerFulfillment

    mail, store, provider, cfg, allowance, clock = setup
    document = {
        "id": "order-1",
        "customer_id": "buyer",
        "number": "#1001",
        "status": "requested",
        "lines": [{"code": "10", "name": "Дръжка", "quantity": 2}],
    }
    store.record_source_order("buyer", document, actor="peter", current=lambda: True)
    fulfillment = ManufacturerFulfillment(store)
    current = fulfillment.read("buyer", "order-1")
    fulfillment.transition(
        "buyer",
        "order-1",
        status="accepted",
        version_id=current["current_version_id"],
        expected_revision=0,
        actor="peter",
        evidence={"method": "staff_action"},
        idempotency_key="accept-1",
        current=lambda: True,
    )
    queued = store.queue_fulfillment(
        "buyer", "order-1", 1, recipient="buyer@example.test", actor="peter", current=lambda: True
    )
    assert (
        store.queue_fulfillment(
            "buyer", "order-1", 1, recipient="buyer@example.test", actor="peter", current=lambda: True
        )
        == queued
    )
    assert len([m for m in store.conversation("buyer")["messages"] if m["kind"] == "fulfillment_update"]) == 1
    assert store.delivery_context(queued["id"])["reference_version_id"] == current["current_version_id"]
    mail.drain()
    assert provider.sent[0][0]["subject"] == "Поръчка #1001"
    assert provider.sent[0][0]["text"] == "Поръчката е приета."


def test_real_delivery_receipt_survives_customer_contact_removal(setup):
    mail, store, provider, cfg, allowance, clock = setup
    item = intent(store)
    mail.drain()
    store.ensure_customer(
        "buyer", contacts=[{"email": "replacement@example.test"}], actor="peter", current=lambda: True
    )
    event = {
        "type": "email.delivered",
        "created_at": "2027-01-15T08:00:00Z",
        "data": {"email_id": PROVIDER_ID, "message_id": "<actual@resend.test>"},
    }
    assert mail.handle_webhook(*signed(event))["status"] == "delivered"
    message = next(m for m in store.conversation("buyer")["messages"] if m.get("delivery"))
    assert message["delivery"]["id"] == item["id"] and message["delivery"]["status"] == "delivered"
