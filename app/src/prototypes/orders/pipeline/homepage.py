#!/usr/bin/env python3
"""Choose what the preview publishes for one company: its homepage and that page's requisites.

    python3 pipeline/homepage.py <company>     list the files and bytes against the homepage budget

The whole site is mirrored and read to build the catalogue. The preview publishes one page of it:
the homepage, once per language, with the styles, scripts, images and fonts that page asks for,
and the product photos the order page shows beside each category.
A file listed under `drop` in company.json stays out; a file larger than the per-file limit is
published from `<cache>/<company>/replace/` when `pipeline/media.py` has made a smaller rendition
there, and stays out otherwise. Everything left out is reported with its size.

Reads   <cache>/<company>/site/ and <cache>/<company>/replace/
Writes  nothing
"""
from __future__ import annotations

import fnmatch
import posixpath
import re
import sys
from pathlib import Path
from urllib.parse import quote, unquote

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline import clean, common  # noqa: E402

FILE_BYTES = 4 * 1024 * 1024                         # one published file
TAG = re.compile(r"<([a-zA-Z][a-zA-Z0-9]*)\b([^<>]*)>")
ATTRIBUTE = re.compile(r"""\s([a-zA-Z_:][-a-zA-Z0-9_:.]*)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'=<>`]+))""")
CSS_REFERENCE = re.compile(r"""url\(\s*["']?([^)"']+)["']?\s*\)|@import\s+["']([^"']+)["']""", re.I)
STYLE_BLOCK = re.compile(r"<style\b[^>]*>(.*?)</style\s*>", re.S | re.I)
COMMENT = re.compile(r"<!--.*?-->", re.S)
FETCHED = {"src", "poster", "srcset", "imagesrcset", "background"}


def resolve(reference: str, base: str) -> str | None:
    """A reference as a site-relative path, or None when it leaves the site or names another host."""
    reference = reference.strip().split("#", 1)[0].split("?", 1)[0]
    if not reference or reference.startswith(("//", "data:", "about:", "blob:", "javascript:")) or "://" in reference:
        return None
    joined = reference if reference.startswith("/") else posixpath.join("/" + base, reference)
    path = unquote(posixpath.normpath(joined).lstrip("/"))
    return None if path in ("", ".") or path.startswith("..") else path


def stored(site: Path, path: str) -> Path | None:
    """The mirrored file for a site path, given as the file's own name (`a b.png`, not `a%20b.png`).

    An older mirror may hold the file under the escaped name, and a crawler may have saved it with its
    query in the name.
    """
    plain = site / path
    if plain.is_file():
        return plain
    escaped = site / quote(path)
    if escaped.is_file():
        return escaped
    variants = sorted(plain.parent.glob(glob_escape(plain.name) + "[?]*")) if plain.parent.is_dir() else []
    return next((variant for variant in variants if variant.is_file()), None)


def glob_escape(name: str) -> str:
    return re.sub(r"([*?\[\]])", r"[\1]", name)


def css_requisites(css: str, base: str) -> set[str]:
    found = set()
    for match in CSS_REFERENCE.finditer(css):
        path = resolve(match.group(1) or match.group(2), base)
        if path:
            found.add(path)
    return found


def page_requisites(html: str, base: str) -> set[str]:
    """Every file the browser fetches to draw this page. A link's target is left out: links are inert."""
    found: set[str] = set()
    html = COMMENT.sub("", html)
    for block in STYLE_BLOCK.findall(html):
        found |= css_requisites(block, base)
    for tag in TAG.finditer(html):
        name, attributes = tag.group(1).lower(), tag.group(2)
        for attribute in ATTRIBUTE.finditer(attributes):
            key = attribute.group(1).lower()
            value = next(group for group in attribute.groups()[1:] if group is not None)
            if key == "style":
                found |= css_requisites(value, base)
            elif key in ("srcset", "imagesrcset") or key.endswith("-srcset"):
                found |= {path for part in value.split(",") if (path := resolve(part.strip().split(" ")[0], base))}
            elif key in FETCHED or (key == "href" and name in ("link", "use", "image")) \
                    or (key.startswith("data-") and name not in ("a", "area") and "/" in value and "." in value):
                path = resolve(value, base)
                if path:
                    found.add(path)
    return found


