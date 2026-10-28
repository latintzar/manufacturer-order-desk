"""Customer capabilities, atomic self-service, held email and threaded provider receipts."""

import json
import time
from base64 import urlsafe_b64decode
from email import message_from_bytes
from types import SimpleNamespace

import mail_transport
import pytest
from customer_mail import CustomerMail, NativeGmail
from mail_relay import reconcile_rows, relay_one, sync_reply_rows

pytest_plugins = ["test_store", "test_order_api"]


def make_order(store, language="en"):
    return store.submit_order(
        {"name": "Customer QA", "email": "customer@example.invalid", "language": language},
        [
            {
                "item_id": "A",
                "quantity": 1,
                "requested_quantity": 2,
                "gross": 12.345,
                "kind": "bar",
                "configuration": {"rows": [{"x": 2000, "n": 2}]},
                "source": "https://example.test/prices",
            }
        ],
        {"gross": 12.345, "net": 10.29, "vat": 2.06, "currency": "EUR", "fulfilment": "pickup"},
        "order-" + language,
        "test",
        "fixture",
        now="2026-10-12T09:00:00+03:00",
    )


@pytest.fixture
def customer(store):
    order = make_order(store)
    mail = CustomerMail(store)
    queued = mail.queue(order["id"])
    link = mail.link(order["id"])
    token = link.rsplit(".", 1)[1]
    return mail, order, queued, token


def test_capability_hashed_private_scoped_and_expiring(customer, store):
    mail, order, queued, token = customer
    assert len(token) >= 40 and "?" not in mail.link(order["id"])
    assert token not in "\n".join(store.db.iterdump())
    assert (store.path.parent / "customer-link.key").stat().st_mode & 0o777 == 0o600
    assert mail.projection(order["id"], token)["customer"]["email"] == "customer@example.invalid"
    other = make_order(store, "bg")
    for oid, cap in [(other["id"], token), (order["id"], "wrong"), ("unknown", token)]:
        with pytest.raises(PermissionError):
            mail.projection(oid, cap)
    store.db.execute("UPDATE customer_links SET expires=?", (time.time() - 1,))
    with pytest.raises(PermissionError):
        mail.projection(order["id"], token)
    store.db.execute("UPDATE customer_links SET expires=?,revoked=1", (time.time() + 3600,))
    with pytest.raises(PermissionError):
        mail.projection(order["id"], token)


def test_receipt_held_idempotent_and_projection_private(customer, store):
    mail, order, queued, token = customer
    assert mail.queue(order["id"])["id"] == queued["id"]
    mail.sync_events()
    assert store.one("SELECT COUNT(*) n FROM mail_outbox")["n"] == 1
    assert queued["state"] == "held"
    assert mail.status()[0]["preview"] is True
    projected = mail.projection(order["id"], token)
    assert "inputs" not in projected["ready"] and "actor" not in json.dumps(projected)
    assert projected["ready"] == {"kind": "confirmation", "timezone": "Europe/Sofia"}
    assert "customer_id" not in projected and "nonce" not in projected
    assert projected["events"] == [{"event": "requested", "created_at": projected["events"][0]["created_at"]}]


def test_private_projection_exposes_only_an_actual_issued_invoice(customer, store):
    mail, order, queued, token = customer
    assert mail.projection(order["id"], token)["invoice"] is None
    store.record_stock("A", 10, "owner", "counted")
    store.accept_order(order["id"], "owner", "accepted", "accept-invoice")
    store.record_invoice(
        order["id"], "MM-2026-14", "2026-10-12T09:00:00+03:00", "EUR", 12.345,
        "https://invoices.example.test/MM-2026-14.pdf", "owner", "ledger", "invoice-1",
    )
    projected = mail.projection(order["id"], token)
    assert projected["invoice"] == {
        "number": "MM-2026-14", "issued_at": "2026-10-12T09:00:00+03:00", "currency": "EUR",
        "amount": 12.345, "document_url": "https://invoices.example.test/MM-2026-14.pdf",
    }
    assert "actor" not in json.dumps(projected["invoice"])


