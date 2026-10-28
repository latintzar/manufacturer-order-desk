"""Native pack/registry integration is opt-in via ORDERS_HARNESS_SOURCE."""

import asyncio
import json
import os
import stat
import threading
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.src.prototypes.orders import harness_launcher as launcher
from app.src.prototypes.orders import order_files
from app.src.prototypes.orders import orders_tools as family

pytest_plugins = ["test_store"]


def context(store, role="operator", writes=False):
    return family.CompanyContext(store, "example", "local:test", role, "test fixture", writes)


def test_native_specs_include_reads_with_writes():
    assert {s["name"] for s in family.specs(False)} == set(family.READ_NAMES)
    assert {s["name"] for s in family.specs(True)} == set(family.READ_NAMES) | set(family.WRITE_NAMES)
    assert all(
        "inputSchema" in s and "parameters" not in s and s["type"] == "function" for s in family.specs(True)
    )
    assert not set(family.HOST_ONLY) & {s["name"] for s in family.specs(True)}


def test_authenticated_context_and_database_identity(store):
    assert family.read(context(store), "catalog_read", {"item_id": "A"})["item"]["p"] == 12.345
    with pytest.raises(PermissionError, match="authenticated"):
        family.read({"store": store, "role": "operator"}, "catalog_read", {"item_id": "A"})
    foreign = family.CompanyContext(store, "another-company", "local:test", "operator")
    with pytest.raises(PermissionError, match="another company"):
        family.read(foreign, "catalog_read", {"item_id": "A"})
    with pytest.raises(PermissionError):
        family.read(context(store, "public"), "orders_read", {"order_id": "private-order"})


def test_write_capability_is_host_selected_and_excludes_identity_grants(store):
    args = {"item_id": "A", "amount": 99, "idempotency_key": "harness-price"}
    with pytest.raises(PermissionError):
        family.call(context(store), "catalog_set_price", args)
    family.call(context(store, writes=True), "catalog_set_price", args)
    assert store.item("A")["item"]["p"] == 99
    assert store.one("SELECT actor,evidence FROM prices ORDER BY id DESC")["actor"] == "local:test"
    with pytest.raises(PermissionError):
        family.call(context(store, "admin", True), "claim_grant", {})
    with pytest.raises(PermissionError):
        family.call(context(store, "owner", True), "orders_submit", {})


def test_readonly_open_cannot_write_or_create_foreign_database(store, tmp_path):
    with pytest.raises(PermissionError, match="another company"):
        launcher.open_store(store.path, "foreign")
    path = tmp_path / "absent.db"
    with pytest.raises(FileNotFoundError):
        launcher.open_store(path, "example")
    assert not path.exists()
    readonly = launcher.open_store(store.path, "example")
    try:
        assert readonly.item("A")["item"]["p"] == 12.345
        import sqlite3

        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            readonly.db.execute("INSERT INTO company VALUES(?,?,?)", ("other", "{}", "{}"))
    finally:
        readonly.close()


def test_payload_cannot_select_authority_or_company(store):
    validate = SimpleNamespace(
        declared=lambda f, n, a: f.business._validate(a, f.business.REGISTRY[n]["parameters"])
    )
    trusted = context(store)
    with pytest.raises(ValueError, match="name string"):
        launcher.dispatch(trusted, {"name": [], "arguments": {}}, validate)
    for field in ["role", "actor", "company", "database", "context", "write"]:
        with pytest.raises(ValueError, match="host fixes identity"):
            launcher.dispatch(
                trusted, {"name": "catalog_read", "arguments": {"item_id": "A"}, field: "owner"}, validate
            )
        with pytest.raises(ValueError, match="unexpected argument"):
            launcher.dispatch(
                trusted, {"name": "catalog_read", "arguments": {"item_id": "A", field: "owner"}}, validate
            )
    with pytest.raises(PermissionError):
        launcher.dispatch(trusted, {"name": "claim_grant", "arguments": {}}, validate)


def test_legacy_flat_pack_contract_remains_loadable(tmp_path):
    (tmp_path / "pack.py").write_text("VALUE = 'legacy-flat'\n", encoding="utf-8")
    assert launcher.load_contract(tmp_path).VALUE == "legacy-flat"


