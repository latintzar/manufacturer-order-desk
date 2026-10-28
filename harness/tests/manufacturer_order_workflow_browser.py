#!/usr/bin/env python3
"""Full native HTTPS order workflow on disposable synthetic source; zero provider calls.

Uses a fresh workspace and local identity. Optionally pass a synthetic source SQLite
fixture as argument 1, then an output directory as argument 2. No existing state is
modified; all credentials and customer review capabilities remain in memory.
"""

from __future__ import annotations

import json
import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import uvicorn
from playwright.sync_api import expect, sync_playwright

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
for key in tuple(os.environ):
    if key.startswith(("ROCOTO_", "WORKOS_", "OPENAI_", "RESEND_")):
        os.environ.pop(key)
os.environ["ROCOTO_VERTICAL"] = "manufacturer"
os.environ["ROCOTO_BROWSE_SESSIONS"] = "false"
import layout  # noqa: E402

layout.install("manufacturer")
from manufacturer_seed import seed  # noqa: E402
from server import create_app  # noqa: E402
from workspace_identity import workspace_scope  # noqa: E402

OUT = Path(sys.argv[2] if len(sys.argv) > 2 else "/tmp/manufacturer-order-workflow-qa")
OUT.mkdir(parents=True, exist_ok=True, mode=0o700)
checks, errors, rejected_external = [], [], set()
CATALOGUE_IMAGES = os.environ.get("MF_QA_CATALOGUE_IMAGES") == "1"


def check(name, result):
    checks.append({"name": name, "passed": bool(result)})
    assert result, name


def shot(page, name):
    path = OUT / (name + ".png")
    if CATALOGUE_IMAGES:
        for photo in page.locator(".mo-product-image img").all():
            expect(photo).not_to_have_js_property("naturalWidth", 0, timeout=20000)
    page.screenshot(path=str(path))
    path.chmod(0o600)


def fits(page):
    return page.evaluate("document.documentElement.scrollWidth <= innerWidth")


