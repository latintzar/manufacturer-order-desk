"""Native widget responsive journeys; local state, no submission or provider calls."""

import argparse
import html
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--base", required=True, help="Disposable preview origin; no orders are submitted.")
parser.add_argument("--out", type=Path, default=Path("app/dist-orders-check/responsive"))
parser.add_argument("--viewport", action="append", help="Limit to WIDTHxHEIGHT; repeat for several sizes.")
parser.add_argument("--thumbnails-only", action="store_true", help="Check every model-filter image cell.")
parser.add_argument("--all-families", action="store_true", help="With thumbnails-only, inspect each family.")
args = parser.parse_args()
if args.all_families and not args.thumbnails_only:
    parser.error("--all-families requires --thumbnails-only")
BASE = args.base.rstrip("/")
OUT = args.out
OUT.mkdir(exist_ok=True, parents=True)
SIZES = [(1280, 1024), (1024, 1024), (1024, 768), (800, 800), (800, 600), (390, 844), (320, 568)]
if args.viewport:
    SIZES = [tuple(map(int, value.split("x"))) for value in args.viewport]
proof = {"origin": BASE, "checks": [], "failures": [], "errors": [], "forbidden_requests": []}


class Host(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(
            (
                '<!doctype html><html lang="bg">'
                '<meta name="viewport" content="width=device-width,initial-scale=1">'
                '<body><h1>Installer website</h1><script src="'
                + html.escape(BASE, quote=True)
                + '/sample-hardware/rocoto/configurator.js" defer></script></body></html>'
            ).encode()
        )

    def log_message(self, *a):
        pass


host = ThreadingHTTPServer(("127.0.0.1", 0), Host)
threading.Thread(target=host.serve_forever, daemon=True).start()


def check(ok, name, **detail):
    (proof["checks"] if ok else proof["failures"]).append({"name": name, **detail})


def box(el):
    return el.bounding_box()


def visible_in(el, w, h):
    r = box(el)
    return bool(
        r and r["x"] >= -1 and r["y"] >= -1 and r["x"] + r["width"] <= w + 1 and r["y"] + r["height"] <= h + 1
    )


def clarify(ctx):
    if ctx.locator(".pick-clarify").is_visible():
        ctx.locator('[data-pick="clarify"]').first.click()


def shot(page, name):
    page.screenshot(path=str(OUT / (name + ".jpg")), quality=65, animations="disabled")


def geometry(ctx, label, w, h):
    data = ctx.locator("#sheet").evaluate(
        """e=>{const r=e.getBoundingClientRect();
        return {x:r.x,y:r.y,width:r.width,height:r.height,sw:e.scrollWidth,cw:e.clientWidth}}"""
    )
    check(
        data["sw"] <= data["cw"] + 1
        and data["x"] >= -1
        and data["y"] >= -1
        and data["width"] <= w + 1
        and data["height"] <= h + 1,
        label + " sheet fits",
        geometry=data,
    )
    for sel in [".pick-scroll", ".pick-filter-panel", ".pick-catalogue-results", "#iscroll", "#coscroll", ".b-lines"]:
        for el in ctx.locator(sel).all():
            if el.is_visible():
                d = el.evaluate(
                    "(e)=>({sw:e.scrollWidth,cw:e.clientWidth,sh:e.scrollHeight,ch:e.clientHeight})"
                )
                check(d["sw"] <= d["cw"] + 1, label + " " + sel + " horizontal fit", geometry=d)


def filters_open(ctx, opened):
    panel = ctx.locator(".pick-filter-panel")
    if panel.evaluate("e=>e.open") != opened:
        panel.locator("summary").click()


def catalogue_geometry(ctx, label, w, h):
    panel = ctx.locator(".pick-filter-panel")
    compact = ctx.locator(".main").evaluate("e=>e.clientWidth<840")
    if compact:
        check(not panel.evaluate("e=>e.open"), label + " compact filters initially collapsed")
    first = ctx.locator(".pick-catalogue-results .pick-article").first
    pane, row = box(ctx.locator(".pick-catalogue-results")), box(first)
    check(
        visible_in(first, w, h)
        and row["y"] >= pane["y"] - 1
        and row["y"] + row["height"] <= pane["y"] + pane["height"] + 1,
        label + " first product visible immediately",
        results=pane,
        first_product=row,
    )
    geometry(ctx, label + " catalogue", w, h)


def model_thumbnail_geometry(ctx, label, require_photos=True):
    panel = ctx.locator(".pick-filter-panel")
    opened, scroll = panel.evaluate("e=>[e.open,e.scrollTop]")
    filters_open(ctx, True)
    options = ctx.locator(".pick-option:has(img)")
    if require_photos:
        check(options.count() > 0, label + " model options have catalogue photographs")
    for index, option in enumerate(options.all()):
        option.scroll_into_view_if_needed()
        photo = option.locator("img")
        expect(photo).not_to_have_js_property("naturalWidth", 0)
        data = photo.evaluate("""image=>{
            const box=e=>{const r=e.getBoundingClientRect();
                return {left:r.left,right:r.right,top:r.top,bottom:r.bottom,width:r.width,height:r.height}};
            return {image:box(image),cell:box(image.parentElement),option:box(image.closest('button'))};
        }""")
        image, cell, button = data["image"], data["cell"], data["option"]
        contained = lambda child, parent: (  # noqa: E731 - same four edges for both containment boundaries
            child["left"] >= parent["left"] - 1
            and child["right"] <= parent["right"] + 1
            and child["top"] >= parent["top"] - 1
            and child["bottom"] <= parent["bottom"] + 1
        )
        check(
            image["width"] > 0 and image["height"] > 0 and contained(image, cell) and contained(cell, button),
            label + f" model photograph {index + 1} contained in cell and button",
            geometry=data,
        )
    panel.evaluate("(e,top)=>e.scrollTop=top", scroll)
    filters_open(ctx, opened)


with sync_playwright() as p:
    b = p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
    for mode in ["page", "embed"]:
        for w, h in SIZES:
            label = f"{mode}-{w}x{h}"
            page = b.new_page(viewport={"width": w, "height": h}, reduced_motion="reduce")
            page.set_default_timeout(12000)
            page.on("pageerror", lambda e: proof["errors"].append(str(e)))

            def forbidden(route):
                proof["forbidden_requests"].append(route.request.url)
                route.abort()

            for path in ["orders", "uploads", "spec", "propose", "places*", "place*", "here*"]:
                page.route("**/rocoto/api/" + path, forbidden)
            try:
                page.goto(
                    BASE + "/sample-hardware/#order" if mode == "page" else f"http://127.0.0.1:{host.server_port}/",
                    wait_until="domcontentloaded",
                )
                ctx = page
                if mode == "embed":
                    page.locator("#rocoto-embed button").click()
                    ctx = page.frame_locator("#rocoto-embed iframe")
                ctx.locator('[data-pick="choose"]').wait_for()
                geometry(ctx, label + " entry", w, h)
                shot(page, label + "-entry")
                ctx.locator('[data-pick="choose"]').click()
                ctx.locator('[data-pick="families"]').click()
                expect(ctx.locator(".pick-family-photo img").first).not_to_have_js_property("naturalWidth", 0)
                photo = ctx.locator(".pick-family-photo").first
                d = photo.evaluate(
                    'e=>({height:e.clientHeight,image:e.querySelector("img").getBoundingClientRect().height,scroll:e.scrollHeight})'
                )
                check(d["image"] <= d["height"] + 1, label + " photograph contained", geometry=d)
                geometry(ctx, label + " families", w, h)
                shot(page, label + "-families")
                families = ctx.locator("[data-family]").evaluate_all("es=>es.map(e=>e.dataset.family)")
                ctx.locator('[data-family="mortise"]').click()
                clarify(ctx)
                catalogue_geometry(ctx, label, w, h)
                shot(page, label + "-catalogue")
                model_thumbnail_geometry(ctx, label)
                shot(page, label + "-model-filters")
                if args.thumbnails_only:
                    if args.all_families:
                        for family in families:
                            if family == "mortise":
                                continue
                            ctx.locator("#back").click()
                            ctx.locator('[data-family="' + family + '"]').click()
                            clarify(ctx)
                            model_thumbnail_geometry(ctx, label + " " + family, require_photos=False)
                    page.close()
                    (OUT / "report.json").write_text(json.dumps(proof, indent=2))
                    continue
                query = ctx.locator('[data-pick-query]')
                query.fill("Lux")
                expect(ctx.locator(".pick-catalogue-results .pick-results-heading h2 span")).to_have_text("36")
                expect(query).to_be_focused()
                results = ctx.locator(".pick-catalogue-results")
                results.evaluate("e=>e.scrollTop=e.scrollHeight")
                check(
                    results.evaluate("e=>e.scrollTop>0") and visible_in(query, w, h),
                    label + " results scroll independently of search",
                )
                query.fill("")
                results.evaluate("e=>e.scrollTop=0")
                filters_open(ctx, True)
                opts = ctx.locator('.pick-filter-panel [data-pick="filter"]')
                if opts.count():
                    opts.first.click()
                    clarify(ctx)
                if ctx.locator(".main").evaluate("e=>e.clientWidth<840"):
                    filters_open(ctx, False)
                geometry(ctx, label + " filter", w, h)
                ctx.locator('[data-pick="inspect"]').first.click()
                clarify(ctx)
                geometry(ctx, label + " product", w, h)
                shot(page, label + "-product")
                ctx.locator("#iscroll").evaluate("(e)=>e.scrollTop=e.scrollHeight")
                check(
                    visible_in(ctx.locator('#item [data-act="add"]'), w, h), label + " add action reachable"
                )
                stage = ctx.locator("#stage").bounding_box()
                sc = ctx.locator("#iscroll").bounding_box()
                heading = ctx.locator("#ihead").bounding_box()
                check(
                    stage["y"] + stage["height"] <= heading["y"] + 1
                    and ctx.locator("#stage").evaluate("e=>getComputedStyle(e).position") != "sticky",
                    label + " image never overlaps product text",
                    stage=stage,
                    heading=heading,
                )
                shot(page, label + "-product-scrolled")
                ctx.locator('#item [data-act="add"]').click()
                clarify(ctx)
                if w <= 900:
                    expect(ctx.locator("#mcart")).to_be_visible()
                    check(visible_in(ctx.locator("#mcart"), w, h), label + " basket entry fits")
                    # A picker action stays in a separate row from the basket bar.
                    r = ctx.locator("#pick").bounding_box()
                    m = ctx.locator("#mcart").bounding_box()
                    check(r["y"] + r["height"] <= m["y"] + 1, label + " picker and basket do not overlap")
                    ctx.locator("#mcart").click()
                expect(ctx.locator('[data-act="checkout"]')).to_be_enabled()
                geometry(ctx, label + " basket", w, h)
                shot(page, label + "-basket")
                ctx.locator('[data-act="checkout"]').click()
                ctx.locator('[data-co="company"]').fill("Responsive QA Company")
                geometry(ctx, label + " checkout", w, h)
                shot(page, label + "-checkout")
                ctx.locator('[data-co="notes"]').fill("Local responsive check; do not submit.")
                ctx.locator("#coscroll").evaluate("(e)=>e.scrollTop=e.scrollHeight")
                check(
                    visible_in(ctx.locator('#cbar [data-act="next"]'), w, h), label + " checkout action fits"
                )
                foot = ctx.locator("#f-foot").bounding_box()
                sc = ctx.locator("#coscroll").bounding_box()
                check(
                    foot["y"] + foot["height"] <= sc["y"] + sc["height"] + 1,
                    label + " last checkout content scrollable",
                )
                shot(page, label + "-checkout-bottom")
                # Native keyboard focus scrolls the field into its visible scroll area.
                ctx.locator('[data-co="company"]').focus()
                page.keyboard.press("Tab")
                focused = ctx.locator('[data-co="website"]')
                check(
                    focused.evaluate("e=>e===e.getRootNode().activeElement") and visible_in(focused, w, h),
                    label + " keyboard field focus visible",
                )
            except Exception as e:
                proof["failures"].append({"name": label + " journey", "error": str(e)[:1500]})
                shot(page, label + "-failure")
            page.close()
            (OUT / "report.json").write_text(json.dumps(proof, indent=2))
    b.close()
host.shutdown()
host.server_close()
print(
    json.dumps(
        {
            "checks": len(proof["checks"]),
            "failures": proof["failures"],
            "errors": proof["errors"],
            "forbidden_requests": proof["forbidden_requests"],
            "report": str(OUT / "report.json"),
        },
        indent=2,
    )
)
sys.exit(bool(proof["failures"] or proof["errors"] or proof["forbidden_requests"]))
