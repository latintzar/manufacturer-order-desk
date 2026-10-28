#!/usr/bin/env python3
"""Browser regression proof against the local Metal-M preview; creates no orders or sends."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from playwright.sync_api import sync_playwright

from pipeline.check import Look

out = Path("app/dist-orders-check/premium-ui")
out.mkdir(parents=True, exist_ok=True)
proof = []
with sync_playwright() as p:
    b = p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"])
    for width, lang in [(390, "en"), (320, "bg"), (1600, "en")]:
        v = Look(b, "http://127.0.0.1:8786", out, width, 900 if width > 500 else 844, 1)
        v.open("/metal-m/" + ("en/" if lang == "en" else ""))
        v.click("#launch")
        v.type("#q", "12-20007")
        v.click("#res .it")
        v.page.evaluate("document.fonts.ready")
        v.page.locator("#slides img").first.evaluate("(i)=>i.decode()")
        assert v.page.locator("#back").inner_text().strip() == ""
        assert v.page.locator("#prev").is_visible() and v.page.locator("#nxt").is_visible()
        v.click("#nxt")
        assert v.page.evaluate("RocotoConfigurator.state.slide") == 1
        v.click("#prev")
        assert v.page.evaluate("RocotoConfigurator.state.slide") == 0
        v.wide()
        v.shot(f"{lang}-{width}-product")
        v.click("#photo-info")
        assert v.page.locator("#product-info").evaluate("(e)=>e.open")
        assert "12-20007" in v.page.locator("#product-info").inner_text()
        assert v.page.locator("#product-info").bounding_box()["width"] == width
        v.shot(f"{lang}-{width}-info")
        v.page.keyboard.press("Escape")
        assert not v.page.locator("#product-info").evaluate("(e)=>e.open")
        assert v.page.evaluate("RocotoConfigurator.state.view") == "item"
        face = v.page.evaluate("[...document.fonts].find(f=>f.family.includes('Rocoto Inter'))?.status")
        assert face == "loaded", face
        if width == 390:
            v.page.emulate_media(reduced_motion="no-preference")
            v.page.mouse.move(0, 0)
            v.page.wait_for_timeout(14000)
            assert v.page.evaluate("RocotoConfigurator.state.slide") != 0
            v.click("#slideshow")
            a = v.page.evaluate("RocotoConfigurator.state.slide")
            v.page.wait_for_timeout(7200)
            assert v.page.evaluate("RocotoConfigurator.state.slide") == a
        assert not v.problems, v.problems
        proof.append(
            {"width": width, "lang": lang, "font": face, "errors": v.problems, "info_fullscreen": True}
        )
        v.page.close()
    b.close()
(out / "evidence.json").write_text(json.dumps(proof, indent=2) + "\n")
print(json.dumps(proof))