def test_issued_invoice_queues_one_held_threaded_update_with_the_actual_document(customer, store):
    mail, order, receipt, token = customer
    store.record_stock("A", 10, "owner", "counted")
    store.accept_order(order["id"], "owner", "accepted", "accept-invoice")
    store.record_invoice(
        order["id"], "MM-2026-14", "2026-10-12T09:00:00+03:00", "EUR", 12.345,
        "https://invoices.example.test/MM-2026-14.pdf", "owner", "ledger", "invoice-1",
    )
    mail.sync_events()
    invoice = store.one("SELECT * FROM mail_outbox WHERE kind='invoice'")
    assert invoice["state"] == "held"
    mail.sync_events()
    assert store.one("SELECT COUNT(*) n FROM mail_outbox WHERE kind='invoice'")["n"] == 1
    rendered = mail.render(invoice["id"])
    assert "MM-2026-14" in rendered["html"]
    assert "https://invoices.example.test/MM-2026-14.pdf" in rendered["html"]
    assert "View invoice" in rendered["text"]


def test_invoice_update_requires_an_actual_issued_record(customer):
    mail, order, receipt, token = customer
    with pytest.raises(ValueError, match="issued invoice"):
        mail.queue(order["id"], "invoice", "invoice-without-record")


@pytest.mark.parametrize("language", ["en", "bg"])
def test_branded_html_plaintext_and_price_details(store, language):
    order = make_order(store, language)
    mail = CustomerMail(store)
    queued = mail.queue(order["id"])
    rendered = mail.render(queued["id"])
    assert f'lang="{language}"' in rendered["html"]
    assert "#f29400" in rendered["html"] and "logo.png" in rendered["html"]
    assert "2000 mm" in rendered["html"] and "2 × 2000 mm" in rendered["text"]
    assert "/example/manage/#" + order["id"] in rendered["html"]
    assert (
        "Ready time confirmation" if language == "en" else "Потвърждение на срока"
    ) in rendered["html"]
    assert ("€12.35" if language == "en" else "12,35 €") in rendered["html"]
    mime = mail.mime(queued["id"])
    assert mime["Reply-To"] == "operator@example.test"
    assert mime["Message-ID"].startswith("<orders-")
    assert mime.get_content_type() == "multipart/alternative"


def test_receipt_keeps_a_quoted_order_quoted_until_delivery_date_confirmation(store):
    order = make_order(store)
    rendered = CustomerMail(store).render(CustomerMail(store).queue(order["id"])["id"])
    assert "Quoted total" in rendered["html"]
    assert "confirm the delivery date" in rendered["html"]
    assert "confirm the price" not in rendered["html"]
    assert "invoice follows confirmation" in rendered["html"]


def test_receipt_keeps_unpriced_lines_as_a_commercial_exception(store):
    order = store.submit_order(
        {"name": "Customer QA", "email": "customer@example.invalid"},
        [{"item_id": "A", "quantity": 1, "confirmation": True, "configuration": {}}],
        {"gross": 12.345, "currency": "EUR", "confirmation": True, "fulfilment": "delivery"},
        "pending-receipt", "test", "fixture",
    )
    rendered = CustomerMail(store).render(CustomerMail(store).queue(order["id"])["id"])
    assert "Price on confirmation" in rendered["html"]
    assert "confirm the price and delivery date" in rendered["html"]
    assert "€12.35" not in rendered["html"]


