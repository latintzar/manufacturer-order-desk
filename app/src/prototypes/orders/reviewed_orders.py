"""Atomic operator review and exact customer assent for held order requests."""

from __future__ import annotations

import copy
import hashlib
import json
import math
import subprocess
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

try:
    from .store import dump, stamp
    from .supply import quote_ready
except ImportError:
    from store import dump, stamp
    from supply import quote_ready


HERE = Path(__file__).resolve().parent


def _finite(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    return value


def _money(value):
    return float(
        Decimal(str(_finite(value, "money amount"))).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
    )


def _goods_breakdown(quote):
    breakdown = quote.get("breakdown")
    if isinstance(breakdown, dict) and isinstance(breakdown.get("goods"), dict):
        goods = breakdown["goods"]
        return {key: _money(goods[key]) for key in ("net", "vat", "gross")}
    gross = _money(quote.get("gross", 0))
    net = _money(quote["net"]) if isinstance(quote.get("net"), (int, float)) else gross
    vat = _money(quote["vat"]) if isinstance(quote.get("vat"), (int, float)) else _money(gross - net)
    return {"net": net, "vat": vat, "gross": gross}


def _delivery_breakdown(quote):
    breakdown = quote.get("breakdown")
    if not isinstance(breakdown, dict) or not isinstance(breakdown.get("delivery"), dict):
        return {"included": True, "net": 0, "vat": 0, "gross": 0}
    delivery = breakdown["delivery"]
    if delivery.get("included"):
        return {"included": True, "net": 0, "vat": 0, "gross": 0}
    return {
        "net": _money(delivery["net"]),
        "vat": _money(delivery["vat"]),
        "gross": _money(delivery["gross"]),
        "vat_rate": _finite(delivery["vat_rate"], "delivery VAT rate"),
        "currency": delivery["currency"],
    }


def _with_breakdown(quote, goods, delivery):
    quote = copy.deepcopy(quote)
    quote["breakdown"] = {"goods": goods, "delivery": delivery}
    quote["net"] = _money(goods["net"] + delivery["net"])
    quote["vat"] = _money(goods["vat"] + delivery["vat"])
    quote["gross"] = _money(goods["gross"] + delivery["gross"])
    return quote


def apply_delivery_commercial_review(order_id, previous_quote, delivery, actor):
    """Add an actual delivery fee to payable totals and require assent when that total changes."""
    quote = copy.deepcopy(previous_quote)
    goods = _goods_breakdown(previous_quote)
    fee = delivery["fee"]
    if fee.get("included"):
        delivery_amounts = {"included": True, "net": 0, "vat": 0, "gross": 0}
        previous_delivery = _delivery_breakdown(previous_quote)
        if previous_delivery["gross"] == 0:
            quote["breakdown"] = {"goods": goods, "delivery": delivery_amounts}
            quote["delivery"] = delivery
            return quote, False
    else:
        if fee["currency"] != quote.get("currency"):
            raise ValueError("delivery fee currency must match the quoted currency")
        rate = _finite(fee.get("vat_rate"), "delivery VAT rate")
        if not 0 <= rate <= 1:
            raise ValueError("delivery VAT rate must be between 0 and 1")
        gross = _money(fee["amount"])
        net = _money(gross / (1 + rate))
        delivery_amounts = {
            "net": net,
            "vat": _money(gross - net),
            "gross": gross,
            "vat_rate": rate,
            "currency": fee["currency"],
        }
    quote = _with_breakdown(quote, goods, delivery_amounts)
    quote["delivery"] = delivery
    existing_review = previous_quote.get("review")
    old_known = previous_quote.get("confirmation") is not True or (
        isinstance(existing_review, dict)
        and existing_review.get("state") in {"awaiting_customer", "assented"}
        and existing_review.get("gross") == previous_quote.get("gross")
    )
    old_gross = previous_quote.get("gross")
    changed = not (
        old_known
        and isinstance(old_gross, (int, float))
        and math.isfinite(old_gross)
        and previous_quote.get("currency", quote.get("currency")) == quote.get("currency")
        and abs(old_gross - quote["gross"]) < 0.005
    )
    if changed:
        review_id = hashlib.sha256(
            dump([order_id, previous_quote, delivery, actor, stamp()]).encode("utf-8")
        ).hexdigest()[:24]
        quote["confirmation"] = True
        quote["review"] = {
            "id": review_id,
            "state": "awaiting_customer",
            "assent_required": True,
            "reason": "delivery_fee",
            "previous_gross": old_gross if old_known else None,
            "gross": quote["gross"],
            "currency": quote.get("currency"),
        }
    return quote, changed


def _catalog_item(catalog, item_id):
    for category in catalog.get("cats", []):
        for item in category.get("items", []):
            if item.get("c") == item_id:
                return item
    raise ValueError(f"unknown catalogue item {item_id}")


def _override(store, item_id, basis):
    row = store.one(
        "SELECT p.id,p.item_id,p.basis,p.amount,p.actor,p.evidence,p.created_at "
        "FROM price_overrides o JOIN prices p ON p.id=o.price_id "
        "WHERE o.item_id=? AND o.basis=?",
        (item_id, basis),
    )
    if row is None:
        raise ValueError(f"record a confirmed {basis} price override for {item_id}")
    return row


def _run_quote(catalog, requests):
    try:
        process = subprocess.run(
            ["node", str(HERE / "quote.mjs")],
            input=json.dumps({"catalog": catalog, "lines": requests}),
            text=True,
            capture_output=True,
            check=False,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ValueError("run the reviewed quote engine") from error
    if process.returncode:
        message = process.stderr.strip().splitlines()[-1] if process.stderr.strip() else "quote failed"
        raise ValueError(message) from None
    try:
        return json.loads(process.stdout)
    except (TypeError, json.JSONDecodeError) as error:
        raise ValueError("reviewed quote engine returned invalid data") from error


def reviewed_price_is_firm(store, line):
    """Verify immutable price rows captured by this module for one reviewed line."""
    review = line.get("review")
    if (
        not isinstance(review, dict)
        or not isinstance(review.get("id"), str)
        or review.get("item_id") != line.get("item_id")
        or line.get("kind") == "custom"
        or line.get("confirmation")
        or line.get("plan", {}).get("pending")
    ):
        return False
    required = {"p"} | ({"cut"} if line.get("cuts", 0) > 0 else set())
    references = review.get("prices")
    if not isinstance(references, list) or {row.get("basis") for row in references} != required:
        return False
    for reference in references:
        row = store.one(
            "SELECT item_id,basis,amount FROM prices WHERE id=?", (reference.get("price_id"),)
        )
        if (
            row is None
            or row["item_id"] != line["item_id"]
            or row["basis"] != reference["basis"]
            or row["amount"] != reference.get("amount")
        ):
            return False
    return True


def commercially_resolved(store, order):
    """Return whether acceptance may treat every recorded line price as firm."""
    if order.get("quote", {}).get("confirmation"):
        return False
    for line in order.get("lines", []):
        if line.get("kind") == "custom" or line.get("confirmation") or line.get("plan", {}).get("pending"):
            return False
        if (
            line.get("item_id")
            and store.item(line["item_id"])["item"].get("q")
            and not reviewed_price_is_firm(store, line)
        ):
            return False
    return True


def confirm_operation_capacity(
    store,
    operation_id,
    resource_id,
    setup_minutes,
    minutes_per_unit,
    minutes_per_day,
    actor,
    evidence,
    idempotency_key,
):
    """Record operator-confirmed physical time inputs used by reviewed order plans."""
    if operation_id != "cut":
        raise ValueError("the current physical quote engine supports the cut operation")
    for value, name in (
        (setup_minutes, "setup minutes"),
        (minutes_per_unit, "minutes per cut"),
        (minutes_per_day, "minutes per day"),
    ):
        _finite(value, name)
        if value < 0 or name == "minutes per day" and not 0 < value <= 1440:
            raise ValueError(f"{name} is outside the physical capacity range")
    payload = {
        "operation_id": operation_id,
        "resource_id": resource_id,
        "setup_minutes": setup_minutes,
        "minutes_per_unit": minutes_per_unit,
        "minutes_per_day": minutes_per_day,
    }

    def update():
        operation = store.one("SELECT data FROM operations WHERE id=?", (operation_id,))
        resource = store.one("SELECT data FROM resources WHERE id=?", (resource_id,))
        if operation is None or resource is None:
            raise ValueError("choose an existing operation and resource")
        operation_data = {
            **json.loads(operation["data"]),
            "status": "confirmed",
            "setup_minutes": setup_minutes,
            "minutes_per_cut": minutes_per_unit,
        }
        resource_data = {
            **json.loads(resource["data"]),
            "status": "confirmed",
            "minutes_per_day": minutes_per_day,
        }
        store.db.execute(
            "UPDATE operations SET resource_id=?,data=? WHERE id=?",
            (resource_id, dump(operation_data), operation_id),
        )
        store.db.execute("UPDATE resources SET data=? WHERE id=?", (dump(resource_data), resource_id))
        return {
            "operation_id": operation_id,
            "resource_id": resource_id,
            "setup_minutes": setup_minutes,
            "minutes_per_unit": minutes_per_unit,
            "minutes_per_day": minutes_per_day,
            "status": "confirmed",
        }

    return store._write(
        "orders.confirm_operation_capacity", payload, actor, evidence, idempotency_key, update
    )


def _unresolved(store, line):
    if line.get("kind") == "custom" or line.get("confirmation") or line.get("plan", {}).get("pending"):
        return True
    return bool(
        line.get("item_id")
        and store.item(line["item_id"])["item"].get("q")
        and not reviewed_price_is_firm(store, line)
    )


def _replacement_map(store, order, replacements):
    if not isinstance(replacements, list) or len(replacements) > 100:
        raise ValueError("review replacements must be a list of at most 100 entries")
    mapped = {}
    for replacement in replacements:
        if not isinstance(replacement, dict) or set(replacement) != {
            "line_index",
            "requests",
            "operation",
        }:
            raise ValueError("each replacement names line_index, requests and operation")
        index = replacement["line_index"]
        if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(order["lines"]):
            raise ValueError("replacement line_index is outside this order")
        if index in mapped:
            raise ValueError("replace each original line once")
        requests = replacement["requests"]
        if not isinstance(requests, list) or not 1 <= len(requests) <= 100:
            raise ValueError("replacement requests require 1 to 100 catalogue lines")
        if any(not isinstance(request, dict) or request.get("custom") for request in requests):
            raise ValueError("review replacements use current catalogue items")
        operation = replacement["operation"]
        if not isinstance(operation, dict) or set(operation) != {"id", "description"}:
            raise ValueError("replacement operation requires id and description")
        if operation["id"] != "cut":
            raise ValueError("the current physical quote engine supports the cut operation")
        description = operation["description"]
        if not isinstance(description, str) or not 1 <= len(description.strip()) <= 4000:
            raise ValueError("operation description is required")
        operation_row = store.one("SELECT resource_id,data FROM operations WHERE id=?", (operation["id"],))
        if operation_row is None or json.loads(operation_row["data"]).get("status") != "confirmed":
            raise ValueError("confirm the operation before reviewing the order")
        resource = store.one("SELECT data FROM resources WHERE id=?", (operation_row["resource_id"],))
        if resource is None or json.loads(resource["data"]).get("status") != "confirmed":
            raise ValueError("confirm the operation resource before reviewing the order")
        mapped[index] = {
            "requests": requests,
            "operation": {**operation, "description": description.strip()},
            "resource_id": operation_row["resource_id"],
        }
    required = {index for index, line in enumerate(order["lines"]) if _unresolved(store, line)}
    if not required.issubset(mapped):
        raise ValueError("replace every unresolved commercial line in one reviewed quote")
    for index in mapped:
        line = order["lines"][index]
        current_review = order["quote"].get("review", {}).get("id")
        if not _unresolved(store, line) and line.get("review", {}).get("id") != current_review:
            raise ValueError("review replacements may change only held lines from this order")
    return mapped


def review_order(
    store,
    order_id,
    replacements,
    actor,
    evidence,
    idempotency_key,
    *,
    now=None,
):
    """Replace held lines with a firm physical quote while preserving the order capability."""
    if not idempotency_key:
        raise ValueError("idempotency key required")
    payload = {
        "order_id": order_id,
        "replacements": replacements,
        "now": now,
    }

    def update():
        order = store.read_order(order_id)
        if order["state"] != "requested":
            raise ValueError("only requested orders can receive a reviewed quote")
        mapped = _replacement_map(store, order, replacements)
        review_id = hashlib.sha256(
            dump([order_id, payload, actor, stamp()]).encode("utf-8")
        ).hexdigest()[:24]
        catalog = store.export_catalog()
        catalog["currency"] = order["quote"].get("currency", catalog.get("currency", "EUR"))
        catalog["vat"] = catalog.get(
            "vat", order["quote"].get("vat_rate", catalog.get("rules", {}).get("vat", 0))
        )
        flat_requests = []
        ranges = {}
        for index, replacement in mapped.items():
            start = len(flat_requests)
            for request in replacement["requests"]:
                code = request.get("code")
                _override(store, code, "p")
                _catalog_item(catalog, code)["q"] = False
                flat_requests.append(copy.deepcopy(request))
            ranges[index] = (start, len(flat_requests))
        priced = _run_quote(catalog, flat_requests) if flat_requests else {"lines": []}
        if len(priced.get("lines", [])) != len(flat_requests):
            raise ValueError("reviewed quote did not return every replacement line")

        lines = []
        review_records = []
        for index, original in enumerate(order["lines"]):
            if index not in mapped:
                lines.append(copy.deepcopy(original))
                continue
            replacement = mapped[index]
            start, stop = ranges[index]
            produced = []
            for line in priced["lines"][start:stop]:
                if line.get("confirmation") or line.get("plan", {}).get("pending"):
                    raise ValueError("replacement still has unresolved commercial pricing")
                references = [_override(store, line["item_id"], "p")]
                if line.get("cuts", 0) > 0:
                    references.append(_override(store, line["item_id"], "cut"))
                price_refs = [
                    {
                        "price_id": reference["id"],
                        "basis": reference["basis"],
                        "amount": reference["amount"],
                    }
                    for reference in references
                ]
                line["resource_id"] = replacement["resource_id"]
                line["confirmation"] = False
                line["review"] = {
                    "id": review_id,
                    "original_line_index": index,
                    "item_id": line["item_id"],
                    "operation": replacement["operation"],
                    "prices": price_refs,
                }
                produced.append(line)
                lines.append(line)
            review_records.append(
                {
                    "original_line_index": index,
                    "original_line": original,
                    "operation": replacement["operation"],
                    "reviewed_lines": produced,
                }
            )
        if len(lines) > 200:
            raise ValueError("reviewed order exceeds 200 lines")
        store.validate_lines(lines)
        ready = quote_ready(store, lines, now)

        previous_quote = copy.deepcopy(order["quote"])
        if mapped:
            goods_gross = _money(
                sum(_finite(line.get("gross"), "line gross") for line in lines)
            )
            vat_rate = _finite(catalog["vat"], "VAT rate")
            goods_net = _money(goods_gross / (1 + vat_rate))
            quote = {
                **previous_quote,
                "currency": catalog["currency"],
                "vat_rate": vat_rate,
            }
            goods = {
                "gross": goods_gross,
                "net": goods_net,
                "vat": _money(goods_gross - goods_net),
            }
            quote = _with_breakdown(quote, goods, _delivery_breakdown(previous_quote))
        else:
            quote = copy.deepcopy(previous_quote)
            quote = _with_breakdown(
                quote, _goods_breakdown(previous_quote), _delivery_breakdown(previous_quote)
            )
        gross = _finite(quote.get("gross"), "quoted gross")
        old_total_known = previous_quote.get("confirmation") is not True
        same_total = (
            old_total_known
            and previous_quote.get("currency", quote.get("currency")) == quote.get("currency")
            and isinstance(previous_quote.get("gross"), (int, float))
            and abs(previous_quote["gross"] - gross) < 0.005
        )
        assent_required = not same_total
        quote["confirmation"] = assent_required
        quote["review"] = {
            "id": review_id,
            "state": "awaiting_customer" if assent_required else "not_required",
            "assent_required": assent_required,
            "previous_gross": previous_quote.get("gross") if old_total_known else None,
            "gross": gross,
            "currency": quote.get("currency"),
        }
        store.db.execute("DELETE FROM order_lines WHERE order_id=?", (order_id,))
        for line in lines:
            store.db.execute(
                "INSERT INTO order_lines(order_id,item_id,quantity,data) VALUES(?,?,?,?)",
                (order_id, line["item_id"], line["quantity"], dump(line)),
            )
        store.db.execute("UPDATE orders SET quote=? WHERE id=?", (dump(quote), order_id))
        store._event(
            "order_events",
            {
                "review_id": review_id,
                "previous_quote": previous_quote,
                "reviewed_quote": quote,
                "replacements": review_records,
                "ready": ready,
            },
            actor,
            evidence,
            order_id=order_id,
            event="quote_reviewed",
        )
        store._event("estimates", ready, actor, evidence, order_id=order_id, kind="estimate")
        return {
            "id": order_id,
            "state": "requested",
            "review_id": review_id,
            "assent_required": assent_required,
            "quote": quote,
            "ready": ready,
        }

    return store._write("orders.review_quote", payload, actor, evidence, idempotency_key, update)


def assent_reviewed_quote(store, order_id, review_id, actor, evidence, idempotency_key):
    """Record customer assent to the exact current reviewed commercial total."""
    if not idempotency_key:
        raise ValueError("idempotency key required")
    payload = {"order_id": order_id, "review_id": review_id}

    def update():
        order = store.read_order(order_id)
        if order["state"] != "requested":
            raise ValueError("only a requested order can receive quote assent")
        quote = order["quote"]
        review = quote.get("review")
        if (
            not isinstance(review, dict)
            or review.get("id") != review_id
            or review.get("state") != "awaiting_customer"
            or not review.get("assent_required")
        ):
            raise ValueError("assent must name the current reviewed quote")
        if any(
            line.get("kind") == "custom"
            or line.get("confirmation")
            or line.get("plan", {}).get("pending")
            for line in order["lines"]
        ):
            raise ValueError("the reviewed order still has unresolved commercial lines")
        if not all(
            not line.get("item_id")
            or not store.item(line["item_id"])["item"].get("q")
            or reviewed_price_is_firm(store, line)
            for line in order["lines"]
        ):
            raise ValueError("reviewed prices are no longer verifiable")
        quote = copy.deepcopy(quote)
        quote["confirmation"] = False
        quote["review"] = {**review, "state": "assented"}
        store.db.execute("UPDATE orders SET quote=? WHERE id=?", (dump(quote), order_id))
        store._event(
            "order_events",
            {"review_id": review_id, "gross": quote.get("gross"), "currency": quote.get("currency")},
            actor,
            evidence,
            order_id=order_id,
            event="quote_assented",
        )
        return {"id": order_id, "state": "requested", "review_id": review_id, "quote": quote}

    return store._write("orders.assent_quote", payload, actor, evidence, idempotency_key, update)