@pytest.fixture
def native():
    path = os.environ.get("ORDERS_HARNESS_SOURCE")
    if not path:
        pytest.skip("Set ORDERS_HARNESS_SOURCE to test against the actual separate harness checkout.")
    return Path(path), launcher.check_pack(Path(path))


def test_actual_native_pack_registry_and_reads(native, store):
    source, (contract, template, monitoring) = native
    assert Path(contract.__file__).resolve() == source.resolve() / "sdk" / "pack.py"
    assert Path(__import__("layout").ROOT).resolve() == source.resolve()
    assert Path(monitoring.__file__).resolve().is_relative_to(source.resolve() / "verticals" / "retail")
    assert template.id == "manufacturer"
    declared = template.import_tool_families()
    names = [spec["name"] for registered in declared for spec in registered.specs(True)]
    assert set(declared[0].READ_NAMES) == set(family.READ_NAMES)
    assert set(declared[0].WRITE_NAMES) == set(family.WRITE_NAMES)
    assert template.check_tools(names) == []
    result = launcher.dispatch(
        context(store), {"name": "catalog_read", "arguments": {"item_id": "A"}}, monitoring
    )
    assert result["item"]["p"] == 12.345
    with pytest.raises(ValueError, match="declared fields"):
        launcher.dispatch(
            context(store),
            {"name": "catalog_read", "arguments": {"item_id": "A", "role": "owner"}},
            monitoring,
        )
    # The former HTTP-style adapter fails the actual native registry contract.
    old = SimpleNamespace(
        READ_NAMES=family.business.READ_NAMES,
        WRITE_NAMES=family.business.WRITE_NAMES,
        specs=family.business.specs,
    )
    with pytest.raises(ValueError, match="one name"):
        monitoring.registry((old,))


def test_workspace_binds_template_and_company(native, tmp_path):
    source, (contract, template, _) = native
    from store import CompanyStore

    company_store = CompanyStore(tmp_path / "example.db")
    company_store.db.execute("INSERT INTO company VALUES(?,?,?)", ("example", "{}", "{}"))
    company_store.close()
    workspace = tmp_path / "company-workspace"
    launcher.bind_workspace(contract, template, workspace, "example", source, tmp_path / "example.db")
    assert json.loads((workspace / contract.BINDING).read_text())["template"] == "manufacturer"
    binding = json.loads((workspace / ".manufacturer-company.json").read_text())
    assert binding == {
        "schema": "rocoto.manufacturer-workspace.v2",
        "company": "example",
        "database": str((tmp_path / "example.db").resolve()),
    }
    assert stat.S_IMODE((workspace / ".manufacturer-company.json").stat().st_mode) == 0o600
    with pytest.raises(PermissionError, match="another company"):
        launcher.bind_workspace(contract, template, workspace, "foreign", source, tmp_path / "example.db")
    foreign = tmp_path / "retail"
    foreign.mkdir()
    (foreign / contract.BINDING).write_text(
        json.dumps({"schema": contract.BINDING_SCHEMA, "template": "retail"})
    )
    with pytest.raises(contract.PackError, match="retail"):
        launcher.bind_workspace(contract, template, foreign, "example", source, tmp_path / "example.db")


