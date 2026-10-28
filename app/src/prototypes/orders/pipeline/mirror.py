#!/usr/bin/env python3
"""Mirror a company's public website into the cache, politely.

    python3 pipeline/mirror.py <company> [--max-pages N] [--sitemap]

The whole site is read so the catalogue, the selling rules and the brand can be worked out from
it; the preview then publishes the homepage alone. The copy is a private working file: it stays
in the cache, outside every repository.

Ground rules, enforced here:
  public pages only     same origin as `source` in company.json, plain GET, nothing behind a form
  robots.txt first      a path the site disallows is skipped and logged
  one request at a time at least 0.4 s apart
  budgets               600 pages or 300 MB by default (`mirror` in company.json), whichever
                        comes first; what was left unread is listed at the end
  important pages first the patterns under `mirror.first`, in their order; the long tail comes last
  a page is data        nothing a page says is carried out

Every URL the site owns is rewritten to a root-relative one (`/bg/produkti/`), so a later step
can move the copy under a path prefix. A file is saved under its URL path with the query left out
of the name; a page becomes `<path>/index.html`. Running it again continues: files already in the
cache are read for their links and fetched no second time, and missing requisites are filled in.
`--sitemap` also seeds the crawl with every same-origin page the site's sitemap lists, for pages no link reaches.

Reads   companies/<slug>/company.json, the company's site over HTTPS
Writes  <cache>/<company>/site/ and <cache>/<company>/mirror.log
"""
from __future__ import annotations

import heapq
import html
import posixpath
import re
import sys
import time
import urllib.error
import urllib.request
import urllib.robotparser
from pathlib import Path
from urllib.parse import quote, unquote, urljoin, urlsplit, urlunsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline import common  # noqa: E402

AGENT = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0 Safari/537.36 "
         "RocotoPreview/1.0")
DELAY = 0.4                                            # seconds between requests, at the least
TIMEOUT = 30
FILE_LIMIT = 80 * 1024 * 1024                          # one file; larger answers are logged and skipped
TAG = re.compile(r"<([a-zA-Z][a-zA-Z0-9]*)\b([^<>]*)>")
ATTRIBUTE = re.compile(r"""(\s)([a-zA-Z_:][-a-zA-Z0-9_:.]*)(\s*=\s*)(?:"([^"]*)"|'([^']*)')""")
CSS_URL = re.compile(r"""url\(\s*(["']?)([^)"']+)\1\s*\)""", re.I)
LINKING = {"href", "src", "action", "poster", "data-src", "data-lazy", "data-bg", "data-background",
           "data-original", "data-med", "data-href", "data-image"}
PAGE_SUFFIXES = ("", ".html", ".htm", ".php", ".asp", ".aspx")


def same_site(url: str, hosts: set[str]) -> bool:
    parts = urlsplit(url)
    return parts.scheme in ("http", "https") and parts.hostname in hosts


def clean_url(url: str) -> str:
    """A URL without its fragment or query: one address per file."""
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}{parts.path or '/'}"


def is_page(path: str) -> bool:
    return posixpath.splitext(path)[1].lower() in PAGE_SUFFIXES


def local_path(url_path: str, html: bool) -> str:
    """Where a URL path is saved inside the mirror."""
    path = posixpath.normpath("/" + unquote(url_path)).lstrip("/")
    if html and (url_path.endswith("/") or path == "" or is_page(path) and not path.endswith((".html", ".htm"))):
        return posixpath.join(path, "index.html") if path else "index.html"
    return path or "index.html"


def rank(path: str, first: list[str]) -> int:
    return next((index for index, pattern in enumerate(first) if re.search(pattern, path)), len(first))


