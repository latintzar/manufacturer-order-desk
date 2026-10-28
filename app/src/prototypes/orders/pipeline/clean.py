#!/usr/bin/env python3
"""Clean a mirrored page for a private preview.

    python3 pipeline/clean.py <company>      report what comes out of the published homepage

Takes out the company's analytics, tag managers, pixels, chat widgets and reCAPTCHA; makes every
form inert; makes every link inert (the preview is one page, so a link has nowhere to go); sets
`noindex, nofollow`. `clean_html` is a pure function and the build applies it on the way to
`app/dist-orders-preview/`. The mirror in the cache stays as fetched.

Reads   the cache (`<cache>/<company>/site/`) when run as a command
Writes  nothing
"""
from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline import common  # noqa: E402

TRACKER_HOSTS = (
    "googletagmanager.com", "google-analytics.com", "analytics.google.com", "doubleclick.net",
    "googlesyndication.com", "gstatic.com/recaptcha", "google.com/recaptcha", "recaptcha.net",
    "connect.facebook.net", "facebook.com/tr", "hotjar.com", "clarity.ms", "mc.yandex.", "tawk.to",
    "crisp.chat", "intercom.io", "intercomcdn.com", "hs-scripts.com", "hs-analytics.net",
    "hsforms.net", "analytics.tiktok.com", "snap.licdn.com", "cdn.segment.com", "plausible.io",
    "matomo", "smartsuppcdn.com", "jivosite.com", "livechatinc.com", "zopim.com", "zdassets.com",
)
TRACKER_CALLS = re.compile(
    r"gtag\(|dataLayer|GoogleAnalyticsObject|grecaptcha|fbq\(|_paq\b|ym\(\d|hj\(|clarity\(|"
    r"Tawk_API|\$crisp|Intercom\(|hbspt\.|ttq\.|_linkedin_partner_id|smartsupp\(|jivo_"
)
SCRIPT = re.compile(r"<script\b([^>]*)>(.*?)</script\s*>", re.S | re.I)
SRC = re.compile(r"""\bsrc\s*=\s*["']?([^"'\s>]+)""", re.I)
NOSCRIPT = re.compile(r"<noscript\b[^>]*>(.*?)</noscript\s*>", re.S | re.I)
IFRAME = re.compile(r"<iframe\b[^>]*>(?:.*?</iframe\s*>)?", re.S | re.I)
ROBOTS = re.compile(r"""<meta\b[^>]*\bname\s*=\s*["']?robots["']?[^>]*>""", re.I)
FORM = re.compile(r"<form\b(?![^>]*\bdata-rocoto-inert)", re.I)
ANCHOR = re.compile(r"<(a|area)(\s[^>]*)>", re.I)
HREF = re.compile(r"""(\s)href\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))""", re.I)
GONE = re.compile(r"""\s(?:target|download|ping)\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]+)""", re.I)
ROCOTO_TAG = re.compile(r"""<script\b[^>]*\bsrc\s*=\s*["'][^"']*/rocoto/configurator\.js["'][^>]*>\s*</script\s*>""",
                        re.I)
GUARD_MARK = "data-rocoto-guard"
# One listener on the page: a click on an inert link and a form submit both end here, before the
# company's own scripts see them.
GUARD = (
    f"<script {GUARD_MARK}>document.addEventListener('click',function(e){{var a=e.target&&e.target.closest"
    "&&e.target.closest('a[data-rocoto-inert],area[data-rocoto-inert]');if(a){e.preventDefault();"
    "e.stopPropagation()}},true);document.addEventListener('submit',function(e){e.preventDefault()},true)"
    "</script>"
)


def _tracker(text: str) -> str | None:
    lowered = text.lower()
    return next((host for host in TRACKER_HOSTS if host in lowered), None)


def _scripts(match: re.Match, removed: Counter) -> str:
    attributes, body = match.group(1), match.group(2)
    source = SRC.search(attributes)
    if source:
        host = _tracker(source.group(1))
        if host:
            removed[f"script from {host}"] += 1
            return ""
        return match.group(0)
    if GUARD_MARK in attributes:
        return ""
    if TRACKER_CALLS.search(body) or _tracker(body):
        removed["inline tracking script"] += 1
        return ""
    return match.group(0)


def _embedded(match: re.Match, removed: Counter) -> str:
    host = _tracker(match.group(0))
    if host:
        removed[f"embed from {host}"] += 1
        return ""
    return match.group(0)


def _anchor(match: re.Match, removed: Counter) -> str:
    tag, attributes = match.group(1), match.group(2)
    href = HREF.search(attributes)
    if not href:
        return match.group(0)
    target = next(value for value in href.groups()[1:] if value is not None)
    if target.startswith("#") or target.lower().startswith("javascript:"):
        return match.group(0)                      # stays on the page already
    attributes = GONE.sub("", HREF.sub(lambda m: m.group(1) + 'href="#"', attributes, count=1)).rstrip()
    removed["link made inert"] += 1
    slash = attributes.endswith("/")
    return f"<{tag}{attributes.rstrip('/').rstrip()} data-rocoto-inert{' /' if slash else ''}>"


def clean_html(html: str) -> tuple[str, Counter]:
    """The page ready for a private preview, and a count of everything that came out."""
    removed: Counter = Counter()
    html, tags = ROCOTO_TAG.subn("", html)
    html = SCRIPT.sub(lambda m: _scripts(m, removed), html)
    html = NOSCRIPT.sub(lambda m: _embedded(m, removed), html)
    html = IFRAME.sub(lambda m: _embedded(m, removed), html)
    html, forms = FORM.subn('<form data-rocoto-inert onsubmit="return false"', html)
    if forms:
        removed["form made inert"] += forms
    html = ANCHOR.sub(lambda m: _anchor(m, removed), html)
    html = ROBOTS.sub("", html)
    head = re.search(r"<head\b[^>]*>", html, re.I)
    robots = '<meta name="robots" content="noindex,nofollow">'
    if head:
        html = html[:head.end()] + robots + GUARD + html[head.end():]
    else:
        html = robots + GUARD + html
    return html, removed


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__.strip().splitlines()[2].strip())
        return 2
    config = common.company(argv[1])
    site = common.site_dir(config["slug"])
    total: Counter = Counter()
    for language, path in config["home"].items():
        page = site / path
        if not page.is_file():
            raise SystemExit(f"{config['slug']}: {page} is missing. Run pipeline/mirror.py {config['slug']}")
        _, removed = clean_html(common.read(page))
        print(f"{language}  {path}")
        for name, count in sorted(removed.items()):
            print(f"  {count:4d}  {name}")
        total += removed
    print(f"{sum(total.values())} changes across {len(config['home'])} pages; nothing written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