def test_actual_host_membership_database_and_orders_surface(native, store, tmp_path, monkeypatch):
    source, (contract, template, _) = native
    workspace = tmp_path / "native-company"
    launcher.bind_workspace(contract, template, workspace, "example", source, store.path)
    native_host = template.import_host()

    from host import Collections
    from tool_families import ToolContext, ToolRegistry, VerticalFamily

    members = {"operator-1": {"id": "operator-1", "role": "operator"}}
    from workspace_identity import workspace_scope

    scope = SimpleNamespace(company_id=workspace_scope(workspace), member=lambda actor: members.get(actor))
    collections = Collections()
    collections.seal()
    selected = {"state": workspace, "business_scope": scope, "collections": collections}
    extension = native_host.install_workspace(SimpleNamespace(), selected)
    assert extension.session_fields() == {
        "category": "company",
        "collections": [{"id": "company", "name": "example"}],
    }
    declared = template.import_tool_families()
    registry = ToolRegistry(tuple(VerticalFamily(registered) for registered in declared))

    first_submitted = store.submit_order(
        {"name": "Buyer", "email": "buyer@example.test"},
        [{"item_id": "A", "quantity": 2, "cuts": 2}],
        {"net": 10, "vat": 2, "gross": 12, "currency": "EUR", "confirmation": False},
        "native-order",
        "web",
        "server quote",
        now="2026-10-12T09:00:00+03:00",
    )
    submitted = store.submit_order(
        {"name": "Second buyer", "email": "second@example.test"},
        [{"item_id": "A", "quantity": 1}],
        {"gross": 20, "currency": "EUR", "confirmation": True},
        "native-order-2",
        "web",
        "server quote",
        now="2026-10-13T09:00:00+03:00",
    )
    admission = extension.read_admission("operator-1", "company")
    context = ToolContext(
        state=workspace,
        company_id=scope.company_id,
        actor="operator-1",
        data_owner="operator-1",
        collection="company",
        admission=admission,
        extension=extension,
    )

    main_thread = threading.get_ident()
    connection_threads = []
    actual_connect = __import__("app.src.prototypes.orders.manufacturer_host", fromlist=["x"]).sqlite3.connect

    def recorded_connect(*args, **kwargs):
        connection_threads.append(threading.get_ident())
        return actual_connect(*args, **kwargs)

    manufacturer = __import__("app.src.prototypes.orders.manufacturer_host", fromlist=["x"])
    monkeypatch.setattr(manufacturer.sqlite3, "connect", recorded_connect)

    async def exercise():
        item, order_list = await asyncio.gather(
            registry.invoke(context, "catalog_read", {"item_id": "A"}),
            registry.invoke(context, "orders_list", {"limit": 1}),
        )
        return item, order_list

    item, order_list = asyncio.run(exercise())
    assert item["item"]["p"] == 12.345
    assert order_list["orders"] == [
        {
            "id": submitted["id"],
            "status": "requested",
            "pricing": {"gross": 20, "currency": "EUR", "confirmation": True},
            "date": {key: submitted["ready"][key] for key in ("kind", "earliest", "latest", "timezone")},
            "fulfilment": {},
            "files": [],
            "created_at": store.one(
                "SELECT created_at FROM orders WHERE id=?", (submitted["id"],)
            )["created_at"],
        }
    ]
    assert isinstance(order_list["next_before"], int)
    second_page = asyncio.run(
        registry.invoke(context, "orders_list", {"limit": 1, "before": order_list["next_before"]})
    )
    assert [row["id"] for row in second_page["orders"]] == [first_submitted["id"]]
    assert second_page["next_before"] is None
    assert connection_threads and all(thread != main_thread for thread in connection_threads)

    members["operator-1"]["role"] = "browse"
    browse = replace(context, admission=extension.read_admission("operator-1", "company"))
    with pytest.raises(PermissionError, match="private orders"):
        asyncio.run(registry.invoke(browse, "orders_list", {}))

    members.clear()
    with pytest.raises(ValueError, match="current authorized workspace"):
        asyncio.run(registry.invoke(context, "orders_list", {}))


def test_native_app_server_dispatch_uses_bound_company_collection(native, store, tmp_path):
    source, (contract, template, _) = native
    workspace = tmp_path / "native-model-company"
    launcher.bind_workspace(contract, template, workspace, "example", source, store.path)
    native_host = template.import_host()

    from agent_bridge import CodexVideoAgent
    from business_scope import BusinessScope
    from host import Collections
    from tool_families import ToolRegistry, VerticalFamily
    from workspace_identity import workspace_scope

    members = {"operator-1": {"id": "operator-1", "role": "operator"}}
    scope = BusinessScope(
        workspace,
        company_id=workspace_scope(workspace),
        member=lambda actor: members.get(actor),
    )
    collections = Collections()
    collections.seal()
    selected = {
        "state": workspace,
        "environment_id": "demo",
        "business_scope": scope,
        "collections": collections,
    }
    extension = native_host.install_workspace(SimpleNamespace(), selected)
    registry = ToolRegistry(tuple(VerticalFamily(item) for item in template.import_tool_families()))

    agent = object.__new__(CodexVideoAgent)
    agent.state = workspace
    agent.children = {
        "chat-1": {
            "id": "chat-1",
            "owner_principal_id": "operator-1",
            "dataset": extension.session_fields()["collections"][0]["id"],
            "parent_id": None,
        }
    }
    agent.active = {}
    agent.automation_store = None
    agent.business_scope_host = selected
    agent.vertical = extension
    agent.tool_registry = registry
    agent._turn_guests = {}
    selected["agent"] = agent

    content, results, success = asyncio.run(
        agent._tool("catalog_read", {"item_id": "A"}, "company", "chat-1")
    )
    assert success is True and results is None
    returned = json.loads(content[0]["text"])
    assert returned["item"]["p"] == 12.345
    assert returned["price"] == {
        "amount": 12.345,
        "currency": None,
        "basis": "stock_length",
        "status": "current",
        "basis_quantity": 6,
        "basis_unit": "m",
    }


