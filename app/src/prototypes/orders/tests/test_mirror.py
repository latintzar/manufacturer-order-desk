"""The mirror reads a site politely, inside its budgets, and saves it with root-relative links."""
from __future__ import annotations

import http.server
import threading

import pytest

from pipeline import mirror

PAGES = {
    "/robots.txt": ("text/plain", "User-agent: *\nDisallow: /private/\n"),
    "/": ("text/html", '<html><head><link rel="stylesheet" href="assets/site.css?v=2"></head><body>'
                       '<a href="/products/">Products</a> <a href="http://{host}/price-list">Prices</a> '
                       '<a href="/private/admin/">Admin</a> <a href="/blog/a/">Blog</a> '
                       '<a href="https://other.example/">Elsewhere</a> <a href="mailto:x@y.z">Mail</a>'
                       '<form action="/search/"><input name="q"></form>'
                       '<img src="/assets/logo.svg"></body></html>'),
    "/products/": ("text/html", '<html><body><a href="../">Home</a><img src="tube.svg"></body></html>'),
    "/price-list": ("text/html", "<html><body><table><tr><td>1</td></tr></table></body></html>"),
    "/blog/a/": ("text/html", "<html><body>long tail</body></html>"),
    "/search/": ("text/html", "<html><body>search results</body></html>"),
    "/private/admin/": ("text/html", "<html><body>private</body></html>"),
    "/assets/site.css": ("text/css", "body{background:url(paper.svg)} a{background:url(http://{host}/assets/logo.svg)}"),
    "/assets/logo.svg": ("image/svg+xml", "<svg/>"),
    "/assets/paper.svg": ("image/svg+xml", "<svg/>"),
    "/products/tube.svg": ("image/svg+xml", "<svg/>"),
}


@pytest.fixture
def site_url():
    asked = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            path = self.path.split("?")[0]
            asked.append(path)
            if path not in PAGES:
                self.send_response(404)
                self.end_headers()
                return
            kind, body = PAGES[path]
            body = body.replace("{host}", self.headers["Host"]).encode()
            self.send_response(200)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}/", asked
    httpd.shutdown()
    httpd.server_close()


def config(url, **settings):
    return {"slug": "example", "source": url, "mirror": {"first": ["price-list", "/products/"], **settings}}


def test_the_site_is_saved_with_root_relative_links_and_pages_as_index_files(site_url, tmp_path):
    url, asked = site_url
    waits = []
    counts = mirror.mirror(config(url), tmp_path, sleep=waits.append, log=lambda line: None)
    home = (tmp_path / "index.html").read_text()
    assert 'href="/assets/site.css?v=2"' in home and 'href="/price-list"' in home
    assert 'href="https://other.example/"' in home and 'href="mailto:x@y.z"' in home
    assert (tmp_path / "products" / "index.html").read_text() == '<html><body><a href="/">Home</a><img src="/products/tube.svg"></body></html>'
    assert (tmp_path / "price-list" / "index.html").is_file()
    assert (tmp_path / "assets" / "site.css").read_text() == "body{background:url(paper.svg)} a{background:url(/assets/logo.svg)}"
    for path in ("assets/logo.svg", "assets/paper.svg", "products/tube.svg", "blog/a/index.html"):
        assert (tmp_path / path).is_file(), path
    assert counts["pages"] == 4 and counts["files"] == 4 and counts["left"] == 0


def test_robots_txt_is_read_first_and_obeyed_and_forms_lead_nowhere(site_url, tmp_path):
    url, asked = site_url
    counts = mirror.mirror(config(url), tmp_path, sleep=lambda seconds: None, log=lambda line: None)
    assert asked[0] == "/robots.txt"
    assert "/private/admin/" not in asked and not (tmp_path / "private").exists()
    assert "/search/" not in asked
    assert counts["refused"] == 1


def test_requests_go_one_at_a_time_at_least_four_tenths_of_a_second_apart(site_url, tmp_path):
    url, asked = site_url
    waits = []
    mirror.mirror(config(url, delay=0.01), tmp_path, sleep=waits.append, log=lambda line: None)
    assert len(waits) == len(asked) - 1                # every request after the first waits its turn
    assert all(0.3 < wait <= 0.4 for wait in waits)    # a company setting cannot shorten the pause