def test_delivery_confirmation_projects_actual_window_and_queues_one_held_threaded_update(store):
    order = store.submit_order(
        {"name": "Customer QA", "email": "customer@example.invalid", "language": "en"},
        [{"item_id": "A", "quantity": 1, "configuration": {}}],
        {"gross": 12.345, "currency": "EUR", "fulfilment": "delivery"}, "delivery-mail", "test", "fixture",
    )
    mail = CustomerMail(store)
    receipt = mail.queue(order["id"])
    token = mail.link(order["id"]).rsplit(".", 1)[1]
    store.confirm_delivery(
        order["id"], "2030-10-14T10:00:00+03:00", "2030-10-14T12:00:00+03:00",
        "Carrier delivery to the recorded address.", "operator", "carrier booking", "delivery-mail-1",
        fee=24.5, currency="EUR", vat_rate=0.2,
    )
    projected = mail.projection(order["id"], token)
    assert projected["delivery"] == {
        "status": "confirmed",
        "arrival": {"earliest": "2030-10-14T10:00:00+03:00", "latest": "2030-10-14T12:00:00+03:00", "timezone": "Europe/Sofia"},
        "terms": "Carrier delivery to the recorded address.",
        "fee": {"amount": 24.5, "currency": "EUR", "vat_rate": 0.2},
    }
    mail.sync_events()
    update = store.one("SELECT * FROM mail_outbox WHERE kind='delivery'")
    assert update["state"] == "held" and update["order_id"] == receipt["order_id"]
    mail.sync_events()
    assert store.one("SELECT COUNT(*) n FROM mail_outbox WHERE kind='delivery'")["n"] == 1
    rendered = mail.render(update["id"])
    assert "14 Oct 2030, 10:00" in rendered["html"]
    assert "Carrier delivery to the recorded address." in rendered["text"]
    assert "€24.50" in rendered["text"]


def test_customer_change_keeps_terms_and_cancel_only_requested(customer, store):
    mail, order, queued, token = customer
    original = store.read_order(order["id"])
    result = mail.change(order["id"], token, "change", "Please make it 3 metres.", "customer-change-001")
    assert (
        mail.change(order["id"], token, "change", "Please make it 3 metres.", "customer-change-001") == result
    )
    assert store.read_order(order["id"])["lines"] == original["lines"]
    assert store.read_order(order["id"])["quote"] == original["quote"]
    mail.change(order["id"], token, "cancel", "", "customer-cancel-001")
    assert store.read_order(order["id"])["state"] == "cancelled"
    mail.sync_events()
    assert store.one("SELECT COUNT(*) n FROM mail_outbox WHERE kind='cancelled'")["n"] == 1
    with pytest.raises(ValueError):
        mail.change(order["id"], token, "change", "Again", "customer-change-002")


def test_company_identity_stays_scoped_in_email_and_manage_page(store):
    from customer_page import page

    config = json.loads(store.one("SELECT config FROM company")["config"])
    config.update({
        "name": {"en": "Second Workshop", "bg": "Втора работилница"},
        "orderPrefix": "SW", "source": "https://second.example.test/", "accent": "#123456",
        "strings": {"en": {"pickup": "Pickup · Second workshop address"}},
    })
    store.db.execute("UPDATE company SET config=?", (json.dumps(config),))
    order = make_order(store)
    mail = CustomerMail(store)
    queued = mail.queue(order["id"])
    rendered = mail.render(queued["id"])
    assert "Second Workshop will confirm" in rendered["html"]
    assert " · Rocoto" not in rendered["html"]
    assert "@font-face" in rendered["html"]
    assert "https://second.example.test/" in rendered["html"]
    assert "Second workshop address" in rendered["text"]
    assert "SW-" in rendered["subject"]
    assert "Metal-M" not in rendered["html"] and "Slivnitsa" not in rendered["text"]
    customer_page = page("example", "/example/logo.png", config).decode()
    assert "Second Workshop" in customer_page and "Metal-M" not in customer_page
    assert "/example/rocoto/inter.woff2" in customer_page
    assert "--company-accent:#123456" in customer_page
    assert "via Rocoto" not in str(mail.mime(queued["id"])["From"])
    assert "Second Workshop" in str(mail.mime(queued["id"])["From"])
    assert "Recorded progress" in customer_page and "Invoice follows delivery-date confirmation" in customer_page
    assert 'id="invoiceLink"' in customer_page and "View invoice" in customer_page


def test_accepted_order_cannot_be_cancelled_by_link(customer, store):
    mail, order, queued, token = customer
    store.record_stock("A", 10, "owner", "fixture")
    store.accept_order(order["id"], "owner", "reviewed", "accept-fixture")
    with pytest.raises(ValueError, match="Reply"):
        mail.change(order["id"], token, "cancel", "", "customer-cancel-001")
    assert store.read_order(order["id"])["state"] == "accepted"
    assert store.item("A")["stock"]["reserved"] == 1


