"""Company-bound human correspondence and immutable customer request reviews.

The host admits members, validates customers/orders against the source, and
verifies customer capabilities or provider webhooks before calling this store.
External customers remain contacts, not workspace members. Every write rechecks
its supplied current-authority callback immediately before commit. This module
calls no model, sends no email, and never mutates the bound Orders source.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from manufacturer_store import Conflict, Invalid, Missing, stamp

_READ = object()


@dataclass(frozen=True)
class EmailEnvelope:
    """A frozen, admitted intent consumed by a separately commissioned transport."""

    company_id: str
    conversation_id: str
    intent_id: str
    recipient: str
    subject: str
    text: str
    idempotency_key: str
    proposal_version_id: str | None = None


@dataclass(frozen=True)
class EmailReceipt:
    provider: str
    provider_message_id: str
    status: str  # accepted, delivered, failed, or uncertain; backed by provider evidence
    evidence_id: str


class EmailTransport(Protocol):
    def send(self, envelope: EmailEnvelope, *, current) -> EmailReceipt:
        """Admit current authority at the wire and return the actual provider receipt."""
        ...


def _id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:@-]{0,199}", value):
        raise Invalid("Use a bounded record identifier.")
    return value


def _text(value, maximum=8000, *, empty=False):
    if (
        not isinstance(value, str)
        or len(value) > maximum
        or not empty
        and not value.strip()
        or any(ord(char) < 32 and char not in "\n\r\t" for char in value)
    ):
        raise Invalid("Use text within the field length.")
    return value.replace("\r\n", "\n").replace("\r", "\n").strip()


def _email(value):
    if (
        not isinstance(value, str)
        or len(value) > 254
        or not re.fullmatch(
            r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,63}",
            value,
        )
        or ".." in value.split("@", 1)[1]
    ):
        raise Invalid("Use a complete customer email address.")
    return value.lower()


def _json(value, maximum=196608):
    count = 0

    def walk(item, depth=0):
        nonlocal count
        count += 1
        if count > 12000 or depth > 16:
            raise Invalid("Use a bounded data document.")
        if item is None or type(item) is bool:
            return
        if type(item) in {float, int}:
            if not math.isfinite(item) or abs(item) > 1e12:
                raise Invalid("Use finite bounded values.")
        elif isinstance(item, str):
            _text(item, 32000, empty=True)
        elif isinstance(item, list):
            for child in item:
                walk(child, depth + 1)
        elif isinstance(item, dict):
            for key, child in item.items():
                _text(key, 160)
                walk(child, depth + 1)
        else:
            raise Invalid("Use JSON data in the document.")

    walk(value)
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    if len(encoded.encode()) > maximum:
        raise Invalid("Keep the document within its size limit.")
    return encoded


def _hash(encoded):
    return hashlib.sha256(encoded.encode()).hexdigest()


def _contacts(values):
    if not isinstance(values, list) or len(values) > 20:
        raise Invalid("Use up to twenty source-validated customer contacts.")
    result = {}
    for value in values:
        if isinstance(value, str):
            value = {"email": value}
        if not isinstance(value, dict) or set(value) - {"email", "name", "phone"}:
            raise Invalid("Use customer contact names and email addresses.")
        address = _email(value["email"]) if value.get("email") else ""
        name = _text(value.get("name", ""), 200, empty=True)
        phone = _text(value.get("phone", ""), 64, empty=True)
        if not (address or name or phone):
            raise Invalid("Use an identified customer contact.")
        result[address or phone or name] = {"email": address, "name": name, "phone": phone}
    return list(result.values())


class ManufacturerConversations:
    def __init__(self, state, company_id):
        self.company_id = _id(company_id)
        root = Path(state)
        root.mkdir(parents=True, exist_ok=True)
        self.path = root / "manufacturer-conversations.sqlite"
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                "CREATE TABLE IF NOT EXISTS scope "
                "(singleton INTEGER PRIMARY KEY CHECK(singleton=1), company_id TEXT NOT NULL)"
            )
            bound = db.execute("SELECT company_id FROM scope WHERE singleton=1").fetchone()
            if bound and bound[0] != self.company_id:
                raise Invalid("Open the conversation store for its owning company.")
            db.execute("INSERT OR IGNORE INTO scope VALUES(1,?)", (self.company_id,))
            for statement in (
                """CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY, kind TEXT NOT NULL, customer_id TEXT, contacts TEXT NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(kind,customer_id))""",
                """CREATE UNIQUE INDEX IF NOT EXISTS one_service_conversation
                    ON conversations(kind) WHERE kind='service' """,
                """CREATE TABLE IF NOT EXISTS messages (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE NOT NULL,
                    conversation_id TEXT NOT NULL REFERENCES conversations(id), kind TEXT NOT NULL,
                    author_type TEXT NOT NULL, author_id TEXT NOT NULL, text TEXT NOT NULL,
                    data TEXT NOT NULL, created_at TEXT NOT NULL)""",
                """CREATE INDEX IF NOT EXISTS message_history ON messages(conversation_id,sequence)""",
                """CREATE TABLE IF NOT EXISTS orders (
                    order_id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL REFERENCES conversations(id),
                    source TEXT NOT NULL, source_sha256 TEXT NOT NULL, source_status TEXT NOT NULL,
                    review_status TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 0,
                    current_version_id TEXT, confirmed_version_id TEXT, updated_at TEXT NOT NULL)""",
                """CREATE TABLE IF NOT EXISTS proposals (
                    id TEXT PRIMARY KEY, order_id TEXT NOT NULL REFERENCES orders(order_id),
                    conversation_id TEXT NOT NULL REFERENCES conversations(id), version INTEGER NOT NULL,
                    document TEXT NOT NULL, sha256 TEXT NOT NULL, source_sha256 TEXT NOT NULL,
                    actor TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(order_id,version))""",
                """CREATE TABLE IF NOT EXISTS delivery_intents (
                    id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL REFERENCES conversations(id),
                    message_id TEXT UNIQUE NOT NULL REFERENCES messages(id), recipient TEXT NOT NULL,
                    subject TEXT NOT NULL, body TEXT NOT NULL, proposal_version_id TEXT,
                    idempotency_key TEXT UNIQUE NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
                    provider TEXT, provider_message_id TEXT, created_at TEXT NOT NULL)""",
                """CREATE TABLE IF NOT EXISTS delivery_contexts (
                    intent_id TEXT PRIMARY KEY REFERENCES delivery_intents(id), context TEXT NOT NULL)""",
                """CREATE TABLE IF NOT EXISTS operations (
                    conversation_id TEXT NOT NULL, operation TEXT NOT NULL, idempotency_key TEXT NOT NULL,
                    request_sha256 TEXT NOT NULL, result TEXT NOT NULL,
                    PRIMARY KEY(conversation_id,operation,idempotency_key))""",
                """CREATE TABLE IF NOT EXISTS incoming_events (
                    provider TEXT NOT NULL, event_id TEXT NOT NULL, conversation_id TEXT NOT NULL,
                    request_sha256 TEXT NOT NULL, message_id TEXT NOT NULL REFERENCES messages(id),
                    PRIMARY KEY(provider,event_id))""",
            ):
                db.execute(statement)
            db.commit()
        os.chmod(self.path, 0o600)

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.path, timeout=15, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            yield db
        finally:
            db.close()

    @contextmanager
    def _transaction(self, current=_READ):
        if current is not _READ and (not callable(current) or current() is not True):
            raise Invalid("Continue with current conversation access.")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE" if current is not _READ else "BEGIN")
            try:
                row = db.execute("SELECT company_id FROM scope WHERE singleton=1").fetchone()
                if not row or row[0] != self.company_id:
                    raise Invalid("Open the conversation store for its owning company.")
                yield db
                if current is not _READ and current() is not True:
                    raise Invalid("Continue with current conversation access.")
                db.commit()
            except BaseException:
                db.rollback()
                raise

    def _conversation(self, db, customer_id=None, *, service=False):
        row = db.execute(
            "SELECT * FROM conversations WHERE kind=? AND customer_id IS ?",
            ("service" if service else "customer", None if service else _id(customer_id)),
        ).fetchone()
        if not row:
            raise Missing("Open an existing customer or service conversation.")
        return row

    def _info(self, row):
        return {**dict(row), "contacts": json.loads(row["contacts"])}

    def _ensure(self, customer_id, contacts, actor, current, *, service=False):
        _id(actor)
        kind = "service" if service else "customer"
        identifier = "conversation-" + _hash(_json([self.company_id, kind, customer_id]))[:32]
        now = stamp()
        with self._transaction(current) as db:
            db.execute(
                "INSERT OR IGNORE INTO conversations VALUES(?,?,?,?,?,?)",
                (identifier, kind, customer_id, _json(contacts), now, now),
            )
            db.execute("UPDATE conversations SET contacts=? WHERE id=?", (_json(contacts), identifier))
            return self._info(self._conversation(db, customer_id, service=service))

    def ensure_customer(self, customer_id, *, contacts, actor, current):
        return self._ensure(_id(customer_id), _contacts(contacts), actor, current)

    def ensure_service(self, *, actor, current):
        return self._ensure(None, [], actor, current, service=True)

    def _message(self, db, identifier):
        row = db.execute("SELECT * FROM messages WHERE id=?", (identifier,)).fetchone()
        if not row:
            raise Missing("Open an existing conversation message.")
        result = {**dict(row), "data": json.loads(row["data"])}
        delivery = db.execute("SELECT * FROM delivery_intents WHERE message_id=?", (identifier,)).fetchone()
        if delivery:
            result["delivery"] = dict(delivery)
        return result

    def _append(self, db, conversation, kind, author_type, actor, text="", data=None):
        identifier, now = "message-" + uuid.uuid4().hex, stamp()
        db.execute(
            "INSERT INTO messages(id,conversation_id,kind,author_type,author_id,text,data,created_at) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (
                identifier,
                conversation["id"],
                kind,
                author_type,
                _text(actor, 254),
                _text(text, empty=True),
                _json(data or {}),
                now,
            ),
        )
        db.execute("UPDATE conversations SET updated_at=? WHERE id=?", (now, conversation["id"]))
        return identifier

    def _replay(self, db, conversation, operation, key, payload):
        _id(key)
        digest = _hash(_json(payload))
        row = db.execute(
            "SELECT * FROM operations WHERE conversation_id=? AND operation=? AND idempotency_key=?",
            (conversation["id"], operation, key),
        ).fetchone()
        if row and row["request_sha256"] != digest:
            raise Conflict("Reuse the original request or choose a new action identifier.")
        return (json.loads(row["result"]) if row else None), digest

    def _remember(self, db, conversation, operation, key, digest, result):
        db.execute(
            "INSERT INTO operations VALUES(?,?,?,?,?)",
            (conversation["id"], operation, key, digest, _json(result, maximum=524288)),
        )

    def _recipient(self, conversation, recipient):
        address = _email(recipient)
        if address not in {item["email"] for item in json.loads(conversation["contacts"])}:
            raise Invalid("Choose a current source-validated contact for this customer.")
        return address

    def _queue(self, db, conversation, message_id, recipient, subject, text, version_id=None):
        identifier, now = "delivery-" + uuid.uuid4().hex, stamp()
        # Source-created customer groups separate real/demo requests. Their first immutable
        # order event owns this fence; later proposal fields cannot enable or suppress delivery.
        demo_origin = db.execute(
            "SELECT 1 FROM messages WHERE conversation_id=? AND kind='order_submitted' "
            "AND (json_type(data,'$.order.is_demo')='true' "
            "OR json_type(data,'$.order.customer.is_demo')='true') LIMIT 1",
            (conversation["id"],),
        ).fetchone() is not None
        db.execute(
            """INSERT INTO delivery_intents(id,conversation_id,message_id,recipient,subject,body,
                      proposal_version_id,idempotency_key,created_at,status,provider) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (
                identifier,
                conversation["id"],
                message_id,
                recipient,
                _text(subject, 200),
                text,
                version_id,
                self.company_id + ":" + identifier,
                now,
                "demo" if demo_origin else "pending",
                "demo-fixture" if demo_origin else None,
            ),
        )
        return dict(db.execute("SELECT * FROM delivery_intents WHERE id=?", (identifier,)).fetchone())

    def send_message(self, customer_id, *, text, recipient, actor, idempotency_key, current):
        text, actor = _text(text), _id(actor)
        with self._transaction(current) as db:
            conversation = self._conversation(db, customer_id)
            recipient = self._recipient(conversation, recipient)
            prior, digest = self._replay(
                db,
                conversation,
                "send_message",
                idempotency_key,
                {"text": text, "recipient": recipient, "actor": actor},
            )
            if prior is not None:
                return prior
            message_id = self._append(db, conversation, "human_message", "staff", actor, text)
            delivery = self._queue(
                db, conversation, message_id, recipient, "Съобщение за вашата поръчка", text
            )
            result = {"message": self._message(db, message_id), "delivery": delivery}
            self._remember(db, conversation, "send_message", idempotency_key, digest, result)
            return result

    def send_service_message(self, *, text, actor, side, idempotency_key, current):
        text, actor = _text(text), _id(actor)
        if side not in {"client", "provider"}:
            raise Invalid("Choose the authenticated human participant.")
        with self._transaction(current) as db:
            conversation = self._conversation(db, service=True)
            prior, digest = self._replay(
                db,
                conversation,
                "service_message",
                idempotency_key,
                {"text": text, "actor": actor, "side": side},
            )
            if prior is not None:
                return prior
            identifier = self._append(db, conversation, "human_message", side, actor, text)
            result = self._message(db, identifier)
            self._remember(db, conversation, "service_message", idempotency_key, digest, result)
            return result

    def _order(self, db, conversation, order_id):
        row = db.execute(
            "SELECT * FROM orders WHERE order_id=? AND conversation_id=?", (_id(order_id), conversation["id"])
        ).fetchone()
        if not row:
            raise Missing("Open an order belonging to this customer conversation.")
        return row

    def _review(self, row):
        result = dict(row)
        result["source"] = json.loads(result["source"])
        # Workshop progress and customer review retain independent meanings.
        progress = {"in_progress": "preparing", "ready": "preparing"}.get(
            result["source_status"], result["source_status"]
        )
        result["fulfillment_status"] = progress
        result["status"] = progress if progress != "requested" else result["review_status"]
        return result

    def order_review(self, customer_id, order_id):
        with self._transaction() as db:
            return self._review(self._order(db, self._conversation(db, customer_id), order_id))

    def record_source_order(self, customer_id, order, *, actor, current):
        if not isinstance(order, dict) or order.get("customer_id") != customer_id:
            raise Invalid("Use the source-validated order for this customer.")
        order_id, source_status = _id(order.get("id")), _text(order.get("status"), 64)
        # Research refreshes enrich the CRM, while order cards reflect the submitted request.
        order = {key: value for key, value in order.items() if key != "enrichment"}
        if isinstance(order.get("customer"), dict):
            derived = {
                "display_company",
                "company_display_source",
                "company_source_url",
                "company_details_needed",
                "display_name",
            }
            order["customer"] = {key: value for key, value in order["customer"].items() if key not in derived}
        encoded, now = _json(order), stamp()
        digest = _hash(encoded)
        with self._transaction(current) as db:
            conversation = self._conversation(db, customer_id)
            old = db.execute("SELECT * FROM orders WHERE order_id=?", (order_id,)).fetchone()
            if old and old["conversation_id"] != conversation["id"]:
                raise Conflict("Keep the order with its original customer conversation.")
            if old and old["source_sha256"] == digest:
                return self._review(old)
            if old:
                db.execute(
                    "UPDATE orders SET source=?,source_sha256=?,source_status=?,updated_at=? "
                    "WHERE order_id=?",
                    (encoded, digest, source_status, now, order_id),
                )
            else:
                db.execute(
                    """INSERT INTO orders(order_id,conversation_id,source,source_sha256,source_status,
                              review_status,updated_at) VALUES(?,?,?,?,?,'requested',?)""",
                    (order_id, conversation["id"], encoded, digest, source_status, now),
                )
            self._append(
                db,
                conversation,
                "order_updated" if old else "order_submitted",
                "system",
                actor,
                data={"order": order, "source_sha256": digest, "basis": "source_snapshot"},
            )
            return self._review(self._order(db, conversation, order_id))

    def _proposal(self, db, conversation, order_id, version_id):
        row = db.execute(
            "SELECT * FROM proposals WHERE id=? AND order_id=? AND conversation_id=?",
            (_id(version_id), _id(order_id), conversation["id"]),
        ).fetchone()
        if not row:
            raise Missing("Open a proposal version from this customer order.")
        result = dict(row)
        result["document"] = json.loads(result["document"])
        return result

    def proposal(self, customer_id, order_id, version_id):
        with self._transaction() as db:
            return self._proposal(db, self._conversation(db, customer_id), order_id, version_id)

    def propose_request(
        self,
        customer_id,
        order_id,
        *,
        proposal,
        recipient,
        actor,
        expected_revision,
        idempotency_key,
        current,
    ):
        if (
            not isinstance(proposal, dict)
            or not isinstance(proposal.get("lines"), list)
            or not 1 <= len(proposal["lines"]) <= 1000
            or any(not isinstance(line, dict) or not line for line in proposal["lines"])
            or proposal.get("id", order_id) != order_id
            or proposal.get("customer_id", customer_id) != customer_id
            or type(expected_revision) is not int
            or expected_revision < 0
        ):
            raise Invalid("Use the complete proposal and current review revision.")
        for line in proposal["lines"]:
            quantity = line.get("quantity")
            if type(quantity) not in {int, float} or not math.isfinite(quantity) or quantity <= 0:
                raise Invalid("Use a positive quantity for each proposed line.")
        encoded = _json(proposal)
        actor = _id(actor)
        with self._transaction(current) as db:
            conversation = self._conversation(db, customer_id)
            recipient = self._recipient(conversation, recipient)
            prior, request_hash = self._replay(
                db,
                conversation,
                "propose_request",
                idempotency_key,
                {
                    "order_id": order_id,
                    "proposal": proposal,
                    "recipient": recipient,
                    "actor": actor,
                    "expected_revision": expected_revision,
                },
            )
            if prior is not None:
                return prior
            order = self._order(db, conversation, order_id)
            if order["revision"] != expected_revision:
                raise Conflict("Review the current request revision before saving your changes.")
            version = db.execute(
                "SELECT coalesce(max(version),0)+1 FROM proposals WHERE order_id=?", (order_id,)
            ).fetchone()[0]
            identifier, now = "proposal-" + uuid.uuid4().hex, stamp()
            db.execute(
                "INSERT INTO proposals VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    identifier,
                    order_id,
                    conversation["id"],
                    version,
                    encoded,
                    _hash(encoded),
                    order["source_sha256"],
                    actor,
                    now,
                ),
            )
            db.execute(
                """UPDATE orders SET current_version_id=?,review_status='review_pending',revision=revision+1,
                          updated_at=? WHERE order_id=?""",
                (identifier, now, order_id),
            )
            saved = self._proposal(db, conversation, order_id, identifier)
            message_id = self._append(
                db,
                conversation,
                "proposal",
                "staff",
                actor,
                data={
                    "order_id": order_id,
                    "version_id": identifier,
                    "version": version,
                    "sha256": saved["sha256"],
                },
            )
            delivery = self._queue(
                db,
                conversation,
                message_id,
                recipient,
                "Преглед на вашата поръчка",
                "Прегледайте предложената версия на вашата поръчка.",
                identifier,
            )
            result = {
                "proposal": saved,
                "review": self._review(self._order(db, conversation, order_id)),
                "message": self._message(db, message_id),
                "delivery": delivery,
            }
            self._remember(db, conversation, "propose_request", idempotency_key, request_hash, result)
            return result

    def confirm_proposal(self, customer_id, order_id, *, version_id, customer_actor, evidence, current):
        customer_actor = _id(customer_actor)
        if not isinstance(evidence, dict) or not evidence:
            raise Invalid("Record the authenticated customer confirmation evidence.")
        _json(evidence, maximum=16384)
        with self._transaction(current) as db:
            conversation = self._conversation(db, customer_id)
            order = self._order(db, conversation, order_id)
            version = self._proposal(db, conversation, order_id, version_id)
            if order["current_version_id"] != version_id:
                raise Conflict("Review the current proposal version before confirming.")
            if order["review_status"] == "customer_confirmed" and order["confirmed_version_id"] == version_id:
                return self._review(order)
            if order["review_status"] != "review_pending":
                raise Conflict("Review the next proposal prepared for confirmation.")
            db.execute(
                """UPDATE orders SET confirmed_version_id=?,review_status='customer_confirmed',
                          revision=revision+1,updated_at=? WHERE order_id=?""",
                (version_id, stamp(), order_id),
            )
            self._append(
                db,
                conversation,
                "customer_confirmation",
                "customer",
                customer_actor,
                data={
                    "order_id": order_id,
                    "version_id": version_id,
                    "sha256": version["sha256"],
                    "evidence": evidence,
                },
            )
            return self._review(self._order(db, conversation, order_id))

    def request_customer_change(
        self,
        customer_id,
        order_id,
        *,
        version_id,
        text,
        customer_actor,
        evidence,
        idempotency_key,
        current,
        patch=None,
    ):
        text, customer_actor = _text(text), _id(customer_actor)
        if (
            not isinstance(evidence, dict)
            or not evidence
            or patch is not None
            and not isinstance(patch, dict)
        ):
            raise Invalid("Record the customer request and its authenticated evidence.")
        data = {
            "order_id": order_id,
            "version_id": version_id,
            "text": text,
            "customer_actor": customer_actor,
            "evidence": evidence,
            "patch": patch,
        }
        _json(data)
        with self._transaction(current) as db:
            conversation = self._conversation(db, customer_id)
            prior, digest = self._replay(db, conversation, "request_customer_change", idempotency_key, data)
            if prior is not None:
                return prior
            order = self._order(db, conversation, order_id)
            self._proposal(db, conversation, order_id, version_id)
            if order["current_version_id"] != version_id:
                raise Conflict("Request changes to the current proposal version.")
            db.execute(
                "UPDATE orders SET review_status='changes_requested',revision=revision+1,updated_at=? "
                "WHERE order_id=?",
                (stamp(), order_id),
            )
            self._append(
                db, conversation, "customer_change_requested", "customer", customer_actor, text, data
            )
            result = self._review(self._order(db, conversation, order_id))
            self._remember(db, conversation, "request_customer_change", idempotency_key, digest, result)
            return result

    def record_customer_message(
        self, customer_id, *, text, sender, provider, provider_event_id, provenance, current
    ):
        text, provider, event_id = _text(text), _id(provider), _id(provider_event_id)
        if not isinstance(provenance, dict) or provenance.get("signature_verified") is not True:
            raise Invalid("Admit the authenticated provider event before recording its message.")
        with self._transaction(current) as db:
            conversation = self._conversation(db, customer_id)
            sender = self._recipient(conversation, sender)
            data = {
                "sender": sender,
                "provider": provider,
                "provider_event_id": event_id,
                "provenance": provenance,
            }
            digest = _hash(_json({"text": text, **data}))
            prior = db.execute(
                "SELECT * FROM incoming_events WHERE provider=? AND event_id=?", (provider, event_id)
            ).fetchone()
            if prior:
                if prior["conversation_id"] != conversation["id"] or prior["request_sha256"] != digest:
                    raise Conflict("Keep the incoming event with its original customer and content.")
                return self._message(db, prior["message_id"])
            identifier = self._append(db, conversation, "human_message", "customer", sender, text, data)
            db.execute(
                "INSERT INTO incoming_events VALUES(?,?,?,?,?)",
                (provider, event_id, conversation["id"], digest, identifier),
            )
            return self._message(db, identifier)

    def record_email_intent(
        self,
        customer_id,
        *,
        message_id,
        intent,
        confidence,
        ambiguous,
        evidence,
        actor,
        idempotency_key,
        current,
    ):
        if (
            intent not in {"question", "change_request", "confirmation", "cancellation", "other", "unknown"}
            or type(confidence) not in {float, int}
            or not math.isfinite(confidence)
            or not 0 <= confidence <= 1
            or type(ambiguous) is not bool
            or not isinstance(evidence, dict)
            or not evidence
        ):
            raise Invalid("Record a bounded classification with provenance and ambiguity.")
        data = {
            "message_id": _id(message_id),
            "intent": intent,
            "confidence": confidence,
            "ambiguous": ambiguous,
            "evidence": evidence,
            "authority": "suggestion",
        }
        with self._transaction(current) as db:
            conversation = self._conversation(db, customer_id)
            incoming = self._message(db, message_id)
            if incoming["conversation_id"] != conversation["id"] or incoming["author_type"] != "customer":
                raise Invalid("Classify a customer message in this conversation.")
            prior, digest = self._replay(
                db, conversation, "email_intent", idempotency_key, {"actor": actor, **data}
            )
            if prior is not None:
                return prior
            identifier = self._append(db, conversation, "email_intent", "system", actor, data=data)
            result = self._message(db, identifier)
            self._remember(db, conversation, "email_intent", idempotency_key, digest, result)
            return result

    def _history(self, db, conversation, limit, before):
        if (
            type(limit) is not int
            or not 1 <= limit <= 100
            or before is not None
            and (type(before) is not int or before < 1)
        ):
            raise Invalid("Choose a bounded conversation history page.")
        rows = db.execute(
            """SELECT id,sequence FROM messages WHERE conversation_id=? AND (? IS NULL OR sequence<?)
                             ORDER BY sequence DESC LIMIT ?""",
            (conversation["id"], before, before, limit + 1),
        ).fetchall()
        more, selected = len(rows) > limit, rows[:limit]
        result = self._info(conversation)
        orders = db.execute(
            "SELECT * FROM orders WHERE conversation_id=? ORDER BY updated_at DESC,order_id LIMIT 101",
            (conversation["id"],),
        ).fetchall()
        summaries = []
        for row in orders[:100]:
            summary = self._review(row)
            source = summary.pop("source")
            summary["number"] = source.get("display_number") or source.get("number") or row["order_id"]
            summaries.append(summary)
        result.update(
            messages=[self._message(db, row["id"]) for row in reversed(selected)],
            has_more=more,
            next_before=selected[-1]["sequence"] if more else None,
            orders=summaries,
            has_more_orders=len(orders) > 100,
        )
        return result

    def conversation(self, customer_id, *, limit=50, before=None):
        with self._transaction() as db:
            return self._history(db, self._conversation(db, customer_id), limit, before)

    def service_conversation(self, *, limit=50, before=None):
        with self._transaction() as db:
            return self._history(db, self._conversation(db, service=True), limit, before)

    def pending_deliveries(self, *, limit=50):
        if type(limit) is not int or not 1 <= limit <= 100:
            raise Invalid("Choose a bounded delivery batch.")
        with self._transaction() as db:
            return [
                dict(row)
                for row in db.execute(
                    "SELECT * FROM delivery_intents WHERE status='pending' ORDER BY created_at,id LIMIT ?",
                    (limit,),
                )
            ]

    def delivery_context(self, intent_id):
        """Frozen external delivery plus its current listed recipient and exact proposal."""
        with self._transaction() as db:
            row = db.execute("SELECT * FROM delivery_intents WHERE id=?", (_id(intent_id),)).fetchone()
            if row is None:
                raise Missing("Choose an existing delivery intent.")
            conversation = db.execute(
                "SELECT * FROM conversations WHERE id=?", (row["conversation_id"],)
            ).fetchone()
            if conversation["kind"] != "customer":
                raise Invalid("Use the customer correspondence channel.")
            self._recipient(conversation, row["recipient"])
            message = db.execute("SELECT author_id FROM messages WHERE id=?", (row["message_id"],)).fetchone()
            result = {
                **dict(row),
                "customer_id": conversation["customer_id"],
                "company_id": self.company_id,
                "actor": message["author_id"],
            }
            metadata = db.execute(
                "SELECT context FROM delivery_contexts WHERE intent_id=?", (row["id"],)
            ).fetchone()
            if metadata:
                result.update(json.loads(metadata["context"]))
            if row["proposal_version_id"]:
                proposal = db.execute(
                    "SELECT * FROM proposals WHERE id=? AND conversation_id=?",
                    (row["proposal_version_id"], conversation["id"]),
                ).fetchone()
                if proposal is None:
                    raise Missing("Use the original proposal revision.")
                result.update(
                    order_id=proposal["order_id"],
                    proposal=json.loads(proposal["document"]),
                    proposal_sha256=proposal["sha256"],
                    proposal_version=proposal["version"],
                )
            return result

    def begin_delivery(self, intent_id, *, current):
        with self._transaction(current) as db:
            row = db.execute("SELECT * FROM delivery_intents WHERE id=?", (_id(intent_id),)).fetchone()
            if row is None:
                raise Missing("Choose an existing delivery intent.")
            conversation = db.execute(
                "SELECT * FROM conversations WHERE id=?", (row["conversation_id"],)
            ).fetchone()
            self._recipient(conversation, row["recipient"])
            if row["status"] == "pending":
                db.execute("UPDATE delivery_intents SET status='sending' WHERE id=?", (intent_id,))
            return dict(db.execute("SELECT * FROM delivery_intents WHERE id=?", (intent_id,)).fetchone())

    def record_delivery(self, intent_id, receipt, *, current):
        if not isinstance(receipt, EmailReceipt) or receipt.status not in {
            "accepted",
            "sent",
            "delivered",
            "failed",
            "uncertain",
        }:
            raise Invalid("Record a verified delivery receipt.")
        _id(receipt.provider)
        _id(receipt.evidence_id)
        if receipt.provider_message_id:
            _id(receipt.provider_message_id)
        with self._transaction(current) as db:
            row = db.execute("SELECT * FROM delivery_intents WHERE id=?", (_id(intent_id),)).fetchone()
            if row is None:
                raise Missing("Choose an existing delivery intent.")
            if row["provider_message_id"] and row["provider_message_id"] != receipt.provider_message_id:
                raise Conflict("Keep the original provider delivery identity.")
            # A late accepted/sent callback does not erase a later delivery outcome.
            terminal = row["status"] in {"delivered", "failed"}
            next_status = (
                row["status"]
                if terminal and receipt.status in {"accepted", "sent", "uncertain"}
                else receipt.status
            )
            conversation = db.execute(
                "SELECT * FROM conversations WHERE id=?", (row["conversation_id"],)
            ).fetchone()
            data = {
                "delivery_id": intent_id,
                "status": receipt.status,
                "provider": receipt.provider,
                "provider_message_id": receipt.provider_message_id,
                "evidence_id": receipt.evidence_id,
            }
            prior, digest = self._replay(db, conversation, "delivery_receipt", receipt.evidence_id, data)
            if prior is not None:
                return prior
            db.execute(
                "UPDATE delivery_intents SET status=?,provider=?,provider_message_id=? WHERE id=?",
                (next_status, receipt.provider, receipt.provider_message_id or None, intent_id),
            )
            result = dict(db.execute("SELECT * FROM delivery_intents WHERE id=?", (intent_id,)).fetchone())
            self._remember(db, conversation, "delivery_receipt", receipt.evidence_id, digest, result)
            return result

    def queue_fulfillment(self, customer_id, order_id, revision, *, recipient, actor, current):
        """Attach one delivery to an exact existing staff update, preserving one timeline event."""
        _id(actor)
        if type(revision) is not int or revision < 1:
            raise Invalid("Choose the exact recorded fulfillment update.")
        with self._transaction(current) as db:
            conversation = self._conversation(db, customer_id)
            order = self._order(db, conversation, order_id)
            recipient = self._recipient(conversation, recipient)
            selected = None
            for row in db.execute(
                "SELECT * FROM messages WHERE conversation_id=? AND kind='fulfillment_update' ORDER BY sequence DESC",
                (conversation["id"],),
            ):
                data = json.loads(row["data"])
                if data.get("order_id") == order_id and data.get("revision") == revision:
                    selected = row
                    break
            if selected is None or selected["author_type"] != "staff":
                raise Missing("Choose an existing staff fulfillment update.")
            prior = db.execute(
                "SELECT * FROM delivery_intents WHERE message_id=?", (selected["id"],)
            ).fetchone()
            if prior:
                if prior["recipient"] != recipient:
                    raise Conflict("Keep the original customer notification recipient.")
                return dict(prior)
            data = json.loads(selected["data"])
            version = data["version_id"] if data["version_id"].startswith("proposal-") else None
            if version:
                self._proposal(db, conversation, order_id, version)
            number = (
                json.loads(order["source"]).get("display_number")
                or json.loads(order["source"]).get("number")
                or order_id
            )
            delivery = self._queue(
                db,
                conversation,
                selected["id"],
                recipient,
                "Поръчка " + str(number),
                selected["text"],
                version,
            )
            context = {
                "purpose": "fulfillment",
                "order_id": order_id,
                "notification_actor": actor,
                "reference_version_id": data["version_id"],
                "reference_sha256": data["document_sha256"],
                "fulfillment_revision": revision,
                "fulfillment_status": data["status"],
            }
            db.execute("INSERT INTO delivery_contexts VALUES(?,?)", (delivery["id"], _json(context)))
            return delivery