def test_native_readonly_runtime_withholds_writes(native, store, tmp_path, monkeypatch):
    source, (contract, template, _) = native
    workspace = tmp_path / "native-readonly-company"
    launcher.bind_workspace(contract, template, workspace, "example", source, store.path)
    native_host = template.import_host()

    from host import Collections
    from tool_families import ToolContext
    from workspace_identity import workspace_scope

    members = {"owner-1": {"id": "owner-1", "role": "owner"}}
    scope = SimpleNamespace(company_id=workspace_scope(workspace), member=lambda actor: members.get(actor))
    collections = Collections()
    collections.seal()
    selected = {"state": workspace, "business_scope": scope, "collections": collections}
    extension = native_host.install_workspace(SimpleNamespace(), selected)
    original = os.statvfs(store.path)
    manufacturer = __import__("app.src.prototypes.orders.manufacturer_host", fromlist=["x"])
    monkeypatch.setattr(
        manufacturer.os,
        "statvfs",
        lambda path: SimpleNamespace(f_flag=original.f_flag | os.ST_RDONLY),
    )
    context = ToolContext(
        state=workspace,
        company_id=scope.company_id,
        actor="owner-1",
        data_owner="owner-1",
        collection="company",
        admission=extension.read_admission("owner-1", "company"),
        extension=extension,
    )
    trusted = extension.tool_context(context)
    assert trusted.writes is False
    assert family.read(trusted, "catalog_read", {"item_id": "A"})["item"]["p"] == 12.345
    with pytest.raises(PermissionError, match="declared manufacturer writes"):
        family.call(
            trusted,
            "catalog_set_price",
            {"item_id": "A", "amount": 99, "idempotency_key": "blocked-readonly"},
        )