def test_important_pages_come_first_and_the_budget_names_what_it_left(site_url, tmp_path):
    url, asked = site_url
    lines = []
    counts = mirror.mirror(config(url), tmp_path, sleep=lambda seconds: None, log=lines.append, max_pages=3)
    pages = [path for path in asked if path in ("/", "/products/", "/price-list", "/blog/a/")]
    assert pages == ["/", "/price-list", "/products/"]
    assert counts["pages"] == 3 and counts["left"] == 1
    assert any(line.startswith("unread") and line.endswith("/blog/a/") for line in lines)


def test_a_second_run_reads_the_cache_and_fetches_only_what_is_missing(site_url, tmp_path):
    url, asked = site_url
    mirror.mirror(config(url), tmp_path, sleep=lambda seconds: None, log=lambda line: None)
    (tmp_path / "assets" / "paper.svg").unlink()
    before = len(asked)
    counts = mirror.mirror(config(url), tmp_path, sleep=lambda seconds: None, log=lambda line: None)
    assert asked[before:] == ["/robots.txt", "/assets/paper.svg"]
    assert counts["fetched"] == 1 and counts["kept"] == 7


@pytest.mark.parametrize(("path", "html", "saved"), [
    ("/", True, "index.html"), ("/bg/produkti/", True, "bg/produkti/index.html"),
    ("/about", True, "about/index.html"), ("/page.html", True, "page.html"),
    ("/assets/site.css", False, "assets/site.css"), ("/a/../b/x.png", False, "b/x.png"),
])
def test_a_url_path_maps_to_one_file_inside_the_mirror(path, html, saved):
    assert mirror.local_path(path, html) == saved


def test_a_new_company_folder_is_ready_for_the_mirror_and_names_what_the_build_still_needs(tmp_path, monkeypatch):
    from pipeline import common, new_company

    monkeypatch.setattr(common, "COMPANIES", tmp_path)
    assert new_company.main(["new_company.py", "acme-steel", "https://www.acme-steel.test/en/"]) == 0
    folder = tmp_path / "acme-steel"
    assert sorted(path.name for path in folder.iterdir()) == ["NOTES.md", "company.json", "mapping.py"]
    assert common.company("acme-steel", folder, complete=False)["source"] == "https://www.acme-steel.test/"
    with pytest.raises(SystemExit) as stopped:
        common.company("acme-steel", folder)
    for field in ("name", "priceList", "accent", "logo", "hours", "strings.en.pickSub"):
        assert field in str(stopped.value)
    hooks = common.mapping(common.company("acme-steel", folder, complete=False))
    for hook in ("TABLE", "COLUMNS", "PARKED", "SHAPES", "METALS", "FORMS", "RULES", "title", "sale", "surface",
                 "tail_en", "form_of", "local_image", "as_of", "site_map"):
        assert hasattr(hooks, hook), hook
    with pytest.raises(SystemExit, match="stands already"):
        new_company.main(["new_company.py", "acme-steel", "https://www.acme-steel.test/"])
    with pytest.raises(SystemExit, match="slug"):
        new_company.main(["new_company.py", "Rocoto", "https://x.test/"])


def test_wire_url_escapes_a_space_and_keeps_existing_escapes():
    assert mirror.wire_url("https://x.example/images/a b.png") == "https://x.example/images/a%20b.png"
    assert mirror.wire_url("https://x.example/images/a%20b.png") == "https://x.example/images/a%20b.png"
    assert mirror.wire_url("https://x.example/p/?a=1&b=2") == "https://x.example/p/?a=1&b=2"


def test_sitemap_pages_follow_a_sitemap_index_and_return_pages_in_order():
    answers = {
        "https://x.example/sitemap.xml": b"<sitemapindex><sitemap><loc>https://x.example/sitemap-bg.xml</loc></sitemap></sitemapindex>",
        "https://x.example/sitemap-bg.xml": b"<urlset><url><loc>https://x.example/</loc></url>"
                                            b"<url><loc>https://x.example/a/?x=1&amp;y=2</loc></url></urlset>"}
    asked = []

    def get(url):
        asked.append(url)
        return (200, "", answers[url]) if url in answers else (404, "", b"")

    assert mirror.sitemap_pages("https://x.example/", get=get, sleep=lambda seconds: None) == [
        "https://x.example/", "https://x.example/a/?x=1&y=2"]
    assert asked == ["https://x.example/sitemap.xml", "https://x.example/sitemap-bg.xml"]