def rewrite_html(html: str, page_url: str, hosts: set[str]) -> tuple[str, set[str], set[str]]:
    """The page with the site's own URLs made root-relative, the pages it links and the files it needs."""
    pages, files = set(), set()

    def rooted(value: str, tag: str, attribute: str) -> str:
        value = value.strip()
        if not value or value.startswith(("#", "data:", "javascript:", "mailto:", "tel:", "about:", "blob:")):
            return value
        absolute = urljoin(page_url, value)
        if not same_site(absolute, hosts):
            return value
        parts = urlsplit(absolute)
        target = clean_url(absolute)
        if tag == "form" or attribute in ("action", "formaction"):
            pass                                       # nothing behind a form is read
        elif tag in ("a", "area") and is_page(parts.path):
            pages.add(target)
        else:
            files.add(target)
        return (parts.path or "/") + (f"?{parts.query}" if parts.query else "") + (f"#{parts.fragment}" if parts.fragment else "")

    def css(text: str) -> str:
        return CSS_URL.sub(lambda m: f"url({m.group(1)}{rooted(m.group(2), 'style', 'url')}{m.group(1)})", text)

    def tag(match: re.Match) -> str:
        name = match.group(1).lower()

        def attribute(found: re.Match) -> str:
            key = found.group(2).lower()
            quote = '"' if found.group(4) is not None else "'"
            value = found.group(4) if found.group(4) is not None else found.group(5)
            if key in LINKING:
                value = rooted(value, name, key)
            elif key in ("srcset", "imagesrcset", "data-srcset"):
                value = ", ".join(" ".join([rooted(part.split()[0], name, key), *part.split()[1:]])
                                  for part in value.split(",") if part.strip())
            elif key == "style":
                value = css(value)
            return f"{found.group(1)}{found.group(2)}{found.group(3)}{quote}{value}{quote}"

        return f"<{match.group(1)}{ATTRIBUTE.sub(attribute, match.group(2))}>"

    pieces = re.split(r"(<script\b[^>]*>.*?</script\s*>|<style\b[^>]*>.*?</style\s*>|<!--.*?-->)", html, flags=re.S | re.I)
    out = []
    for piece in pieces:
        low = piece[:7].lower()
        if low.startswith("<!--"):
            out.append(piece)
        elif low.startswith("<script"):
            head = piece.index(">") + 1
            out.append(TAG.sub(tag, piece[:head]) + rewrite_text(piece[head:], hosts))
        elif low.startswith("<style"):
            head = piece.index(">") + 1
            out.append(piece[:head] + css(piece[head:]))
        else:
            out.append(TAG.sub(tag, piece))
    return "".join(out), pages, files


def rewrite_text(text: str, hosts: set[str]) -> str:
    """Script or stylesheet text with the site's absolute URLs made root-relative."""
    for host in sorted(hosts, key=len, reverse=True):
        text = re.sub(r"https?:(\\?/\\?/)" + re.escape(host) + r"(?::\d+)?(?=[\\/\"'`\s)]|$)", "", text)
    return text


def css_files(css: str, sheet_url: str, hosts: set[str]) -> set[str]:
    found = set()
    for match in CSS_URL.finditer(css):
        value = match.group(2).strip()
        if value.startswith("data:"):
            continue
        absolute = urljoin(sheet_url, value)
        if same_site(absolute, hosts):
            found.add(clean_url(absolute))
    return found


def wire_url(url: str) -> str:
    """The address as it goes on the wire: a space or any other unsafe character in the path is escaped."""
    parts = urlsplit(url)
    unsafe = "/%:@!$&'()*+,;=-._~"
    return urlunsplit((parts.scheme, parts.netloc, quote(parts.path, safe=unsafe), quote(parts.query, safe=unsafe + "?"), ""))


def fetch(url: str) -> tuple[int, str, bytes]:
    """One GET. Returns status, content type and body; a refusal comes back as its status."""
    request = urllib.request.Request(wire_url(url), headers={"User-Agent": AGENT, "Accept": "*/*"})  # noqa: S310
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:  # noqa: S310 - http(s) checked by caller
            return response.status, response.headers.get_content_type(), response.read(FILE_LIMIT + 1)
    except urllib.error.HTTPError as error:
        return error.code, "", b""
    except (OSError, ValueError) as error:
        return 0, str(error)[:80], b""


LOC = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>")


def sitemap_pages(source: str, get=fetch, sleep=time.sleep, limit: int = 8) -> list[str]:
    """Every page address the site's sitemap lists, nested sitemaps included, in the order listed."""
    queue, seen, pages = [urljoin(source, "/sitemap.xml")], set(), []
    while queue and len(seen) < limit:
        url = queue.pop(0)
        if url in seen:
            continue
        seen.add(url)
        sleep(DELAY)
        status, _, body = get(url)
        if status != 200:
            continue
        for found in LOC.findall(body.decode("utf-8", "replace")):
            found = html.unescape(found)
            (queue if urlsplit(found).path.endswith(".xml") else pages).append(found)
    return pages


