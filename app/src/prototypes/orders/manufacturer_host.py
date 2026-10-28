"""Native harness composition for one bound manufacturer company database."""

from __future__ import annotations

import json
import os
import sqlite3
import stat
from contextlib import asynccontextmanager, closing
from pathlib import Path

from host import BareWorkspace
from starlette.requests import Request

from app.src.prototypes.orders import order_files, orders_tools
from app.src.prototypes.orders.store import CompanyStore

BINDING = ".manufacturer-company.json"
BINDING_SCHEMA = "rocoto.manufacturer-workspace.v2"
ROLE_MAP = {"browse": "public", "operator": "operator", "owner": "owner"}
PACK_ASSETS = Path(__file__).resolve().parent / "packs" / "manufacturer" / "web"


def _private_file(path: Path) -> os.stat_result:
    try:
        info = path.lstat()
    except OSError as error:
        raise PermissionError("Commission the private manufacturer company binding.") from error
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != os.geteuid()
        or info.st_mode & 0o077
        or info.st_nlink != 1
    ):
        raise PermissionError("Keep the manufacturer company binding private to this host account.")
    return info


def read_binding(state) -> dict:
    """Read the host-owned database binding; tool/model input never selects it."""
    marker = Path(state).resolve() / BINDING
    _private_file(marker)
    try:
        value = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise PermissionError("Commission a valid manufacturer company binding.") from error
    if set(value) != {"schema", "company", "database"} or value.get("schema") != BINDING_SCHEMA:
        raise PermissionError("Commission the current manufacturer company binding.")
    company = value.get("company")
    database = value.get("database")
    if not isinstance(company, str) or not company or not isinstance(database, str):
        raise PermissionError("Commission a valid manufacturer company binding.")
    path = Path(database)
    if not path.is_absolute() or path.resolve(strict=True) != path:
        raise PermissionError("Bind one canonical manufacturer database path.")
    _private_file(path)
    _check_company(path, company)
    return {**value, "database": path}


def _check_company(path: Path, company: str) -> None:
    try:
        with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=5)) as database:
            rows = database.execute("SELECT id FROM company").fetchall()
    except sqlite3.Error as error:
        raise PermissionError("Open the bound manufacturer company database.") from error
    if rows != [(company,)]:
        raise PermissionError("The bound database belongs to another company.")


def _open_store(path: Path, company: str, writes: bool) -> CompanyStore:
    """Open and verify one SQLite handle in the thread performing the operation."""
    _check_company(path, company)
    if writes:
        return CompanyStore(path)
    store = object.__new__(CompanyStore)
    store.path = path
    store.db = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=5)
    store.db.row_factory = sqlite3.Row
    store.db.execute("PRAGMA query_only=ON")
    return store


def _database_writable(path: Path) -> bool:
    """Honor the runtime filesystem boundary before advertising write tools."""
    try:
        return os.access(path, os.W_OK) and not os.statvfs(path).f_flag & os.ST_RDONLY
    except OSError as error:
        raise PermissionError("Open the bound manufacturer company database.") from error


class PerCallCompanyStore:
    """Give every store operation its own same-thread SQLite connection."""

    def __init__(self, path: Path, company: str, writes: bool):
        self.path = path
        self.company = company
        self.writes = writes

    def __getattr__(self, name):
        method = getattr(CompanyStore, name, None)
        if name.startswith("_") or not callable(method):
            raise AttributeError(name)

        def invoke(*args, **kwargs):
            store = _open_store(self.path, self.company, self.writes)
            try:
                return getattr(store, name)(*args, **kwargs)
            finally:
                store.close()

        return invoke


class ManufacturerWorkspace(BareWorkspace):
    """Translate current native membership into the orders-owned capability."""

    def __init__(self, host, selected, binding):
        super().__init__(selected)
        self.host = host
        self.binding = binding

    def tool_context(self, context):
        if (
            context.collection != "company"
            or context.company_id != self.selected["business_scope"].company_id
        ):
            raise PermissionError("Open the company collection in its bound workspace.")
        if context.admission is None or not context.admission.current():
            raise PermissionError("Refresh current manufacturer workspace access.")
        member = self.selected["business_scope"].member(context.actor)
        role = ROLE_MAP.get(member.get("role") if isinstance(member, dict) else None)
        if role is None:
            raise PermissionError("Use a current manufacturer workspace membership.")
        writes = role in {"operator", "owner"} and _database_writable(self.binding["database"])
        evidence = f"native harness:{context.chat_id or context.collection}"
        store = PerCallCompanyStore(self.binding["database"], self.binding["company"], writes)
        return orders_tools.CompanyContext(
            store, self.binding["company"], context.actor, role, evidence, writes
        )

    def session_fields(self):
        """Expose the host-owned collection used by new native conversations."""
        return {
            "category": "company",
            "collections": [{"id": "company", "name": self.binding["company"]}],
        }


def install_workspace(host, selected):
    extension = ManufacturerWorkspace(host, selected, read_binding(selected["state"]))
    selected["vertical"] = extension
    return extension