class Provider:
    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail
        self.receipt = None

    def send(self, raw, thread):
        self.calls.append((raw, thread))
        if self.fail:
            raise TimeoutError("uncertain provider")
        self.receipt = {"id": "gmail" + str(len(self.calls)), "threadId": "thread1"}
        return self.receipt

    def lookup(self, message_id):
        return self.receipt


def test_same_email_thread_and_reply_headers(customer, store):
    mail, order, queued, token = customer
    provider = Provider()
    with pytest.raises(PermissionError):
        mail.deliver(queued["id"], provider, None)
    first = mail.deliver(queued["id"], provider, "fixture sending approval")
    assert first["state"] == "sent"
    prepared = json.loads(store.one("SELECT data FROM mail_events WHERE kind='prepared'")["data"])
    assert prepared["subject"] == str(mail.mime(queued["id"])["Subject"])
    assert prepared["message_id"] == queued["message_id"]
    mail.deliver(queued["id"], provider, "fixture sending approval")
    assert len(provider.calls) == 1
    reply = {
        "id": "customerreply",
        "threadId": "thread1",
        "payload": {
            "headers": [
                {"name": "From", "value": "Customer <customer@example.invalid>"},
                {"name": "Message-ID", "value": "<customer-reply@example.invalid>"},
            ]
        },
    }
    mail.record_reply(
        order["id"],
        reply,
    )
    mail.record_reply(order["id"], reply)
    assert store.one("SELECT COUNT(*) AS n FROM mail_replies")["n"] == 1
    update = mail.queue(order["id"], "reply", "reply-fixture", "We can prepare this tomorrow.")
    rendered = mail.mime(update["id"])
    original = mail.mime(queued["id"])
    assert rendered["Subject"] == original["Subject"]
    assert rendered["In-Reply-To"] == "<customer-reply@example.invalid>"
    assert original["Message-ID"] in rendered["References"]
    mail.deliver(update["id"], provider, "fixture reply approval")
    assert provider.calls[1][1] == "thread1"
    assert message_from_bytes(provider.calls[1][0])["In-Reply-To"] == "<customer-reply@example.invalid>"


def test_uncertain_send_holds_and_reconciles_without_resend(customer, store):
    mail, order, queued, token = customer
    provider = Provider(fail=True)
    with pytest.raises(TimeoutError):
        mail.deliver(queued["id"], provider, "fixture sending approval")
    assert store.one("SELECT state FROM mail_outbox")["state"] == "uncertain"
    with pytest.raises(ValueError):
        mail.deliver(queued["id"], provider, "fixture sending approval")
    assert mail.reconcile(queued["id"], provider, "review")["state"] == "uncertain"
    provider.receipt = {"id": "recovered1", "threadId": "thread1"}
    assert mail.reconcile(queued["id"], provider, "review")["state"] == "sent"
    assert len(provider.calls) == 1