def mirror(config: dict, site: Path, *, get=fetch, sleep=time.sleep, log=print, max_pages: int | None = None, refresh: bool = False, seed_urls: list[str] | None = None) -> dict:
    """Crawl `config["source"]` into `site`. Returns the counts and what the budgets left unread."""
    source = config["source"]
    host = urlsplit(source).hostname or ""
    bare = host.removeprefix("www.")
    hosts = {bare, "www." + bare}
    settings = config.get("mirror") or {}
    page_budget = max_pages or int(settings.get("maxPages", 600))
    byte_budget = int(settings.get("maxBytes", 300 * 1024 * 1024))
    first = list(settings.get("first") or [])
    delay = max(DELAY, float(settings.get("delay", DELAY)))
    last = [0.0]

    def polite(url: str) -> tuple[int, str, bytes]:
        wait = delay - (time.monotonic() - last[0])
        if last[0] and wait > 0:
            sleep(wait)
        answer = get(url)
        last[0] = time.monotonic()
        return answer

    robots = urllib.robotparser.RobotFileParser()
    status, _, body = polite(urljoin(source, "/robots.txt"))
    robots.parse(body.decode("utf-8", "replace").splitlines() if status == 200 else [])
    counts = {"pages": 0, "page_attempts": 0, "files": 0, "bytes": 0, "fetched": 0, "kept": 0, "refused": 0, "failed": 0}
    queue: list[tuple[int, int, int, str, bool]] = []
    seen: set[str] = set()
    order = [0]

    def push(url: str, level: int, page: bool, inherited: int | None = None) -> None:
        url = clean_url(url)
        if url in seen:
            return
        seen.add(url)
        order[0] += 1
        position = rank(urlsplit(url).path, first) if inherited is None else inherited
        heapq.heappush(queue, (position, level, order[0], url, page))

    push(source, 0, True, -1)
    for seed in seed_urls or []:
        if not same_site(seed, hosts) or not is_page(urlsplit(seed).path):
            raise ValueError("crawl seed must be a same-origin public page")
        push(seed, 1, True)
    left = []
    while queue:
        position, level, _, url, page = heapq.heappop(queue)
        path = urlsplit(url).path
        stored = [site / local_path(path, page), site / local_path(path, not page)]
        target = next((candidate for candidate in stored if candidate.is_file()), stored[0])
        refreshed = refresh and (page or target.suffix.lower() == ".pdf")
        if target.is_file() and not refreshed:
            body, kind, status = target.read_bytes(), "text/html" if target.suffix in (".html", ".htm") else "", 200
            counts["kept"] += 1
        else:
            if not robots.can_fetch(AGENT, url):
                counts["refused"] += 1
                log(f"robots  {url}")
                continue
            if (page and max(counts["pages"], counts["page_attempts"]) >= page_budget) or counts["bytes"] >= byte_budget:
                left.append(url)
                continue
            if page:
                counts["page_attempts"] += 1
            status, kind, body = polite(url)
            counts["fetched"] += 1
            if status != 200 or len(body) > FILE_LIMIT:
                counts["failed"] += 1
                log(f"{status or 'lost':>6}  {url}  {kind if not status else ''}".rstrip())
                continue
            target = site / local_path(path, kind == "text/html")
        is_html = kind == "text/html" or target.suffix in (".html", ".htm")
        if is_html:
            text, pages, files = rewrite_html(body.decode("utf-8", "replace"), url, hosts)
            body = text.encode("utf-8")
            for found in sorted(pages):
                push(found, level + 1, True)
            for found in sorted(files):
                push(found, level, False, position)
            counts["pages"] += 1
        else:
            if target.suffix.lower() == ".css":
                for found in sorted(css_files(body.decode("utf-8", "replace"), url, hosts)):
                    push(found, level, False, position)
                body = rewrite_text(body.decode("utf-8", "surrogateescape"), hosts).encode("utf-8", "surrogateescape")
            elif target.suffix.lower() in (".js", ".mjs"):
                body = rewrite_text(body.decode("utf-8", "surrogateescape"), hosts).encode("utf-8", "surrogateescape")
            counts["files"] += 1
        counts["bytes"] += len(body)
        if not target.is_file() or refreshed:
            target.parent.mkdir(parents=True, exist_ok=True)
            partial = target.with_name(target.name + ".part")
            partial.write_bytes(body)
            partial.replace(target)
            log(f"{status:>6}  {len(body):>9}  {url}")
    counts["left"] = len(left)
    for url in left[:20]:
        log(f"unread  {url}")
    return counts


def main(argv: list[str]) -> int:
    rest = [arg for arg in argv[1:] if arg != "--sitemap"]
    if len(rest) not in (1, 3) or (len(rest) == 3 and rest[1] != "--max-pages"):
        print(__doc__.strip().splitlines()[2].strip())
        return 2
    config = common.company(rest[0], complete=False)
    site = common.site_dir(config["slug"])
    site.mkdir(parents=True, exist_ok=True)
    seeds = None
    if len(rest) != len(argv) - 1:
        bare = (urlsplit(config["source"]).hostname or "").removeprefix("www.")
        seeds = [url for url in sitemap_pages(config["source"])
                 if same_site(url, {bare, "www." + bare}) and is_page(urlsplit(url).path)]
    with open(site.parent / "mirror.log", "a", encoding="utf-8") as record:
        def log(line: str) -> None:
            record.write(line + "\n")

        counts = mirror(config, site, log=log, max_pages=int(rest[2]) if len(rest) == 3 else None, seed_urls=seeds)
    print(f"{counts['pages']} pages and {counts['files']} files in {site} ({counts['bytes'] / 2**20:.1f} MiB); "
          f"{counts['fetched']} fetched now, {counts['kept']} already there, {counts['failed']} failed, "
          f"{counts['refused']} kept out by robots.txt, {counts['left']} left unread by the budgets")
    print(f"log: {site.parent / 'mirror.log'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
