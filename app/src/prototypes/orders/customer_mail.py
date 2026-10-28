# ruff: noqa: E501
"""Private customer links and a held, threaded transactional email outbox.

The database stores capability hashes and message metadata. Private link tokens are derived
from a company-owned key outside SQLite; HTML/MIME is rendered only when previewed or sent.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import html
import http.client
import json
import os
import re
import secrets
import subprocess
import sys
import tempfile
import time
import uuid
from contextlib import suppress
from datetime import datetime
from email.message import EmailMessage
from email.policy import SMTP
from email.utils import format_datetime, formataddr, parseaddr
from pathlib import Path
from urllib.parse import urlencode, urlsplit
from zoneinfo import ZoneInfo

try:
    from .supply import public_ready
except ImportError:
    from supply import public_ready

SCHEMA = """
CREATE TABLE IF NOT EXISTS customer_links(
 order_id TEXT PRIMARY KEY REFERENCES orders(id),nonce TEXT NOT NULL,token_hash TEXT NOT NULL,
 expires REAL NOT NULL,revoked INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS customer_requests(
 id TEXT PRIMARY KEY,order_id TEXT NOT NULL REFERENCES orders(id),kind TEXT NOT NULL,body TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'requested',created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS mail_threads(
 order_id TEXT PRIMARY KEY REFERENCES orders(id),subject TEXT NOT NULL,root_message_id TEXT NOT NULL,
 last_message_id TEXT,provider_thread_id TEXT,language TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS mail_outbox(
 id TEXT PRIMARY KEY,order_id TEXT NOT NULL REFERENCES orders(id),event_key TEXT NOT NULL UNIQUE,
 kind TEXT NOT NULL,body TEXT NOT NULL DEFAULT '',message_id TEXT NOT NULL UNIQUE,
 state TEXT NOT NULL DEFAULT 'held',provider_id TEXT,provider_thread_id TEXT,
 attempts INTEGER NOT NULL DEFAULT 0,created_at TEXT NOT NULL,sent_at TEXT);
CREATE TABLE IF NOT EXISTS mail_events(
 id INTEGER PRIMARY KEY,mail_id TEXT,kind TEXT NOT NULL,data TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS mail_replies(
 provider_id TEXT PRIMARY KEY,order_id TEXT NOT NULL,provider_thread_id TEXT NOT NULL,
 message_id TEXT NOT NULL,in_reply_to TEXT,refs TEXT,received_at TEXT NOT NULL);
"""
ORIGIN = "https://orders.example.test"


class UnrelatedReply(ValueError):
    """A provider-thread message whose sender is not the order customer."""

SENDER = "operator@example.test"
C = {
    "en": {
        "received": "We received your order",
        "accepted": "Your order is confirmed",
        "deliveryConfirmed": "Delivery arrival confirmed",
        "reviewed": "Your order total is ready",
        "cancelled": "Your order is cancelled",
        "changed": "Your order update",
        "reply": "A message about your order",
        "intro": "{company} will confirm the delivery date in this email conversation. Your invoice follows confirmation.",
        "introPrice": "{company} will confirm the price and delivery date in this email conversation. Your invoice follows confirmation.",
        "confirmed": "Your order is in the workshop schedule.",
        "deliveryCopy": "Your delivery arrival window and transport terms are confirmed below.",
        "reviewedCopy": "Review the total below and confirm it on your private order page.",
        "cancelCopy": "Your cancellation is recorded.",
        "manage": "View your order",
        "order": "Order",
        "summary": "Order summary",
        "estimated": "Estimated ready time",
        "confirmationReady": "Ready time confirmation",
        "ready": "Ready time",
        "total": "Quoted total",
        "priceOnConfirmation": "Total on confirmation",
        "reviewedTotal": "Reviewed total",
        "vat": "Includes VAT",
        "pending": "Price on confirmation",
        "delivery": "Delivery date follows confirmation.",
        "pickup": "Pickup",
        "replyCopy": "Reply to this email to talk about your order. Your messages stay in this conversation.",
        "pageReply": "Reply to your order email to talk with {company}.",
        "private": "This link gives access to your order. Keep it for yourself.",
        "source": "Products and prices from {company}",
        "await": "The team confirms the time with your order.",
        "workshopEstimate": "Estimated workshop ready time",
        "workshopPromise": "Confirmed workshop ready time",
        "pickupReady": "Pickup is available when the workshop marks this order ready.",
        "deliveryReady": "This is the workshop-ready time. Delivery arrival follows the confirmed delivery date.",
        "deliveryDate": "Delivery arrival",
        "deliveryAwaiting": "Awaiting confirmation",
        "deliveryTerms": "Transport terms",
        "deliveryFeeIncluded": "Delivery included in your confirmed order",
        "deliveryFee": "Delivery fee",
        "invoice": "Invoice",
        "invoiceIssued": "Your invoice is available",
        "invoiceFollows": "Invoice follows delivery-date confirmation",
        "viewInvoice": "View invoice",
        "invoiceDocument": "Invoice document",
        "progress": "Recorded progress",
        "receivedTimeline": "Order request received",
        "confirmedTimeline": "Order confirmed",
        "progressTimeline": "Work started",
        "readyTimeline": "Order marked ready",
        "completedTimeline": "Order completed",
        "cancelTimeline": "Order cancelled",
        "timeChangedTimeline": "Workshop ready time updated",
        "deliveryTimeline": "Delivery arrival confirmed",
        "invoiceTimeline": "Invoice issued",
        "quoteReviewedTimeline": "Order total reviewed",
        "quoteAssentedTimeline": "Reviewed total confirmed",
        "pieces": "pcs",
        "line": "Line total",
        "requestReceived": "Your request is saved",
        "requestCopy": "The team will review your requested changes.",
        "status": "Status",
        "change": "Request a change",
        "cancel": "Cancel order",
        "note": "Describe your change",
        "send": "Save change request",
        "saved": "Your change request is saved.",
        "reviewAction": "Confirm reviewed total",
        "reviewSaved": "Reviewed total confirmed.",
        "contact": "Your contact details",
        "closed": "The team is preparing this order. Reply to your order email to discuss changes.",
        "open": "Open the private link from your order email.",
        "receivedState": "Awaiting confirmation",
        "cancelState": "Cancelled",
        "acceptedState": "Confirmed",
        "progressState": "In progress",
        "readyState": "Ready",
        "completedState": "Completed",
        "receipt": "Order receipt",
        "details": "Order details",
    },
    "bg": {
        "received": "Получихме вашата поръчка",
        "accepted": "Поръчката ви е потвърдена",
        "deliveryConfirmed": "Потвърдено пристигане за доставка",
        "reviewed": "Сумата по поръчката ви е готова",
        "cancelled": "Поръчката ви е отказана",
        "changed": "Промяна по вашата поръчка",
        "reply": "Съобщение за вашата поръчка",
        "intro": "{company} ще потвърди датата за доставка в тази кореспонденция. Фактурата следва потвърждението.",
        "introPrice": "{company} ще потвърди цената и датата за доставка в тази кореспонденция. Фактурата следва потвърждението.",
        "confirmed": "Поръчката ви е включена в работния график.",
        "deliveryCopy": "Потвърдените часове за пристигане и условията за транспорт са по-долу.",
        "reviewedCopy": "Прегледайте сумата по-долу и я потвърдете в личната страница на поръчката.",
        "cancelCopy": "Отказът ви е записан.",
        "manage": "Вижте поръчката",
        "order": "Поръчка",
        "summary": "Вашата поръчка",
        "estimated": "Очакван срок",
        "confirmationReady": "Потвърждение на срока",
        "ready": "Срок за изпълнение",
        "total": "Договорена сума",
        "priceOnConfirmation": "Сума при потвърждение",
        "reviewedTotal": "Прегледана сума",
        "vat": "С ДДС",
        "pending": "Цена при потвърждение",
        "delivery": "Датата за доставка следва потвърждението.",
        "pickup": "Получаване",
        "replyCopy": "Отговорете на този имейл за въпроси по поръчката. Разговорът остава в същата кореспонденция.",
        "pageReply": "Отговорете на имейла за поръчката, за да се свържете с {company}.",
        "private": "Тази връзка дава достъп до поръчката ви. Запазете я за себе си.",
        "source": "Продукти и цени от {company}",
        "await": "Екипът потвърждава срока с поръчката.",
        "workshopEstimate": "Очаквана готовност от работилницата",
        "workshopPromise": "Потвърдена готовност от работилницата",
        "pickupReady": "Получаването е възможно, когато работилницата отбележи поръчката като готова.",
        "deliveryReady": "Това е срокът за готовност от работилницата. Пристигането следва потвърдената дата за доставка.",
        "deliveryDate": "Пристигане за доставка",
        "deliveryAwaiting": "Очаква потвърждение",
        "deliveryTerms": "Условия за транспорт",
        "deliveryFeeIncluded": "Доставката е включена в потвърдената поръчка",
        "deliveryFee": "Такса доставка",
        "invoice": "Фактура",
        "invoiceIssued": "Фактурата ви е готова",
        "invoiceFollows": "Фактурата следва потвърждението на датата за доставка",
        "viewInvoice": "Вижте фактурата",
        "invoiceDocument": "Документ за фактурата",
        "progress": "Записан напредък",
        "receivedTimeline": "Заявката за поръчка е получена",
        "confirmedTimeline": "Поръчката е потвърдена",
        "progressTimeline": "Работата е започнала",
        "readyTimeline": "Поръчката е отбелязана като готова",
        "completedTimeline": "Поръчката е завършена",
        "cancelTimeline": "Поръчката е отказана",
        "timeChangedTimeline": "Срокът за готовност от работилницата е обновен",
        "deliveryTimeline": "Потвърдено пристигане за доставка",
        "invoiceTimeline": "Фактурата е издадена",
        "quoteReviewedTimeline": "Сумата по поръчката е прегледана",
        "quoteAssentedTimeline": "Прегледаната сума е потвърдена",
        "pieces": "бр.",
        "line": "Общо",
        "requestReceived": "Заявката ви е записана",
        "requestCopy": "Екипът ще прегледа желаните промени.",
        "status": "Статус",
        "change": "Поискайте промяна",
        "cancel": "Откажете поръчката",
        "note": "Опишете промяната",
        "send": "Запазете заявката за промяна",
        "saved": "Заявката ви за промяна е записана.",
        "reviewAction": "Потвърдете прегледаната сума",
        "reviewSaved": "Прегледаната сума е потвърдена.",
        "contact": "Вашите данни",
        "closed": "Екипът подготвя поръчката. Отговорете на имейла за промени.",
        "open": "Отворете личната връзка от имейла за поръчката.",
        "receivedState": "Очаква потвърждение",
        "cancelState": "Отказана",
        "acceptedState": "Потвърдена",
        "progressState": "В изпълнение",
        "readyState": "Готова",
        "completedState": "Завършена",
        "receipt": "Получена поръчка",
        "details": "Детайли на поръчката",
    },
}


def company_words(config):
    names = config.get("name", {})
    result = {}
    for language, words in C.items():
        name = names.get(language, names.get("en", config.get("slug", "Company")))
        result[language] = {key: value.replace("{company}", name) for key, value in words.items()}
        result[language]["pickup"] = config.get("strings", {}).get(language, {}).get("pickup", words["pickup"])
    return result


def stamp():
    return datetime.now().astimezone().isoformat()


def dump(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


def private_key(path):
    path = Path(path)
    if not path.exists():
        fd, temporary = tempfile.mkstemp(prefix=".customer-link-", dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(secrets.token_bytes(32))
                stream.flush()
                os.fsync(stream.fileno())
            with suppress(FileExistsError):
                os.link(temporary, path)
        finally:
            os.unlink(temporary)
    info = path.lstat()
    if path.is_symlink() or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise PermissionError("Use the private company customer-link key.")
    key = path.read_bytes()
    if len(key) != 32:
        raise ValueError("The company customer-link key requires review.")
    return key


class CustomerMail:
    def __init__(self, store, origin=ORIGIN):
        if (
            urlsplit(origin).scheme not in {"https", "http"}
            or not urlsplit(origin).netloc
            or urlsplit(origin).path not in {"", "/"}
            or urlsplit(origin).query
            or urlsplit(origin).fragment
        ):
            raise ValueError("Choose the configured order-page origin.")
        self.store, self.origin = store, origin.rstrip("/")
        self.store.db.executescript(SCHEMA)
        company = store.one("SELECT id,config FROM company")
        self.company, self.config = company["id"], json.loads(company["config"])
        self.key = private_key(store.path.parent / "customer-link.key")

    def number(self, order_id):
        return str(self.config.get("orderPrefix", self.company.upper())) + "-" + order_id[:8].upper()

    def token(self, order_id, nonce):
        raw = hmac.new(
            self.key, (self.company + ":" + order_id + ":" + nonce).encode(), hashlib.sha256
        ).digest()
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")

    def ensure_link(self, order_id):
        self.store.read_order(order_id)
        row = self.store.one("SELECT * FROM customer_links WHERE order_id=?", (order_id,))
        if row is None:
            nonce = secrets.token_hex(24)
            token = self.token(order_id, nonce)
            self.store.db.execute(
                "INSERT OR IGNORE INTO customer_links VALUES(?,?,?,?,0)",
                (order_id, nonce, hashlib.sha256(token.encode()).hexdigest(), time.time() + 90 * 86400),
            )
            row = self.store.one("SELECT * FROM customer_links WHERE order_id=?", (order_id,))
        return row

    def link(self, order_id):
        row = self.ensure_link(order_id)
        return f"{self.origin}/{self.company}/manage/#{order_id}.{self.token(order_id, row['nonce'])}"

    def authorize(self, order_id, token):
        row = self.store.one("SELECT * FROM customer_links WHERE order_id=?", (order_id,))
        if (
            not isinstance(token, str)
            or len(token) > 128
            or row is None
            or row["revoked"]
            or row["expires"] <= time.time()
            or not hmac.compare_digest(row["token_hash"], hashlib.sha256(token.encode()).hexdigest())
        ):
            raise PermissionError("Open the private link from your order email.")
        return self.store.read_order(order_id)

    def language(self, order):
        lang = order["customer"].get("language", self.config.get("defaultLanguage", "en"))
        return lang if lang in C else "en"

    def queue(self, order_id, kind="received", event_key=None, body=""):
        if kind not in {"received", "accepted", "delivery", "reviewed", "cancelled", "changed", "reply", "requestReceived", "invoice"}:
            raise ValueError("Choose an order email type.")
        if not isinstance(body, str) or len(body) > 10000:
            raise ValueError("Keep the message within 10000 characters.")
        order = self.store.read_order(order_id)
        # Demo identity belongs to the saved order, including when its contact is edited.
        # All producers share this boundary: event scans, public receipts and staff updates.
        if order["customer"].get("is_demo") is True:
            return None
        if kind == "invoice" and not order.get("invoice"):
            raise ValueError("Record the issued invoice before queuing its update.")
        self.ensure_link(order_id)
        language = self.language(order)
        names = self.config.get("name", {})
        company_name = names.get(language, names.get("en", self.company))
        subject = (
            company_name + (" · Поръчка " if language == "bg" else " · Order ") + self.number(order_id)
        )
        root_id = f"<orders-{order_id}-received@orders.example.test>"
        self.store.db.execute(
            "INSERT OR IGNORE INTO mail_threads VALUES(?,?,?,NULL,NULL,?)",
            (order_id, subject, root_id, language),
        )
        if kind != "received" and not event_key:
            raise ValueError("An update requires a stable event key.")
        key = event_key or f"{order_id}:received"
        identity = hashlib.sha256(key.encode()).hexdigest()[:32]
        message_id = (
            root_id if kind == "received" else f"<orders-{order_id}-{identity}@orders.example.test>"
        )
        self.store.db.execute(
            "INSERT OR IGNORE INTO mail_outbox(id,order_id,event_key,kind,body,message_id,created_at) VALUES(?,?,?,?,?,?,?)",
            (identity, order_id, key, kind, body, message_id, stamp()),
        )
        queued = self.store.one("SELECT * FROM mail_outbox WHERE event_key=?", (key,))
        if queued["order_id"] != order_id or queued["kind"] != kind or queued["body"] != body:
            raise ValueError("Email event key belongs to different content.")
        return queued

    def sync_events(self):
        mapping = {
            "requested": "received",
            "accepted": "accepted",
            "delivery_confirmed": "delivery",
            "quote_reviewed": "reviewed",
            "cancelled": "cancelled",
            "time_changed": "changed",
            "change_requested": "requestReceived",
            "invoice_issued": "invoice",
        }
        for event in self.store.rows("SELECT id,order_id,event FROM order_events ORDER BY id"):
            if event["event"] in mapping:
                if not self.store.read_order(event["order_id"])["customer"].get("email"):
                    continue
                key = None if event["event"] == "requested" else f"event:{event['id']}"
                self.queue(event["order_id"], mapping[event["event"]], key)

    def lines(self, order, language):
        result = []
        catalog = self.store.export_catalog()
        items = {i["c"]: (cat, i) for cat in catalog["cats"] for i in cat["items"]}
        for line in order["lines"]:
            cat, item = items.get(line.get("item_id"), ({}, {}))
            title = line.get("description") or (
                cat.get("product", {}).get(language)
                or cat.get(language)
                or cat.get("en")
                or line.get("item_id", "")
            )
            if item.get("s"):
                title += " " + item["s"]
            conf = line.get("configuration", {})
            detail = []
            if line.get("kind") == "sheet" and conf.get("sheet"):
                sheet = conf["sheet"]
                detail.append(f"{sheet['n']} × {sheet['a']:g} × {sheet['b']:g} mm")
            elif conf.get("rows"):
                for row in conf["rows"]:
                    detail.append(
                        f"{row['n']} × {row['x']:g} mm"
                        if row.get("x")
                        else f"{row['n']} {C[language]['pieces']}"
                    )
            else:
                detail.append(f"{line.get('requested_quantity', line['quantity']):g} {C[language]['pieces']}")
            if conf.get("angle"):
                angle = conf["angle"]
                if isinstance(angle, dict):
                    detail.append(f"{angle.get('degrees', 90)}° · {angle.get('ends', 1)} ends")
            result.append(
                {
                    "sku": line.get("item_id"),
                    "title": title,
                    "details": " · ".join(detail),
                    "gross": line.get("gross", 0),
                    "confirmation": bool(line.get("confirmation")),
                    "source": line.get("source") or catalog.get("source"),
                }
            )
        return result

    def projection(self, order_id, token):
        order = self.authorize(order_id, token)
        language = self.language(order)
        internal_ready = (
            order["estimates"][-1]["data"]
            if order["estimates"]
            else order["quote"].get("ready", {})
        )
        ready = public_ready(internal_ready)
        delivery = order["quote"].get("delivery")
        invoice = self.store.one(
            "SELECT number,issued_at,currency,amount,document_url FROM invoices WHERE order_id=?", (order_id,)
        )
        projection = {
            "id": order_id,
            "number": self.number(order_id),
            "state": order["state"],
            "language": language,
            "logo": f"/{self.company}/"
            + self.config.get("logos", {})
            .get(language, self.config.get("logo", "/_public/images/logo.png"))
            .lstrip("/"),
            "customer": {
                k: v
                for k, v in order["customer"].items()
                if k in {"name", "email", "phone", "line1", "line2", "city", "zip"}
            },
            "lines": self.lines(order, language),
            "quote": {
                k: v
                for k, v in order["quote"].items()
                if k in {"gross", "net", "vat", "currency", "confirmation", "fulfilment", "breakdown"}
            },
            "delivery": {
                "status": delivery["status"],
                "arrival": {k: delivery["arrival"][k] for k in {"earliest", "latest", "timezone"}},
                "terms": delivery["terms"],
                "fee": delivery["fee"],
            }
            if isinstance(delivery, dict) and delivery.get("status") == "confirmed"
            else None,
            "ready": ready,
            "invoice": invoice,
            "changes": [
                {k: v for k, v in row.items() if k in {"kind", "body", "status", "created_at"}}
                for row in self.store.rows(
                    "SELECT * FROM customer_requests WHERE order_id=? ORDER BY created_at", (order_id,)
                )
            ],
            "events": [
                {k: v for k, v in row.items() if k in {"event", "created_at"}}
                for row in self.store.rows(
                    "SELECT event,created_at FROM order_events WHERE order_id=? ORDER BY id", (order_id,)
                )
            ],
        }
        if isinstance(order["quote"].get("review"), dict):
            projection["quote"]["review"] = {
                key: order["quote"]["review"][key]
                for key in ("id", "state", "assent_required", "reason", "previous_gross", "gross", "currency")
                if key in order["quote"]["review"]
            }
        return projection

    def change(self, order_id, token, kind, body, key, review_id=None):
        self.authorize(order_id, token)
        if kind not in {"cancel", "change", "assent"} or not isinstance(body, str) or len(body) > 4000:
            raise ValueError("Describe a change within 4000 characters.")
        if kind == "change" and not body.strip():
            raise ValueError("Describe the change you would like.")
        if not re.fullmatch(r"[A-Za-z0-9_-]{16,128}", key or ""):
            raise ValueError("Refresh the order page and try again.")
        if kind == "assent":
            if not isinstance(review_id, str) or not re.fullmatch(r"[a-f0-9]{24}", review_id):
                raise ValueError("Confirm the current reviewed total.")
            try:
                from .reviewed_orders import assent_reviewed_quote
            except ImportError:
                from reviewed_orders import assent_reviewed_quote
            return assent_reviewed_quote(
                self.store,
                order_id,
                review_id,
                "customer-link",
                "private order link",
                key,
            )
        payload = {"order_id": order_id, "kind": kind, "body": body.strip()}

        def update():
            order = self.store.read_order(order_id)
            if order["state"] != "requested":
                raise ValueError("Reply to your order email to discuss changes with the team.")
            identity = uuid.uuid4().hex
            self.store.db.execute(
                "INSERT INTO customer_requests(id,order_id,kind,body,created_at) VALUES(?,?,?,?,?)",
                (identity, order_id, kind, body.strip(), stamp()),
            )
            if kind == "cancel":
                self.store.db.execute("UPDATE orders SET state='cancelled' WHERE id=?", (order_id,))
                self.store.db.execute(
                    "UPDATE customer_requests SET status='completed' WHERE id=?", (identity,)
                )
                event_id = self.store._event(
                    "order_events",
                    {"customer_request": identity},
                    "customer-link",
                    "private order link",
                    order_id=order_id,
                    event="cancelled",
                )
            else:
                event_id = self.store._event(
                    "order_events",
                    {"customer_request": identity, "body": body.strip()},
                    "customer-link",
                    "private order link",
                    order_id=order_id,
                    event="change_requested",
                )
            return {
                "id": identity,
                "event_id": event_id,
                "state": "cancelled" if kind == "cancel" else "requested",
            }

        result = self.store._write(
            "customer.change", payload, "customer-link", "private order link", key, update
        )
        self.queue(
            order_id, "cancelled" if kind == "cancel" else "requestReceived", f"event:{result['event_id']}"
        )
        return result

    def status(self):
        rows = self.store.rows(
            "SELECT id,order_id,kind,state,message_id,provider_id,provider_thread_id,attempts FROM mail_outbox ORDER BY created_at"
        )
        for row in rows:
            customer = self.store.read_order(row["order_id"])["customer"]
            address = customer.get("email", "")
            row["preview"] = customer.get("is_demo") is True or address.rsplit(".", 1)[-1].lower() in {"invalid", "test", "example", "localhost"}
        return rows

    def render(self, mail_id):
        mail = self.store.one("SELECT * FROM mail_outbox WHERE id=?", (mail_id,))
        if not mail:
            raise ValueError("Unknown email.")
        order = self.store.read_order(mail["order_id"])
        thread = self.store.one("SELECT * FROM mail_threads WHERE order_id=?", (order["id"],))
        lang = thread["language"]
        words = company_words(self.config)[lang]
        link = self.link(order["id"])
        esc = html.escape
        internal_ready = (
            order["estimates"][-1]["data"]
            if order["estimates"]
            else order["quote"].get("ready", {})
        )
        ready = public_ready(internal_ready)
        ready_text = words["await"]
        if ready.get("earliest") and ready.get("latest"):
            dates = [datetime.fromisoformat(ready[x]) for x in ("earliest", "latest")]
            ready_text = " – ".join(d.strftime("%d.%m.%Y" if lang == "bg" else "%d %b %Y") for d in dates)
        delivery = order["quote"].get("delivery")
        delivery_text = ""
        delivery_html = ""
        delivery_plain = ""
        if isinstance(delivery, dict) and delivery.get("status") == "confirmed":
            arrival = delivery["arrival"]
            zone = ZoneInfo(arrival["timezone"])
            dates = [datetime.fromisoformat(arrival[x]).astimezone(zone) for x in ("earliest", "latest")]
            delivery_text = " – ".join(
                value.strftime("%d.%m.%Y, %H:%M" if lang == "bg" else "%d %b %Y, %H:%M")
                for value in dates
            )
            fee = delivery["fee"]
            fee_text = words["deliveryFeeIncluded"] if fee.get("included") else (
                words["deliveryFee"] + ": " + money(fee["amount"], lang, fee["currency"])
            )
            delivery_html = f'<div style="margin-top:14px"><div style="font-size:13px;color:#68706c;margin-bottom:6px">{esc(words["deliveryDate"])}</div><strong style="font-size:17px;line-height:1.4">{esc(delivery_text)}</strong><div style="font-size:14px;line-height:1.5;color:#65706a;margin-top:8px">{esc(words["deliveryTerms"])}: {esc(delivery["terms"])}</div><div style="font-size:14px;line-height:1.5;color:#65706a;margin-top:4px">{esc(fee_text)}</div></div>'
            delivery_plain = f"\n{words['deliveryDate']}: {delivery_text}\n{words['deliveryTerms']}: {delivery['terms']}\n{fee_text}\n"
        names = self.config.get("name", {})
        name = names.get(lang, names.get("en", self.company))
        logo = self.config.get("logos", {}).get(lang, self.config.get("logo", "/_public/images/logo.png"))
        logo_url = f"{self.origin}/{self.company}/{logo.lstrip('/')}"
        accent = self.config.get("accent", "#f29400")
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", accent):
            accent = "#f29400"
        source_url = self.config.get("source", self.origin + "/" + self.company + "/")
        if urlsplit(source_url).scheme not in {"https", "http"}:
            source_url = self.origin + "/" + self.company + "/"
        lines = self.lines(order, lang)
        rows = ""
        plain = []
        for line in lines:
            amount = words["pending"] if line["confirmation"] else money(line["gross"], lang)
            plain.append(f"{line['title']} ({line['sku'] or ''})\n{line['details']} · {amount}")
            rows += f'<tr><td style="padding:20px 0;border-bottom:1px solid #e6e5e0;vertical-align:top"><strong style="font-size:17px;line-height:1.35">{esc(line["title"])}</strong><div style="font-size:14px;color:#666b6c;margin-top:6px">{esc(line["details"])}</div><div style="font-size:12px;color:#888e8c;margin-top:5px">{esc(line["sku"] or "")}</div></td><td style="padding:20px 0 20px 14px;border-bottom:1px solid #e6e5e0;text-align:right;vertical-align:top;font-weight:700;white-space:nowrap">{esc(amount)}</td></tr>'
        awaiting_review = order["quote"].get("review", {}).get("state") == "awaiting_customer"
        has_pending_price = order["quote"].get("confirmation") or any(line["confirmation"] for line in lines)
        total = money(order["quote"].get("gross", 0), lang) if awaiting_review else words["pending"] if has_pending_price else money(order["quote"].get("gross", 0), lang)
        total_label = words["reviewedTotal"] if awaiting_review else words["priceOnConfirmation"] if has_pending_price else words["total"]
        heading = words["invoiceIssued"] if mail["kind"] == "invoice" else words["deliveryConfirmed"] if mail["kind"] == "delivery" else words[mail["kind"]]
        intro = (
            words["confirmed"]
            if mail["kind"] == "accepted"
            else words["cancelCopy"]
            if mail["kind"] == "cancelled"
            else words["requestCopy"]
            if mail["kind"] == "requestReceived"
            else words["invoiceDocument"]
            if mail["kind"] == "invoice"
            else words["deliveryCopy"]
            if mail["kind"] == "delivery"
            else words["reviewedCopy"]
            if mail["kind"] == "reviewed"
            else words["introPrice"]
            if has_pending_price
            else words["intro"]
        )
        if awaiting_review and mail["kind"] != "reviewed":
            intro = intro + " " + words["reviewedCopy"]
        fulfil = words["delivery"] if order["quote"].get("fulfilment") == "delivery" else words["pickup"]
        note = (
            f'<p style="font-size:16px;line-height:1.6;white-space:pre-wrap">{esc(mail["body"])}</p>'
            if mail["body"]
            else ""
        )
        context_labels = {'company': ('Company', 'Фирма'), 'website': ('Website', 'Уебсайт'),
                          'trade': ('Type of work', 'Дейност'), 'project': ('Project', 'Проект')}
        context = [(labels[1 if lang == 'bg' else 0], order['customer'].get(key, ''))
                   for key, labels in context_labels.items() if order['customer'].get(key)]
        context_html = ''.join(f'<p style="font-size:14px;line-height:1.5"><strong>{esc(label)}</strong>: {esc(str(value))}</p>' for label, value in context)
        context_text = '\n'.join(f'{label}: {value}' for label, value in context)
        note += context_html
        ready_label = (
            words["ready"]
            if ready.get("kind") == "promise"
            else words["confirmationReady"]
            if ready.get("kind") == "confirmation"
            else words["estimated"]
        )
        number = self.number(order["id"])
        invoice = order.get("invoice")
        invoice_html = ""
        invoice_text = ""
        if mail["kind"] == "invoice" and invoice:
            invoice_amount = money(invoice["amount"], lang)
            invoice_html = f'<p style="margin:0 0 24px;font-size:16px;line-height:1.6"><strong>{esc(invoice["number"])}</strong> · {esc(invoice_amount)}<br><a href="{esc(invoice["document_url"], quote=True)}" style="color:{accent};font-weight:700">{esc(words["viewInvoice"])}</a></p>'
            invoice_text = f"\n{words['invoice']}: {invoice['number']} · {invoice_amount}\n{words['viewInvoice']}: {invoice['document_url']}\n"
        body = f'''<!doctype html><html lang="{lang}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{esc(thread["subject"])}</title><style>@font-face{{font-family:Inter;src:url("{esc(self.origin, quote=True)}/{esc(self.company, quote=True)}/rocoto/inter.woff2") format("woff2");font-style:normal;font-weight:400;font-display:swap}}</style></head>
<body style="margin:0;background:#f3f3ef;color:#242728;font-family:Inter,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif"><div style="display:none;max-height:0;overflow:hidden">{esc(heading)} · {esc(number)}</div>
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f3f3ef"><tr><td align="center" style="padding:32px 14px"><table role="presentation" width="600" cellspacing="0" cellpadding="0" style="width:100%;max-width:600px"><tr><td style="padding:0 10px 26px"><img src="{esc(logo_url, quote=True)}" alt="{esc(name, quote=True)}" width="182" style="width:182px;max-width:70%;height:auto;display:block"></td></tr>
<tr><td style="background:#fff;border-top:5px solid {accent};padding:32px 26px;border-radius:3px;font-family:Inter,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif"><div style="color:#707674;font-size:13px;margin-bottom:16px">{esc(words["order"])} {esc(number)}</div><h1 style="font-size:32px;line-height:1.16;letter-spacing:-.6px;margin:0 0 17px;font-weight:700">{esc(heading)}</h1><p style="font-size:16px;line-height:1.55;color:#555e5b;margin:0 0 24px">{esc(intro)}</p>{invoice_html}{note}
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f5f5f0;border-radius:8px;margin-bottom:26px"><tr><td style="padding:20px"><div style="font-size:13px;color:#68706c;margin-bottom:6px">{esc(ready_label)}</div><strong style="font-size:19px;line-height:1.4">{esc(ready_text)}</strong><div style="font-size:14px;line-height:1.5;color:#65706a;margin-top:10px">{esc(fulfil)}</div>{delivery_html}</td></tr></table>
<a href="{esc(link, quote=True)}" style="display:block;background:{accent};border-radius:7px;text-decoration:none;text-align:center;color:#181a18;font-size:17px;line-height:24px;font-weight:700;padding:17px 14px">{esc(words["manage"])} →</a>
<h2 style="font-size:19px;margin:34px 0 0">{esc(words["summary"])}</h2><table role="presentation" cellspacing="0" cellpadding="0" width="100%">{rows}</table>
<table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr><td style="padding-top:22px;font-size:16px">{esc(total_label)}<div style="font-size:12px;color:#727974;margin-top:6px">{esc(words["vat"])}</div></td><td style="padding-top:22px;text-align:right;font-size:24px;font-weight:700;white-space:nowrap">{esc(total)}</td></tr></table>
<p style="margin:30px 0 0;padding-top:24px;border-top:1px solid #e6e5e0;font-size:15px;line-height:1.6;color:#59635e">{esc(words["replyCopy"])}</p></td></tr>
<tr><td style="padding:24px 18px;font-size:12px;line-height:1.65;color:#7c837f">{esc(words["private"])}<br><a href="{esc(source_url, quote=True)}" style="color:#6d7570;text-decoration:underline">{esc(words["source"])}</a><br>{esc(name)}</td></tr></table></td></tr></table></body></html>'''
        text = (
            f"{name}\n{words['order']} {number}\n\n{heading}\n{intro}\n{invoice_text}{delivery_plain}\n{mail['body']}\n{context_text}\n{ready_label}: {ready_text}\n{fulfil}\n\n{words['manage']}: {link}\n\n"
            + "\n\n".join(plain)
            + f"\n\n{total_label}: {total} · {words['vat']}\n\n{words['replyCopy']}\n{words['private']}\n"
        )
        return {
            "html": body,
            "text": text,
            "subject": thread["subject"],
            "to": order["customer"]["email"],
            "message_id": mail["message_id"],
            "thread": thread,
            "company_name": name,
        }

    def mime(self, mail_id, sender=SENDER):
        rendered = self.render(mail_id)
        message = EmailMessage(policy=SMTP)
        message["Date"] = format_datetime(datetime.now().astimezone())
        message["From"] = formataddr((rendered["company_name"], sender))
        message["To"] = rendered["to"]
        message["Reply-To"] = sender
        message["Subject"] = rendered["subject"]
        message["Message-ID"] = rendered["message_id"]
        thread = rendered["thread"]
        if rendered["message_id"] != thread["root_message_id"]:
            message["In-Reply-To"] = thread["last_message_id"] or thread["root_message_id"]
            message["References"] = " ".join(
                dict.fromkeys(
                    [thread["root_message_id"], thread["last_message_id"] or thread["root_message_id"]]
                )
            )
        message.set_content(rendered["text"])
        message.add_alternative(rendered["html"], subtype="html")
        return message

    def prepare(self, mail_id, authorization):
        if not authorization:
            raise PermissionError("Commission the email runtime and record sending authority first.")
        mail = self.store.one("SELECT * FROM mail_outbox WHERE id=?", (mail_id,))
        if not mail or mail["state"] != "held":
            raise ValueError("Select a held email; review earlier attempts before sending.")
        if self.store.read_order(mail["order_id"])["customer"].get("is_demo") is True:
            raise PermissionError("Demo order messages remain held for preview.")
        thread = self.store.one("SELECT * FROM mail_threads WHERE order_id=?", (mail["order_id"],))
        if mail["message_id"] != thread["root_message_id"] and not thread["provider_thread_id"]:
            raise ValueError("Send the original receipt before threaded updates.")
        mime = self.mime(mail_id)
        changed = self.store.db.execute(
            "UPDATE mail_outbox SET state='sending',attempts=attempts+1 WHERE id=? AND state='held'",
            (mail_id,),
        ).rowcount
        if not changed:
            raise ValueError("Email is already being handled.")
        self.store.db.execute(
            "INSERT INTO mail_events(mail_id,kind,data,created_at) VALUES(?,?,?,?)",
            (
                mail_id,
                "prepared",
                dump(
                    {
                        "authorization": authorization,
                        "subject": str(mime["Subject"]),
                        "message_id": str(mime["Message-ID"]),
                        "in_reply_to": str(mime["In-Reply-To"] or ""),
                        "references": str(mime["References"] or ""),
                        "provider_thread_id": thread["provider_thread_id"],
                    }
                ),
                stamp(),
            ),
        )
        return {
            "raw": base64.urlsafe_b64encode(mime.as_bytes()).decode(),
            "threadId": thread["provider_thread_id"],
            "message_id": mail["message_id"],
        }

    def settle(self, mail_id, receipt, authorization):
        if (
            not authorization
            or not isinstance(receipt, dict)
            or any(
                not isinstance(receipt.get(k), str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", receipt[k])
                for k in ("id", "threadId")
            )
        ):
            raise ValueError("Record the provider message/thread receipt and authority.")
        provider_message_id = receipt.get("messageId") or None
        if provider_message_id is not None and not re.fullmatch(r"<[^\s<>]{1,240}>", provider_message_id):
            raise ValueError("Record the provider RFC Message-ID with the receipt.")
        self.store.db.execute("BEGIN IMMEDIATE")
        try:
            mail = self.store.one("SELECT * FROM mail_outbox WHERE id=?", (mail_id,))
            if not mail or mail["state"] not in {"sending", "uncertain", "sent"}:
                raise ValueError("An attempted email is required for a receipt.")
            if mail["state"] == "sent" and (
                mail["provider_id"] != receipt["id"] or mail["provider_thread_id"] != receipt["threadId"]
            ):
                raise ValueError("The recorded receipt differs; review the provider conversation.")
            thread = self.store.one("SELECT * FROM mail_threads WHERE order_id=?", (mail["order_id"],))
            if thread["provider_thread_id"] and thread["provider_thread_id"] != receipt["threadId"]:
                raise ValueError("The provider returned a different email thread.")
            if mail["state"] != "sent":
                self.store.db.execute(
                    "UPDATE mail_outbox SET state='sent',provider_id=?,provider_thread_id=?,sent_at=? WHERE id=?",
                    (receipt["id"], receipt["threadId"], stamp(), mail_id),
                )
                self.store.db.execute(
                    "UPDATE mail_threads SET provider_thread_id=?,last_message_id=? WHERE order_id=?",
                    (receipt["threadId"], provider_message_id or mail["message_id"], mail["order_id"]),
                )
                self.store.db.execute(
                    "INSERT INTO mail_events(mail_id,kind,data,created_at) VALUES(?,?,?,?)",
                    (mail_id, "sent", dump({"receipt": receipt, "authorization": authorization}), stamp()),
                )
            self.store.db.execute("COMMIT")
        except BaseException:
            self.store.db.execute("ROLLBACK")
            raise
        return self.store.one("SELECT * FROM mail_outbox WHERE id=?", (mail_id,))

    def uncertain(self, mail_id, reason="Provider receipt requires review"):
        changed = self.store.db.execute(
            "UPDATE mail_outbox SET state='uncertain' WHERE id=? AND state='sending'", (mail_id,)
        ).rowcount
        if changed:
            self.store.db.execute(
                "INSERT INTO mail_events(mail_id,kind,data,created_at) VALUES(?,?,?,?)",
                (mail_id, "uncertain", dump({"reason": reason}), stamp()),
            )

    def reconcile(self, mail_id, transport, authorization):
        mail = self.store.one("SELECT * FROM mail_outbox WHERE id=?", (mail_id,))
        if not mail or mail["state"] not in {"sending", "uncertain"}:
            raise ValueError("Select an attempted email awaiting its receipt.")
        receipt = transport.lookup(mail["message_id"])
        if receipt:
            return self.settle(mail_id, receipt, authorization)
        self.uncertain(mail_id)
        return {
            "id": mail_id,
            "state": "uncertain",
            "note": "SENT lookup has no receipt; review before any retry.",
        }

    def deliver(self, mail_id, transport, authorization):
        mail = self.store.one("SELECT * FROM mail_outbox WHERE id=?", (mail_id,))
        if mail and mail["state"] == "sent":
            return mail
        prepared = self.prepare(mail_id, authorization)
        try:
            receipt = transport.send(base64.urlsafe_b64decode(prepared["raw"]), prepared["threadId"])
            return self.settle(mail_id, receipt, authorization)
        except BaseException as error:
            self.uncertain(mail_id, type(error).__name__)
            raise

    def record_reply(self, order_id, message):
        thread = self.store.one("SELECT * FROM mail_threads WHERE order_id=?", (order_id,))
        if not thread or message.get("threadId") != thread["provider_thread_id"]:
            raise ValueError("Reply belongs to another provider conversation.")
        headers = {h["name"].lower(): h["value"] for h in message.get("payload", {}).get("headers", [])}
        expected = self.store.read_order(order_id)["customer"]["email"].casefold()
        if parseaddr(headers.get("from", ""))[1].casefold() != expected:
            raise UnrelatedReply("Reply sender must match the order contact.")
        mid = headers.get("message-id", "")
        if not re.fullmatch(r"<[^\s<>]{1,240}>", mid):
            raise ValueError("Reply Message-ID requires review.")
        inserted = self.store.db.execute(
            "INSERT OR IGNORE INTO mail_replies VALUES(?,?,?,?,?,?,?)",
            (
                message["id"],
                order_id,
                message["threadId"],
                mid,
                headers.get("in-reply-to", ""),
                headers.get("references", ""),
                stamp(),
            ),
        ).rowcount
        if inserted:
            self.store.db.execute(
                "UPDATE mail_threads SET last_message_id=? WHERE order_id=?", (mid, order_id)
            )


class NativeGmail:
    """The commissioned Rocoto route; MIME travels as a private Gmail Message.raw request."""

    def __init__(
        self,
        launcher="/home/peter/rocoto-company/tools/google",
        cwd="/home/peter/rocoto-company",
        connection_factory=None,
    ):
        self.launcher, self.cwd = launcher, cwd
        self.connection_factory = connection_factory or http.client.HTTPSConnection

    def call(self, method, params, extra=(), *, cwd=None):
        result = subprocess.run(
            [self.launcher, "gmail", "users", *method, "--params", dump({"userId": "me", **params}), *extra],
            cwd=cwd or self.cwd,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if result.returncode:
            raise RuntimeError("Gmail operation requires receipt review.")
        return json.loads(result.stdout)

    def lookup(self, message_id):
        if not re.fullmatch(r"<[^\s<>]{1,240}>", message_id):
            raise ValueError("Use a valid Message-ID.")
        found = self.call(
            ["messages", "list"], {"q": "in:sent rfc822msgid:" + message_id[1:-1], "maxResults": 2}
        )
        messages = found.get("messages", [])
        if len(messages) > 1:
            raise ValueError("Multiple SENT receipts require review.")
        if not messages:
            return None
        result = self.call(
            ["messages", "get"],
            {"id": messages[0]["id"], "format": "metadata", "metadataHeaders": ["Message-ID"]},
        )
        headers = {h["name"].lower(): h["value"] for h in result.get("payload", {}).get("headers", [])}
        if headers.get("message-id") != message_id or "SENT" not in result.get("labelIds", []):
            raise ValueError("The SENT receipt does not match this message.")
        return {"id": result["id"], "threadId": result["threadId"], "messageId": message_id}

    def native_credentials(self):
        status = subprocess.run(
            [self.launcher, "auth", "status"],
            cwd=self.cwd,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        try:
            identity = json.loads(status.stdout)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise RuntimeError("Gmail identity requires review.") from error
        if status.returncode or identity.get("token_valid") is not True or identity.get("user") != SENDER:
            raise RuntimeError("Gmail identity requires review.")
        exported = subprocess.run(
            [self.launcher, "auth", "export", "--unmasked"],
            cwd=self.cwd,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        try:
            credentials = json.loads(exported.stdout)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise RuntimeError("Gmail credentials require review.") from error
        required = ("client_id", "client_secret", "refresh_token")
        if exported.returncode or credentials.get("type") != "authorized_user" or any(
            not isinstance(credentials.get(key), str) or not credentials[key] for key in required
        ):
            raise RuntimeError("Gmail credentials require review.")
        return {key: credentials[key] for key in required}

    def post_json(self, host, path, body, headers):
        connection = self.connection_factory(host, timeout=30)
        try:
            connection.request("POST", path, body, headers)
            response = connection.getresponse()
            raw = response.read(64 * 1024 + 1)
        finally:
            connection.close()
        if response.status != 200 or len(raw) > 64 * 1024:
            raise RuntimeError("Gmail operation requires receipt review.")
        try:
            result = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise RuntimeError("Gmail operation requires receipt review.") from error
        if not isinstance(result, dict):
            raise RuntimeError("Gmail operation requires receipt review.")
        return result

    def raw_send(self, raw, thread_id=None):
        credentials = self.native_credentials()
        token = self.post_json(
            "oauth2.googleapis.com",
            "/token",
            urlencode({**credentials, "grant_type": "refresh_token"}).encode(),
            {"Content-Type": "application/x-www-form-urlencoded"},
        ).get("access_token")
        if not isinstance(token, str) or not 10 <= len(token) <= 4096:
            raise RuntimeError("Gmail authorization requires review.")
        message = {"raw": base64.urlsafe_b64encode(raw).decode()}
        if thread_id:
            message["threadId"] = thread_id
        receipt = self.post_json(
            "gmail.googleapis.com",
            "/gmail/v1/users/me/messages/send",
            dump(message).encode(),
            {"Authorization": "Bearer " + token, "Content-Type": "application/json"},
        )
        if any(
            not isinstance(receipt.get(key), str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", receipt[key])
            for key in ("id", "threadId")
        ):
            raise RuntimeError("Gmail operation requires receipt review.")
        return receipt

    def stored_receipt(self, receipt):
        result = self.call(
            ["messages", "get"],
            {
                "id": receipt["id"],
                "format": "metadata",
                "metadataHeaders": ["Message-ID"],
            },
        )
        headers = {h["name"].lower(): h["value"] for h in result.get("payload", {}).get("headers", [])}
        message_id = headers.get("message-id", "")
        if (
            result.get("id") != receipt["id"]
            or result.get("threadId") != receipt["threadId"]
            or "SENT" not in result.get("labelIds", [])
            or not re.fullmatch(r"<[^\s<>]{1,240}>", message_id)
        ):
            raise RuntimeError("Gmail receipt requires review.")
        return {"id": receipt["id"], "threadId": receipt["threadId"], "messageId": message_id}

    def send(self, raw, thread_id=None):
        from email import message_from_bytes

        message = message_from_bytes(raw)
        message_id = message["Message-ID"].strip()
        recipient = parseaddr(message["To"])[1]
        if recipient.rsplit(".", 1)[-1].lower() in {"invalid", "test", "example", "localhost"}:
            raise ValueError("Preview recipients remain held for local inspection.")
        found = self.lookup(message_id)
        if found:
            return found
        return self.stored_receipt(self.raw_send(raw, thread_id))

    def replies(self, thread_id):
        return self.call(
            ["threads", "get"],
            {
                "id": thread_id,
                "format": "metadata",
                "metadataHeaders": ["From", "Message-ID", "In-Reply-To", "References"],
            },
        ).get("messages", [])


def money(value, language, currency="EUR"):
    text = f"{float(value):,.2f}"
    if language == "bg":
        text = text.replace(",", " ").replace(".", ",")
    if currency == "EUR":
        return f"{text} €" if language == "bg" else f"€{text}"
    return f"{text} {currency}" if language == "bg" else f"{currency} {text}"


def main():
    from store import CompanyStore

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--origin", default=ORIGIN)
    parser.add_argument(
        "command",
        choices=[
            "scan",
            "preview",
            "status",
            "send",
            "prepare",
            "receipt",
            "uncertain",
            "reconcile",
            "replies",
            "reply-record",
        ],
    )
    parser.add_argument("--mail")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--authorization")
    args = parser.parse_args()
    store = CompanyStore(args.database)
    try:
        mail = CustomerMail(store, args.origin)
        if args.command == "scan":
            mail.sync_events()
        elif args.command == "preview":
            if not args.output:
                parser.error("--output is required")
            args.output.mkdir(mode=0o700, parents=True, exist_ok=True)
            rendered = mail.render(args.mail)
            for kind, extension in [("html", "html"), ("text", "txt")]:
                path = args.output / ("order-email." + extension)
                path.write_text(rendered[kind])
                path.chmod(0o600)
            print(
                dump(
                    {
                        "html": str(args.output / "order-email.html"),
                        "text": str(args.output / "order-email.txt"),
                    }
                )
            )
        elif args.command == "send":
            print(dump(mail.deliver(args.mail, NativeGmail(), args.authorization)))
        elif args.command == "prepare":
            print(dump(mail.prepare(args.mail, args.authorization)))
        elif args.command == "receipt":
            print(dump(mail.settle(args.mail, json.load(sys.stdin), args.authorization)))
        elif args.command == "uncertain":
            mail.uncertain(args.mail)
        elif args.command == "reconcile":
            print(dump(mail.reconcile(args.mail, NativeGmail(), args.authorization)))
        elif args.command == "reply-record":
            row = store.one("SELECT order_id FROM mail_outbox WHERE id=?", (args.mail,))
            if not row:
                raise ValueError("Unknown email.")
            mail.record_reply(row["order_id"], json.load(sys.stdin))
        elif args.command == "replies":
            row = store.one("SELECT order_id FROM mail_outbox WHERE id=?", (args.mail,))
            thread = store.one(
                "SELECT provider_thread_id FROM mail_threads WHERE order_id=?", (row["order_id"],)
            )
            for message in NativeGmail().replies(thread["provider_thread_id"]):
                if "SENT" not in message.get("labelIds", []):
                    mail.record_reply(row["order_id"], message)
        else:
            print(dump(mail.status()))
    finally:
        store.close()


if __name__ == "__main__":
    main()
