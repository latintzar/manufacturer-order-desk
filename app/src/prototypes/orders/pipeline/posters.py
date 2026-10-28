#!/usr/bin/env python3
"""Draw one poster per catalogue category, so the menu shows every product before three.js loads.

    python3 pipeline/posters.py <company>

Each poster is 336 x 336, transparent, drawn by the widget's own 3D engine with the same camera as
its live thumbnails. Safe to run again: it redraws every poster and removes stale ones.

Reads   the company's catalogue (built in memory from the mirror), <cache>/_vendor/three.min.js,
        widget/engine3d.js
Writes  <cache>/<company>/posters/<category code>.webp and <cache>/<company>/posters/index.json
Needs   Playwright for Python with Chromium, and Pillow. Starts no server and reads no network.
"""
from __future__ import annotations

import base64
import io
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline import bundle, catalog, common  # noqa: E402

SIZE = 336
CHROMIUM = ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"]
FLAT = ("sheet", "chequer")
RENDER = """([shape, d, mat, pat, f, size]) => {
  const R = window.Rocoto3D;
  return R.thumb({g: R.geomOf(shape, d), mat: mat, pattern: pat || undefined, f: f}, size, size);
}"""


def representative(category: dict) -> dict | None:
    """The item a category is pictured by: 42% of the way down its list, or the first with sizes."""
    items = category.get("items") or []
    if not items:
        return None
    item = items[min(len(items) - 1, math.floor(len(items) * 0.42))]
    return item if item.get("d") else next((other for other in items if other.get("d")), None)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__.strip().splitlines()[2].strip())
        return 2
    from PIL import Image, features
    from playwright.sync_api import sync_playwright

    config = common.company(argv[1])
    categories = catalog.build(config, common.site_dir(config["slug"]))[0]["cats"]
    out = common.cache_root() / config["slug"] / "posters"
    out.mkdir(parents=True, exist_ok=True)
    webp = features.check("webp")
    extension = "webp" if webp else "png"
    index, total, skipped = {}, 0, []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(args=CHROMIUM)
        page = browser.new_page(viewport={"width": 400, "height": 400})
        page.goto("about:blank")
        page.add_script_tag(path=str(bundle.three()))
        page.add_script_tag(path=str(common.WIDGET / "engine3d.js"))
        if not page.evaluate("() => !!(window.Rocoto3D && window.Rocoto3D.ok)"):
            raise SystemExit("posters: the 3D engine did not start in this Chromium")
        for category in categories:
            item = representative(category)
            if not item:
                skipped.append(category["code"])
                continue
            factor = 0.72 if category["shape"] in FLAT else 2.3
            url = page.evaluate(RENDER, [category["shape"], item["d"], item.get("m") or category["mat"],
                                         category.get("pat") or "", factor, SIZE])
            if not url.startswith("data:image/png;base64,"):
                raise SystemExit(f"posters: no image for category {category['code']}")
            image = Image.open(io.BytesIO(base64.b64decode(url.split(",", 1)[1]))).convert("RGBA")
            if image.size != (SIZE, SIZE) or image.getextrema()[3][1] == 0:
                raise SystemExit(f"posters: empty or wrong-size image for category {category['code']}")
            name = f"{category['code']}.{extension}"
            if webp:
                image.save(out / name, "WEBP", quality=88, alpha_quality=100, method=6)
            else:
                image.save(out / name, "PNG", optimize=True)
            index[category["code"]] = name
            total += (out / name).stat().st_size
        browser.close()
    for old in list(out.glob("*.webp")) + list(out.glob("*.png")):
        if old.name not in index.values():
            old.unlink()
    (out / "index.json").write_text(json.dumps(index, separators=(",", ":"), sort_keys=True) + "\n", encoding="utf-8")
    print(f"{len(index)} posters, {total / 1024:.0f} KB, {extension}, in {out}")
    if skipped:
        print("categories pictured by the company's photo (no item with sizes): " + ", ".join(skipped))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
