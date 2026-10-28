"""Private per-company SQLite record. Current projections and immutable evidence coexist."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit


def dump(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def stamp():
    return datetime.now(timezone.utc).isoformat()


def number(value, name, minimum=0):
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value < minimum
    ):
        raise ValueError(f"{name} must be a finite number >= {minimum}")
    return value


SCHEMA = """
CREATE TABLE IF NOT EXISTS company(id TEXT PRIMARY KEY, config TEXT NOT NULL, catalog_meta TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS members(id TEXT PRIMARY KEY, email TEXT NOT NULL, role TEXT NOT NULL, verified_at TEXT NOT NULL, evidence TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS claims(id TEXT PRIMARY KEY,email TEXT NOT NULL,name TEXT NOT NULL,status TEXT NOT NULL,actor TEXT NOT NULL,evidence TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sources(id TEXT PRIMARY KEY,kind TEXT NOT NULL,url TEXT,printed_date TEXT,rank INTEGER,refresh TEXT,data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS source_rows(id INTEGER PRIMARY KEY,source_id TEXT REFERENCES sources(id),item_id TEXT,status TEXT NOT NULL,reason TEXT,data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS product_types(id TEXT PRIMARY KEY,position INTEGER NOT NULL,data TEXT NOT NULL,active INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS items(id TEXT PRIMARY KEY,type_id TEXT NOT NULL REFERENCES product_types(id),position INTEGER NOT NULL,data TEXT NOT NULL,active INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS prices(id INTEGER PRIMARY KEY,item_id TEXT NOT NULL REFERENCES items(id),basis TEXT NOT NULL,amount REAL NOT NULL,actor TEXT NOT NULL,evidence TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS price_current ON prices(item_id,basis,id DESC);
CREATE TABLE IF NOT EXISTS price_overrides(item_id TEXT NOT NULL REFERENCES items(id),basis TEXT NOT NULL,price_id INTEGER NOT NULL REFERENCES prices(id),PRIMARY KEY(item_id,basis));
CREATE TABLE IF NOT EXISTS selling(item_id TEXT PRIMARY KEY REFERENCES items(id),minimum REAL NOT NULL,step REAL NOT NULL,pack REAL NOT NULL,status TEXT NOT NULL,data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS rules(id TEXT PRIMARY KEY,status TEXT NOT NULL,data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS services(id TEXT PRIMARY KEY,position INTEGER NOT NULL,data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS stock(item_id TEXT PRIMARY KEY REFERENCES items(id),state TEXT NOT NULL,quantity REAL,reserved REAL NOT NULL DEFAULT 0,restock_date TEXT,status TEXT NOT NULL,actor TEXT NOT NULL,evidence TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS stock_events(id INTEGER PRIMARY KEY,item_id TEXT NOT NULL,event TEXT NOT NULL,data TEXT NOT NULL,actor TEXT NOT NULL,evidence TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS resources(id TEXT PRIMARY KEY,data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS operations(id TEXT PRIMARY KEY,resource_id TEXT NOT NULL REFERENCES resources(id),data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS calendar(weekday INTEGER PRIMARY KEY,opens INTEGER NOT NULL,closes INTEGER NOT NULL,cutoff INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS calendar_exceptions(day TEXT PRIMARY KEY,closed INTEGER NOT NULL,opens INTEGER,closes INTEGER,data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS capacity_events(id INTEGER PRIMARY KEY,resource_id TEXT NOT NULL REFERENCES resources(id),day TEXT NOT NULL,minutes REAL NOT NULL,data TEXT NOT NULL,actor TEXT NOT NULL,evidence TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS capacity_load(id INTEGER PRIMARY KEY,order_id TEXT NOT NULL,resource_id TEXT NOT NULL,day TEXT NOT NULL,minutes REAL NOT NULL,event TEXT NOT NULL DEFAULT 'book',actor TEXT NOT NULL,evidence TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS lead_rules(id TEXT PRIMARY KEY,data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS customers(id TEXT PRIMARY KEY,data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS orders(id TEXT PRIMARY KEY,customer_id TEXT NOT NULL REFERENCES customers(id),state TEXT NOT NULL,quote TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS order_lines(id INTEGER PRIMARY KEY,order_id TEXT NOT NULL REFERENCES orders(id),item_id TEXT REFERENCES items(id),quantity REAL NOT NULL,data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS order_files(id TEXT PRIMARY KEY,upload_key TEXT NOT NULL UNIQUE,order_id TEXT REFERENCES orders(id),name TEXT NOT NULL,content_type TEXT NOT NULL,size INTEGER NOT NULL,sha256 TEXT NOT NULL,created_at REAL NOT NULL,claimed_at TEXT);
CREATE INDEX IF NOT EXISTS order_files_order ON order_files(order_id,id);
CREATE TRIGGER IF NOT EXISTS immutable_claimed_order_file_update BEFORE UPDATE ON order_files WHEN OLD.order_id IS NOT NULL BEGIN SELECT RAISE(ABORT,'claimed order file is immutable'); END;
CREATE TRIGGER IF NOT EXISTS immutable_claimed_order_file_delete BEFORE DELETE ON order_files WHEN OLD.order_id IS NOT NULL BEGIN SELECT RAISE(ABORT,'claimed order file is immutable'); END;
CREATE TABLE IF NOT EXISTS order_events(id INTEGER PRIMARY KEY,order_id TEXT NOT NULL REFERENCES orders(id),event TEXT NOT NULL,data TEXT NOT NULL,actor TEXT NOT NULL,evidence TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS estimates(id INTEGER PRIMARY KEY,order_id TEXT REFERENCES orders(id),kind TEXT NOT NULL,data TEXT NOT NULL,actor TEXT NOT NULL,evidence TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS invoices(id TEXT PRIMARY KEY,order_id TEXT NOT NULL UNIQUE REFERENCES orders(id),number TEXT NOT NULL,issued_at TEXT NOT NULL,currency TEXT NOT NULL,amount REAL NOT NULL,document_url TEXT NOT NULL,actor TEXT NOT NULL,evidence TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS messages(id TEXT PRIMARY KEY,order_id TEXT NOT NULL REFERENCES orders(id),status TEXT NOT NULL CHECK(status='held'),body TEXT NOT NULL,actor TEXT NOT NULL,evidence TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY,action TEXT NOT NULL,data TEXT NOT NULL,actor TEXT NOT NULL,evidence TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS idempotency(key TEXT PRIMARY KEY,digest TEXT NOT NULL,result TEXT NOT NULL);
"""
RECORD_TABLES = ("runs", "stage_runs", "pages", "page_reads", "adapters", "questions", "agent_notes")
IMMUTABLE = (
    "prices",
    "stock_events",
    "capacity_events",
    "capacity_load",
    "order_events",
    "estimates",
    "invoices",
    "messages",
    "audit",
    "source_rows",
)


class CompanyStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(self.path), timeout=30, isolation_level=None)
        os.chmod(self.path, 0o600)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA journal_mode=WAL")
        had_overrides = self.one(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='price_overrides'"
        )
        self.db.executescript(SCHEMA)
        if not had_overrides:
            # Recover explicit owner edits from the previous schema's immutable audit.
            for event in self.rows(
                "SELECT data,actor,created_at FROM audit WHERE action='catalog.set_price' ORDER BY id"
            ):
                payload = json.loads(event["data"])["input"]
                price = self.one(
                    "SELECT id FROM prices WHERE item_id=? AND basis=? AND amount=? AND actor=? AND created_at<=? ORDER BY id DESC LIMIT 1",
                    (
                        payload["item_id"],
                        payload.get("basis", "p"),
                        payload["amount"],
                        event["actor"],
                        event["created_at"],
                    ),
                )
                if price:
                    self.db.execute(
                        "INSERT OR REPLACE INTO price_overrides VALUES(?,?,?)",
                        (payload["item_id"], payload.get("basis", "p"), price["id"]),
                    )
        for table in RECORD_TABLES:
            self.db.execute(
                f"CREATE TABLE IF NOT EXISTS {table}(id INTEGER PRIMARY KEY,data TEXT NOT NULL,actor TEXT NOT NULL,evidence TEXT NOT NULL,created_at TEXT NOT NULL)"
            )
        for table in IMMUTABLE + RECORD_TABLES:
            for action in ("UPDATE", "DELETE"):
                self.db.execute(
                    f"CREATE TRIGGER IF NOT EXISTS immutable_{table}_{action} BEFORE {action} ON {table} BEGIN SELECT RAISE(ABORT,'append-only record'); END"
                )

    def close(self):
        self.db.close()

    def rows(self, sql, args=()):
        return [dict(row) for row in self.db.execute(sql, args)]

    def one(self, sql, args=()):
        row = self.db.execute(sql, args).fetchone()
        return dict(row) if row else None

    def _event(self, table, data, actor, evidence, **columns):
        if not actor or not evidence:
            raise ValueError("actor and evidence are required")
        values = {**columns, "data": dump(data), "actor": actor, "evidence": evidence, "created_at": stamp()}
        names = ",".join(values)
        return self.db.execute(
            f"INSERT INTO {table}({names}) VALUES({','.join('?' for _ in values)})", tuple(values.values())
        ).lastrowid

    def _write(self, action, payload, actor, evidence, key, operation):
        if not actor or not evidence:
            raise ValueError("actor and evidence are required")
        digest = hashlib.sha256(dump([action, payload, actor]).encode()).hexdigest()
        self.db.execute("BEGIN IMMEDIATE")
        try:
            if key:
                old = self.one("SELECT * FROM idempotency WHERE key=?", (key,))
                if old:
                    if old["digest"] != digest:
                        raise ValueError("idempotency key reused with different input")
                    self.db.execute("COMMIT")
                    return json.loads(old["result"])
            result = operation()
            self._event("audit", {"input": payload, "result": result}, actor, evidence, action=action)
            if key:
                self.db.execute("INSERT INTO idempotency VALUES(?,?,?)", (key, digest, dump(result)))
            self.db.execute("COMMIT")
            return result
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def replay(self, action, payload, actor, key):
        """Replay an identical request before re-quoting changing prices or ready times."""
        old = self.one("SELECT * FROM idempotency WHERE key=?", (key,))
        if old is None:
            return None
        digest = hashlib.sha256(dump([action, payload, actor]).encode()).hexdigest()
        if old["digest"] != digest:
            raise ValueError("idempotency key reused with different input")
        return json.loads(old["result"])

    def ingest_catalog(
        self, catalog, config, actor="catalog-ingest", evidence="catalogue source", idempotency_key=None
    ):
        def ingest():
            slug = config["slug"]
            existing = self.one("SELECT id FROM company")
            if existing and existing["id"] != slug:
                raise ValueError("database belongs to a different company")
            meta = {k: v for k, v in catalog.items() if k != "cats"}
            self.db.execute("INSERT OR REPLACE INTO company VALUES(?,?,?)", (slug, dump(config), dump(meta)))
            source_id = hashlib.sha256(str(catalog.get("source", evidence)).encode()).hexdigest()[:20]
            self.db.execute(
                "INSERT OR REPLACE INTO sources VALUES(?,?,?,?,?,?,?)",
                (
                    source_id,
                    "catalog",
                    catalog.get("source"),
                    catalog.get("asOf"),
                    1,
                    "nightly",
                    dump({"evidence": evidence}),
                ),
            )
            self.db.execute("UPDATE items SET active=0")
            self.db.execute("UPDATE product_types SET active=0")
            seen = set()
            for pos, cat in enumerate(catalog["cats"]):
                self.db.execute(
                    "INSERT INTO product_types VALUES(?,?,?,1) ON CONFLICT(id) DO UPDATE SET position=excluded.position,data=excluded.data,active=1",
                    (cat["code"], pos, dump({k: v for k, v in cat.items() if k != "items"})),
                )
                for ipos, item in enumerate(cat["items"]):
                    item_id = item["c"]
                    if item_id in seen:
                        raise ValueError(f"duplicate item: {item_id}")
                    seen.add(item_id)
                    if item.get("validation"):
                        self._event(
                            "questions",
                            {
                                "item_id": item_id,
                                "kind": "source_validation",
                                "status": "open",
                                "validation": item["validation"],
                            },
                            actor,
                            evidence,
                        )
                    self.db.execute(
                        "INSERT INTO items VALUES(?,?,?,?,1) ON CONFLICT(id) DO UPDATE SET type_id=excluded.type_id,position=excluded.position,data=excluded.data,active=1",
                        (item_id, cat["code"], ipos, dump(item)),
                    )
                    for basis in ("p", "cut"):
                        if basis in item:
                            amount = number(item[basis], basis)
                            old = self.one(
                                "SELECT amount FROM prices WHERE item_id=? AND basis=? ORDER BY id DESC LIMIT 1",
                                (item_id, basis),
                            )
                            if not old or old["amount"] != amount:
                                self.db.execute(
                                    "INSERT INTO prices(item_id,basis,amount,actor,evidence,created_at) VALUES(?,?,?,?,?,?)",
                                    (item_id, basis, amount, actor, evidence, stamp()),
                                )
                    self.db.execute(
                        "INSERT OR IGNORE INTO selling VALUES(?,?,?,?,?,?)",
                        (
                            item_id,
                            item.get("minimum", 1),
                            item.get("step", 1),
                            item.get("pack", 1),
                            "assumed",
                            dump(
                                {
                                    "sold_as": item.get("u", "stock"),
                                    "lengths": item.get("r", {}),
                                    "question": "Confirm minimum quantity, step and pack.",
                                }
                            ),
                        ),
                    )
                    self.db.execute(
                        "INSERT OR IGNORE INTO stock VALUES(?,?,NULL,0,NULL,?,?,?,?)",
                        (item_id, "listed", "unknown", actor, evidence, stamp()),
                    )
                    self.db.execute(
                        "INSERT INTO source_rows(source_id,item_id,status,reason,data) VALUES(?,?,?,?,?)",
                        (source_id, item_id, "kept", None, dump(item)),
                    )
            self.db.execute("DELETE FROM services")
            for pos, service in enumerate(catalog.get("services", [])):
                self.db.execute("INSERT INTO services VALUES(?,?,?)", (service["id"], pos, dump(service)))
            self.db.execute("DELETE FROM rules WHERE id='catalog'")
            if "rules" in catalog:
                self.db.execute(
                    "INSERT OR REPLACE INTO rules VALUES(?,?,?)", ("catalog", "read", dump(catalog["rules"]))
                )
            for weekday, hours in config.get("hours", {}).items():
                self.db.execute("INSERT OR IGNORE INTO calendar VALUES(?,?,?,?)", (int(weekday), *hours))
            shop = config.get("shop", {})
            self.db.execute(
                "INSERT OR IGNORE INTO resources VALUES(?,?)",
                ("workshop", dump({"status": "assumed", "name": "Workshop", "minutes_per_day": 480})),
            )
            self.db.execute(
                "INSERT OR IGNORE INTO operations VALUES(?,?,?)",
                (
                    "cut",
                    "workshop",
                    dump(
                        {
                            "status": "assumed",
                            "setup_minutes": shop.get("perLine", 6),
                            "minutes_per_cut": shop.get("perCut", 1.5),
                            "minutes_per_sheet_cut": shop.get("perSheetCut", 2.5),
                        }
                    ),
                ),
            )
            self.db.execute(
                "INSERT OR IGNORE INTO lead_rules VALUES(?,?)",
                (
                    "default",
                    dump(
                        {
                            "status": "assumed",
                            "unknown_stock_days": 3,
                            "window_workdays": 2,
                            "initial_backlog_minutes": shop.get("backlog", 0),
                            "timezone": "Europe/Sofia",
                        }
                    ),
                ),
            )
            return {"company": slug, "types": len(catalog["cats"]), "items": len(seen)}

        return self._write(
            "catalog.ingest", {"catalog": catalog, "config": config}, actor, evidence, idempotency_key, ingest
        )

    def export_catalog(self):
        company = self.one("SELECT * FROM company")
        if not company:
            raise ValueError("company catalogue has not been ingested")
        out = json.loads(company["catalog_meta"])
        if "services" in out:
            out["services"] = [
                json.loads(row["data"]) for row in self.rows("SELECT data FROM services ORDER BY position")
            ]
        cats = []
        for row in self.rows("SELECT * FROM product_types WHERE active=1 ORDER BY position"):
            cat = json.loads(row["data"])
            cat["items"] = []
            for item in self.rows(
                "SELECT * FROM items WHERE type_id=? AND active=1 ORDER BY position", (row["id"],)
            ):
                data = json.loads(item["data"])
                for price in self.rows(
                    "SELECT p.basis,p.amount FROM prices p WHERE p.id IN (SELECT COALESCE(o.price_id,MAX(h.id)) FROM prices h LEFT JOIN price_overrides o ON o.item_id=h.item_id AND o.basis=h.basis WHERE h.item_id=? GROUP BY h.basis)",
                    (item["id"],),
                ):
                    data[price["basis"]] = price["amount"]
                cat["items"].append(data)
            cats.append(cat)
        out["cats"] = cats
        rule = self.one("SELECT data FROM rules WHERE id='catalog'")
        if rule:
            out["rules"] = json.loads(rule["data"])
        return out

    def item(self, item_id):
        row = self.one("SELECT * FROM items WHERE id=? AND active=1", (item_id,))
        if not row:
            raise ValueError("unknown or retired item")
        data = json.loads(row["data"])
        for price in self.rows(
            "SELECT p.basis,p.amount FROM prices p WHERE p.id IN (SELECT COALESCE(o.price_id,MAX(h.id)) FROM prices h LEFT JOIN price_overrides o ON o.item_id=h.item_id AND o.basis=h.basis WHERE h.item_id=? GROUP BY h.basis)",
            (item_id,),
        ):
            data[price["basis"]] = price["amount"]
        return {
            "item": data,
            "type_id": row["type_id"],
            "selling": self.one("SELECT * FROM selling WHERE item_id=?", (item_id,)),
            "stock": self.one("SELECT * FROM stock WHERE item_id=?", (item_id,)),
        }

    def set_price(self, item_id, amount, actor, evidence, basis="p", idempotency_key=None):
        number(amount, "amount")
        if basis not in ("p", "cut"):
            raise ValueError("basis must be p or cut")

        def update():
            self.item(item_id)
            price_id = self.db.execute(
                "INSERT INTO prices(item_id,basis,amount,actor,evidence,created_at) VALUES(?,?,?,?,?,?)",
                (item_id, basis, amount, actor, evidence, stamp()),
            ).lastrowid
            self.db.execute(
                "INSERT OR REPLACE INTO price_overrides VALUES(?,?,?)", (item_id, basis, price_id)
            )
            return self.item(item_id)

        return self._write(
            "catalog.set_price",
            locals_payload(item_id=item_id, amount=amount, basis=basis),
            actor,
            evidence,
            idempotency_key,
            update,
        )

    def set_selling(
        self, item_id, minimum, step, pack, actor, evidence, status="confirmed", idempotency_key=None
    ):
        for key, val in [("minimum", minimum), ("step", step), ("pack", pack)]:
            number(val, key, 0.000001)

        def update():
            self.item(item_id)
            self.db.execute(
                "UPDATE selling SET minimum=?,step=?,pack=?,status=? WHERE item_id=?",
                (minimum, step, pack, status, item_id),
            )
            return self.item(item_id)

        return self._write(
            "catalog.set_selling",
            locals_payload(item_id=item_id, minimum=minimum, step=step, pack=pack, status=status),
            actor,
            evidence,
            idempotency_key,
            update,
        )

    def validate_lines(self, lines):
        if not isinstance(lines, list) or not lines or len(lines) > 200:
            raise ValueError("order requires 1 to 200 lines")
        for line in lines:
            if line.get("kind") == "custom":
                if (
                    line.get("item_id") is not None
                    or line.get("quantity") != 1
                    or not isinstance(line.get("description"), str)
                    or not 1 <= len(line["description"].strip()) <= 4000
                ):
                    raise ValueError("custom order requires a description and quantity one")
                continue
            rule = self.item(line["item_id"])["selling"]
            qty = number(line["quantity"], "quantity", 0.000001)
            if (
                qty < rule["minimum"]
                or abs(qty / rule["step"] - round(qty / rule["step"])) > 1e-7
                or abs(qty / rule["pack"] - round(qty / rule["pack"])) > 1e-7
            ):
                raise ValueError(f"quantity must meet minimum, step and pack for {line['item_id']}")
            number(line.get("cuts", 0), "cuts")
            if not self.one("SELECT id FROM resources WHERE id=?", (line.get("resource_id", "workshop"),)):
                raise ValueError("unknown resource")
        return lines

    def record_stock(
        self,
        item_id,
        quantity,
        actor,
        evidence,
        state="known",
        restock_date=None,
        status="confirmed",
        idempotency_key=None,
    ):
        if state not in ("known", "listed", "unknown", "out"):
            raise ValueError("invalid stock state")
        if state in ("known", "out"):
            number(quantity, "quantity")
            if state == "out" and quantity != 0:
                raise ValueError("out stock has quantity zero")
        elif quantity is not None:
            raise ValueError("listed and unknown quantities must be null")
        if restock_date:
            from datetime import date

            date.fromisoformat(restock_date)
        payload = locals_payload(
            item_id=item_id, quantity=quantity, state=state, restock_date=restock_date, status=status
        )

        def update():
            self.item(item_id)
            row = self.one("SELECT * FROM stock WHERE item_id=?", (item_id,))
            self.db.execute(
                "UPDATE stock SET state=?,quantity=?,restock_date=?,status=?,actor=?,evidence=?,updated_at=? WHERE item_id=?",
                (state, quantity, restock_date, status, actor, evidence, stamp(), item_id),
            )
            self._event("stock_events", payload, actor, evidence, item_id=item_id, event="observation")
            if row["reserved"] and (quantity is None or quantity < row["reserved"]):
                affected = self.rows(
                    "SELECT o.id,SUM(l.quantity) AS required FROM orders o "
                    "JOIN order_lines l ON l.order_id=o.id "
                    "WHERE l.item_id=? AND o.state IN ('accepted','in_progress','ready') GROUP BY o.id",
                    (item_id,),
                )
                risk = {
                    "kind": "stock_shortage" if quantity is not None else "stock_verification_required",
                    "status": "open",
                    "item_id": item_id,
                    "observed_quantity": quantity,
                    "reserved_quantity": row["reserved"],
                    "available_quantity": max(0, quantity - row["reserved"]) if quantity is not None else None,
                    "shortage_quantity": row["reserved"] - quantity if quantity is not None else None,
                    "order_ids": [order["id"] for order in affected],
                }
                self._event("questions", risk, actor, evidence)
                for order in affected:
                    self._event(
                        "order_events", {**risk, "order_required": order["required"]}, actor, evidence,
                        order_id=order["id"], event=risk["kind"],
                    )
            return self.one("SELECT * FROM stock WHERE item_id=?", (item_id,))

        return self._write("stock.record", payload, actor, evidence, idempotency_key, update)

    def capacity_event(self, resource_id, day, minutes, actor, evidence, idempotency_key=None):
        from datetime import date

        date.fromisoformat(day)
        number(minutes, "minutes")
        payload = locals_payload(resource_id=resource_id, day=day, minutes=minutes)

        def update():
            event_id = self._event(
                "capacity_events", payload, actor, evidence, resource_id=resource_id, day=day, minutes=minutes
            )
            return {"id": event_id, **payload}

        return self._write("capacity.event", payload, actor, evidence, idempotency_key, update)

    def set_exception(self, day, closed, actor, evidence, opens=None, closes=None, idempotency_key=None):
        from datetime import date

        date.fromisoformat(day)
        if not isinstance(closed, bool):
            raise ValueError("closed must be boolean")
        if not closed and (
            not isinstance(opens, int) or not isinstance(closes, int) or not 0 <= opens < closes <= 1440
        ):
            raise ValueError("opening interval required")
        payload = locals_payload(day=day, closed=closed, opens=opens, closes=closes)

        def update():
            self.db.execute(
                "INSERT OR REPLACE INTO calendar_exceptions VALUES(?,?,?,?,?)",
                (day, int(closed), opens, closes, dump(payload)),
            )
            return payload

        return self._write("calendar.exception", payload, actor, evidence, idempotency_key, update)

    def supply_projection(self):
        return {
            "timezone": "Europe/Sofia",
            "items": {
                row["item_id"]: {
                    **row,
                    "selling": self.one(
                        "SELECT minimum,step,pack,status FROM selling WHERE item_id=?", (row["item_id"],)
                    ),
                }
                for row in self.rows(
                    "SELECT item_id,state,quantity,reserved,restock_date,status FROM stock WHERE item_id IN (SELECT id FROM items WHERE active=1)"
                )
            },
            "calendar": self.rows("SELECT * FROM calendar"),
            "exceptions": self.rows("SELECT * FROM calendar_exceptions"),
            "resources": [{**r, "data": json.loads(r["data"])} for r in self.rows("SELECT * FROM resources")],
            "capacity_events": self.rows("SELECT resource_id,day,minutes FROM capacity_events"),
            "capacity_load": self.rows(
                "SELECT resource_id,day,SUM(minutes) AS minutes FROM capacity_load GROUP BY resource_id,day"
            ),
            "lead_rules": [json.loads(r["data"]) for r in self.rows("SELECT data FROM lead_rules")],
            "operations": [
                {**r, "data": json.loads(r["data"])} for r in self.rows("SELECT * FROM operations")
            ],
        }

    def public_supply_projection(self):
        """Selling constraints needed by the configurator, without private inventory or capacity."""
        return {
            "timezone": "Europe/Sofia",
            "items": {
                row["item_id"]: {
                    "selling": {
                        "minimum": row["minimum"],
                        "step": row["step"],
                        "pack": row["pack"],
                        "status": row["status"],
                    }
                }
                for row in self.rows(
                    "SELECT s.item_id,s.minimum,s.step,s.pack,s.status FROM selling s "
                    "JOIN items i ON i.id=s.item_id WHERE i.active=1"
                )
            },
        }

    def submit_order(self, customer, lines, quote, idempotency_key, actor, evidence, now=None, request=None):
        if not idempotency_key:
            raise ValueError("idempotency key required")
        self.validate_lines(lines)
        if (
            not isinstance(customer, dict)
            or not customer.get("name")
            or not (customer.get("email") or customer.get("phone"))
        ):
            raise ValueError("customer name and contact required")
        if not isinstance(quote, dict):
            raise ValueError("trusted quote required")

        def submit():
            try:
                from .order_files import claim_line, claim_specification
                from .supply import quote_ready
            except ImportError:
                from order_files import claim_line, claim_specification
                from supply import quote_ready
            ready = quote_ready(self, lines, now)
            oid = uuid.uuid4().hex
            cid = uuid.uuid4().hex
            self.db.execute("INSERT INTO customers VALUES(?,?)", (cid, dump(customer)))
            self.db.execute(
                "INSERT INTO orders VALUES(?,?,?,?,?)", (oid, cid, "requested", dump(quote), stamp())
            )
            for line in lines:
                line = claim_line(self, oid, dict(line))
                self.db.execute(
                    "INSERT INTO order_lines(order_id,item_id,quantity,data) VALUES(?,?,?,?)",
                    (oid, line["item_id"], line["quantity"], dump(line)),
                )
            specification = claim_specification(self, oid, customer.get('specification_file'))
            if specification:
                customer_snapshot = json.loads(dump(customer))
                capture = customer_snapshot.get('capture')
                if isinstance(capture, dict) and isinstance(capture.get('specification'), dict):
                    capture['specification']['file'] = specification
                    self.db.execute('UPDATE customers SET data=? WHERE id=?', (dump(customer_snapshot), cid))
            self._event("order_events", {"quote": quote}, actor, evidence, order_id=oid, event="requested")
            self._event("estimates", ready, actor, evidence, order_id=oid, kind="estimate")
            return {"id": oid, "state": "requested", "ready": ready, "quote": quote}

        payload = (
            {"request": request}
            if request is not None
            else {"customer": customer, "lines": lines, "quote": quote}
        )
        return self._write("orders.submit", payload, actor, evidence, idempotency_key, submit)

    def read_order(self, order_id):
        row = self.one("SELECT * FROM orders WHERE id=?", (order_id,))
        if not row:
            raise ValueError("unknown order")
        row["quote"] = json.loads(row["quote"])
        row["customer"] = json.loads(
            self.one("SELECT data FROM customers WHERE id=?", (row["customer_id"],))["data"]
        )
        row["lines"] = [
            json.loads(r["data"])
            for r in self.rows("SELECT data FROM order_lines WHERE order_id=? ORDER BY id", (order_id,))
        ]
        row["estimates"] = [
            {**r, "data": json.loads(r["data"])}
            for r in self.rows("SELECT * FROM estimates WHERE order_id=? ORDER BY id", (order_id,))
        ]
        row["invoice"] = self.one(
            "SELECT number,issued_at,currency,amount,document_url,actor,evidence,created_at FROM invoices WHERE order_id=?",
            (order_id,),
        )
        return row

    def accept_order(self, order_id, actor, evidence, idempotency_key, now=None):
        def accept():
            try:
                from .reviewed_orders import commercially_resolved
                from .supply import quote_ready
            except ImportError:
                from reviewed_orders import commercially_resolved
                from supply import quote_ready
            order = self.read_order(order_id)
            if order["state"] != "requested":
                raise ValueError("only requested orders can be accepted")
            if not commercially_resolved(self, order):
                raise ValueError('confirm commercial terms and submit a reviewed quote before acceptance')
            delivery = order["quote"].get("delivery")
            if order["quote"].get("fulfilment") == "delivery" and (
                not isinstance(delivery, dict) or delivery.get("status") != "confirmed"
            ):
                raise ValueError("confirm delivery terms and submit a reviewed quote before acceptance")
            ready = quote_ready(self, order["lines"], now)
            if order["quote"].get("fulfilment") == "delivery":
                arrival = datetime.fromisoformat(delivery["arrival"]["earliest"])
                promised_ready = datetime.fromisoformat(ready["latest"])
                if arrival < promised_ready:
                    raise ValueError("confirmed delivery arrival must follow the workshop ready promise")
            for demand in ready["stock"]:
                if (
                    demand["available"] is None
                    or demand["available"] < demand["required"]
                    or self.item(demand["item_id"])["stock"]["status"] != "confirmed"
                ):
                    raise ValueError("record sufficient confirmed stock before acceptance")
                self.db.execute(
                    "UPDATE stock SET reserved=reserved+? WHERE item_id=?",
                    (demand["required"], demand["item_id"]),
                )
                self._event(
                    "stock_events",
                    {"quantity": demand["required"], "order_id": order_id},
                    actor,
                    evidence,
                    item_id=demand["item_id"],
                    event="reserve",
                )
            for allocation in ready["allocation"]:
                self.db.execute(
                    "INSERT INTO capacity_load(order_id,resource_id,day,minutes,event,actor,evidence,created_at) VALUES(?,?,?,?,?,?,?,?)",
                    (
                        order_id,
                        allocation["resource_id"],
                        allocation["day"],
                        allocation["minutes"],
                        "book",
                        actor,
                        evidence,
                        stamp(),
                    ),
                )
            ready["kind"] = "promise"
            self._event("estimates", ready, actor, evidence, order_id=order_id, kind="promise")
            self._event("order_events", ready, actor, evidence, order_id=order_id, event="accepted")
            self.db.execute("UPDATE orders SET state='accepted' WHERE id=?", (order_id,))
            return {"id": order_id, "state": "accepted", "ready": ready}

        return self._write("orders.accept", {"order_id": order_id}, actor, evidence, idempotency_key, accept)

    def confirm_delivery(
        self, order_id, earliest, latest, terms, actor, evidence, idempotency_key,
        fee=None, currency=None, included=False, vat_rate=None,
    ):
        """Record company-confirmed transport terms for a requested delivery order."""
        if not isinstance(earliest, str) or not isinstance(latest, str):
            raise ValueError("ordered timezone-aware delivery window required")
        try:
            start, end = datetime.fromisoformat(earliest), datetime.fromisoformat(latest)
        except ValueError as exc:
            raise ValueError("ordered timezone-aware delivery window required") from exc
        if start.tzinfo is None or end.tzinfo is None or start > end:
            raise ValueError("ordered timezone-aware delivery window required")
        if not isinstance(terms, str) or not 1 <= len(terms.strip()) <= 2000 or any(ord(char) < 32 for char in terms):
            raise ValueError("delivery transport terms are required")
        if not isinstance(included, bool):
            raise ValueError("delivery fee inclusion must be boolean")
        if included:
            if fee is not None or currency is not None or vat_rate is not None:
                raise ValueError("record either an actual delivery fee or a confirmed included fee")
            transport_fee = {"included": True}
        else:
            if (
                fee is None
                or not isinstance(currency, str)
                or not re.fullmatch(r"[A-Z]{3}", currency)
                or vat_rate is None
            ):
                raise ValueError("delivery fee needs an amount, ISO currency and VAT rate")
            transport_fee = {
                "amount": number(fee, "delivery fee"),
                "currency": currency,
                "vat_rate": number(vat_rate, "delivery VAT rate"),
            }
        delivery = {
            "status": "confirmed",
            "arrival": {"earliest": start.isoformat(), "latest": end.isoformat(), "timezone": "Europe/Sofia"},
            "terms": terms.strip(),
            "fee": transport_fee,
        }
        payload = {"order_id": order_id, "delivery": delivery}

        def confirm():
            try:
                from .reviewed_orders import apply_delivery_commercial_review
            except ImportError:
                from reviewed_orders import apply_delivery_commercial_review
            order = self.read_order(order_id)
            if order["state"] != "requested":
                raise ValueError("only requested delivery orders can be confirmed")
            if order["quote"].get("fulfilment") != "delivery":
                raise ValueError("delivery fulfilment is required")
            quote, commercial_change = apply_delivery_commercial_review(
                order_id, order["quote"], delivery, actor
            )
            self.db.execute("UPDATE orders SET quote=? WHERE id=?", (dump(quote), order_id))
            self._event(
                "order_events",
                {
                    "delivery": delivery,
                    "commercial_change": commercial_change,
                    "review": quote.get("review") if commercial_change else None,
                },
                actor,
                evidence,
                order_id=order_id,
                event="delivery_confirmed",
            )
            return {
                "id": order_id,
                "state": "requested",
                "delivery": delivery,
                "commercial_change": commercial_change,
                "quote": quote,
            }

        return self._write("orders.confirm_delivery", payload, actor, evidence, idempotency_key, confirm)

    def record_invoice(
        self, order_id, invoice_number, issued_at, currency, amount, document_url, actor, evidence, idempotency_key
    ):
        """Record an invoice the operator has actually issued; this never creates a financial document."""
        if not isinstance(invoice_number, str) or not 1 <= len(invoice_number.strip()) <= 200 or any(
            ord(char) < 32 for char in invoice_number
        ):
            raise ValueError("invoice number is required")
        if not isinstance(currency, str) or not re.fullmatch(r"[A-Z]{3}", currency):
            raise ValueError("invoice currency must be an ISO code")
        number(amount, "invoice amount")
        if not isinstance(issued_at, str):
            raise ValueError("invoice issue time is required")
        try:
            issue_time = datetime.fromisoformat(issued_at)
        except ValueError as exc:
            raise ValueError("invoice issue time must be ISO 8601") from exc
        if issue_time.tzinfo is None:
            raise ValueError("invoice issue time requires a timezone")
        if not isinstance(document_url, str) or len(document_url) > 2000:
            raise ValueError("invoice document requires an HTTPS URL")
        document_url = document_url.strip()
        parsed = urlsplit(document_url)
        if (
            parsed.scheme != "https"
            or not parsed.netloc
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
        ):
            raise ValueError("invoice document requires a safe HTTPS URL")
        payload = {
            "order_id": order_id,
            "number": invoice_number.strip(),
            "issued_at": issue_time.isoformat(),
            "currency": currency,
            "amount": amount,
            "document_url": document_url,
        }

        def record():
            order = self.read_order(order_id)
            if order["state"] not in {"accepted", "in_progress", "ready", "completed"}:
                raise ValueError("accept the order before recording its issued invoice")
            invoice = {"id": uuid.uuid4().hex, **payload}
            self.db.execute(
                "INSERT INTO invoices VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    invoice["id"],
                    order_id,
                    invoice["number"],
                    invoice["issued_at"],
                    invoice["currency"],
                    invoice["amount"],
                    invoice["document_url"],
                    actor,
                    evidence,
                    stamp(),
                ),
            )
            self._event(
                "order_events",
                {"invoice_id": invoice["id"], "number": invoice["number"]},
                actor,
                evidence,
                order_id=order_id,
                event="invoice_issued",
            )
            return {key: invoice[key] for key in payload}

        return self._write("orders.record_invoice", payload, actor, evidence, idempotency_key, record)

    def mark_order(self, order_id, state, actor, evidence, idempotency_key=None):
        transitions = {
            "requested": {"cancelled"},
            "accepted": {"in_progress", "cancelled"},
            "in_progress": {"ready", "cancelled"},
            "ready": {"completed", "cancelled"},
        }

        def update():
            order = self.read_order(order_id)
            if state not in transitions.get(order["state"], set()):
                raise ValueError("invalid order state transition")
            if state in ("cancelled", "completed") and order["state"] != "requested":
                if state == "completed":
                    demand = {}
                    for line in order["lines"]:
                        demand[line["item_id"]] = demand.get(line["item_id"], 0) + line["quantity"]
                    for item_id, required in demand.items():
                        stock = self.one("SELECT * FROM stock WHERE item_id=?", (item_id,))
                        if (
                            stock is None
                            or stock["state"] not in ("known", "out")
                            or stock["status"] != "confirmed"
                            or stock["quantity"] is None
                            or stock["quantity"] < required
                            or stock["reserved"] < required
                        ):
                            raise ValueError("record sufficient confirmed physical stock before completion")
                for line in order["lines"]:
                    self.db.execute(
                        "UPDATE stock SET reserved=reserved-?,quantity=quantity-? WHERE item_id=?",
                        (line["quantity"], line["quantity"] if state == "completed" else 0, line["item_id"]),
                    )
                    self._event(
                        "stock_events",
                        {"quantity": line["quantity"], "order_id": order_id},
                        actor,
                        evidence,
                        item_id=line["item_id"],
                        event="consume" if state == "completed" else "release",
                    )
                if state == "cancelled":
                    for load in self.rows(
                        "SELECT resource_id,day,SUM(minutes) AS minutes FROM capacity_load WHERE order_id=? GROUP BY resource_id,day",
                        (order_id,),
                    ):
                        self.db.execute(
                            "INSERT INTO capacity_load(order_id,resource_id,day,minutes,event,actor,evidence,created_at) VALUES(?,?,?,?,?,?,?,?)",
                            (
                                order_id,
                                load["resource_id"],
                                load["day"],
                                -load["minutes"],
                                "release",
                                actor,
                                evidence,
                                stamp(),
                            ),
                        )
            self.db.execute("UPDATE orders SET state=? WHERE id=?", (state, order_id))
            self._event("order_events", {"state": state}, actor, evidence, order_id=order_id, event=state)
            return {"id": order_id, "state": state}

        return self._write(
            "orders.state", {"order_id": order_id, "state": state}, actor, evidence, idempotency_key, update
        )

    def change_time(self, order_id, earliest, latest, actor, evidence, idempotency_key=None):
        start = datetime.fromisoformat(earliest)
        end = datetime.fromisoformat(latest)
        if not start.tzinfo or not end.tzinfo or start > end:
            raise ValueError("ordered timezone-aware window required")

        def update():
            order = self.read_order(order_id)
            if order["state"] not in ("accepted", "in_progress", "ready"):
                raise ValueError("accepted order required")
            try:
                from .supply import quote_ready
            except ImportError:
                from supply import quote_ready
            # Reallocate this order under the same transaction; other orders keep their bookings.
            for load in self.rows(
                "SELECT resource_id,day,SUM(minutes) AS minutes FROM capacity_load WHERE order_id=? GROUP BY resource_id,day",
                (order_id,),
            ):
                self.db.execute(
                    "INSERT INTO capacity_load(order_id,resource_id,day,minutes,event,actor,evidence,created_at) VALUES(?,?,?,?,?,?,?,?)",
                    (
                        order_id,
                        load["resource_id"],
                        load["day"],
                        -load["minutes"],
                        "reschedule_release",
                        actor,
                        evidence,
                        stamp(),
                    ),
                )
            for line in order["lines"]:
                self.db.execute(
                    "UPDATE stock SET reserved=reserved-? WHERE item_id=?",
                    (line["quantity"], line["item_id"]),
                )
            plan = quote_ready(self, order["lines"], start)
            if datetime.fromisoformat(plan["earliest"]) > end:
                raise ValueError("requested window has insufficient capacity")
            for line in order["lines"]:
                self.db.execute(
                    "UPDATE stock SET reserved=reserved+? WHERE item_id=?",
                    (line["quantity"], line["item_id"]),
                )
            for allocation in plan["allocation"]:
                self.db.execute(
                    "INSERT INTO capacity_load(order_id,resource_id,day,minutes,event,actor,evidence,created_at) VALUES(?,?,?,?,?,?,?,?)",
                    (
                        order_id,
                        allocation["resource_id"],
                        allocation["day"],
                        allocation["minutes"],
                        "reschedule_book",
                        actor,
                        evidence,
                        stamp(),
                    ),
                )
            payload = {
                **plan,
                "kind": "promise",
                "earliest": plan["earliest"],
                "latest": latest,
                "reason": evidence,
            }
            self._event("estimates", payload, actor, evidence, order_id=order_id, kind="promise")
            self._event("order_events", payload, actor, evidence, order_id=order_id, event="time_changed")
            return payload

        return self._write(
            "orders.change_time",
            {"order_id": order_id, "earliest": earliest, "latest": latest},
            actor,
            evidence,
            idempotency_key,
            update,
        )

    def draft_message(self, order_id, body, actor, evidence, idempotency_key=None):
        if not isinstance(body, str) or not body.strip():
            raise ValueError("message body required")

        def draft():
            self.read_order(order_id)
            mid = uuid.uuid4().hex
            self.db.execute(
                "INSERT INTO messages VALUES(?,?,?,?,?,?,?)",
                (mid, order_id, "held", body, actor, evidence, stamp()),
            )
            return {"id": mid, "status": "held"}

        return self._write(
            "orders.draft_message",
            {"order_id": order_id, "body": body},
            actor,
            evidence,
            idempotency_key,
            draft,
        )

    def request_claim(self, email, name, actor, evidence, idempotency_key):
        if not isinstance(email, str) or "@" not in email or len(email) > 254 or not name:
            raise ValueError("company contact name and email required")

        def request():
            cid = uuid.uuid4().hex
            self.db.execute(
                "INSERT INTO claims VALUES(?,?,?,?,?,?,?)",
                (cid, email, name, "pending", actor, evidence, stamp()),
            )
            return {"id": cid, "status": "pending"}

        return self._write(
            "claim.request", {"email": email, "name": name}, actor, evidence, idempotency_key, request
        )

    def grant_member(self, claim_id, role, verified, actor, evidence, idempotency_key):
        """Privileged caller must verify identity out of band before invoking this action."""
        if verified is not True or role not in ("owner", "operator"):
            raise ValueError("verified identity and a company role are required")

        def grant():
            claim = self.one("SELECT * FROM claims WHERE id=?", (claim_id,))
            if not claim or claim["status"] != "pending":
                raise ValueError("pending claim required")
            mid = uuid.uuid4().hex
            self.db.execute(
                "INSERT INTO members VALUES(?,?,?,?,?)", (mid, claim["email"], role, stamp(), evidence)
            )
            self.db.execute("UPDATE claims SET status='verified' WHERE id=?", (claim_id,))
            return {"id": mid, "role": role, "claim_id": claim_id}

        return self._write(
            "claim.grant",
            {"claim_id": claim_id, "role": role, "verified": verified},
            actor,
            evidence,
            idempotency_key,
            grant,
        )

    def set_supply_plan(
        self,
        resource_id,
        minutes_per_day,
        setup_minutes,
        minutes_per_cut,
        unknown_stock_days,
        window_workdays,
        status,
        actor,
        evidence,
        idempotency_key=None,
    ):
        for name, value in [
            ("minutes_per_day", minutes_per_day),
            ("setup_minutes", setup_minutes),
            ("minutes_per_cut", minutes_per_cut),
            ("unknown_stock_days", unknown_stock_days),
            ("window_workdays", window_workdays),
        ]:
            number(value, name)
        if (
            minutes_per_day > 1440
            or status not in ("assumed", "confirmed")
            or int(unknown_stock_days) != unknown_stock_days
            or int(window_workdays) != window_workdays
        ):
            raise ValueError("invalid supply plan")
        payload = locals_payload(
            resource_id=resource_id,
            minutes_per_day=minutes_per_day,
            setup_minutes=setup_minutes,
            minutes_per_cut=minutes_per_cut,
            unknown_stock_days=unknown_stock_days,
            window_workdays=window_workdays,
            status=status,
        )

        def update():
            if resource_id != "workshop":
                raise ValueError("current engine uses the workshop cutting operation")
            self.db.execute(
                "INSERT OR REPLACE INTO resources VALUES(?,?)",
                (
                    resource_id,
                    dump({"name": "Workshop", "minutes_per_day": minutes_per_day, "status": status}),
                ),
            )
            self.db.execute(
                "INSERT OR REPLACE INTO operations VALUES(?,?,?)",
                (
                    "cut",
                    resource_id,
                    dump(
                        {"setup_minutes": setup_minutes, "minutes_per_cut": minutes_per_cut, "status": status}
                    ),
                ),
            )
            previous = json.loads(self.one("SELECT data FROM lead_rules WHERE id='default'")["data"])
            self.db.execute(
                "UPDATE lead_rules SET data=? WHERE id=?",
                (
                    dump(
                        {
                            **previous,
                            "unknown_stock_days": unknown_stock_days,
                            "window_workdays": window_workdays,
                            "status": status,
                            "initial_backlog_minutes": 0
                            if status == "confirmed"
                            else previous.get("initial_backlog_minutes", 0),
                        }
                    ),
                    "default",
                ),
            )
            return payload

        return self._write("supply.plan", payload, actor, evidence, idempotency_key, update)

    def record(self, table, data, actor, evidence, idempotency_key=None):
        if table not in RECORD_TABLES:
            raise ValueError("unsupported record family")
        return self._write(
            "run." + table,
            data,
            actor,
            evidence,
            idempotency_key,
            lambda: {"id": self._event(table, data, actor, evidence)},
        )


# Explicit keyword payloads prevent credentials/connections entering audit records.
def locals_payload(**kwargs):
    return kwargs


Store = CompanyStore
