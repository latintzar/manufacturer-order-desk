#!/usr/bin/env python3
"""Freeze a client-rendered homepage into static markup.

    python3 pipeline/freeze.py <company> [--language bg]

A site built with a client framework answers a plain request with a page that fills itself in
afterwards: the mirror then holds an empty shell, or one still waiting for its scripts. This step
opens each language's homepage in a browser at 1440 px, closes the company's cookie dialog, scrolls
through the page so every lazy picture and reveal has run, and saves what the browser painted as
markup that needs no JavaScript:

  scripts and their preloads   out; the page is one still, links are made inert later by clean.py
  cookie and consent dialogs   closed through their own «only necessary» button; any that stay are
                               removed with the scroll lock they set, so the page opens on its header
  pictures                     at their own addresses: an image-optimiser address (`/_next/image?url=`)
                               becomes the file it names, `srcset` and `sizes` stay as the company wrote
                               them, lazy loading is switched to eager
  files the page names         fetched into the mirror when it lacks them, one request at a time,
                               0.4 s apart, from the company's own origin

The saved page replaces the mirror's file at the company's `home` path; the mirrored original stays
beside it as `<name>.mirrored`. Run `pipeline/media.py` next for heavy pictures and videos, then look at
the page at 1440 and 390 px beside the live one.

Reads   companies/<slug>/company.json (source, languages, home), the company's homepage over HTTPS
Writes  <cache>/<company>/site/<home path> and the files that page names and the mirror lacked
Needs   Playwright for Python with Chromium
"""
from __future__ import annotations

import argparse
import posixpath
import re
import sys
import time
from pathlib import Path
from urllib.parse import quote, urljoin, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline import common, homepage, mirror  # noqa: E402
from pipeline.check import CHROMIUM  # noqa: E402

WIDTH, HEIGHT = 1440, 900
STEP = 600                                            # pixels scrolled at a time
PAUSE = 250                                           # milliseconds between steps
DECLINE = re.compile(r"only necessary|necessary only|essential only|reject|decline|refuse|"
                     r"само необходими|само задължителни|отказ", re.I)
CONSENT = re.compile(r"cookie|consent|бисквитк|съгласие", re.I)

# Runs in the page: unlocks it, makes every address direct, takes out what needs JavaScript, returns the markup.
FREEZE_JS = r"""
({consent, origin}) => {
  const pattern = new RegExp(consent, 'i');
  const direct = (value) => {
    try {
      const url = new URL(value, location.href);
      if (url.pathname === '/_next/image') return decodeURIComponent(url.searchParams.get('url') || '');
      return url.origin === origin ? url.pathname : value;
    } catch (error) { return value; }
  };
  const list = (value) => value.split(',').map((part) => {
    const [address, ...rest] = part.trim().split(/\s+/);
    return [direct(address), ...rest].join(' ');
  }).join(', ');
  let dialogs = 0;
  document.querySelectorAll('[role=dialog], [aria-modal=true], [id*=cookie i], [class*=cookie i], [id*=consent i], [class*=consent i]')
    .forEach((element) => {
      if (!element.isConnected) return;
      const dialog = element.matches('[role=dialog], [aria-modal=true]');
      const consent = dialog ? pattern.test(element.textContent.slice(0, 600)) : getComputedStyle(element).position === 'fixed';
      if (consent) { element.remove(); dialogs += 1; }
    });
  [document.documentElement, document.body].forEach((element) => {
    element.style.removeProperty('overflow'); element.style.removeProperty('padding-right');
    element.removeAttribute('inert'); element.removeAttribute('aria-hidden');
    if (!element.getAttribute('style')) element.removeAttribute('style');
  });
  [...document.body.children].forEach((element) => { element.removeAttribute('inert'); element.removeAttribute('aria-hidden'); });
  document.querySelectorAll('img').forEach((image) => {
    const src = image.getAttribute('src'), set = image.getAttribute('srcset');
    if (src && !src.startsWith('data:')) image.setAttribute('src', direct(src));
    if (set) image.setAttribute('srcset', list(set));
    image.setAttribute('loading', 'eager'); image.removeAttribute('fetchpriority');
  });
  document.querySelectorAll('source').forEach((source) => {
    ['srcset', 'src'].forEach((key) => { const value = source.getAttribute(key); if (value) source.setAttribute(key, key === 'srcset' ? list(value) : direct(value)); });
  });
  document.querySelectorAll('video').forEach((video) => {
    ['src', 'poster'].forEach((key) => { const value = video.getAttribute(key); if (value) video.setAttribute(key, direct(value)); });
    ['muted', 'loop', 'autoplay'].forEach((key) => { if (video[key]) video.setAttribute(key, ''); });
    if (video.playsInline) video.setAttribute('playsinline', '');
  });
  document.querySelectorAll('[style]').forEach((element) => {
    const style = element.getAttribute('style');
    if (/url\(/.test(style)) element.setAttribute('style', style.replace(/url\((['"]?)([^)'"]+)\1\)/g, (m, q, u) => 'url(' + direct(u) + ')'));
  });
  document.querySelectorAll('script, noscript, next-route-announcer, nextjs-portal, link[rel=modulepreload], link[rel=prefetch], link[rel=preload][as=script], link[rel=preload][as=image]')
    .forEach((element) => element.remove());
  return {html: '<!DOCTYPE html>' + document.documentElement.outerHTML, removed: dialogs};
}
"""


