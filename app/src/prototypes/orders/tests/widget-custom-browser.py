#!/usr/bin/env python3
"""Browser regression proof against the local Metal-M preview; creates no orders or sends."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from playwright.sync_api import sync_playwright

from pipeline.check import Look

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--base", default="http://127.0.0.1:8786")
parser.add_argument("--out", type=Path, default=Path("app/dist-orders-check/premium-ui"))
args = parser.parse_args()
out = args.out
out.mkdir(parents=True, exist_ok=True)
proof = []
with sync_playwright() as p:
    b = p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"])
    v = Look(b, args.base, out, 390, 844, 1)
    v.open("/metal-m/en/")
    v.click("#launch")
    v.type("#q", "01-00075")
    v.click("#res .it")
    inp = v.page.locator('[data-f="x"]')
    add = v.page.locator('[data-act="add"]')
    for value in ["", "-5", "100000", "1e3", "<img>"]:
        inp.fill(value)
        inp.blur()
        assert inp.input_value() == value, (value, inp.input_value())
        assert add.is_disabled(), value
    inp.fill("1250.5")
    inp.blur()
    assert inp.input_value() == "1250.5"
    assert add.is_enabled()
    qty = v.page.locator('[data-f="n"]')
    qty.fill("1.5")
    qty.blur()
    assert qty.input_value() == "1.5"
    assert add.is_disabled()
    qty.fill("2")
    v.click('[data-act="add"]')
    assert v.page.evaluate("RocotoConfigurator.state.basket[0].rows[0].x") == 1250.5
    proof.append(
        "raw invalid dimensions and fractional counts preserved; Add blocked; decimal millimetres retained"
    )
    v.click('[data-act="custom"]')
    v.click('[data-act="add-custom"]')
    assert v.page.locator("[data-custom]").is_visible()
    step = b"ISO-10303-21;\nHEADER;\nENDSEC;\nEND-ISO-10303-21;\n"
    picker = v.page.locator("#design-file")
    picker.set_input_files({"name": "picker-bracket.step", "mimeType": "model/step", "buffer": step})
    v.page.locator(".file-card", has_text="picker-bracket.step").wait_for()
    v.click('[data-act="remove-file"]')
    v.page.evaluate(
        """body => {
          const root=document.querySelector('#rocoto-configurator').shadowRoot;
          const transfer=new DataTransfer();
          transfer.items.add(new File([body], 'drop-bracket.step', {type:'model/step'}));
          root.querySelector('#file-drop').dispatchEvent(new DragEvent('drop', {bubbles:true, dataTransfer:transfer}));
        }""",
        step.decode(),
    )
    v.page.locator(".file-card", has_text="drop-bracket.step").wait_for()
    v.shot("en-390-custom-design-upload")
    for width, height in [(320, 844), (1600, 1000)]:
        v.page.set_viewport_size({"width": width, "height": height})
        v.page.wait_for_timeout(200)
        bounds = v.page.evaluate(
            """() => {
              const root=document.querySelector('#rocoto-configurator').shadowRoot;
              const scroll=root.querySelector('#coscroll');
              const rows=['.q','.q-sub','.file-drop','.file-card','.custom-notes'].map(selector => {
                const box=root.querySelector(selector).getBoundingClientRect();
                return {selector,left:box.left,right:box.right,width:box.width};
              });
              return {viewport:innerWidth,scrollWidth:scroll.scrollWidth,clientWidth:scroll.clientWidth,rows};
            }"""
        )
        assert bounds["scrollWidth"] <= bounds["clientWidth"], bounds
        assert all(row["left"] >= 0 and row["right"] <= width for row in bounds["rows"]), bounds
        v.shot(f"en-{width}-custom-design-upload")
    v.page.set_viewport_size({"width": 390, "height": 844})
    v.page.wait_for_timeout(200)
    v.type("[data-custom]", "Laser-cut plate 420 × 280 mm, four Ø12 holes, 8 pieces.")
    v.click('[data-act="add-custom"]')
    assert v.page.evaluate("RocotoConfigurator.state.basket.length") == 2
    assert v.page.evaluate("RocotoConfigurator.state.basket[1].file.name") == "drop-bracket.step"
    v.click('[data-act="bask-open"]')
    v.click('[data-edit="1"]')
    assert v.page.locator(".file-card", has_text="drop-bracket.step").is_visible()
    v.type("[data-custom]", "Laser-cut plate 420 × 280 mm, four Ø12 holes, 12 pieces.")
    v.click('[data-act="add-custom"]')
    assert v.page.evaluate("RocotoConfigurator.state.basket[1].custom").endswith("12 pieces.")
    v.page.reload(wait_until="load")
    v.page.wait_for_timeout(700)
    v.click("#launch")
    assert v.page.evaluate("RocotoConfigurator.state.basket.length") == 2
    v.click('[data-act="bask-open"]')
    v.click('[data-edit="1"]')
    assert v.page.locator(".file-card", has_text="drop-bracket.step").is_visible()
    v.click('[data-act="back"]')
    v.click('[data-act="bask-open"]')
    v.click('[data-act="checkout"]')
    assert "Priced items" in v.page.locator("#cbar").inner_text()
    v.shot("en-390-custom-mixed-checkout")
    proof.append(
        "picker and drag/drop uploads attached privately; custom request edited and persisted through reload; mixed checkout labels priced items"
    )
    v.page.set_viewport_size({"width": 1600, "height": 1000})
    v.page.wait_for_timeout(300)
    v.shot("en-1600-custom-mixed-checkout")
    v.wide()
    assert not v.problems, v.problems
    b.close()
(out / "custom-evidence.json").write_text(json.dumps({"checks": proof, "errors": []}, indent=2) + "\n")
print(json.dumps(proof))