def test_authenticated_orders_http_surface_uses_native_admission(native, store, tmp_path):
    source, (contract, template, _) = native
    workspace = tmp_path / "native-http-company"
    launcher.bind_workspace(contract, template, workspace, "example", source, store.path)
    native_host = template.import_host()

    from fastapi import FastAPI, HTTPException, Request
    from fastapi.testclient import TestClient
    from host import Collections
    from tool_families import ToolRegistry, VerticalFamily
    from workspace_identity import workspace_scope

    members = {
        "operator-1": {"id": "operator-1", "role": "operator"},
        "browser-1": {"id": "browser-1", "role": "browse"},
    }
    scope = SimpleNamespace(company_id=workspace_scope(workspace), member=lambda actor: members.get(actor))
    collections = Collections()
    collections.seal()
    selected = {"state": workspace, "business_scope": scope, "collections": collections}
    native_host.install_workspace(SimpleNamespace(), selected)
    registry = ToolRegistry(
        tuple(VerticalFamily(registered) for registered in template.import_tool_families())
    )
    selected["agent"] = SimpleNamespace(tool_registry=registry)

    order = store.submit_order(
        {"name": "Buyer", "email": "buyer@example.test"},
        [
            {"item_id": "A", "quantity": 1},
            {
                "item_id": None,
                "kind": "custom",
                "description": "Customer bracket",
                "quantity": 1,
                "cuts": 0,
                "upload_id": order_files.stage(
                    store,
                    "bracket.step",
                    b"ISO-10303-21;\nHEADER;\nENDSEC;\nEND-ISO-10303-21;\n",
                    "native-upload-0001",
                )["id"],
            },
        ],
        {
            "gross": 22.345,
            "currency": "EUR",
            "confirmation": False,
            "fulfilment": "delivery",
            "delivery": "confirmed",
        },
        "native-http-order",
        "web",
        "server quote",
        now="2026-10-13T09:00:00+03:00",
    )
    app = FastAPI()

    @app.middleware("http")
    async def workspace_request(request: Request, call_next):
        request.state.workspace = selected
        return await call_next(request)

    def connection_identity(request):
        principal = request.headers.get("x-test-principal")
        if principal not in members:
            raise HTTPException(401, "Enter your company access code.")
        return principal, "test-session"

    native_host.register_routes(
        app, SimpleNamespace(), SimpleNamespace(connection_identity=connection_identity)
    )
    with TestClient(app) as client:
        assert client.get("/api/manufacturer/orders").status_code == 401
        assert (
            client.get(
                "/api/manufacturer/orders", headers={"x-test-principal": "browser-1"}
            ).status_code
            == 403
        )
        response = client.get(
            "/api/manufacturer/orders?limit=1", headers={"x-test-principal": "operator-1"}
        )
        assert response.status_code == 200
        assert response.headers["cache-control"] == "private, no-store"
        assert response.json()["orders"][0] == {
            "id": order["id"],
            "status": "requested",
            "pricing": {"gross": 22.345, "currency": "EUR", "confirmation": False},
            "date": {key: order["ready"][key] for key in ("kind", "earliest", "latest", "timezone")},
            "fulfilment": {"fulfilment": "delivery", "delivery": "confirmed"},
            "files": [
                {
                    **order_files.list_for_order(store, order["id"])[0],
                    "download_url": f"/api/manufacturer/orders/{order['id']}/files/"
                    + order_files.list_for_order(store, order["id"])[0]["id"],
                }
            ],
            "created_at": store.one(
                "SELECT created_at FROM orders WHERE id=?", (order["id"],)
            )["created_at"],
        }
        file = order_files.list_for_order(store, order["id"])[0]
        file_url = f"/api/manufacturer/orders/{order['id']}/files/{file['id']}"
        assert client.get(file_url).status_code == 401
        assert client.get(file_url, headers={"x-test-principal": "browser-1"}).status_code == 403
        downloaded = client.get(file_url, headers={"x-test-principal": "operator-1"})
        assert downloaded.status_code == 200
        assert downloaded.content.startswith(b"ISO-10303-21;")
        assert downloaded.headers["content-type"] == "application/octet-stream"
        assert downloaded.headers["cache-control"] == "private, no-store"
        assert downloaded.headers["x-content-type-options"] == "nosniff"
        assert downloaded.headers["content-disposition"].startswith("attachment;")
        assert client.get(
            file_url.replace(order["id"], "0" * 32),
            headers={"x-test-principal": "operator-1"},
        ).status_code == 404
        page = client.get("/manufacturer/orders", headers={"x-test-principal": "operator-1"})
        assert page.status_code == 200 and "<h1>Orders</h1>" in page.text
        assert client.get("/manufacturer/orders.css").status_code == 401
        assert (
            client.get(
                "/manufacturer/orders.js", headers={"x-test-principal": "operator-1"}
            ).status_code
            == 200
        )


def test_stdio_rejects_escalation_then_continues(native, store, tmp_path, monkeypatch, capsys):
    from io import StringIO

    source, _ = native
    requests = [
        {"name": "catalog_read", "arguments": {"item_id": "A"}, "role": "admin"},
        {"name": "catalog_read", "arguments": {"item_id": "A"}},
    ]
    monkeypatch.setattr("sys.stdin", StringIO("\n".join(json.dumps(x) for x in requests)))
    code = launcher.main(
        [
            "--harness-source",
            str(source),
            "--database",
            str(store.path),
            "--company",
            "example",
            "--workspace",
            str(tmp_path / "host"),
            "--role",
            "operator",
            "stdio",
        ]
    )
    assert code == 0
    rows = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert rows[0]["ok"] is False
    assert rows[1]["ok"] and rows[1]["result"]["item"]["p"] == 12.345
