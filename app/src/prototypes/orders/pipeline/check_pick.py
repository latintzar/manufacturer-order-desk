#!/usr/bin/env python3
"""Walk a real specification-first widget and its company API at desktop and phone widths.

    python3 pipeline/check_pick.py sample-hardware --base http://127.0.0.1:8797 --out /tmp/picker-proof

Uses the published catalogue and routes. Local loopback checks submit one clearly labelled QA order to an
@example.invalid address. Public checks validate checkout without creating records.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline import common  # noqa: E402
from pipeline.check import CHROMIUM  # noqa: E402


def run(company: str, base: str, out: Path, *, skip_assistant: bool = False) -> None:
    from playwright.sync_api import sync_playwright

    out.mkdir(parents=True, exist_ok=True)
    errors, evidence = [], {}
    with sync_playwright() as driver:
        browser = driver.chromium.launch(headless=True, args=CHROMIUM)
        page = browser.new_page(viewport={"width": 1600, "height": 1000}, reduced_motion="reduce")
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(f"{base}/{company}/#order", wait_until="load")
        page.locator("#pick .pick-pair").wait_for(timeout=30000)
        configuration = page.evaluate("RocotoConfig")
        catalogue = page.evaluate("RocotoCore.C.data")
        first = catalogue["cats"][0]
        code = first["items"][0]["c"]

        def shot(name: str) -> None:
            page.wait_for_timeout(250)
            page.screenshot(path=str(out / f"{name}.png"), animations="disabled")

        def press(action: str) -> None:
            page.locator(f'[data-pick="{action}"]').first.click()

        def reset() -> None:
            page.evaluate("localStorage.clear()")
            page.goto(f"{base}/{company}/#order", wait_until="load")
            page.reload(wait_until="load")
            page.locator("#pick .pick-pair").wait_for()

        shot("01-specification-start")
        cards = page.locator("#pick .pick-card")
        left, right = cards.nth(0).bounding_box(), cards.nth(1).bounding_box()
        assert left and right and abs(left["y"] - right["y"]) < 2, "Desktop choices must be side by side"
        press("choose")
        press("families")
        shot("02-product-families")
        family_counts = {}
        for family in configuration["picker"]["families"]:
            page.locator(f'[data-family="{family["id"]}"]').click()
            if page.locator(".pick-clarify").count():
                page.locator('[data-pick="clarify"]').first.click()
            count = page.locator(".pick-article").count()
            assert count > 0, f'{family["id"]} must show catalogue articles'
            family_counts[family["id"]] = count
            assert page.locator(".pick-facet").count() == len(family["facets"])
            page.locator("#back").click()
        evidence["family_rows_visible"] = family_counts
        page.locator('[data-family="mortise"]').click()
        shot("03-visible-facets")
        for facet in ["fn", "backset", "centres"]:
            option = page.locator(f'[data-pick="filter"][data-key="{facet}"]:not([disabled])').first
            if option.count():
                option.click()
                if page.locator(".pick-clarify").count():
                    page.locator('[data-pick="clarify"]').first.click()
                assert page.locator(".pick-article").count() > 0
        shot("04-filtered-articles")
        press("clear")
        page.locator("#back").click()
        # This is the immediate, source-qualified customer shape question.
        clarified = False
        for family in configuration["picker"]["families"]:
            facet = next((f for f in family["facets"] if f["key"] == "purpose"), None)
            if not facet:
                continue
            page.locator(f'[data-family="{family["id"]}"]').click()
            for option in facet["options"]:
                if str(option["value"]) in {"P", "B", "K", "G"}:
                    page.locator(f'[data-pick="filter"][data-key="purpose"][data-value="{option["value"]}"]').click()
                    page.locator(".pick-clarify").wait_for()
                    assert page.locator('[data-pick="clarify"]:not([disabled])').count() == 2
                    shot("05-keyhole-shapes")
                    page.locator('[data-pick="clarify"]').first.click()
                    clarified = True
                    break
            if clarified:
                break
            page.locator("#back").click()
        assert clarified, "Keyhole clarification must be enabled"
        page.locator(".pick-add").first.click()
        page.locator('[data-act="checkout"]').click()
        page.locator('[data-co="company"]').wait_for()
        for key, value in {"email": "picker-qa@example.invalid", "phone": "+359881234567", "name": "Picker QA"}.items():
            page.locator(f'[data-co="{key}"]').fill(value)
        page.locator('[data-act="next"]').click()
        assert page.locator('[data-co="company"]').evaluate("e=>e.closest('.fl').classList.contains('bad')")
        for key, value in {"company": "Synthetic picker QA company", "website": "https://example.com",
                           "trade": "Door installation", "project": "Synthetic configurator QA order"}.items():
            page.locator(f'[data-co="{key}"]').fill(value)
        shot("06-company-checkout")
        if urlsplit(base).hostname in {"127.0.0.1", "localhost", "::1"}:
            with page.expect_response(lambda response: response.url.endswith("/api/orders") and response.request.method == "POST", timeout=30000) as pending:
                page.locator('[data-act="next"]').click()
            response = pending.value
            receipt = response.json()
            assert response.ok and receipt.get("ok"), receipt
            assert response.request.post_data_json["customer"]["company"] == "Synthetic picker QA company"
            evidence["order_id"] = receipt["id"]
            shot("07-saved-order")
        else:
            assert page.locator('[data-co="company"]').input_value() == "Synthetic picker QA company"
            evidence["checkout"] = "Required fields validated; public order submission omitted"
            shot("07-checkout-ready")
        if not skip_assistant:
            reset()
            press("spec")
            page.locator("[data-pick-text]").fill(f"24 x {code}\n12 x 55/72\n2 x custom part for specialist review")
            press("read")
            page.locator(".pick-spec-row").first.wait_for(timeout=95000)
            assert page.locator(".pick-spec-row").count() == 3
            assert page.locator(".pick-confirmed").count() >= 1
            shot("08-specification-results")
            press("add-spec")
            assert page.evaluate("RocotoConfigurator.state.basket.length") >= 1
            reset()
            press("choose")
            press("help")
            page.locator('[data-question="parts"][data-answer="lock"]').click()
            page.locator('[data-section="hand"]').click()
            page.locator('[data-question="hand"][data-answer="?"]').click()
            page.locator('[data-section="door"]').click()
            page.locator('[data-question="door"][data-answer="?"]').click()
            page.locator("[data-pick-project]").fill("A school door repair; confirm existing dimensions.")
            shot("09-independent-sections")
            press("propose")
            page.locator(".pick-proposal").wait_for(timeout=95000)
            shot("10-written-proposal")
        for width in (390, 320):
            page.set_viewport_size({"width": width, "height": 844})
            reset()
            shot(f"11-start-{width}")
            left, right = page.locator("#pick .pick-card").nth(0).bounding_box(), page.locator("#pick .pick-card").nth(1).bounding_box()
            assert left and right and right["y"] > left["y"] + left["height"], "Phone cards must stack"
            assert not page.evaluate("document.documentElement.scrollWidth>innerWidth")
            press("choose")
            press("families")
            page.locator('[data-family="mortise"]').click()
            shot(f"12-facets-{width}")
            assert not page.locator("#pick").evaluate("e=>e.scrollWidth>innerWidth")
        assert not errors, errors
        evidence["assistant_proof"] = "reused prior proof; provider calls omitted" if skip_assistant else "specification and proposal checked"
        evidence["errors"] = errors
        (out / "evidence.json").write_text(json.dumps(evidence, indent=2) + "\n")
        browser.close()
    checked = "picker and company checkout" if skip_assistant else "picker, specification, proposal and company checkout"
    print(f"{company}: {checked}, all families and 390/320px passed; {out}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("company", choices=common.slugs())
    parser.add_argument("--base", required=True)
    parser.add_argument("--out", type=Path, default=common.REPO / "app/dist-orders-check/picker")
    parser.add_argument("--skip-assistant", action="store_true", help="Reuse prior assistant proof and keep this walk free of provider calls")
    args = parser.parse_args()
    run(args.company, args.base.rstrip("/"), args.out, skip_assistant=args.skip_assistant)


if __name__ == "__main__":
    main()
