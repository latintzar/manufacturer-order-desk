"""Public submission recomputes prices, persists once and keeps ownership private."""

import http.client
import json
import threading
import time
from urllib.parse import quote

import mail_transport
import pytest
from customer_mail import CustomerMail
from mail_relay import RemoteOutbox, relay_one
from store import CompanyStore

import serve


@pytest.fixture
def order_api(tmp_path):
    root = tmp_path / "site"
    (root / "example/rocoto").mkdir(parents=True)
    (root / "example/rocoto/site.json").write_text('{"languages":["en"]}')
    state = tmp_path / "state"
    path = state / "companies/example/company.db"
    database = CompanyStore(path)
    catalog = {
        "company": {"en": "Example"},
        "source": "https://example.test/prices",
        "asOf": "11/10/2026",
        "currency": "EUR",
        "vat": 0.2,
        "services": [],
        "rules": {},
        "cats": [
            {
                "code": "square",
                "shape": "sq_tube",
                "items": [
                    {
                        "c": "A",
                        "s": "40x40x3",
                        "p": 20,
                        "cut": 1,
                        "w": 6,
                        "L": 6,
                        "d": [40, 40, 3],
                        "r": {"k": "len", "l": [6]},
                    }
                ],
            },
            {
                "code": "held-bar",
                "shape": "sq_tube",
                "items": [
                    {
                        "c": "QB",
                        "s": "held bar",
                        "p": 20,
                        "q": 1,
                        "cut": 1,
                        "w": 6,
                        "L": 6,
                        "d": [40, 40, 3],
                        "r": {"k": "len", "l": [3, 6]},
                    }
                ],
            },
            {
                "code": "held-sheet",
                "shape": "sheet",
                "items": [
                    {
                        "c": "QS",
                        "s": "held sheet",
                        "p": 40,
                        "q": 1,
                        "cut": 1,
                        "w": 20,
                        "L": 0,
                        "d": [2, 1000, 2000],
                        "r": {"k": "strip"},
                    }
                ],
            },
        ],
    }
    database.ingest_catalog(
        catalog,
        {"slug": "example", "hours": {str(i): [510, 1050, 1020] for i in range(1, 7)}},
        "test",
        "synthetic price list",
    )
    database.close()
    server = serve.server(root, 0, state)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server.server_address[1], path, root
    server.shutdown()
    server.server_close()


def request(api, route, body, key="request-00000000001", origin=None):
    conn = http.client.HTTPConnection("127.0.0.1", api[0], timeout=10)
    headers = {"Content-Type": "application/json", "Idempotency-Key": key}
    if origin:
        headers["Origin"] = origin
    conn.request("POST", f"/example/rocoto/api/{route}", json.dumps(body), headers)
    response = conn.getresponse()
    result = response.status, json.loads(response.read())
    conn.close()
    return result


def upload(api, name, body, key="upload-request-0001", content_type="application/octet-stream"):
    conn = http.client.HTTPConnection("127.0.0.1", api[0], timeout=10)
    conn.request(
        "POST",
        "/example/rocoto/api/uploads",
        body,
        {
            "Content-Type": content_type,
            "Content-Length": str(len(body)),
            "X-File-Name": quote(name, safe=""),
            "Idempotency-Key": key,
        },
    )
    response = conn.getresponse()
    result = response.status, json.loads(response.read())
    conn.close()
    return result


def discard_upload(api, upload_id, token, origin=None):
    conn = http.client.HTTPConnection("127.0.0.1", api[0], timeout=10)
    headers = {"Upload-Capability": token}
    if origin:
        headers["Origin"] = origin
    conn.request("DELETE", f"/example/rocoto/api/uploads/{upload_id}", headers=headers)
    response = conn.getresponse()
    result = response.status, json.loads(response.read())
    conn.close()
    return result