with tempfile.TemporaryDirectory(prefix="manufacturer-workflow-drive-") as directory:
    state = Path(directory)
    scope = workspace_scope(state)
    if len(sys.argv) > 1:
        source = state / "synthetic-source.sqlite"
        with (
            sqlite3.connect("file:" + str(Path(sys.argv[1]).resolve()) + "?mode=ro", uri=True) as original,
            sqlite3.connect(source) as copied,
        ):
            original.backup(copied)
        source.chmod(0o600)
        binding = state / "manufacturer-source.json"
        binding.write_text(
            json.dumps({"company_id": scope, "company_slug": "sample-hardware", "database": str(source)})
        )
        binding.chmod(0o600)
    else:
        source = Path(seed(state, scope)["source"])
    with sqlite3.connect(source) as db:
        order_id, source_customer = db.execute(
            "SELECT id,customer_id FROM orders WHERE state='requested' ORDER BY created_at LIMIT 1"
        ).fetchone()
        fixture = json.loads(
            db.execute("SELECT data FROM customers WHERE id=?", (source_customer,)).fetchone()[0]
        )
        fixture["phone"] = "+12025550123"  # Reserved fictional number, never called.
        db.execute("UPDATE customers SET data=? WHERE id=?", (json.dumps(fixture), source_customer))
        source_before = list(db.iterdump())
    cert, key = state / "localhost.crt", state / "localhost.key"
    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-days",
            "1",
            "-subj",
            "/CN=localhost",
            "-addext",
            "subjectAltName=IP:127.0.0.1,DNS:localhost",
            "-keyout",
            str(key),
            "-out",
            str(cert),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    key.chmod(0o600)
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    origin = "https://manufacturer-workflow.test"
    os.environ["ROCOTO_PUBLIC_ORIGIN"] = origin
    app = create_app(state=state)
    code = app.state.access.issue("demo", principal_id="workflow-qa", owner=True)
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host="127.0.0.1",
            port=port,
            ssl_certfile=str(cert),
            ssl_keyfile=str(key),
            log_level="warning",
        )
    )
    worker = threading.Thread(target=lambda: server.run(sockets=[sock]), daemon=True)
    worker.start()
    for _ in range(300):
        if server.started:
            break
        time.sleep(0.1)
    check("Isolated full native HTTPS server started", server.started)
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                args=[
                    "--no-sandbox",
                    "--disable-gpu",
                    "--disable-dev-shm-usage",
                    f"--host-resolver-rules=MAP manufacturer-workflow.test 127.0.0.1:{port}",
                    "--no-proxy-server",
                ]
            )
            merchant = browser.new_context(
                ignore_https_errors=True, viewport={"width": 1600, "height": 1000}, locale="bg-BG"
            )
            customer = browser.new_context(
                ignore_https_errors=True, viewport={"width": 390, "height": 844}, locale="bg-BG"
            )

            def local_only(route):
                url = route.request.url
                if url.startswith((origin + "/", "data:", "blob:")) or (
                    CATALOGUE_IMAGES
                    and route.request.resource_type == "image"
                    and url.startswith("https://orders.example.test/")
                ):
                    route.continue_()
                else:
                    rejected_external.add(url.split("?", 1)[0].split("#", 1)[0])
                    route.abort()

            for context in (merchant, customer):
                context.route("**/*", local_only)
            page = merchant.new_page()
            page.goto(origin, wait_until="domcontentloaded")
            login = page.evaluate(
                """async code => {const r=await fetch('/api/session',{
                    method:'POST',headers:{'Content-Type':'application/json','X-Rocoto-Page':'1'},
                    body:JSON.stringify({code})}); return r.status;}""",
                code,
            )
            check("Local owner admitted with native session", login == 200)
            page.on("pageerror", lambda error: errors.append(str(error)))
            portal = customer.new_page()
            portal.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(origin + "/?view=orders&order=" + order_id, wait_until="domcontentloaded")
            edit = page.get_by_role("button", name="Редактирай заявката", exact=True)
            edit.wait_for(timeout=30000)
            check("Native order edit action rendered", edit.is_visible())
            if CATALOGUE_IMAGES:
                photos = page.locator(".mo-product-image img")
                check("Authentic catalogue images available", photos.count() > 0)
                for photo in photos.all():
                    expect(photo).not_to_have_js_property("naturalWidth", 0, timeout=20000)
            shot(page, "01-order-desktop")
            page.get_by_role("button", name="Свържи се с клиента", exact=True).click()
            chat = page.locator(".mh-panel:not([hidden])")
            chat.locator(".mh-order-card").first.wait_for(timeout=20000)
            check("Order opens its human customer conversation", True)
            for width in (1600, 390, 320):
                page.set_viewport_size({"width": width, "height": 1000 if width == 1600 else 844})
                check(f"Contextual customer chat fits {width}", fits(page))
                shot(page, "01-order-chat-" + str(width))
            chat.get_by_role("button", name="Затваряне", exact=True).click()
            page.set_viewport_size({"width": 1600, "height": 1000})
            page.locator('a[href="tel:+12025550123"]').click()
            phone_drawer = page.locator("dialog.mr-drawer")
            qr = phone_drawer.locator(".mr-phone-qr")
            page.locator(".mr-phone-qr,.mr-drawer .mr-notice").wait_for(timeout=20000)
            if not qr.count():
                raise AssertionError("Phone drawer: " + phone_drawer.inner_text())
            qr.wait_for(timeout=20000)
            expect(qr).not_to_have_js_property("naturalWidth", 0)
            check(
                "Private phone QR loads under full native CSP",
                qr.evaluate(
                    "image => image.complete && image.naturalWidth > 0 "
                    "&& image.src.startsWith('data:image/svg+xml')"
                ),
            )
            shot(page, "01-phone-qr-desktop")
            phone_url = phone_drawer.get_by_role(
                "link", name="Отвори на това устройство", exact=True
            ).get_attribute("href")
            portal.goto(phone_url, wait_until="domcontentloaded")
            call = portal.get_by_role("link", name="Обади се", exact=True)
            call.wait_for(timeout=20000)
            check(
                "Phone handoff resolves exact verified source number",
                call.get_attribute("href") == "tel:+12025550123",
            )
            shot(portal, "01-phone-handoff-390")
            phone_drawer.get_by_role("button", name="Затваряне", exact=True).click()
            check(
                "Phone drawer returns focus to source contact",
                page.locator('a[href="tel:+12025550123"]').evaluate(
                    "element => document.activeElement === element"
                ),
            )
            edit.click()
            drawer = page.locator("dialog.mr-drawer")
            drawer.get_by_label("Количество", exact=True).first.wait_for()
            check("Request dialog has accessible name", bool(drawer.get_attribute("aria-labelledby")))
            check(
                "Drawer Close target is 44px",
                drawer.get_by_role("button", name="Затваряне", exact=True).bounding_box()["width"] >= 44,
            )
            drawer.get_by_label("Количество", exact=True).first.fill("24")
            for price in drawer.get_by_label("Ед. цена · EUR", exact=True).all():
                price.fill("15.50")
            drawer.get_by_label("Получаване", exact=True).fill("Доставка до адрес")
            drawer.get_by_label("Дата", exact=True).fill("30 октомври 2026")
            drawer.get_by_label("Адрес", exact=True).fill("София, ул. Примерна 12")
            drawer.get_by_label("Бележка към клиента", exact=True).fill(
                "Моля, потвърдете количествата и срока."
            )
            for width in (1600, 390, 320):
                page.set_viewport_size({"width": width, "height": 1000 if width == 1600 else 844})
                check(f"Request editor fits {width}", fits(page))
                shot(page, "02-editor-" + str(width))
            drawer.get_by_role("button", name="Провери с клиента", exact=True).click()
            preview = drawer.get_by_role("link", name="Преглед като клиент", exact=True)
            preview.wait_for(timeout=20000)
            check("Immutable proposal and private customer review created", preview.is_visible())
            private_url = preview.get_attribute("href")
            check("Review capability stays in fragment", "#demo." in private_url)
            shot(page, "03-review-ready-320")
            drawer.get_by_role("button", name="Затваряне", exact=True).click()
            portal.goto(private_url, wait_until="domcontentloaded")
            confirm = portal.get_by_role("button", name="Потвърждавам тази версия", exact=True)
            confirm.wait_for(timeout=20000)
            check("Customer page requires explicit confirmation", confirm.is_visible())
            check(
                "Customer page has exact edited quantity and price",
                portal.locator(".portal-product").first.inner_text().find("24 бр.") >= 0
                and "15,50" in portal.locator(".portal-product").first.inner_text(),
            )
            check("Capability removed from address after redemption", "#" not in portal.url)
            check("Public customer context has no workspace cookies", not customer.cookies())
            for width in (1600, 390, 320):
                portal.set_viewport_size({"width": width, "height": 1000 if width == 1600 else 844})
                check(f"Customer review fits {width}", fits(portal))
                shot(portal, "04-customer-review-" + str(width))
            confirm.click()
            portal.get_by_text("Екипът получи вашето потвърждение.", exact=True).wait_for()
            check("Exact-version customer confirmation saved", True)
            shot(portal, "05-customer-confirmed-320")
            page.set_viewport_size({"width": 1600, "height": 1000})
            customer_panel = page.locator(".mh-panel:not([hidden])")
            if customer_panel.count():
                customer_panel.get_by_role("button", name="Затваряне", exact=True).click()
            page.bring_to_front()
            page.get_by_role("button", name="Приеми поръчката", exact=True).wait_for(timeout=15000)
            check("Customer confirmation updates merchant detail without reload", True)
            for index, (status, label) in enumerate(
                (
                    ("accepted", "Приеми поръчката"),
                    ("preparing", "Започни подготовката"),
                    ("dispatched", "Изпратена за доставка"),
                )
            ):
                action = page.get_by_role("button", name=label, exact=True)
                action.wait_for(timeout=20000)
                action.click()
                drawer = page.locator("dialog.mr-drawer")
                check(f"{status} has no empty alert bar", not drawer.locator(".mr-notice").is_visible())
                drawer.get_by_label("Бележка за екипа", exact=True).fill("Проверено в локалния тест.")
                page.set_viewport_size(
                    {"width": (1600, 390, 320)[index], "height": 1000 if index == 0 else 844}
                )
                check(f"{status} drawer fits viewport", fits(page))
                shot(page, f"06-{status}-drawer")
                drawer.get_by_role("button", name=label, exact=True).click()
                drawer.wait_for(state="detached", timeout=15000)
                workflow = page.evaluate(
                    "async id => (await fetch('/api/manufacturer/orders/'+id+'/fulfillment')).json()",
                    order_id,
                )
                check(f"Staff {status} persisted", workflow["status"] == status)
                check(
                    f"{status} retains exact confirmed version",
                    workflow["version_id"] == workflow["current_version_id"],
                )
                page.goto(origin + "/?view=orders&order=" + order_id, wait_until="domcontentloaded")
                edit.wait_for(timeout=20000)
                check(f"{status} order detail fits viewport", fits(page))
                check(
                    f"{status} header actions stay visible",
                    page.locator(".mo-detail-heading").evaluate(
                        "h=>[...h.querySelectorAll('button')].every(b=>{const r=b.getBoundingClientRect();"
                        "return r.left>=0 && r.right<=innerWidth;})"
                    ),
                )
                shot(page, f"07-{status}-order")
            check("Dispatched is terminal", workflow["allowed_actions"] == [])
            page.goto(origin + "/?view=orders", wait_until="domcontentloaded")
            row = page.locator('[data-order-id="' + order_id + '"]')
            row.wait_for(timeout=20000)
            check("Orders list projects current staff status", "Изпратена" in row.inner_text())
            for width in (1600, 390, 320):
                page.set_viewport_size({"width": width, "height": 1000 if width == 1600 else 844})
                check(f"Orders list fits {width}", fits(page))
                shot(page, "08-orders-list-" + str(width))
            with sqlite3.connect(source) as db:
                check(
                    "Original source catalogue, order, stock unchanged", list(db.iterdump()) == source_before
                )
            check("No JavaScript exceptions", not errors)
            browser.close()
    finally:
        server.should_exit = True
        worker.join(timeout=10)
        report = {
            "checks": checks,
            "errors": errors,
            "external_requests_blocked": len(rejected_external),
            "source": "disposable synthetic SQLite copy" if len(sys.argv) > 1 else "fresh synthetic seed",
            "provider_calls": 0,
            "email_transport": "disconnected",
            "authentic_catalogue_images": CATALOGUE_IMAGES,
            "screenshots": [p.name for p in sorted(OUT.glob("*.png"))],
        }
        (OUT / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))
        print(json.dumps(report, indent=2, ensure_ascii=False))
