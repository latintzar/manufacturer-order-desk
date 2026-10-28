#!/usr/bin/env python3
"""Exercise pending claims, manual delivery and an order retry after losing a saved response.

Run against the local stateful preview. Writes clearly labelled Preview QA records and
screenshots; sends no messages. Keep one Chromium run at a time and inspect its pictures.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from playwright.sync_api import sync_playwright

from pipeline.check import CHROMIUM, HOST, STATE, Look

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--base", default="http://127.0.0.1:8786")
parser.add_argument("--out", type=Path, default=Path("app/dist-orders-check/api-proof"))
args = parser.parse_args()
out = args.out
out.mkdir(parents=True, exist_ok=True)
proof = {"checks": [], "order_keys": [], "errors": []}
with sync_playwright() as p:
    b = p.chromium.launch(args=CHROMIUM)
    v = Look(b, args.base, out, 390, 844, 2)
    v.open("/metal-m/en/")
    v.click("#launch", 800)
    v.click('[data-act="claim"]')
    v.type('[data-claim-field="name"]', "Preview QA")
    v.type('[data-claim-field="email"]', "preview-qa@example.invalid")
    v.shot("claim-form")
    v.click('[data-act="claim-submit"]', 1000)
    assert "Your access request is saved" in v.page.locator(HOST).evaluate("(h)=>h.shadowRoot.textContent")
    v.shot("claim-saved")
    proof["checks"].append("pending claim saved")
    v.click('[data-act="claim-back"]')
    v.type("#q", "01-00061")
    v.click("#res .it", 700)
    v.click('[data-act="add"]', 1000)
    v.click('[data-act="bask-open"]')
    v.click('[data-act="checkout"]')
    v.type('[data-co="email"]', "preview-qa@example.invalid")
    v.type('[data-co="phone"]', "+359881234567")
    v.click('[data-fulfil="delivery"]')
    # Disabled autocomplete exercises the typed address without a provider call.
    v.page.route(
        "**/api/places**",
        lambda route: route.fulfill(
            status=200, content_type="application/json", body='{"ok":false,"reason":"off"}'
        ),
    )
    v.type('[data-addr="d"]', "бул. Витоша 12")
    v.type('[data-co="city"]', "София")
    v.type('[data-co="zip"]', "1000")
    v.shot("delivery-address")
    v.type('[data-co="name"]', "Preview QA")
    v.type('[data-co="notes"]', "Preview QA delivery and lost-response retry check")

    def lose_once(route):
        proof["order_keys"].append(route.request.headers.get("idempotency-key"))
        if len(proof["order_keys"]) == 1:
            response = route.fetch()
            proof["first_saved"] = response.json()
            assert response.status == 201 or response.status == 200
            route.abort("failed")
        else:
            route.continue_()

    v.page.route("**/api/orders", lose_once)
    v.click('[data-act="next"]', 1200)
    assert v.page.evaluate(STATE) == {"view": "co", "lines": 1}
    v.shot("delivery-retry")
    proof["checks"].append("saved response lost: basket and contact retained")
    v.click('[data-act="next"]', 1200)
    assert v.page.evaluate(STATE) == {"view": "done", "lines": 0}
    assert proof["order_keys"][0] == proof["order_keys"][1]
    assert proof["first_saved"]["id"] in v.page.locator(HOST).evaluate("(h)=>h.shadowRoot.textContent")
    v.shot("delivery-saved")
    proof["checks"].append("retry returns original persisted receipt with same idempotency key")
    proof["errors"] = [e for e in v.problems if "api/orders (net::ERR_FAILED)" not in e]
    assert not proof["errors"], proof["errors"]
    v.wide()
    assert not v.problems or all("api/orders (net::ERR_FAILED)" in e for e in v.problems), v.problems
    b.close()
(out / "evidence.json").write_text(json.dumps(proof, indent=2) + "\n")
print(json.dumps(proof, indent=2))