def relay_request(api, key, body, origin=None):
    conn = http.client.HTTPConnection("127.0.0.1", api[0], timeout=10)
    headers = {"Content-Type": "application/json", "Authorization": "Bearer " + key}
    if origin:
        headers["Origin"] = origin
    conn.request("POST", "/example/rocoto/api/mail-relay", json.dumps(body), headers)
    response = conn.getresponse()
    result = response.status, json.loads(response.read())
    conn.close()
    return result


def get(api, path, token=""):
    conn = http.client.HTTPConnection("127.0.0.1", api[0], timeout=10)
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    conn.request("GET", path, headers=headers)
    response = conn.getresponse()
    result = response.status, dict(response.getheaders()), response.read()
    conn.close()
    return result


def get_json(api, path):
    status, _, body = get(api, path)
    return status, json.loads(body)


def order():
    return {
        "customer": {"name": "Preview QA", "email": "qa@example.invalid"},
        "lines": [{"code": "A", "rows": [{"x": 6000, "n": 1}], "total": 0.01}],
        "total": 0.01,
        "fulfilment": "pickup",
    }


def test_price_is_server_computed_and_retry_replays_after_price_change(order_api):
    status, first = request(order_api, "orders", order())
    assert status == 201 and first["quote"]["gross"] == 20
    assert first["ready"] == {"kind": "confirmation", "timezone": "Europe/Sofia"}
    database = CompanyStore(order_api[1])
    database.set_price("A", 30, "operator", "new list")
    status, repeated = request(order_api, "orders", order())
    assert status == 200 and repeated == first
    assert database.one("SELECT count(*) AS n FROM orders")["n"] == 1
    assert database.one("SELECT sum(reserved) AS n FROM stock")["n"] == 0
    database.close()


def test_changed_request_cannot_reuse_key(order_api):
    request(order_api, "orders", order())
    changed = order()
    changed["lines"][0]["rows"][0]["n"] = 2
    assert request(order_api, "orders", changed)[0] == 400


def test_claim_is_pending_and_cross_site_is_refused(order_api):
    status, claim = request(order_api, "claims", {"name": "Preview QA", "email": "owner@example.invalid"})
    assert status == 201 and claim["status"] == "pending"
    database = CompanyStore(order_api[1])
    assert database.one("SELECT count(*) AS n FROM members")["n"] == 0
    database.close()
    assert request(order_api, "orders", order(), origin="https://unrelated.test")[0] == 403


def test_https_mail_relay_is_capability_scoped_and_preserves_send_receipts(order_api, tmp_path):
    config = tmp_path / "relay.json"
    server_key = order_api[1].parent / "mail-relay.key"
    mail_transport.commission("example", config, server_key)
    key = mail_transport.load_config(config, "example")["key"]
    assert config.stat().st_mode & 0o777 == server_key.stat().st_mode & 0o777 == 0o600

    status, created = request(order_api, "orders", order(), key="relay-order-00001")
    assert status == 201
    database = CompanyStore(order_api[1])
    queued = database.one("SELECT id FROM mail_outbox WHERE order_id=?", (created["id"],))["id"]
    database.close()
    body = {"command": "status", "mail": None, "payload": None, "authorization": "relay test"}
    assert relay_request(order_api, "A" * 43, body)[0] == 403
    assert relay_request(order_api, key, body, origin="https://orders.example.test")[0] == 403
    assert relay_request(order_api, key, {**body, "command": "shell"})[0] == 400
    assert relay_request(order_api, key, {**body, "payload": "x" * mail_transport.MAX_REQUEST_BYTES})[0] == 400

    class Provider:
        def send(self, raw, thread):
            assert b"Content-Type: multipart/alternative" in raw and thread is None
            return {"id": "gmail1", "threadId": "thread1"}

    remote = RemoteOutbox(
        "example",
        "relay test",
        config,
        connection_factory=lambda host, timeout: http.client.HTTPConnection("127.0.0.1", order_api[0], timeout=timeout),
    )
    checkpoint = {"schema": 1, "last_thread": "thread1", "after": {"thread1": "reply1"}}
    remote.save_reply_state(checkpoint)
    assert remote.reply_state() == checkpoint and config.with_name(config.name + ".state").stat().st_mode & 0o777 == 0o600
    result = relay_one(remote, Provider(), queued)
    assert result == {
        "id": queued,
        "state": "sent",
        "provider_id": "gmail1",
        "provider_thread_id": "thread1",
    }
    database = CompanyStore(order_api[1])
    assert database.one("SELECT state,attempts FROM mail_outbox WHERE id=?", (queued,)) == {
        "state": "sent",
        "attempts": 1,
    }
    database.close()
    now = time.monotonic()
    try:
        serve.Handler.requests["127.0.0.1"] = [now] * 30
        assert relay_request(order_api, key, body)[0] == 200
        serve.Handler.relay_requests[("example", "127.0.0.1")] = [now] * 60
        assert relay_request(order_api, key, body)[0] == 429
    finally:
        serve.Handler.requests.clear()
        serve.Handler.relay_requests.clear()
        serve.Handler.relay_failures.clear()


