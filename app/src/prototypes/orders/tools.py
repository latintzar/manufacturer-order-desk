"""Shared harness/API/CLI tool registry; caller assigns an authenticated role."""

from __future__ import annotations

import json

try:
    from .supply import quote_ready
except ImportError:
    from supply import quote_ready

S = {"type": "string", "minLength": 1}
N = {"type": "number", "minimum": 0}
INTEGER = {"type": "integer", "minimum": 0}
LINE = {
    "type": "object",
    "properties": {
        "item_id": {"type": ["string", "null"]},
        "quantity": {"type": "number", "exclusiveMinimum": 0},
        "cuts": N,
        "resource_id": S,
        "kind": {"type": "string"},
        "description": {"type": "string", "maxLength": 4000},
        "configuration": {"type": "object"},
    },
    "required": ["item_id", "quantity"],
    "additionalProperties": True,
}
LINES = {"type": "array", "items": LINE, "minItems": 1, "maxItems": 200}
REGISTRY = {}


def register(name, description, write, properties, required=(), roles=("operator", "owner", "admin")):
    REGISTRY[name] = {
        "name": name,
        "description": description,
        "write": write,
        "roles": roles,
        "parameters": {
            "type": "object",
            "properties": properties,
            "required": list(required),
            "additionalProperties": False,
        },
    }