def test_native_gmail_raw_request_is_private_and_records_the_provider_message_id(customer, monkeypatch):
    mail, order, queued, token = customer
    raw = mail.mime(queued["id"]).as_bytes().replace(b"customer@example.invalid", b"customer@example.com")
    calls, requests = [], []

    def process(argv, **kwargs):
        calls.append(argv)
        command = " ".join(argv)
        assert "customer@example.com" not in command and token not in command
        if "list" in argv:
            return SimpleNamespace(returncode=0, stdout="{}")
        if argv[-2:] == ["auth", "status"]:
            return SimpleNamespace(
                returncode=0, stdout='{"token_valid":true,"user":"operator@example.test"}'
            )
        if argv[-3:] == ["auth", "export", "--unmasked"]:
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps(
                    {
                        "type": "authorized_user",
                        "client_id": "private-client",
                        "client_secret": "private-secret",
                        "refresh_token": "private-refresh",
                    }
                ),
            )
        assert "get" in argv
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "id": "sent1",
                    "threadId": "thread1",
                    "labelIds": ["SENT"],
                    "payload": {
                        "headers": [{"name": "Message-ID", "value": "<gmail-normalized@example>"}]
                    },
                }
            ),
        )

    class Response:
        status = 200

        def __init__(self, payload):
            self.payload = payload

        def read(self, _size):
            return json.dumps(self.payload).encode()

    class Connection:
        def __init__(self, host, timeout):
            self.host = host

        def request(self, method, path, body, headers):
            requests.append((self.host, method, path, body, headers))

        def getresponse(self):
            return Response(
                {"access_token": "private-access-token"}
                if self.host == "oauth2.googleapis.com"
                else {"id": "sent1", "threadId": "thread1"}
            )

        def close(self):
            pass

    monkeypatch.setattr("customer_mail.subprocess.run", process)
    provider = NativeGmail(connection_factory=Connection)
    assert provider.send(raw, "existing-thread") == {
        "id": "sent1",
        "threadId": "thread1",
        "messageId": "<gmail-normalized@example>",
    }
    assert [request[0] for request in requests] == ["oauth2.googleapis.com", "gmail.googleapis.com"]
    sent = json.loads(requests[1][3])
    assert urlsafe_b64decode(sent["raw"]) == raw and sent["threadId"] == "existing-thread"
    assert "private-access-token" not in " ".join(" ".join(call) for call in calls)
    monkeypatch.setattr(
        provider,
        "lookup",
        lambda mid: {"id": "existing", "threadId": "thread1", "messageId": mid},
    )
    assert provider.send(raw)["id"] == "existing" and len(requests) == 2


def test_provider_rfc_message_id_drives_the_next_reply_reference(customer, store):
    mail, order, queued, token = customer
    mail.prepare(queued["id"], "fixture sending approval")
    mail.settle(
        queued["id"],
        {"id": "gmail1", "threadId": "thread1", "messageId": "<provider-root@example>"},
        "fixture sending approval",
    )
    update = mail.queue(order["id"], "reply", "provider-reference", "Workshop update")
    rendered = mail.mime(update["id"])
    assert rendered["In-Reply-To"] == "<provider-root@example>"
    assert queued["message_id"] in rendered["References"]
    assert "<provider-root@example>" in rendered["References"]


def test_remote_relay_keeps_payload_out_of_receipt_output(customer):
    mail, order, queued, token = customer

    class Remote:
        def call(self, command, identity, payload=None):
            if command == "prepare":
                return mail.prepare(identity, "relay fixture")
            if command == "receipt":
                return mail.settle(identity, payload, "relay fixture")
            return mail.uncertain(identity)

    result = relay_one(Remote(), Provider(), queued["id"])
    assert result["state"] == "sent" and token not in json.dumps(result) and "raw" not in result


def test_remote_reconciliation_records_uncertain_and_reply_sync_is_bounded():
    class Remote:
        def __init__(self):
            self.calls = []
            self.state = {"schema": 1, "last_thread": None, "after": {}}

        def call(self, command, identity, payload=None):
            self.calls.append((command, identity, payload))
            return {"state": "sent"}

        def reply_state(self):
            return self.state

        def save_reply_state(self, value):
            self.state = json.loads(json.dumps(value))

    class Provider:
        def lookup(self, message_id):
            return None

        def replies(self, thread_id):
            return [
                {
                    "id": str(n),
                    "threadId": thread_id,
                    "internalDate": str(n),
                    "labelIds": [],
                    "payload": {"headers": []},
                }
                for n in range(100)
            ]

    remote = Remote()
    row = {"id": "a" * 32, "state": "sending", "message_id": "<mail@example>", "provider_thread_id": "t1"}
    assert reconcile_rows(remote, Provider(), [row], None, 5) == [
        {"id": "a" * 32, "state": "uncertain"}
    ]
    assert remote.calls == [("uncertain", "a" * 32, None)]
    result = sync_reply_rows(remote, Provider(), [row], 5)
    reply_calls = [call for call in remote.calls if call[0] == "reply-record"]
    assert result == {"threads_checked": 1, "replies_checked": 5}
    assert len(reply_calls) == 5 and [call[2]["id"] for call in reply_calls] == ["0", "1", "2", "3", "4"]

    visited = []

    class FairProvider:
        def replies(self, thread_id):
            visited.append(thread_id)
            return [{"id": thread_id + "m", "threadId": thread_id, "labelIds": ["SENT"]}]

    rows = [
        {"id": f"{number:032x}", "provider_thread_id": f"thread{number}"} for number in range(7)
    ]
    fair = Remote()
    for _ in range(4):
        assert sync_reply_rows(fair, FairProvider(), rows, 2)["threads_checked"] <= 2
    assert set(visited) == {f"thread{number}" for number in range(7)}


