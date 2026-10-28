"""The preview server: right types, noindex on every answer, nothing outside its root."""
from __future__ import annotations

import http.client
import json
import threading

import pytest

import places
import serve


class Stub:
    """Stands in for the address search."""

    def __init__(self):
        self.seen = []

    def suggestions(self, query, session, language, client, geo=None):
        self.seen.append(("places", query, session, language, client, geo))
        if query == "refuse":
            raise places.Refusal("cap")
        return {"ok": True, "items": [{"id": "p1", "main": "Main St 1", "secondary": "Town"}]}

    def place(self, place_id, session, language, client):
        self.seen.append(("place", place_id, session, language, client))
        return {"ok": True, "address": "Main St 1, Town", "lat": 1.5, "lng": 2.5}


@pytest.fixture
def running(tmp_path):
    root = tmp_path / "site"
    (root / "co" / "rocoto").mkdir(parents=True)
    (root / "co" / "en").mkdir()
    (root / "index.html").write_text("<h1>Rocoto order pages</h1>")
    (root / "co" / "index.html").write_text("<p>home</p>")
    (root / "co" / "en" / "index.html").write_text("<p>english home</p>")
    (root / "co" / "site.css").write_text("a{}")
    (root / "co" / "PHOTO.JPG").write_bytes(b"jpeg")
    (root / "co" / "film.mp4").write_bytes(bytes(range(100)))
    (root / "co" / "rocoto" / "configurator.js").write_text("void 0")
    (root / "co" / "rocoto" / "poster.webp").write_bytes(b"webp")
    (root / "co" / "rocoto" / "site.json").write_text(json.dumps({"languages": ["bg", "en"], "geo": {"regions": ["bg"]}}))
    (tmp_path / "outside.txt").write_text("outside the root")
    (root / "co" / "escape").symlink_to(tmp_path / "outside.txt")
    stub = Stub()
    httpd = serve.server(root, 0, service=stub)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield httpd.server_address[1], stub
    httpd.shutdown()
    httpd.server_close()


def get(port, path, method="GET", headers=None):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    connection.request(method, path, headers=headers or {})
    response = connection.getresponse()
    body = response.read()
    connection.close()
    return response, body


@pytest.mark.parametrize(("path", "kind"), [
    ("/", "text/html; charset=utf-8"), ("/co/", "text/html; charset=utf-8"),
    ("/co/en/", "text/html; charset=utf-8"), ("/co/site.css?v=1.0.18", "text/css; charset=utf-8"),
    ("/co/PHOTO.JPG", "image/jpeg"), ("/co/film.mp4", "video/mp4"),
    ("/co/rocoto/configurator.js", "text/javascript; charset=utf-8"), ("/co/rocoto/poster.webp", "image/webp"),
    ("/co//rocoto//poster.webp", "image/webp"), ("/healthz", "text/plain; charset=utf-8"),
])
def test_each_file_answers_with_its_type_and_asks_search_engines_to_stay_away(running, path, kind):
    response, _ = get(running[0], path)
    assert response.status == 200
    assert response.getheader("Content-Type") == kind
    assert response.getheader("X-Robots-Tag") == "noindex, nofollow"
    assert response.getheader("Referrer-Policy") == "no-referrer"
    assert response.getheader("X-Content-Type-Options") == "nosniff"


@pytest.mark.parametrize("path", [
    "/co/../../outside.txt", "/co/%2e%2e/%2e%2e/outside.txt", "/..%2foutside.txt", "/co/escape",
    "/co/%00", "/co\\..\\..\\outside.txt", "/nowhere", "/co/rocoto/", "/co/rocoto/missing.js",
])
def test_a_path_outside_the_root_or_absent_answers_404_with_noindex(running, path):
    response, body = get(running[0], path)
    assert response.status == 404
    assert b"outside the root" not in body
    assert response.getheader("X-Robots-Tag") == "noindex, nofollow"


