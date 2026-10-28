#!/usr/bin/env python3
"""Standalone real-route customer review drive; disposable data and zero provider calls."""

from __future__ import annotations

import json
import socket
import sqlite3
import sys
import tempfile
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import uvicorn
from fastapi import FastAPI
from fastapi.responses import Response
from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "verticals/manufacturer"))
from manufacturer_conversations import ManufacturerConversations  # noqa: E402
from manufacturer_customer_portal import CustomerPortal, register_customer_portal  # noqa: E402

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/manufacturer-customer-portal-qa")
OUT.mkdir(parents=True, exist_ok=True, mode=0o700)
checks, errors = [], []


def check(name, result):
    checks.append({"name": name, "passed": bool(result)})
    assert result, name


def current():
    return True


with tempfile.TemporaryDirectory(prefix="manufacturer-portal-drive-") as directory:
    state = Path(directory)
    store = ManufacturerConversations(state, "company-a")
    store.ensure_customer(
        "buyer",
        contacts=[{"email": "buyer@example.test", "phone": "+359888123456", "name": "Иван Петров"}],
        actor="peter",
        current=current,
    )
    document = {
        "id": "order-1",
        "customer_id": "buyer",
        "number": "#1001",
        "status": "requested",
        "currency": "EUR",
        "lines": [
            {
                "code": "101037",
                "name": "Дръжка за врата с розетка",
                "description": "Сатен · комплект",
                "quantity": 24,
                "unit": "pc",
                "unit_price": 15.5,
                "total": 372,
            },
            {
                "code": "104235",
                "name": "Секретна брава",
                "description": "За интериорна врата · 72 мм",
                "quantity": 24,
                "unit": "pc",
                "unit_price": 12.5,
                "total": 300,
            },
        ],
        "subtotal": 560,
        "tax": 112,
        "total": 672,
        "delivery": {
            "method": "Доставка до адрес",
            "address": "София, ул. Примерна 12",
            "date": "30 октомври 2026",
        },
        "terms": "Плащане по банков път.",
    }
    store.record_source_order("buyer", document, actor="peter", current=current)
    proposal = store.propose_request(
        "buyer",
        "order-1",
        proposal=document,
        recipient="buyer@example.test",
        actor="peter",
        expected_revision=0,
        idempotency_key="proposal-1",
        current=current,
    )["proposal"]
    portal = CustomerPortal(state, "company-a", "demo")
    display = {
        "company": "Sample Hardware",
        "customer": "Примерен клиент",
        "contact_name": "Иван Петров",
        "order_number": "#1001",
    }
    review = portal.mint_review(
        "buyer",
        "order-1",
        proposal["id"],
        recipient="buyer@example.test",
        actor="peter",
        display=display,
        current=current,
    )
    phone = portal.mint_phone("buyer", phone="+359888123456", actor="peter", display=display, current=current)
    access_path = state / "access.sqlite"
    with sqlite3.connect(access_path) as db:
        db.execute("CREATE TABLE environments(id TEXT PRIMARY KEY)")
        db.execute("INSERT INTO environments VALUES('demo')")

    @contextmanager
    def connect():
        with sqlite3.connect(access_path) as db:
            yield db

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    origin = "http://127.0.0.1:" + str(sock.getsockname()[1])
    host = SimpleNamespace(
        state=state, access=SimpleNamespace(connect=connect), options={}, public_origin=origin
    )
    app = FastAPI()
    theme = json.loads((HERE / "theme.json").read_text())
    css = ":root{" + "".join(f"--{key}:{value};" for key, value in theme["palette"].items())
    css += "--font:system-ui,sans-serif;--surface:color-mix(in srgb,var(--ink) 3%,var(--paper));"
    css += "--muted:color-mix(in srgb,var(--ink) 60%,var(--paper));"
    css += "--border:color-mix(in srgb,var(--ink) 14%,var(--paper));}"

    @app.get("/theme.css")
    def theme_css():
        return Response(css, media_type="text/css")

    def context(*_):
        raise AssertionError("Customer page attempted workspace access")

    register_customer_portal(app, host, context=context, invoke=lambda function: function())
    server = uvicorn.Server(uvicorn.Config(app, log_level="error"))
    thread = threading.Thread(target=lambda: server.run(sockets=[sock]), daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.02)
    assert server.started
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"]
        )
        context = browser.new_context(viewport={"width": 1600, "height": 1000})
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        try:
            page.goto(origin + "/customer/review#demo." + review["token"])
            page.get_by_role("button", name="Потвърждавам тази версия").wait_for()
            check("Fragment removed before page data", "#" not in page.url)
            check("Exact saved line count", page.locator(".portal-product").count() == 2)
            check(
                "No automatic confirmation",
                store.order_review("buyer", "order-1")["review_status"] == "review_pending",
            )
            check("Desktop fits", page.evaluate("document.documentElement.scrollWidth <= innerWidth"))
            page.screenshot(path=str(OUT / "review-1600.png"), full_page=True)
            page.get_by_role("button", name="Искам промяна").click()
            page.get_by_role("textbox", name="Какво искате да променим?").wait_for()
            check("Native modal focus", page.evaluate("document.activeElement.id === 'change-text'"))
            page.keyboard.press("Escape")
            check(
                "Escape restores trigger focus",
                page.get_by_role("button", name="Искам промяна").evaluate(
                    "el => el === document.activeElement"
                ),
            )
            for width in (390, 320):
                page.set_viewport_size({"width": width, "height": 844})
                check(
                    f"Review fits {width}",
                    page.evaluate("document.documentElement.scrollWidth <= innerWidth"),
                )
                page.screenshot(path=str(OUT / f"review-{width}.png"), full_page=True)
            page.set_viewport_size({"width": 390, "height": 844})
            page.get_by_role("button", name="Искам промяна").click()
            check(
                "Phone sheet fits",
                page.locator("dialog").evaluate("el => el.getBoundingClientRect().width <= innerWidth"),
            )
            page.screenshot(path=str(OUT / "change-390.png"))
            page.get_by_role("textbox", name="Какво искате да променим?").fill("Моля, срокът да е 2 ноември.")
            page.get_by_role("button", name="Изпрати промяната").click()
            page.get_by_text("Екипът ще подготви следващата версия.", exact=True).wait_for()
            check(
                "Change request committed to exact version",
                store.order_review("buyer", "order-1")["review_status"] == "changes_requested",
            )
            revision = store.order_review("buyer", "order-1")["revision"]
            updated = store.propose_request(
                "buyer",
                "order-1",
                proposal=document,
                recipient="buyer@example.test",
                actor="peter",
                expected_revision=revision,
                idempotency_key="proposal-2",
                current=current,
            )["proposal"]
            page.goto(origin + "/customer/review#demo." + review["token"])
            page.get_by_text("Версия за справка", exact=True).wait_for()
            check(
                "Old version remains readable with no confirm button",
                page.get_by_role("button", name="Потвърждавам тази версия").count() == 0,
            )
            latest = portal.mint_review(
                "buyer",
                "order-1",
                updated["id"],
                recipient="buyer@example.test",
                actor="peter",
                display=display,
                current=current,
            )
            page.goto(origin + "/customer/review#demo." + latest["token"])
            page.get_by_role("button", name="Потвърждавам тази версия").click()
            page.get_by_text("Екипът получи вашето потвърждение.", exact=True).wait_for()
            check(
                "Explicit latest confirmation preserves source state",
                store.order_review("buyer", "order-1")["source_status"] == "requested",
            )
            page.screenshot(path=str(OUT / "confirmed-390.png"), full_page=True)
            page.goto(origin + "/customer/phone#demo." + phone["token"])
            page.get_by_role("link", name="Обади се").wait_for()
            check(
                "Call targets exact verified number",
                page.get_by_role("link", name="Обади се").get_attribute("href") == "tel:+359888123456",
            )
            check("Phone fits", page.evaluate("document.documentElement.scrollWidth <= innerWidth"))
            page.screenshot(path=str(OUT / "phone-390.png"), full_page=True)
            check("No workspace cookies", context.cookies() == [])
            check(
                "No persistent capability storage",
                page.evaluate("localStorage.length === 0 && sessionStorage.length === 0"),
            )
            check("No browser exceptions", not errors)
        finally:
            (OUT / "report.json").write_text(json.dumps({"checks": checks, "errors": errors}, indent=2))
            print(
                json.dumps(
                    {
                        "passed": sum(row["passed"] for row in checks),
                        "checks": len(checks),
                        "errors": errors,
                        "out": str(OUT),
                    }
                )
            )
            browser.close()
            server.should_exit = True
            thread.join(timeout=5)