def test_mail_relay_config_is_fixed_to_company_origin_and_private_permissions(order_api, tmp_path):
    config = tmp_path / "relay.json"
    server_key = order_api[1].parent / "mail-relay.key"
    mail_transport.commission("example", config, server_key)
    with pytest.raises(FileExistsError, match="explicit rotation"):
        mail_transport.commission("example", config, server_key)
    with pytest.raises(PermissionError, match="commissioned private"):
        RemoteOutbox("another-company", "relay test", config)
    value = json.loads(config.read_text())
    value["origin"] = "https://redirect.example"
    config.write_text(json.dumps(value))
    config.chmod(0o600)
    with pytest.raises(PermissionError, match="commissioned private"):
        RemoteOutbox("example", "relay test", config)
    value["origin"] = "https://orders.example.test"
    config.write_text(json.dumps(value))
    config.chmod(0o644)
    with pytest.raises(PermissionError, match="private mail relay"):
        RemoteOutbox("example", "relay test", config)


def test_invalid_item_and_nonfinite_amount_are_rejected(order_api):
    data = order()
    data["lines"][0]["code"] = "unknown"
    assert request(order_api, "orders", data)[0] == 400
    data = order()
    data["lines"][0]["rows"][0]["n"] = float("inf")
    assert request(order_api, "orders", data)[0] == 400


def test_held_price_custom_dimensions_use_parent_stock_demand(order_api):
    status, result = request(
        order_api,
        "quote",
        {
            "lines": [
                {"code": "QB", "rows": [{"x": 2000, "n": 3}]},
                {"code": "QS", "sheet": {"a": 500, "b": 500, "n": 4}},
            ]
        },
    )
    assert status == 200
    bar, sheet = result["lines"]
    assert (bar["item_id"], bar["quantity"], bar["requested_quantity"]) == ("QB", 1, 3)
    assert (sheet["item_id"], sheet["quantity"], sheet["requested_quantity"]) == ("QS", 1, 4)
    assert result["quote"]["confirmation"] is True
    assert bar["gross"] == sheet["gross"] == 0
    assert result["ready"] == {"kind": "confirmation", "timezone": "Europe/Sofia"}
    assert result["quote"]["ready"] == {"kind": "confirmation", "timezone": "Europe/Sofia"}
    assert "stock" not in result["ready"] and "allocation" not in result["ready"]

    status, _ = request(
        order_api,
        "quote",
        {"lines": [{"code": "QS", "sheet": {"a": 2500, "b": 500, "n": 1}}]},
    )
    assert status == 400


def test_quote_reveals_ready_window_after_operational_inputs_are_confirmed(order_api):
    database = CompanyStore(order_api[1])
    database.record_stock("A", 10, "owner", "physical count", status="confirmed")
    database.set_supply_plan(
        "workshop", 480, 6, 2, 3, 2, "confirmed", "owner", "measured plan", "api-supply-plan"
    )
    database.close()

    status, result = request(order_api, "quote", {"lines": order()["lines"]})
    assert status == 200
    assert result["ready"]["kind"] == "estimate"
    assert set(result["ready"]) == {"kind", "earliest", "latest", "timezone"}
    assert result["quote"]["ready"] == result["ready"]


