#!/usr/bin/env python3
"""Move a mirrored page under its company prefix.

    python3 pipeline/prefix.py <company>     report the rewrite for the published homepage

Every company shares one preview origin, so `/_public/site.css` on the company's site is
`/<company>/_public/site.css` in the preview. This rewrites root-absolute URLs in HTML attributes,
`srcset` lists, inline styles, `<style>` blocks, stylesheets and the quoted paths in scripts, and
lists what it left alone so a person can look at it.

`prefix_html`, `prefix_css` and `prefix_js` are pure functions; the build applies them once, on
the way from the cache to `app/dist-orders-preview/`.

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

URL_ATTRIBUTES = {"href", "src", "action", "poster", "data", "cite", "formaction", "background",
                  "manifest", "longdesc", "xlink:href", "icon"}
LIST_ATTRIBUTES = {"srcset", "imagesrcset"}
BLOCK = re.compile(r"(<script\b[^>]*>.*?</script\s*>|<style\b[^>]*>.*?</style\s*>|<!--.*?-->)", re.S | re.I)
TAG = re.compile(r"<[a-zA-Z][^<>]*>")
ATTRIBUTE = re.compile(r"""(\s)([a-zA-Z_:][-a-zA-Z0-9_:.]*)(\s*=\s*)(?:"([^"]*)"|'([^']*)'|([^\s"'=<>`]+))""")
CSS_URL = re.compile(r"""url\(\s*(["']?)(/(?!/)[^)"']*)\1\s*\)""", re.I)
CSS_IMPORT = re.compile(r"""(@import\s+)(["'])(/(?!/)[^"']*)\2""", re.I)
JS_PATH = re.compile(r"""(["'`])(/[A-Za-z_][\w.-]*(?:/[^"'`\\\s]*)?)\1""")
JS_HOME = re.compile(r"""((?:location(?:\.href)?|\.href)\s*=\s*)(["'])/\2""")
REFRESH = re.compile(r"(url\s*=\s*)(/(?!/))", re.I)


def rooted(value: str) -> bool:
    return value.startswith("/") and not value.startswith("//")


def top(value: str) -> str:
    return value.lstrip("/").split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]


def prefix_css(css: str, prefix: str) -> tuple[str, Counter]:
    """Stylesheet text with every root-absolute `url()` and `@import` under the prefix."""
    report: Counter = Counter()

    def url(match: re.Match) -> str:
        report["css url"] += 1
        return f"url({match.group(1)}{prefix}{match.group(2)}{match.group(1)})"

    def imported(match: re.Match) -> str:
        report["css import"] += 1
        return f"{match.group(1)}{match.group(2)}{prefix}{match.group(3)}{match.group(2)}"

    return CSS_IMPORT.sub(imported, CSS_URL.sub(url, css)), report


def prefix_js(script: str, prefix: str, tops: set[str]) -> tuple[str, Counter]:
    """Script text with quoted site paths under the prefix. `tops` is the mirror's top-level names.

    A quoted path whose first segment is one of the mirror's own folders is the site's own URL and
    moves. Any other quoted root-absolute path is reported under `left alone` and stays as written:
    it may be a server endpoint the mirror has no file for.
    """
    report: Counter = Counter()

    def path(match: re.Match) -> str:
        quote, value = match.group(1), match.group(2)
        if top(value) in tops:
            report["script path"] += 1
            return f"{quote}{prefix}{value}{quote}"
        report[f"left alone: script path {value[:60]}"] += 1
        return match.group(0)

    def home(match: re.Match) -> str:
        report["script path"] += 1
        return f"{match.group(1)}{match.group(2)}{prefix}/{match.group(2)}"

    return JS_HOME.sub(home, JS_PATH.sub(path, script)), report


def _tag(tag: str, prefix: str, tops: set[str], report: Counter) -> str:
    def attribute(match: re.Match) -> str:
        space, name, equals = match.group(1), match.group(2), match.group(3)
        quote = "'" if match.group(5) is not None else '"'
        value = next(group for group in match.groups()[3:] if group is not None)
        lowered = name.lower()
        changed = value
        if lowered in LIST_ATTRIBUTES or lowered.endswith("-srcset"):
            parts = [part.strip() for part in value.split(",")]
            changed = ", ".join(prefix + part if rooted(part) else part for part in parts)
        elif lowered == "style":
            changed, counts = prefix_css(value, prefix)
            report.update(counts)
        elif lowered == "content":
            if rooted(value) and (value == "/" or top(value) in tops):
                changed = prefix + value
            else:
                changed = REFRESH.sub(lambda m: m.group(1) + prefix + m.group(2), value)
        elif rooted(value) and (lowered in URL_ATTRIBUTES or lowered.startswith("data-")):
            changed = prefix + value
        elif rooted(value) and top(value) in tops:
            report[f"left alone: {lowered}={value[:60]}"] += 1
        if changed != value and lowered != "style":
            report["html attribute"] += 1
        return f"{space}{name}{equals}{quote}{changed}{quote}"

    if tag[1:5].lower() == "base":
        report["left alone: <base> tag"] += 1
    return ATTRIBUTE.sub(attribute, tag)


def prefix_html(html: str, prefix: str, tops: set[str]) -> tuple[str, Counter]:
    """The page with every root-absolute URL under the prefix, and a count of what moved."""
    report: Counter = Counter()
    out = []
    for piece in BLOCK.split(html):
        lowered = piece[:8].lower()
        if lowered.startswith("<!--"):
            out.append(piece)
        elif lowered.startswith("<script"):
            opening, body = piece[:piece.index(">") + 1], piece[piece.index(">") + 1:]
            end = body.lower().rindex("</script")
            code, closing = body[:end], body[end:]
            if not re.search(r"""type\s*=\s*["']?application/(?:ld\+)?json""", opening, re.I):
                code, counts = prefix_js(code, prefix, tops)
                report.update(counts)
            out.append(_tag(opening, prefix, tops, report) + code + closing)
        elif lowered.startswith("<style"):
            opening, body = piece[:piece.index(">") + 1], piece[piece.index(">") + 1:]
            end = body.lower().rindex("</style")
            css, counts = prefix_css(body[:end], prefix)
            report.update(counts)
            out.append(opening + css + body[end:])
        else:
            out.append(TAG.sub(lambda m: _tag(m.group(0), prefix, tops, report), piece))
    return "".join(out), report


def tops_of(site: Path) -> set[str]:
    """The names at the root of a mirror: the first path segment of every URL the site owns."""
    return {entry.name for entry in site.iterdir()} | {"rocoto"}


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__.strip().splitlines()[2].strip())
        return 2
    config = common.company(argv[1])
    site = common.site_dir(config["slug"])
    tops = tops_of(site)
    for language, path in config["home"].items():
        _, report = prefix_html(common.read(site / path),
                                common.prefix_of(config), tops)
        print(f"{language}  {path}")
        for name, count in sorted(report.items()):
            print(f"  {count:4d}  {name}")
    print("nothing written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
