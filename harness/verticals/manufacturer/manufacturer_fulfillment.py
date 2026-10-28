"""Human-reported fulfillment, independent of the read-only source's reservations.

Each commitment refers to an exact source snapshot or confirmed customer proposal.
It records a staff action; it never reserves stock, books capacity or calls a carrier.
"""

from __future__ import annotations

import json

from fastapi import HTTPException, Request
from manufacturer_conversations import _id, _json, _text
from manufacturer_store import Conflict, Invalid, stamp
from starlette.concurrency import run_in_threadpool

LABELS = {
    "accepted": "Поръчката е приета.",
    "preparing": "Поръчката се подготвя.",
    "dispatched": "Поръчката е изпратена.",
}
SOURCE_PROGRESS = {
    "accepted": "accepted",
    "in_progress": "preparing",
    "ready": "preparing",
    "completed": "completed",
    "cancelled": "cancelled",
    "dispatched": "dispatched",
}


class ManufacturerFulfillment:
    def __init__(self, conversations):
        self.conversations = conversations
        with conversations._transaction(current=lambda: True) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS fulfillment (
                order_id TEXT PRIMARY KEY REFERENCES orders(order_id),
                conversation_id TEXT NOT NULL REFERENCES conversations(id),
                status TEXT NOT NULL, revision INTEGER NOT NULL, version_id TEXT NOT NULL,
                document_sha256 TEXT NOT NULL, actor TEXT NOT NULL, updated_at TEXT NOT NULL)""")
            db.execute("""CREATE TABLE IF NOT EXISTS fulfillment_events (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id TEXT NOT NULL REFERENCES orders(order_id),
                conversation_id TEXT NOT NULL REFERENCES conversations(id), status TEXT NOT NULL,
                revision INTEGER NOT NULL, version_id TEXT NOT NULL, document_sha256 TEXT NOT NULL,
                actor TEXT NOT NULL, evidence TEXT NOT NULL, created_at TEXT NOT NULL,
                UNIQUE(order_id,revision))""")

    def _target(self, db, conversation, order):
        if order["current_version_id"]:
            proposal = self.conversations._proposal(
                db, conversation, order["order_id"], order["current_version_id"]
            )
            eligible = (
                order["review_status"] == "customer_confirmed"
                and order["confirmed_version_id"] == proposal["id"]
            )
            return proposal["id"], proposal["sha256"], eligible
        return (
            "source:" + order["source_sha256"],
            order["source_sha256"],
            order["review_status"] == "requested",
        )

    def _read(self, db, conversation, order, *, events=True):
        saved = db.execute(
            "SELECT * FROM fulfillment WHERE order_id=? AND conversation_id=?",
            (order["order_id"], conversation["id"]),
        ).fetchone()
        target, digest, eligible = self._target(db, conversation, order)
        result = (
            dict(saved)
            if saved
            else {
                "order_id": order["order_id"],
                "conversation_id": conversation["id"],
                "status": SOURCE_PROGRESS.get(order["source_status"], "requested"),
                "revision": 0,
                "version_id": target,
                "document_sha256": digest,
                "actor": None,
                "updated_at": None,
            }
        )
        terminal = order["source_status"] in {"cancelled", "completed", "dispatched"}
        actions = []
        if eligible and not terminal and result["status"] not in {"cancelled", "completed", "dispatched"}:
            if result["version_id"] != target or result["status"] == "requested":
                actions = ["accepted"]
            elif result["status"] == "accepted":
                actions = ["preparing"]
            elif result["status"] == "preparing":
                actions = ["dispatched"]
        result.update(
            basis="staff_reported" if saved else "source",
            source_status=order["source_status"],
            review_status=order["review_status"],
            current_version_id=target,
            current_document_sha256=digest,
            allowed_actions=actions,
        )
        if events:
            rows = db.execute(
                "SELECT * FROM fulfillment_events WHERE order_id=? AND conversation_id=? "
                "ORDER BY revision DESC LIMIT 100",
                (order["order_id"], conversation["id"]),
            ).fetchall()
            result["events"] = [
                {**dict(row), "evidence": json.loads(row["evidence"])} for row in reversed(rows)
            ]
            result["has_more_events"] = result["revision"] > len(rows)
        return result

    def read(self, customer_id, order_id):
        with self.conversations._transaction() as db:
            conversation = self.conversations._conversation(db, customer_id)
            order = self.conversations._order(db, conversation, order_id)
            return self._read(db, conversation, order)

    def transition(
        self,
        customer_id,
        order_id,
        *,
        status,
        version_id,
        expected_revision,
        actor,
        evidence,
        idempotency_key,
        current,
    ):
        if status not in LABELS or type(expected_revision) is not int or expected_revision < 0:
            raise Invalid("Изберете следващата стъпка по поръчката.")
        actor, version_id = _id(actor), _id(version_id)
        if not isinstance(evidence, dict) or evidence.get("method") != "staff_action":
            raise Invalid("Потвърдете действието от фирмения профил.")
        evidence_json = _json(evidence, maximum=8192)
        payload = {
            "order_id": order_id,
            "status": status,
            "version_id": version_id,
            "expected_revision": expected_revision,
            "actor": actor,
            "evidence": evidence,
        }
        store = self.conversations
        with store._transaction(current=current) as db:
            conversation = store._conversation(db, customer_id)
            order = store._order(db, conversation, order_id)
            previous, digest = store._replay(db, conversation, "fulfillment", idempotency_key, payload)
            if previous is not None:
                return previous
            before = self._read(db, conversation, order, events=False)
            if before["revision"] != expected_revision:
                raise Conflict("Опреснете текущата стъпка по поръчката.")
            if version_id != before["current_version_id"]:
                raise Conflict("Прегледайте актуалната версия на поръчката.")
            if status not in before["allowed_actions"]:
                raise Conflict("Потвърдете текущата версия преди следващата стъпка.")
            revision, now = expected_revision + 1, stamp()
            values = (
                order_id,
                conversation["id"],
                status,
                revision,
                version_id,
                before["current_document_sha256"],
                actor,
                now,
            )
            db.execute(
                """INSERT INTO fulfillment VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(order_id) DO UPDATE SET
                status=excluded.status,revision=excluded.revision,version_id=excluded.version_id,
                document_sha256=excluded.document_sha256,actor=excluded.actor,updated_at=excluded.updated_at""",
                values,
            )
            db.execute(
                """INSERT INTO fulfillment_events(order_id,conversation_id,status,revision,version_id,
                document_sha256,actor,evidence,created_at) VALUES(?,?,?,?,?,?,?,?,?)""",
                (*values[:-1], evidence_json, now),
            )
            store._append(
                db,
                conversation,
                "fulfillment_update",
                "staff",
                actor,
                LABELS[status],
                data={
                    "order_id": order_id,
                    "status": status,
                    "revision": revision,
                    "version_id": version_id,
                    "document_sha256": before["current_document_sha256"],
                    "basis": "staff_reported",
                    "source_status": order["source_status"],
                    "evidence": evidence,
                },
            )
            result = self._read(db, conversation, order)
            store._remember(db, conversation, "fulfillment", idempotency_key, digest, result)
            return result


def register_fulfillment(app, *, context, body, invoke):
    def prepare(extension, actor, order_id, *, writable=False):
        order = extension.order(actor, order_id)["order"]
        customer_id = order["customer_id"]
        profile = extension.customer(actor, customer_id)["customer"]
        def current():
            try:
                return extension.authorized(actor) if writable else bool(extension.member(actor))
            except ValueError:
                return False
        permission = {"actor": actor, "current": current}
        extension.conversations.ensure_customer(
            customer_id, contacts=profile.get("contacts", []), **permission
        )
        # This projection is our own ledger, never part of the immutable upstream request.
        original = {key: value for key, value in order.items() if key != "fulfillment"}
        extension.conversations.record_source_order(customer_id, original, **permission)
        return ManufacturerFulfillment(extension.conversations), customer_id

    @app.get("/api/manufacturer/orders/{order_id}/fulfillment")
    async def get_progress(order_id: str, request: Request):
        actor, extension = context(request)

        def read():
            workflow, customer_id = prepare(extension, actor, order_id)
            result = workflow.read(customer_id, order_id)
            extension.member(actor)
            return result

        return await run_in_threadpool(invoke, read)

    @app.post("/api/manufacturer/orders/{order_id}/fulfillment")
    async def set_progress(order_id: str, request: Request):
        actor, extension = context(request, True)
        value = await body(request)
        required = {"status", "version_id", "expected_revision", "idempotency_key"}
        if not required <= set(value) or set(value) - required - {"note"}:
            raise HTTPException(400, "Изберете действие и актуалната версия на поръчката.")

        def change():
            workflow, customer_id = prepare(extension, actor, order_id, writable=True)
            evidence = {"method": "staff_action"}
            if value.get("note"):
                evidence["note"] = _text(value["note"], 2000)
            return workflow.transition(
                customer_id,
                order_id,
                **{key: value[key] for key in required},
                actor=actor,
                evidence=evidence,
                current=lambda: extension.authorized(actor),
            )

        return await run_in_threadpool(invoke, change)