def test_private_design_upload_persists_with_mixed_order_and_customer_capability(order_api):
    body = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF\n"
    status, uploaded = upload(order_api, "customer bracket.pdf", body)
    assert status == 201
    design = uploaded["upload"]
    payload = order()
    payload["lines"].append(
        {"custom": "Laser-cut mounting bracket, 3 mm steel", "upload_id": design["id"]}
    )
    status, result = request(order_api, "orders", payload, key="mixed-order-000001")
    assert status == 201

    database = CompanyStore(order_api[1])
    saved = database.read_order(result["id"])
    assert [line["item_id"] for line in saved["lines"]] == ["A", None]
    assert saved["lines"][1]["file"] == {
        key: value for key, value in design.items() if key != "discard_token"
    }
    private_link = CustomerMail(database).link(result["id"])
    database.close()
    linked_order, token = private_link.split("#", 1)[1].split(".", 1)
    path = f"/example/rocoto/api/manage/orders/{linked_order}/files/{design['id']}"

    assert get(order_api, path)[0] == 403
    code, headers, downloaded = get(order_api, path, token)
    assert code == 200 and downloaded == body
    assert headers["Content-Type"] == "application/octet-stream"
    assert headers["Cache-Control"] == "private, no-store"
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["Content-Disposition"].startswith("attachment;")
    assert get(order_api, path.replace(linked_order, "0" * 32), token)[0] == 403
    assert discard_upload(order_api, design["id"], design["discard_token"])[0] == 403


def test_upload_refuses_active_or_mismatched_content(order_api):
    assert upload(order_api, "drawing.pdf", b"<html><script>alert(1)</script></html>")[0] == 400
    assert upload(order_api, "drawing.svg", b"<svg/>", key="upload-request-0002")[0] == 400


def test_unclaimed_upload_delete_requires_its_capability_and_same_origin(order_api):
    body = b"%PDF-1.4\n%%EOF\n"
    status, result = upload(order_api, "temporary.pdf", body, key="discard-api-upload-01")
    assert status == 201
    design = result["upload"]
    assert discard_upload(order_api, design["id"], "A" * 43)[0] == 403
    assert discard_upload(
        order_api, design["id"], design["discard_token"], origin="https://unrelated.test"
    )[0] == 403
    assert discard_upload(order_api, design["id"], design["discard_token"])[0] == 200
    database = CompanyStore(order_api[1])
    assert database.one("SELECT id FROM order_files WHERE id=?", (design["id"],)) is None
    assert not (database.path.parent / "order-files" / design["id"]).exists()
    database.close()


def test_reviewed_public_scope_filters_catalogue_supply_and_guessed_quotes(order_api):
    site = order_api[2] / "example/rocoto"
    (site / "site.json").write_text('{"languages":["en"],"catalogueScope":"reviewed_images"}')
    (site / "g").mkdir()
    (site / "g/index.json").write_text(
        json.dumps(
            {
                "sets": {"finished": ["finished.webp"]},
                "items": {"A": "finished", "QB": None, "QS": None},
            }
        )
    )

    status, public = get_json(order_api, "/example/rocoto/catalog.json")
    assert status == 200
    assert [item["c"] for category in public["cats"] for item in category["items"]] == ["A"]
    status, supply = get_json(order_api, "/example/rocoto/api/supply")
    assert status == 200 and set(supply["items"]) == {"A"}
    assert request(
        order_api, "quote", {"lines": [{"code": "QB", "rows": [{"x": 2000, "n": 1}]}]}
    )[0] == 400
    status, custom = request(order_api, "quote", {"lines": [{"custom": "One-off guard plate"}]})
    assert status == 200 and custom["lines"][0]["kind"] == "custom"