def test_reply_sync_records_chronologically_so_thread_reference_is_latest(customer, store):
    mail, order, queued, token = customer
    mail.deliver(queued["id"], Provider(), "fixture sending approval")

    class Remote:
        def __init__(self):
            self.state = {"schema": 1, "last_thread": None, "after": {}}

        def call(self, command, identity, payload=None):
            assert command == "reply-record" and identity == queued["id"]
            return mail_transport.dispatch(store, command, identity, payload, "fixture sending approval")

        def reply_state(self):
            return self.state

        def save_reply_state(self, value):
            self.state = json.loads(json.dumps(value))

    def reply(number):
        return {
            "id": f"reply{number}",
            "threadId": "thread1",
            "internalDate": str(number * 1000),
            "labelIds": [],
            "payload": {
                "headers": [
                    {"name": "From", "value": "Customer <customer@example.invalid>"},
                    {"name": "Message-ID", "value": f"<reply-{number}@example.invalid>"},
                ]
            },
        }

    class Replies:
        def replies(self, thread_id):
            assert thread_id == "thread1"
            bounce = reply(4)
            bounce["internalDate"] = "1500"
            bounce["payload"]["headers"][0]["value"] = "Mailer daemon <bounce@example.invalid>"
            return [reply(3), bounce, reply(1), reply(2)]

    remote = Remote()
    result = sync_reply_rows(
        remote, Replies(), [{"id": queued["id"], "provider_thread_id": "thread1"}], 5
    )
    assert result == {"threads_checked": 1, "replies_checked": 4}
    assert store.one("SELECT COUNT(*) AS n FROM mail_replies")["n"] == 3
    skipped = store.one("SELECT data FROM mail_events WHERE kind='reply-skipped'")
    assert json.loads(skipped["data"]) == {"provider_id": "reply4", "reason": "sender-mismatch"}
    assert store.one("SELECT last_message_id FROM mail_threads WHERE order_id=?", (order["id"],)) == {
        "last_message_id": "<reply-3@example.invalid>"
    }
    update = mail.queue(order["id"], "reply", "after-bounce", "Your updated order is ready.")
    assert mail.mime(update["id"])["In-Reply-To"] == "<reply-3@example.invalid>"

    class Broken(Remote):
        def call(self, command, identity, payload=None):
            raise TimeoutError("relay unavailable")

    broken = Broken()
    with pytest.raises(TimeoutError, match="relay unavailable"):
        sync_reply_rows(
            broken, Replies(), [{"id": queued["id"], "provider_thread_id": "thread1"}], 5
        )
    assert broken.state["after"] == {}


def test_email_html_escapes_customer_requested_body(customer):
    mail, order, queued, token = customer
    update = mail.queue(order["id"], "reply", "escape-fixture", "<script>alert(1)</script>")
    assert "<script>alert" not in mail.render(update["id"])["html"]
    assert "&lt;script&gt;" in mail.render(update["id"])["html"]


def manage(api, order_id, token, action="read", **fields):
    import http.client

    connection = http.client.HTTPConnection("127.0.0.1", api[0])
    headers = {"Content-Type": "application/json", "Authorization": "Bearer " + token}
    connection.request(
        "POST",
        "/example/rocoto/api/manage",
        json.dumps({"order_id": order_id, "action": action, **fields}),
        headers,
    )
    response = connection.getresponse()
    value = response.status, json.loads(response.read())
    connection.close()
    return value


