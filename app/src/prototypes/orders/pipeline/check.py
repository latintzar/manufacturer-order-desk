#!/usr/bin/env python3
"""Open the built preview in a browser and order something, at desktop and at phone width.

    python3 pipeline/check.py <company> --base http://127.0.0.1:<port> [--out DIR]

Run it against `serve.py`. For each language's homepage it counts requests to the preview that
failed, confirms a click on a link stays on the page, then walks the order page: menu, search,
product, cut list, add to basket, basket, order form, submit. Desktop is 1600 x 1000; the phone is
390 x 844 at double density. Then look at the screenshots: a page that was only measured is
unchecked.

Reads   the running preview
Writes  screenshots to app/dist-orders-check/<company>/ (git-ignored by `app/dist*`), or --out
Exits   1 on a page error, a failed request to the preview, a step the order page lacks, an
        order that stays unsubmitted, or a page wider than its screen
Needs   Playwright for Python with Chromium
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline import common  # noqa: E402

# CPU compositing keeps checkout screenshots responsive on the GPU-less preview host.
# WebGL-specific checks select their own renderer separately.
CHROMIUM = ["--disable-gpu", "--disable-dev-shm-usage"]
ANSWERS = {"email": "preview-qa@example.invalid", "name": "Preview QA", "phone": "+359 88 123 4567",
           "address": "bul. Vitosha 12", "city": "Sofia", "coName": "Preview QA Company", "company": "Preview QA Company", "website": "https://example.com",
           "workType": "Construction", "work_type": "Construction", "project": "Preview QA hardware order",
           "eik": "123456789", "line1": "bul. Vitosha 12", "bline1": "bul. Vitosha 12", "zip": "1000"}
HOST = "#rocoto-configurator"
CLICK = "(host, selector) => { const e = host.shadowRoot.querySelector(selector); if (e) e.click(); return !!e }"
TYPE = """(host, [selector, value]) => { const e = host.shadowRoot.querySelector(selector); if (!e) return false;
  e.value = value; e.dispatchEvent(new Event('input', {bubbles: true})); return true }"""
FILL = """(host, answers) => { let n = 0; host.shadowRoot.querySelectorAll('input[data-co],textarea[data-co],select[data-co],input[data-addr]').forEach(e => {
  const key = e.dataset.co || (e.dataset.addr === 'b' ? 'bline1' : 'line1');
  const v = answers[key]; if (v && !e.value && e.offsetParent) {
    e.value = e.tagName === 'SELECT' ? [...e.options].find(o => o.value)?.value || '' : v;
    e.dispatchEvent(new Event('input', {bubbles: true}));
    e.dispatchEvent(new Event('change', {bubbles: true})); n++ } }); return n }"""

STATE = "() => ({view: RocotoConfigurator.state.view, lines: RocotoConfigurator.state.basket.length})"


class Look:
    """One browser page, with everything that went wrong on it."""

    def __init__(self, browser, base: str, out: Path, width: int, height: int, density: int):
        self.base, self.out, self.problems = base, out, []
        self.page = browser.new_page(viewport={"width": width, "height": height}, device_scale_factor=density,
                                     reduced_motion="reduce")
        origin = urlsplit(base).netloc
        self.page.on("pageerror", lambda error: self.problems.append(f"page error: {str(error)[:200]}"))
        self.page.on("response", lambda response: self.problems.append(
            f"{response.status} {urlsplit(response.url).path}")
            if urlsplit(response.url).netloc == origin and response.status >= 400
            and "/rocoto/api/" not in response.url else None)
        self.page.on("requestfailed", lambda request: self.problems.append(
            f"failed {urlsplit(request.url).path} ({request.failure})")
            if urlsplit(request.url).netloc == origin and "ERR_ABORTED" not in str(request.failure) else None)

    def open(self, path: str) -> None:
        self.page.goto(self.base + path, wait_until="load")
        self.page.wait_for_timeout(500)
        self.page.evaluate("localStorage.clear()")
        self.page.reload(wait_until="load")
        self.page.wait_for_timeout(500)

    def click(self, selector: str, wait: int = 600) -> None:
        if not self.page.locator(HOST).evaluate(CLICK, selector):
            self.problems.append(f"the order page has no {selector}")
        self.page.wait_for_timeout(wait)

    def type(self, selector: str, value: str, wait: int = 400) -> None:
        if not self.page.locator(HOST).evaluate(TYPE, [selector, value]):
            self.problems.append(f"the order page has no {selector}")
        self.page.wait_for_timeout(wait)

    def shot(self, name: str) -> None:
        self.page.screenshot(path=str(self.out / f"{name}.jpg"), type="jpeg", quality=82, animations="disabled", timeout=30000)

    def links_stay(self) -> None:
        """Every link on the page is inert: a click changes nothing, and none still names a target."""
        before = self.page.url
        self.page.evaluate("() => { const a = document.querySelector('a[data-rocoto-inert]'); if (a) a.click() }")
        self.page.wait_for_timeout(400)
        if self.page.url != before:
            self.problems.append(f"a link left the page for {self.page.url}")
        live = self.page.evaluate("""() => [...document.querySelectorAll('a[href], area[href]')].filter(a => {
          const h = a.getAttribute('href').toLowerCase(); return !(h.startsWith('#') || h.startsWith('javascript:')) }).length""")
        if live:
            self.problems.append(f"{live} links still lead somewhere")

    def submit(self, tag: str) -> None:
        """Fill the complete one-page checkout and assert the saved order response."""
        if self.page.evaluate(STATE)["view"] != "co":
            self.problems.append("checkout did not open")
            return
        self.page.locator(HOST).evaluate(FILL, ANSWERS)
        self.page.wait_for_timeout(300)
        self.shot(f"{tag}-form")
        self.click('[data-act="next"]', 300)
        try:
            self.page.wait_for_function("RocotoConfigurator.state.view === 'done'", timeout=20000)
        except Exception:
            errors = self.page.evaluate("JSON.stringify(RocotoConfigurator.state.errs || {})")
            self.problems.append(f"the order stayed unsubmitted; field validation: {errors}")
        self.shot(f"{tag}-submitted")

    def wide(self) -> None:
        if self.page.evaluate("document.documentElement.scrollWidth > innerWidth"):
            self.problems.append("the page is wider than its screen")


def run(config: dict, base: str, out: Path) -> list[str]:
    from playwright.sync_api import sync_playwright

    out.mkdir(parents=True, exist_ok=True)
    slug, look = config["slug"], config.get("check") or {}
    default = config["defaultLanguage"]
    paths = {language: f"/{slug}/" if language == default else f"/{slug}/{language}/" for language in config["home"]}
    other = next((path for language, path in paths.items() if language != default), paths[default])
    problems = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(args=CHROMIUM)
        desk = Look(browser, base, out, 1600, 1000, 1)
        desk.open(paths[default])
        desk.shot("d0-home")
        desk.links_stay()
        desk.click("#launch", 3500)
        desk.shot("d1-menu")
        # Search an article that exists in this release, even when the catalogue grows.
        article = desk.page.evaluate("category => {const cats=RocotoCore.C.cats; return (cats.find(c=>c.code===category)||cats[0]).items[0].c}", look.get("category", ""))
        desk.type("#q", article, 1000)
        desk.shot("d2-search")
        desk.click("#res .it[data-item]", 1000)
        desk.shot("d3-product")
        if desk.page.locator(HOST).evaluate("host => !!host.shadowRoot.querySelector('[data-f=\"x\"]')"):
            desk.type('[data-f="x"]', "1200")
            desk.click('[data-act="addrow"]')
        desk.shot("d4-cut-list")
        desk.click('[data-act="add"]', 1500)
        desk.shot("d5-basket")
        if desk.page.evaluate(STATE)["lines"] < 1:
            desk.problems.append("the basket is empty after Add")
        desk.click('[data-act="checkout"]', 1200)
        desk.submit("d6")
        desk.wide()
        problems += [f"desktop {paths[default]}: {problem}" for problem in desk.problems]
        desk.page.close()
        phone = Look(browser, base, out, 390, 844, 2)
        phone.open(other)
        phone.shot("m0-home")
        phone.links_stay()
        phone.click("#launch", 3500)
        phone.shot("m1-menu")
        phone.click(f'[data-cat="{look.get("category", "")}"]', 5000)
        phone.shot("m2-product")
        phone.click('[data-act="add"]', 1500)
        phone.click('[data-act="bask-open"]', 800)
        phone.shot("m3-basket")
        phone.click('[data-act="checkout"]', 1000)
        phone.submit("m4")
        phone.wide()
        phone.page.close()
        small = Look(browser, base, out, 320, 740, 1)
        small.open(other)
        small.shot("s0-home")
        small.click("#launch")
        small.shot("s1-menu")
        small.click(f'[data-cat="{look.get("category", "")}"]')
        small.shot("s2-product")
        small.click('[data-act="add"]')
        small.click('[data-act="bask-open"]')
        small.shot("s3-basket")
        small.wide()
        problems += [f"small phone {other}: {problem}" for problem in small.problems]
        problems += [f"phone {other}: {problem}" for problem in phone.problems]
        browser.close()
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("company")
    parser.add_argument("--base", required=True, help="where serve.py listens, such as http://127.0.0.1:8786")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    config = common.company(args.company)
    out = args.out or common.CHECK_OUT / config["slug"]
    problems = run(config, args.base.rstrip("/"), out)
    for problem in problems:
        print(problem)
    print(f"{len(problems)} problems; screenshots in {out}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