PUBLIC = ("public", "operator", "owner", "admin")
COMPANY = ("operator", "owner", "admin")
register(
    "catalog_find",
    "Find active catalogue items by text or article number.",
    False,
    {"query": S, "limit": {"type": "integer", "minimum": 1, "maximum": 100}},
    ("query",),
    COMPANY,
)
register(
    "catalog_read",
    "Read an item with its current price and selling rules.",
    False,
    {"item_id": S},
    ("item_id",),
    COMPANY,
)
register("stock_read", "Read company stock and capacity planning data.", False, {}, (), COMPANY)
register(
    "quote_ready",
    "Estimate a ready window from stock, calendar and current load.",
    False,
    {"lines": LINES, "now": S},
    ("lines",),
    COMPANY,
)
register(
    "orders_read", "Read an order including private customer details.", False, {"order_id": S}, ("order_id",)
)
register(
    "run_stage_plan",
    "Read the manufacturer stage index, or one stage's instructions, evidence gate and intended model profile. This reads the plan; it neither runs a stage nor selects a model.",
    False,
    {"stage": {"type": "string", "minLength": 1, "maxLength": 64}},
)
register(
    "run_read",
    "Read stage, source and question records.",
    False,
    {
        "table": {
            "type": "string",
            "enum": [
                "runs",
                "stage_runs",
                "pages",
                "page_reads",
                "adapters",
                "questions",
                "agent_notes",
                "claims",
                "sources",
            ],
        },
        "limit": {"type": "integer", "minimum": 1, "maximum": 500},
    },
    ("table",),
)
register(
    "catalog_set_price",
    "Append a price observation and update the current catalogue.",
    True,
    {"item_id": S, "amount": N, "basis": {"type": "string", "enum": ["p", "cut"]}},
    ("item_id", "amount"),
)
register(
    "catalog_set_selling",
    "Record minimum quantity, quantity step and pack.",
    True,
    {
        "item_id": S,
        "minimum": N,
        "step": N,
        "pack": N,
        "status": {"type": "string", "enum": ["assumed", "read", "confirmed"]},
    },
    ("item_id", "minimum", "step", "pack"),
)
register(
    "stock_record",
    "Record observed stock; unknown stock has a null quantity.",
    True,
    {
        "item_id": S,
        "quantity": {"type": ["number", "null"], "minimum": 0},
        "state": {"type": "string", "enum": ["known", "out", "listed", "unknown"]},
        "restock_date": {"type": ["string", "null"]},
        "status": {"type": "string", "enum": ["assumed", "read", "confirmed"]},
    },
    ("item_id", "quantity"),
)
register(
    "capacity_event",
    "Record minutes of unavailable capacity for a resource and date.",
    True,
    {"resource_id": S, "day": S, "minutes": N},
    ("resource_id", "day", "minutes"),
)
register(
    "calendar_exception",
    "Set a closed day or an exceptional opening interval.",
    True,
    {"day": S, "closed": {"type": "boolean"}, "opens": INTEGER, "closes": INTEGER},
    ("day", "closed"),
)
register(
    "orders_submit",
    "Persist an order request using a trusted server-computed quote.",
    True,
    {"customer": {"type": "object"}, "lines": LINES, "quote": {"type": "object"}, "now": S},
    ("customer", "lines", "quote"),
)
register(
    "orders_accept",
    "Accept an order, reserve observed stock and book capacity atomically.",
    True,
    {"order_id": S, "now": S},
    ("order_id",),
    ("owner", "admin"),
)
register(
    "orders_confirm_operation_capacity",
    "Confirm measured operation and resource capacity used by reviewed custom quotes.",
    True,
    {
        "operation_id": S,
        "resource_id": S,
        "setup_minutes": N,
        "minutes_per_unit": N,
        "minutes_per_day": {"type": "number", "exclusiveMinimum": 0, "maximum": 1440},
    },
    ("operation_id", "resource_id", "setup_minutes", "minutes_per_unit", "minutes_per_day"),
    ("owner", "admin"),
)
register(
    "orders_review_quote",
    "Replace every held custom line with firm catalogue pricing and a confirmed physical operation.",
    True,
    {
        "order_id": S,
        "replacements": {
            "type": "array",
            "maxItems": 100,
            "items": {
                "type": "object",
                "properties": {
                    "line_index": {"type": "integer", "minimum": 0},
                    "requests": {"type": "array", "items": {"type": "object"}, "minItems": 1, "maxItems": 100},
                    "operation": {
                        "type": "object",
                        "properties": {"id": S, "description": {"type": "string", "minLength": 1, "maxLength": 4000}},
                        "required": ["id", "description"],
                        "additionalProperties": False,
                    },
                },
                "required": ["line_index", "requests", "operation"],
                "additionalProperties": False,
            },
        },
        "now": S,
    },
    ("order_id", "replacements"),
    ("owner", "admin"),
)
register(
    "orders_confirm_delivery",
    "Record the actual delivery-arrival window and company-confirmed transport terms for a requested order.",
    True,
    {
        "order_id": S,
        "earliest": S,
        "latest": S,
        "terms": S,
        "fee": N,
        "currency": S,
        "included": {"type": "boolean"},
        "vat_rate": {"type": "number", "minimum": 0, "maximum": 1},
    },
    ("order_id", "earliest", "latest", "terms"),
)
register(
    "orders_state",
    "Record an order state transition and inventory movements.",
    True,
    {"order_id": S, "state": {"type": "string", "enum": ["in_progress", "ready", "completed", "cancelled"]}},
    ("order_id", "state"),
)
register(
    "orders_change_time",
    "Record an owner-approved revised promised ready window.",
    True,
    {"order_id": S, "earliest": S, "latest": S},
    ("order_id", "earliest", "latest"),
    ("owner", "admin"),
)
register(
    "orders_record_invoice",
    "Record an invoice that the company has already issued; this does not create or send a document.",
    True,
    {
        "order_id": S,
        "invoice_number": S,
        "issued_at": S,
        "currency": S,
        "amount": N,
        "document_url": S,
    },
    ("order_id", "invoice_number", "issued_at", "currency", "amount", "document_url"),
)
register(
    "orders_draft_message",
    "Create a held message for human approval.",
    True,
    {"order_id": S, "body": S},
    ("order_id", "body"),
)
register(
    "claim_request",
    "Record a pending company claim; identity verification happens separately.",
    True,
    {"email": S, "name": S},
    ("email", "name"),
    PUBLIC,
)
for name, description in [
    ("run_start_stage", "Record the start, agent model and prompt of a stage."),
    ("run_finish_stage", "Record completion with measurements and evidence."),
    ("run_note", "Append an agent observation."),
    ("run_question", "Append a question or a sourced answer."),
    ("run_record", "Record a source-page read or company adapter."),
]:
    props = {"data": {"type": "object"}}
    if name == "run_record":
        props["table"] = {"type": "string", "enum": ["runs", "pages", "page_reads", "adapters"]}
    register(name, description, True, props, tuple(props))