def test_submission_queues_email_and_private_manage_http(order_api):
    from store import CompanyStore
    from test_order_api import order, request

    status, created = request(order_api, "orders", order())
    assert status == 201
    store = CompanyStore(order_api[1])
    mail = CustomerMail(store)
    assert store.one("SELECT COUNT(*) n FROM mail_outbox")["n"] == 1
    request(order_api, "orders", order())
    assert store.one("SELECT COUNT(*) n FROM mail_outbox")["n"] == 1
    token = mail.link(created["id"]).rsplit(".", 1)[1]
    assert manage(order_api, created["id"], "wrong")[0] == 403
    status, private = manage(order_api, created["id"], token)
    assert status == 200 and private["order"]["quote"]["gross"] == 20
    assert "customer_id" not in private["order"]
    assert (
        manage(
            order_api,
            created["id"],
            token,
            "change",
            body="Two bars please",
            idempotency_key="private-change-0001",
        )[0]
        == 200
    )
    assert store.read_order(created["id"])["quote"]["gross"] == 20
    assert (
        manage(order_api, created["id"], token, "cancel", body="", idempotency_key="test-000000000002")[0]
        == 200
    )
    assert store.read_order(created["id"])["state"] == "cancelled"
    store.close()


def test_tracking_uses_workshop_calendar_day_for_a_customer_abroad():
    import os
    import subprocess

    from customer_page import page

    source = page("metal-m", "/logo.png").decode()
    formatter = next(line for line in source.splitlines() if line.startswith("function date("))
    script = (
        "const W={await:'Awaiting'},order={language:'en',ready:{timezone:'Europe/Sofia'}};"
        + formatter
        + ";if(date('2026-10-12T08:00:00+03:00')!=='12 Oct 2026')throw Error('Wrong company day');"
    )
    subprocess.run(["node", "-e", script], check=True, env={**os.environ, "TZ": "America/Los_Angeles"})


def mark_demo_order(store, order_id):
    record = store.one("SELECT customer_id FROM orders WHERE id=?", (order_id,))
    customer = json.loads(store.one("SELECT data FROM customers WHERE id=?", (record["customer_id"],))["data"])
    customer.update(is_demo=True, email="procurement@real-customer.com")
    store.db.execute("UPDATE customers SET data=? WHERE id=?", (json.dumps(customer), record["customer_id"]))


def test_demo_event_scans_and_direct_updates_create_no_outbox_messages(store):
    order = make_order(store)
    mark_demo_order(store, order["id"])
    mail = CustomerMail(store)
    mail.sync_events()
    mail.sync_events()
    for kind in ("received", "accepted", "delivery", "reviewed", "reply", "invoice"):
        assert mail.queue(order["id"], kind, "demo-" + kind, "Preview message") is None
    assert store.one("SELECT COUNT(*) AS n FROM mail_outbox")["n"] == 0
    assert store.one("SELECT COUNT(*) AS n FROM mail_threads")["n"] == 0


def test_previously_queued_demo_message_is_held_even_with_real_contact(customer, store):
    mail, order, queued, token = customer
    mark_demo_order(store, order["id"])
    assert mail.status()[0]["preview"] is True
    with pytest.raises(PermissionError, match="Demo order messages"):
        mail.prepare(queued["id"], "Preview QA authority")
    class NeverSend:
        def send(self, *args, **kwargs):
            raise AssertionError("A demo must remain inside the portal")
    with pytest.raises(PermissionError, match="Demo order messages"):
        mail.deliver(queued["id"], NeverSend(), "Preview QA authority")
    saved = store.one("SELECT state,attempts FROM mail_outbox WHERE id=?", (queued["id"],))
    assert saved == {"state": "held", "attempts": 0}


def test_demo_customer_change_succeeds_while_mail_is_suppressed(store):
    order = make_order(store)
    mark_demo_order(store, order['id'])
    mail = CustomerMail(store)
    token = mail.link(order['id']).rsplit('.', 1)[1]
    result = mail.change(order['id'], token, 'change', 'Use the revised delivery reference.', 'demo-customer-change-01')
    assert result['state'] == 'requested'
    assert store.one('SELECT COUNT(*) AS n FROM customer_requests')['n'] == 1
    assert store.one('SELECT COUNT(*) AS n FROM mail_outbox')['n'] == 0
    assert mail.projection(order['id'], token)['state'] == 'requested'
