"""One deterministic, timezone-aware ready-window engine for tools and HTTP callers."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

ZONE = ZoneInfo("Europe/Sofia")
DATE_DEPENDENCIES = {"stock", "capacity", "resource", "backlog", "lead", "custom"}


def public_ready(ready):
    """Project dates only when the operational inputs behind them are confirmed."""
    timezone = ready.get("timezone", "Europe/Sofia") if isinstance(ready, dict) else "Europe/Sofia"
    if not isinstance(ready, dict):
        return {"kind": "confirmation", "timezone": timezone}
    if ready.get("kind") == "promise":
        return {
            key: ready[key]
            for key in ("kind", "earliest", "latest", "timezone")
            if key in ready
        }
    assumptions = ready.get("assumptions", [])
    depends_on_unconfirmed = any(
        assumption.get(
            "affects_public_date", assumption.get("kind") in DATE_DEPENDENCIES
        )
        for assumption in assumptions
        if isinstance(assumption, dict)
    )
    if depends_on_unconfirmed or not ready.get("earliest") or not ready.get("latest"):
        return {"kind": "confirmation", "timezone": timezone}
    return {
        key: ready[key]
        for key in ("kind", "earliest", "latest", "timezone")
        if key in ready
    }


def local_time(value=None):
    if value is None:
        return datetime.now(ZONE)
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None:
        raise ValueError("now must include timezone")
    return value.astimezone(ZONE)


def interval(store, day):
    exception = store.one("SELECT * FROM calendar_exceptions WHERE day=?", (day.isoformat(),))
    if exception:
        return None if exception["closed"] else (exception["opens"], exception["closes"], exception["closes"])
    row = store.one("SELECT * FROM calendar WHERE weekday=?", (day.isoweekday(),))
    return (row["opens"], row["closes"], row["cutoff"]) if row else None


def next_open(store, day, include=True):
    for offset in range(0 if include else 1, 367):
        candidate = day + timedelta(days=offset)
        if interval(store, candidate):
            return candidate
    raise ValueError("calendar has no working day in the next year")


def workdays_after(store, day, count):
    for _ in range(count):
        day = next_open(store, day, False)
    return day


def at(day, minutes):
    return datetime.combine(day, time(), ZONE) + timedelta(minutes=minutes)


def quote_ready(store, lines, now=None):
    store.validate_lines(lines)
    current = local_time(now)
    lead = json.loads(store.one("SELECT data FROM lead_rules WHERE id='default'")["data"])
    stock_demand = defaultdict(float)
    workload = defaultdict(float)
    assumptions = []
    op = json.loads(store.one("SELECT data FROM operations WHERE id='cut'")["data"])
    for line in lines:
        if line.get("kind") == "custom":
            assumptions.append(
                {
                    "kind": "custom",
                    "text": "Custom work requires company pricing and a production schedule.",
                    "affects_public_date": True,
                }
            )
        else:
            stock_demand[line["item_id"]] += line["quantity"]
        workload[line.get("resource_id", "workshop")] += (
            op["setup_minutes"] + line.get("cuts", 0) * op["minutes_per_cut"]
        )
        if line.get("kind") != "custom" and store.item(line["item_id"])["selling"]["status"] != "confirmed":
            assumptions.append(
                {
                    "kind": "selling",
                    "item_id": line["item_id"],
                    "text": "Minimum quantity, quantity step and pack await company confirmation.",
                }
            )
    if op.get("status") != "confirmed":
        assumptions.append(
            {
                "kind": "capacity",
                "text": "Workshop setup and cutting minutes are assumed.",
                "affects_public_date": True,
            }
        )
    first = next_open(store, current.date())
    hours = interval(store, first)
    if first == current.date() and current.hour * 60 + current.minute >= hours[2]:
        first = next_open(store, first, False)
    start = first
    stock = []
    for item_id, quantity in stock_demand.items():
        row = store.one("SELECT * FROM stock WHERE item_id=?", (item_id,))
        known = row["state"] in ("known", "out") and row["quantity"] is not None
        available = max(0, row["quantity"] - row["reserved"]) if known else None
        stock.append(
            {"item_id": item_id, "required": quantity, "available": available, "state": row["state"]}
        )
        if available is None or available < quantity:
            reason = (
                "Stock quantity awaits company confirmation."
                if available is None
                else "Additional stock is required."
            )
            assumptions.append(
                {
                    "kind": "stock",
                    "item_id": item_id,
                    "text": reason,
                    "affects_public_date": row["status"] != "confirmed"
                    or (not row["restock_date"] and lead.get("status") != "confirmed"),
                }
            )
            if row["restock_date"]:
                arrival = next_open(store, max(first, date.fromisoformat(row["restock_date"])))
            else:
                arrival = workdays_after(store, first, int(lead["unknown_stock_days"]))
                assumptions.append(
                    {
                        "kind": "lead",
                        "item_id": item_id,
                        "text": f"Replenishment allowance is assumed at {lead['unknown_stock_days']} working days.",
                        "affects_public_date": lead.get("status") != "confirmed",
                    }
                )
            start = max(start, arrival)
    allocation = []
    finishes = []
    for resource_id, minutes in workload.items():
        resource = json.loads(store.one("SELECT data FROM resources WHERE id=?", (resource_id,))["data"])
        if resource.get("status") != "confirmed":
            assumptions.append(
                {
                    "kind": "resource",
                    "resource_id": resource_id,
                    "text": "Daily workshop capacity awaits company confirmation.",
                    "affects_public_date": True,
                }
            )
        # The inherited demo backlog is a one-time planning assumption ahead of this quote.
        backlog = lead.get("initial_backlog_minutes", 0)
        if backlog:
            assumptions.append(
                {
                    "kind": "backlog",
                    "resource_id": resource_id,
                    "text": f"{backlog} minutes of existing workload are assumed.",
                    "affects_public_date": True,
                }
            )
        day = start
        for _ in range(366):
            hours = interval(store, day)
            if not hours:
                day += timedelta(days=1)
                continue
            opens, closes, _ = hours
            earliest = (
                max(opens, current.hour * 60 + current.minute + current.second / 60)
                if day == current.date()
                else opens
            )
            used = store.one(
                "SELECT COALESCE(SUM(minutes),0) AS n FROM capacity_load WHERE resource_id=? AND day=?",
                (resource_id, day.isoformat()),
            )["n"]
            unavailable = store.one(
                "SELECT COALESCE(SUM(minutes),0) AS n FROM capacity_events WHERE resource_id=? AND day=?",
                (resource_id, day.isoformat()),
            )["n"]
            capacity = max(0, min(closes - earliest, resource["minutes_per_day"]) - used - unavailable)
            consumed = min(backlog, capacity)
            backlog -= consumed
            capacity -= consumed
            assigned = min(minutes, capacity)
            if assigned > 0:
                allocation.append({"resource_id": resource_id, "day": day.isoformat(), "minutes": assigned})
                minutes -= assigned
            if minutes <= 1e-9:
                finishes.append(at(day, min(closes, earliest + used + unavailable + consumed + assigned)))
                break
            day += timedelta(days=1)
        else:
            raise ValueError("workload exceeds the one-year capacity horizon")
    earliest = max(finishes)
    latest_day = workdays_after(store, earliest.date(), int(lead.get("window_workdays", 2)))
    latest = at(latest_day, interval(store, latest_day)[1])
    return {
        "kind": "estimate",
        "earliest": earliest.isoformat(),
        "latest": latest.isoformat(),
        "timezone": "Europe/Sofia",
        "assumptions": assumptions,
        "stock": stock,
        "allocation": allocation,
        "inputs": {"as_of": current.isoformat(), "lines": lines, "lead_rules": lead},
    }