def register_routes(app, host, http):
    """Serve the authenticated interim Orders page through current native admission."""
    from fastapi import HTTPException, Query
    from fastapi.responses import FileResponse, Response
    from tool_families import ToolContext
    from workspace_identity import workspace_scope

    def identity(request):
        principal, _ = http.connection_identity(request)
        selected = request.state.workspace
        extension = selected.get("vertical")
        if not isinstance(extension, ManufacturerWorkspace):
            raise HTTPException(403, "Open the manufacturer workspace.")
        return selected, principal, extension

    @app.get("/manufacturer/orders")
    async def orders_page(request: Request):
        identity(request)
        return FileResponse(
            PACK_ASSETS / "manufacturer_orders.html",
            media_type="text/html",
            headers={"Cache-Control": "private, no-store"},
        )

    @app.get("/manufacturer/orders.css")
    async def orders_style(request: Request):
        identity(request)
        return FileResponse(
            PACK_ASSETS / "manufacturer_orders.css",
            media_type="text/css",
            headers={"Cache-Control": "private, no-store"},
        )

    @app.get("/manufacturer/orders.js")
    async def orders_script(request: Request):
        identity(request)
        return FileResponse(
            PACK_ASSETS / "manufacturer_orders.js",
            media_type="application/javascript",
            headers={"Cache-Control": "private, no-store"},
        )

    @app.get("/api/manufacturer/orders")
    async def orders_api(
        request: Request,
        limit: int = Query(default=50, ge=1, le=100),
        before: int | None = Query(default=None, ge=1),
    ):
        selected, principal, extension = identity(request)
        try:
            admission = extension.read_admission(principal, "company")
            context = ToolContext(
                state=selected["state"],
                company_id=workspace_scope(selected["state"]),
                actor=principal,
                data_owner=principal,
                collection="company",
                admission=admission,
                extension=extension,
            )
            arguments = {"limit": limit, **({"before": before} if before is not None else {})}
            result = await selected["agent"].tool_registry.invoke(context, "orders_list", arguments)
        except PermissionError as error:
            raise HTTPException(403, str(error)) from None
        except ValueError as error:
            raise HTTPException(400, str(error)) from None
        return Response(
            json.dumps(result, ensure_ascii=False, allow_nan=False),
            media_type="application/json",
            headers={"Cache-Control": "private, no-store"},
        )

    @app.get("/api/manufacturer/orders/{order_id}/files/{file_id}")
    async def order_file(request: Request, order_id: str, file_id: str):
        selected, principal, extension = identity(request)
        try:
            context = ToolContext(
                state=selected["state"],
                company_id=workspace_scope(selected["state"]),
                actor=principal,
                data_owner=principal,
                collection="company",
                admission=extension.read_admission(principal, "company"),
                extension=extension,
            )
            company_context = extension.tool_context(context)
            company_context.checked()
            if company_context.role not in {"operator", "owner", "admin"}:
                raise PermissionError("Current company membership does not include private orders.")
            path, metadata = order_files.read_for_operator(
                extension.binding["database"], extension.binding["company"], order_id, file_id
            )
        except PermissionError as error:
            raise HTTPException(403, str(error)) from None
        except (ValueError, OSError):
            raise HTTPException(404, "Unknown order file.") from None
        return FileResponse(
            path,
            media_type="application/octet-stream",
            filename=metadata["name"],
            headers={
                "Cache-Control": "private, no-store",
                "X-Content-Type-Options": "nosniff",
                "X-Content-SHA256": metadata["sha256"],
            },
        )


@asynccontextmanager
async def lifespan(app, host):
    yield


class OrdersSurfaceFamily:
    """Privacy-minimal order rows for the pack's paginated list surface."""

    READ_NAMES = frozenset({"orders_list"})
    WRITE_NAMES = frozenset()
    SURFACE_READS = {
        "native": frozenset({"orders_list"}),
        "public": frozenset(),
        "local": frozenset(),
    }

    @staticmethod
    def specs(write=True):
        return [
            {
                "type": "function",
                "name": "orders_list",
                "description": "List current order status, recorded price and ready-date projection.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                        "before": {"type": "integer", "minimum": 1},
                    },
                    "additionalProperties": False,
                },
            }
        ]

    @staticmethod
    def read(context, name, args):
        if name != "orders_list" or not isinstance(context, orders_tools.CompanyContext):
            raise PermissionError("Use the admitted manufacturer order surface.")
        trusted = context.checked()
        if context.role not in {"operator", "owner", "admin"}:
            raise PermissionError("Current company membership does not include private orders.")
        limit = args.get("limit", 50)
        before = args.get("before")
        where, parameters = ("WHERE o.rowid<?", (before,)) if before is not None else ("", ())
        rows = trusted["store"].rows(
            "SELECT o.rowid AS cursor,o.id,o.state,o.quote,o.created_at,"
            "(SELECT e.data FROM estimates e WHERE e.order_id=o.id ORDER BY e.id DESC LIMIT 1) AS ready "
            f"FROM orders o {where} ORDER BY o.rowid DESC LIMIT ?",
            (*parameters, limit + 1),
        )
        more = len(rows) > limit
        rows = rows[:limit]
        result = []
        for row in rows:
            quote = json.loads(row["quote"])
            ready = json.loads(row["ready"]) if row["ready"] else None
            pricing = {
                key: quote[key]
                for key in ("net", "vat", "gross", "currency", "confirmation")
                if key in quote
            }
            date = (
                {key: ready[key] for key in ("kind", "earliest", "latest", "timezone") if key in ready}
                if ready
                else None
            )
            fulfilment = {
                key: quote[key] for key in ("fulfilment", "delivery") if key in quote
            }
            result.append(
                {
                    "id": row["id"],
                    "status": row["state"],
                    "pricing": pricing,
                    "date": date,
                    "fulfilment": fulfilment,
                    "files": [
                        {
                            **file,
                            "download_url": f"/api/manufacturer/orders/{row['id']}/files/{file['id']}",
                        }
                        for file in order_files.list_for_order(trusted["store"], row["id"])
                    ],
                    "created_at": row["created_at"],
                }
            )
        return {"orders": result, "next_before": rows[-1]["cursor"] if more and rows else None}


orders_surface = OrdersSurfaceFamily()