def test_a_folder_without_its_slash_redirects_to_it(running):
    response, _ = get(running[0], "/co?x=1")
    assert response.status == 301 and response.getheader("Location") == "/co/?x=1"


def test_the_server_listens_on_the_loopback_address_only(running, tmp_path):
    httpd = serve.server(tmp_path / "site", 0, service=running[1])
    assert httpd.server_address[0] == "127.0.0.1"
    httpd.server_close()
    with pytest.raises(SystemExit, match="build_preview.py"):
        serve.server(tmp_path / "absent", 0, service=running[1])


def test_a_range_request_answers_with_that_part(running):
    response, body = get(running[0], "/co/film.mp4", headers={"Range": "bytes=10-19"})
    assert response.status == 206 and body == bytes(range(10, 20))
    assert response.getheader("Content-Range") == "bytes 10-19/100"
    response, body = get(running[0], "/co/film.mp4", headers={"Range": "bytes=-5"})
    assert response.status == 206 and body == bytes(range(95, 100))
    response, _ = get(running[0], "/co/film.mp4", headers={"Range": "bytes=500-"})
    assert response.status == 416


def test_head_answers_without_a_body_and_other_methods_are_refused(running):
    response, body = get(running[0], "/co/", method="HEAD")
    assert response.status == 200 and body == b"" and response.getheader("Content-Length") == "11"
    response, _ = get(running[0], "/co/", method="POST")
    assert response.status == 405 and response.getheader("Allow") == "GET, HEAD"


def test_pages_and_the_order_page_are_asked_for_again_on_every_visit(running):
    assert get(running[0], "/co/")[0].getheader("Cache-Control") == "no-cache"
    assert get(running[0], "/co/rocoto/configurator.js")[0].getheader("Cache-Control") == "no-cache"
    assert get(running[0], "/co/PHOTO.JPG")[0].getheader("Cache-Control") == "public, max-age=3600"


def test_address_suggestions_answer_in_the_shape_the_order_page_calls(running):
    port, stub = running
    response, body = get(port, "/co/rocoto/api/places?q=Main+St&session=abc&lang=bg",
                         headers={"X-Forwarded-For": "198.51.100.7, 203.0.113.9"})
    assert response.status == 200 and response.getheader("Cache-Control") == "no-store"
    assert response.getheader("Content-Type") == "application/json; charset=utf-8"
    assert json.loads(body) == {"ok": True, "items": [{"id": "p1", "main": "Main St 1", "secondary": "Town"}]}
    assert stub.seen[-1] == ("places", "Main St", "abc", "bg", "203.0.113.9", {"regions": ["bg"]})
    response, body = get(port, "/co/rocoto/api/place?id=p1&session=abc&lang=fr")
    assert json.loads(body) == {"ok": True, "address": "Main St 1, Town", "lat": 1.5, "lng": 2.5}
    assert stub.seen[-1] == ("place", "p1", "abc", "en", "127.0.0.1")       # a language the company lacks reads as en


def test_a_refusal_answers_with_its_reason_and_status(running):
    response, body = get(running[0], "/co/rocoto/api/places?q=refuse&session=abc&lang=bg")
    assert response.status == 429 and json.loads(body) == {"ok": False, "reason": "cap"}
    response, body = get(running[0], "/other/rocoto/api/places?q=Main+St&session=abc")
    assert response.status == 503 and json.loads(body) == {"ok": False, "reason": "off"}


def test_without_a_state_directory_the_real_service_answers_off(tmp_path, monkeypatch):
    monkeypatch.delenv(places.KEY_ENV, raising=False)
    root = tmp_path / "site"
    (root / "co" / "rocoto").mkdir(parents=True)
    (root / "co" / "rocoto" / "site.json").write_text("{}")
    httpd = serve.server(root, 0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        response, body = get(httpd.server_address[1], "/co/rocoto/api/places?q=Main+St&session=abc")
        assert response.status == 503 and json.loads(body) == {"ok": False, "reason": "off"}
    finally:
        httpd.shutdown()
        httpd.server_close()