def address(config: dict, language: str) -> str:
    """The live homepage of one language: the company's origin and that language's path."""
    return config["source"].rstrip("/") + "/" + (config.get("languages") or {}).get(language, "/").lstrip("/")


def locate(html: str, base: str) -> list[str]:
    """The site paths a frozen page names (pictures, styles, fonts, video), once each, in sorted order."""
    return sorted(homepage.page_requisites(html, base))


def render(url: str) -> tuple[str, dict]:
    """Open `url` in Chromium, close the consent dialog, scroll through, and return (markup, notes)."""
    from playwright.sync_api import sync_playwright

    notes: dict = {"declined": ""}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(args=CHROMIUM)
        try:
            page = browser.new_page(viewport={"width": WIDTH, "height": HEIGHT})
            page.goto(url, wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(1000)
            for button in page.locator("[role=dialog] button, [aria-modal=true] button").all():
                label = (button.inner_text() or "").strip()
                if DECLINE.search(label) and button.is_visible():
                    button.click()
                    notes["declined"] = label
                    page.wait_for_timeout(600)
                    break
            height, y = page.evaluate("document.documentElement.scrollHeight"), 0
            while y < height:
                page.mouse.wheel(0, STEP)
                y += STEP
                page.wait_for_timeout(PAUSE)
                height = page.evaluate("document.documentElement.scrollHeight")
            page.wait_for_timeout(800)
            page.evaluate("window.scrollTo(0, 0)")
            page.wait_for_timeout(600)
            origin = f"{urlsplit(url).scheme}://{urlsplit(url).netloc}"
            frozen = page.evaluate(FREEZE_JS, {"consent": CONSENT.pattern, "origin": origin})
        finally:
            browser.close()
    notes["dialogs_removed"] = frozen["removed"]
    return frozen["html"], notes


def fetch_missing(config: dict, site: Path, html: str, base: str, *, get=mirror.fetch, sleep=time.sleep) -> tuple[int, list[str]]:
    """Fetch the files the page names that the mirror lacks. Returns (how many came, which did not)."""
    origin = config["source"].rstrip("/")
    wanted, seen, got, lost, last = list(locate(html, base)), set(), 0, [], 0.0
    while wanted:
        path = wanted.pop()
        if path in seen or homepage.stored(site, path) or (site / path).is_dir():
            continue
        seen.add(path)
        wait = mirror.DELAY - (time.monotonic() - last)
        if last and wait > 0:
            sleep(wait)
        status, _, body = get(urljoin(origin + "/", quote(path)))
        last = time.monotonic()
        if status != 200 or len(body) > mirror.FILE_LIMIT:
            lost.append(path)
            continue
        target = site / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body)
        got += 1
        if path.lower().endswith(".css"):
            wanted += sorted(homepage.css_requisites(body.decode("utf-8", "replace"), posixpath.dirname(path)) - seen)
    return got, lost


def freeze(config: dict, site: Path, language: str, *, shown=print) -> dict:
    """Freeze one language's homepage into the mirror."""
    source = config["home"][language]
    target = site / source
    html, notes = render(address(config, language))
    if re.search(r"<script\b", html, re.I):
        raise SystemExit(f"{config['slug']}: the frozen {language} page still holds a script")
    target.parent.mkdir(parents=True, exist_ok=True)
    original = target.with_name(target.name + ".mirrored")
    if target.is_file() and not original.is_file():
        original.write_bytes(target.read_bytes())
    common.write(target, html)
    got, lost = fetch_missing(config, site, html, posixpath.dirname(source))
    shown(f"{language}: {len(html.encode()) / 1024:.0f} KB saved to {target}; cookie dialog closed with "
          f"«{notes['declined'] or 'no button'}», {notes['dialogs_removed']} left over removed; "
          f"{got} files fetched, {len(lost)} not found")
    for path in lost:
        shown(f"  not found: {path}")
    return {"bytes": len(html.encode()), "fetched": got, "lost": lost, **notes}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("company")
    parser.add_argument("--language", help="one language of the company's `home`; every language by default")
    args = parser.parse_args(argv[1:])
    config = common.company(args.company)
    site = common.site_dir(config["slug"])
    languages = [args.language] if args.language else list(config["home"])
    for language in languages:
        if language not in config["home"]:
            raise SystemExit(f"{config['slug']}: no `{language}` homepage in company.json")
        freeze(config, site, language)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