def plan(config: dict, site: Path, extra: set[str] | None = None) -> dict:
    """What to publish for this company: {'pages', 'files', 'left_out', 'renditions', 'missing', 'bytes'}.

    `extra` names files the order page itself shows: the logo and the catalogue's product photos.
    """
    slug = config["slug"]
    replace = site.parent / "replace"
    pages = {}
    wanted = set(config.get("keep") or []) | set(extra or ()) | {config["logo"].lstrip("/")}
    for language, source in config["home"].items():
        page = site / source
        if not page.is_file():
            raise SystemExit(f"{slug}: the {language} homepage {page} is missing. Run pipeline/mirror.py {slug}")
        published = "index.html" if language == config["defaultLanguage"] else f"{language}/index.html"
        pages[published] = page
        cleaned, _ = clean.clean_html(common.read(page))
        wanted |= page_requisites(cleaned, posixpath.dirname(source))
    files, left_out, renditions, missing, seen = {}, [], [], [], set()
    queue = sorted(wanted)
    while queue:
        path = queue.pop()
        if path in seen or path in pages:
            continue
        seen.add(path)
        source = stored(site, path)
        if source is None:
            if not (site / path).is_dir():
                missing.append(path)
            continue
        size = source.stat().st_size
        if any(fnmatch.fnmatch(path, pattern) for pattern in config.get("drop") or []):
            left_out.append((path, size, "listed under drop in company.json"))
            continue
        smaller = replace / path
        if smaller.is_file():
            renditions.append((path, size, smaller.stat().st_size))
            source, size = smaller, smaller.stat().st_size
        if size > FILE_BYTES:
            left_out.append((path, size, f"over {FILE_BYTES // 2**20} MiB: pipeline/media.py {slug} makes a rendition"))
            continue
        files[path] = source
        if path.lower().endswith(".css"):
            queue += sorted(css_requisites(source.read_text(encoding="utf-8", errors="replace"),
                                           posixpath.dirname(path)) - seen)
    total = sum(p.stat().st_size for p in pages.values()) + sum(p.stat().st_size for p in files.values())
    return {"pages": pages, "files": files, "left_out": sorted(left_out), "renditions": sorted(renditions),
            "missing": sorted(missing), "bytes": total}


def renditions_line(renditions: list) -> str:
    before, after = sum(item[1] for item in renditions), sum(item[2] for item in renditions)
    return (f"{len(renditions)} files published as smaller renditions "
            f"({before / 1e6:.1f} MB as mirrored, {after / 1e6:.1f} MB as published)")


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__.strip().splitlines()[2].strip())
        return 2
    from pipeline import catalog

    config = common.company(argv[1])
    site = common.site_dir(config["slug"])
    chosen = plan(config, site, catalog.photos(catalog.build(config, site)[0]))
    for published, source in chosen["pages"].items():
        print(f"page  {source.stat().st_size:>10,}  {published}")
    for path, source in sorted(chosen["files"].items(), key=lambda item: -item[1].stat().st_size):
        print(f"file  {source.stat().st_size:>10,}  {path}")
    for path, size, why in chosen["left_out"]:
        print(f"out   {size:>10,}  {path}  ({why})")
    print(renditions_line(chosen["renditions"]))
    for path in chosen["missing"]:
        print(f"gone  {'':>10}  {path}  (the page asks for it and the mirror has no such file)")
    print(f"{len(chosen['pages'])} pages and {len(chosen['files'])} files, {chosen['bytes'] / 2**20:.1f} MiB "
          f"before the widget, against {common.COMPANY_BYTES // 2**20} MiB for one company")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
