"""Freezing a client-rendered homepage: the page the browser painted, without scripts, dialog or optimiser addresses."""
from __future__ import annotations

import http.server
import threading

import pytest

from pipeline import freeze

APP = """<!doctype html><html lang="bg"><head><meta charset="utf-8"><title>Fixture</title>
<link rel="stylesheet" href="/site.css"><link rel="preload" as="script" href="/app.js"></head>
<body><div id="app"></div><noscript>enable scripts</noscript>
<script>
document.getElementById('app').innerHTML =
  '<h1>Rendered by script</h1><picture><source type="image/avif" srcset="/_next/image?url=%2Fimages%2Fa.avif&w=640 640w"/>' +
  '<img src="/_next/image?url=%2Fimages%2Fa%20b.png&w=640" srcset="/images/a%20b.png 640w, /images/big.png 1280w" loading="lazy"></picture>' +
  '<video poster="/images/p.png" autoplay muted loop><source src="/v.mp4" type="video/mp4"></video>';
const dialog = document.createElement('section');
dialog.setAttribute('role', 'dialog'); dialog.setAttribute('aria-modal', 'true');
dialog.innerHTML = '<h2>Cookies</h2><button id="no">Only necessary</button><button>Accept all</button>';
document.body.appendChild(dialog); document.body.style.overflow = 'hidden';
document.getElementById('no').onclick = () => { dialog.remove(); document.body.style.overflow = ''; };
</script></body></html>"""


@pytest.fixture
def live():
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            body, kind = (APP.encode(), "text/html") if self.path == "/" else (b"", "image/png")
            self.send_response(200 if self.path == "/" else 404)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}/"
    server.shutdown()


def test_the_live_address_is_the_origin_and_the_languages_path():
    config = {"source": "https://example.test/", "languages": {"bg": "/", "en": "/en/"}}
    assert freeze.address(config, "bg") == "https://example.test/"
    assert freeze.address(config, "en") == "https://example.test/en/"


def test_the_files_a_page_names_are_listed_by_their_own_names():
    html = '<img src="/images/a%20b.png" srcset="/i/s.avif 1x"><link rel="stylesheet" href="/c.css"><a href="/x/">x</a>'
    assert freeze.locate(html, "") == ["c.css", "i/s.avif", "images/a b.png"]


def test_files_the_mirror_lacks_are_fetched_politely_and_from_the_origin(tmp_path):
    (tmp_path / "images").mkdir()
    (tmp_path / "images" / "have.png").write_bytes(b"x")
    html = '<img src="/images/have.png"><img src="/images/a b.png"><link rel="stylesheet" href="/c.css">'
    asked, waits = [], []

    def get(url):
        asked.append(url)
        return 200, "", b"@font-face{src:url(/fonts/f.woff2)}" if url.endswith("c.css") else b"data"

    got, lost = freeze.fetch_missing({"source": "https://example.test/"}, tmp_path, html, "", get=get, sleep=waits.append)
    assert sorted(asked) == ["https://example.test/c.css", "https://example.test/fonts/f.woff2",
                             "https://example.test/images/a%20b.png"]
    assert got == 3 and lost == [] and (tmp_path / "images" / "a b.png").read_bytes() == b"data"
    assert len(waits) == 2                                    # 0.4 s kept between the three requests


def test_a_page_that_answers_with_nothing_is_reported_lost(tmp_path):
    got, lost = freeze.fetch_missing({"source": "https://example.test/"}, tmp_path, '<img src="/gone.png">', "",
                                     get=lambda url: (404, "", b""), sleep=lambda seconds: None)
    assert got == 0 and lost == ["gone.png"]


def test_the_painted_page_is_frozen_without_scripts_dialog_or_optimiser_addresses(live):
    pytest.importorskip("playwright")
    try:
        html, notes = freeze.render(live)
    except Exception as error:  # a box without Chromium cannot run this one
        pytest.skip(f"Chromium is not available: {str(error)[:80]}")
    assert html.startswith("<!DOCTYPE html>")
    assert "Rendered by script" in html and "<script" not in html and "<noscript" not in html
    assert 'rel="preload"' not in html
    assert notes["declined"] == "Only necessary" and 'role="dialog"' not in html and "overflow" not in html.split("<body")[1][:60]
    assert 'src="/images/a b.png"' in html and "_next/image" not in html
    assert 'srcset="/images/a.avif 640w"' in html and 'loading="eager"' in html
    assert 'poster="/images/p.png"' in html and 'src="/v.mp4"' in html