register(
    "run_gate",
    "Evaluate and record a catalogue-count or stock-truth gate.",
    True,
    {"gate": {"type": "string", "enum": ["catalog_counts", "stock_truth"]}, "expected": {"type": "object"}},
    ("gate", "expected"),
)
register(
    "claim_grant",
    "Grant membership after separate verified identity review.",
    True,
    {
        "claim_id": S,
        "role": {"type": "string", "enum": ["owner", "operator"]},
        "verified": {"type": "boolean"},
    },
    ("claim_id", "role", "verified"),
    ("admin",),
)
register(
    "supply_set_plan",
    "Record confirmed or assumed workshop rates and lead allowances.",
    True,
    {
        "resource_id": S,
        "minutes_per_day": N,
        "setup_minutes": N,
        "minutes_per_cut": N,
        "unknown_stock_days": INTEGER,
        "window_workdays": INTEGER,
        "status": {"type": "string", "enum": ["assumed", "confirmed"]},
    },
    (
        "resource_id",
        "minutes_per_day",
        "setup_minutes",
        "minutes_per_cut",
        "unknown_stock_days",
        "window_workdays",
        "status",
    ),
)
for tool in REGISTRY.values():
    if tool["write"]:
        tool["parameters"]["properties"].update({"idempotency_key": S})
        tool["parameters"]["required"].append("idempotency_key")

READ_NAMES = tuple(name for name, tool in REGISTRY.items() if not tool["write"])
WRITE_NAMES = tuple(name for name, tool in REGISTRY.items() if tool["write"])


def specs(write=False):
    return [
        {"name": name, "description": tool["description"], "parameters": tool["parameters"]}
        for name, tool in REGISTRY.items()
        if tool["write"] == write
    ]


def openai_specs(write=False):
    return [{"type": "function", **spec} for spec in specs(write)]


def _validate(value, schema, path="arguments"):
    types = schema.get("type")
    types = [types] if isinstance(types, str) else types
    checks = {
        "string": lambda: isinstance(value, str),
        "number": lambda: isinstance(value, (int, float)) and not isinstance(value, bool),
        "integer": lambda: isinstance(value, int) and not isinstance(value, bool),
        "object": lambda: isinstance(value, dict),
        "array": lambda: isinstance(value, list),
        "boolean": lambda: isinstance(value, bool),
        "null": lambda: value is None,
    }
    if types and not any(checks[t]() for t in types):
        raise ValueError(f"{path}: invalid type")
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError(f"{path}: unsupported value")
    if isinstance(value, dict):
        if any(key not in value for key in schema.get("required", [])):
            raise ValueError(f"{path}: required argument missing")
        for key, item in value.items():
            if key not in schema.get("properties", {}):
                if schema.get("additionalProperties", True) is False:
                    raise ValueError(f"{path}: unexpected argument {key}")
            else:
                _validate(item, schema["properties"][key], path + "." + key)
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0) or len(value) > schema.get("maxItems", float("inf")):
            raise ValueError(f"{path}: invalid list length")
        for item in value:
            _validate(item, schema.get("items", {}), path + "[]")
    if isinstance(value, str) and (
        len(value) < schema.get("minLength", 0) or len(value) > schema.get("maxLength", float("inf"))
    ):
        raise ValueError(f"{path}: invalid string length")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        import math

        if (
            not math.isfinite(value)
            or value < schema.get("minimum", float("-inf"))
            or value > schema.get("maximum", float("inf"))
            or ("exclusiveMinimum" in schema and value <= schema["exclusiveMinimum"])
        ):
            raise ValueError(f"{path}: invalid number")


def _context(context, name, args, write):
    tool = REGISTRY.get(name)
    if not tool or tool["write"] != write:
        raise ValueError("unknown tool or wrong read/write family")
    if context.get("role") not in tool["roles"]:
        raise PermissionError("authenticated role does not permit this tool")
    _validate(args, tool["parameters"])
    if write and (not context.get("actor") or not context.get("evidence")):
        raise ValueError("write context requires actor and evidence")
    return context["store"]


def _item_read(store, item_id):
    result = store.item(item_id)
    item = result["item"]
    company = store.one("SELECT config,catalog_meta FROM company") or {}
    try:
        config = json.loads(company.get("config") or "{}")
        catalog_meta = json.loads(company.get("catalog_meta") or "{}")
    except (TypeError, ValueError):
        config, catalog_meta = {}, {}
    currency = config.get("currency") or catalog_meta.get("currency")
    basis = item.get("priceBasis") or item.get("u")
    basis = {"m": "metre", "kg": "kilogram", "pc": "piece"}.get(basis, basis)
    if not basis:
        basis = "stock_length" if item.get("L") else "piece"
    price = {
        "amount": None if item.get("q") else item.get("p"),
        "currency": currency,
        "basis": basis,
        "status": "confirmation_required" if item.get("q") else "current",
    }
    if basis == "stock_length":
        price.update(basis_quantity=item["L"], basis_unit="m")
    result["measurements"] = {
        **({"dimensions_unit": "mm"} if item.get("d") is not None else {}),
        **({"stock_length_unit": "m"} if item.get("L") is not None else {}),
    }
    result["price"] = price
    if item.get("cut") is not None:
        result["cutting_price"] = {"amount": item["cut"], "currency": currency, "basis": "cut"}
    return result


def read(context, name, args):
    store = _context(context, name, args, False)
    if name == "run_stage_plan":
        try:
            from .manufacturer import stage_plan
        except ImportError:
            from manufacturer import stage_plan
        return stage_plan(args.get("stage"))
    if name == "catalog_find":
        needle = args["query"].casefold()
        matches = []
        for row in store.rows("SELECT id,data,type_id FROM items WHERE active=1 ORDER BY type_id,position"):
            if needle in row["data"].casefold():
                matches.append(_item_read(store, row["id"]))
                if len(matches) >= args.get("limit", 30):
                    break
        return matches
    if name == "catalog_read":
        return _item_read(store, args["item_id"])
    if name == "stock_read":
        return store.supply_projection()
    if name == "quote_ready":
        return quote_ready(store, **args)
    if name == "orders_read":
        return store.read_order(args["order_id"])
    if name == "run_read":
        table = args["table"]
        return store.rows(f"SELECT * FROM {table} ORDER BY rowid DESC LIMIT ?", (args.get("limit", 100),))
    raise ValueError("tool dispatch missing")


def call(context, name, args):
    store = _context(context, name, args, True)
    kwargs = {**args, "actor": context["actor"], "evidence": context["evidence"]}
    if name in {"orders_confirm_operation_capacity", "orders_review_quote"}:
        try:
            from .reviewed_orders import confirm_operation_capacity, review_order
        except ImportError:
            from reviewed_orders import confirm_operation_capacity, review_order
        method = {
            "orders_confirm_operation_capacity": confirm_operation_capacity,
            "orders_review_quote": review_order,
        }[name]
        return method(store, **kwargs)
    methods = {
        "catalog_set_price": "set_price",
        "catalog_set_selling": "set_selling",
        "stock_record": "record_stock",
        "capacity_event": "capacity_event",
        "calendar_exception": "set_exception",
        "orders_submit": "submit_order",
        "orders_accept": "accept_order",
        "orders_confirm_delivery": "confirm_delivery",
        "orders_state": "mark_order",
        "orders_change_time": "change_time",
        "orders_record_invoice": "record_invoice",
        "orders_draft_message": "draft_message",
        "claim_request": "request_claim",
        "claim_grant": "grant_member",
        "supply_set_plan": "set_supply_plan",
    }
    if name in methods:
        return getattr(store, methods[name])(**kwargs)
    if name == "run_gate":
        if args["gate"] == "catalog_counts":
            actual = {
                "types": store.one("SELECT COUNT(*) AS n FROM product_types WHERE active=1")["n"],
                "items": store.one("SELECT COUNT(*) AS n FROM items WHERE active=1")["n"],
            }
        else:
            actual = {
                "invalid": store.one(
                    "SELECT COUNT(*) AS n FROM stock WHERE (state IN ('listed','unknown') AND quantity IS NOT NULL) OR reserved<0 OR quantity<0"
                )["n"]
            }
        data = {
            "gate": args["gate"],
            "expected": args["expected"],
            "actual": actual,
            "passed": actual == args["expected"],
        }
        store.record("stage_runs", data, context["actor"], context["evidence"], args["idempotency_key"])
        return data
    table = {
        "run_start_stage": "stage_runs",
        "run_finish_stage": "stage_runs",
        "run_note": "agent_notes",
        "run_question": "questions",
    }.get(name, args.get("table"))
    data = dict(args["data"])
    data["action"] = name
    return store.record(table, data, context["actor"], context["evidence"], args["idempotency_key"])
