"""The preview publishes the homepage, its requisites and the order page, inside its limits."""
from __future__ import annotations

import json
import re

import pytest

import build_preview
from pipeline import bundle, catalog, common, homepage


def site(cache):
    return cache / "example-steel" / "site"


def test_the_homepage_and_only_what_it_draws_are_chosen(example, cache):
    chosen = homepage.plan(example, site(cache))
    assert sorted(chosen["pages"]) == ["de/index.html", "index.html"]
    assert sorted(chosen["files"]) == [
        "assets/example.woff2", "assets/film.mp4", "assets/hero.svg", "assets/logo.svg", "assets/site.css",
        "assets/site.js", "assets/tube-2x.svg", "assets/tube.svg"]
    assert "assets/retired.svg" not in chosen["files"]               # only named inside a comment
    assert "assets/brochure.pdf" not in chosen["files"]              # a link's target; links are inert
    assert "price-list/index.html" not in chosen["files"]            # read for the catalogue, left unpublished
    assert [(path, why) for path, _, why in chosen["left_out"]] == [
        ("assets/paper.svg", "listed under drop in company.json")]


def test_a_heavy_file_is_left_out_until_a_rendition_stands_in(example, cache, monkeypatch):
    monkeypatch.setattr(homepage, "FILE_BYTES", 10)
    chosen = homepage.plan(example, site(cache))
    assert "assets/film.mp4" not in chosen["files"]
    assert any(path == "assets/film.mp4" and "media.py" in why for path, _, why in chosen["left_out"])
    smaller = cache / "example-steel" / "replace" / "assets" / "film.mp4"
    smaller.parent.mkdir(parents=True)
    smaller.write_bytes(b"small")
    chosen = homepage.plan(example, site(cache))
    assert chosen["files"]["assets/film.mp4"] == smaller
    assert chosen["renditions"] == [("assets/film.mp4", 19, 5)]


def test_a_file_saved_with_its_query_in_the_name_is_found(example, cache):
    plain = site(cache) / "assets" / "site.css"
    plain.rename(plain.with_name("site.css?v=3.css"))
    assert "assets/site.css" in homepage.plan(example, site(cache))["files"]


def test_a_reference_resolves_inside_the_site_the_way_a_browser_does():
    assert homepage.resolve("../../etc/passwd", "") == "etc/passwd"     # clamped at the site's own root
    assert homepage.resolve("https://other.example/x.png", "a") is None
    assert homepage.resolve("//cdn.example/x.png", "a") is None
    assert homepage.resolve("data:image/png;base64,AAAA", "a") is None
    assert homepage.resolve("..//fonts/icons.woff2?v=1", "plugins/css") == "plugins/fonts/icons.woff2"


def test_the_widget_config_puts_the_company_under_its_own_prefix(example):
    config = bundle.widget_config(example, posters=True)
    assert config["base"] == "/example-steel/rocoto/" and config["root"] == "/example-steel"
    assert config["logo"] == "/example-steel/assets/logo.svg"
    assert config["key"] == "rocoto-basket-example-steel" and config["prefix"] == "EX"
    assert config["lang"] == "en" and config["langs"] == {"de": "/de/"}
    assert config["strings"]["de"]["pickAddr"] == "Beispielstadt, Werkstraße 1"
    assert config["posters"] is True and "mapsKey" not in config


def test_the_browser_map_key_comes_from_the_cache_outside_the_repository(example, cache):
    (cache / "_config").mkdir()
    (cache / "_config" / "maps-embed-key").write_text("EXAMPLE-browser-key-0123456789\n")
    assert bundle.widget_config(example)["mapsKey"] == "EXAMPLE-browser-key-0123456789"
    assert "EXAMPLE-browser-key-0123456789" in bundle.bundle(example)
    (cache / "_config" / "maps-embed-key").write_text("two words\n")
    with pytest.raises(SystemExit, match="browser key"):
        bundle.widget_config(example)


def test_the_bundle_is_one_script_with_config_engine_and_interface(example):
    script = bundle.bundle(example)
    assert script.startswith("/* Rocoto order page for Example Steel.")
    assert "window.RocotoConfig=" in script and "RocotoPricing" in script and "RocotoCore" in script
    assert "__ICONS__" not in script and "__CSS__" not in script
    assert bundle.tag(example) == ('<script src="/example-steel/rocoto/configurator.js" '
                                   'data-rocoto="example-steel" defer></script>')


def test_a_company_with_a_missing_address_line_stops_before_any_build(companies):
    path = companies / "example-steel" / "company.json"
    config = json.loads(path.read_text())
    config["strings"]["de"]["pickSub"] = ""
    path.write_text(json.dumps(config))
    with pytest.raises(SystemExit, match=r"strings\.de\.pickSub"):
        common.company("example-steel", companies / "example-steel")


def test_the_build_writes_one_folder_per_company_and_a_root_that_names_none(companies, cache, tmp_path):
    out = tmp_path / "dist"
    results = build_preview.build(out, companies)
    text, ok = build_preview.summary(results, out)
    assert ok, text
    home = (out / "example-steel" / "index.html").read_text(encoding="utf-8")
    german = (out / "example-steel" / "de" / "index.html").read_text(encoding="utf-8")
    for page in (home, german):
        assert page.count("/example-steel/rocoto/configurator.js") == 1
        assert '<meta name="robots" content="noindex,nofollow">' in page
        assert "googletagmanager" not in page
        uncommented = re.sub(r"<!--.*?-->", "", page, flags=re.S)
        assert not re.search(r"""(?:src|href|poster|action)=["']/(?!example-steel/|/)""", uncommented)
        assert not re.search(r"""<a\b[^>]*href=["'](?!#)""", uncommented)
    assert 'lang="de"' in german
    assert (out / "example-steel" / "assets" / "site.css").read_text() .count("/example-steel/assets/paper.svg") == 1
    assert "'/example-steel/products/tubes/'" in (out / "example-steel" / "assets" / "site.js").read_text()
    assert not (out / "example-steel" / "price-list").exists()
    assert not (out / "example-steel" / "assets" / "paper.svg").exists()
    made = json.loads((out / "example-steel" / "rocoto" / "catalog.json").read_text(encoding="utf-8"))
    assert made["asOf"] == "2026-10-01" and made["cats"][0]["img"] == "/example-steel/assets/tube.svg"
    about = json.loads((out / "example-steel" / "rocoto" / "site.json").read_text(encoding="utf-8"))
    assert about == {"slug": "example-steel", "name": {"en": "Example Steel", "de": "Beispiel Stahl"},
                     "source": "https://example-steel.test/", "languages": ["en", "de"],
                     "geo": {"regions": ["de"]}, "catalogueScope": "full"}
    for name in ("configurator.js", "three.min.js", "embed.html"):
        assert (out / "example-steel" / "rocoto" / name).is_file()
    root = (out / "index.html").read_text(encoding="utf-8")
    assert "Rocoto order pages" in root and "noindex,nofollow" in root
    assert "example" not in root.lower().replace("for example", "")
    assert (out / "health").read_text() == "ok\n"
    assert "example-steel: 2 pages" in text and "package:" in text


def test_a_missing_mirror_stops_the_build_and_names_the_command(companies, cache, tmp_path):
    import shutil
    shutil.rmtree(cache / "example-steel")
    with pytest.raises(SystemExit) as stopped:
        build_preview.build(tmp_path / "dist", companies)
    assert "its mirror is missing" in str(stopped.value) and "pipeline/mirror.py example-steel" in str(stopped.value)


def test_a_missing_three_js_stops_the_build_and_names_the_command(companies, cache, tmp_path):
    (cache / "_vendor" / "three.min.js").unlink()
    with pytest.raises(SystemExit, match=r"bundle\.py --three"):
        build_preview.build(tmp_path / "dist", companies)


def test_a_company_over_the_homepage_budget_fails_the_summary(companies, cache, tmp_path, monkeypatch):
    out = tmp_path / "dist"
    results = build_preview.build(out, companies)
    monkeypatch.setattr(common, "COMPANY_BYTES", 1000)
    text, ok = build_preview.summary(results, out)
    assert not ok and "OVER the homepage budget" in text
    monkeypatch.setattr(common, "COMPANY_BYTES", 16 * 2**20)
    monkeypatch.setattr(common, "PACKAGE_FILES", 3)
    text, ok = build_preview.summary(results, out)
    assert not ok and "OVER the receiver's limits" in text


def test_a_file_name_the_packager_refuses_stops_the_build(companies, cache, tmp_path):
    secret = site(cache) / "assets" / "token"
    secret.mkdir()
    (secret / "x.svg").write_text("<svg/>")
    page = site(cache) / "index.html"
    page.write_text(page.read_text().replace("</main>", '<img src="/assets/token/x.svg"></main>'))
    with pytest.raises(SystemExit, match="the packager refuses this name"):
        build_preview.build(tmp_path / "dist", companies)


def test_the_catalogue_photos_ride_with_the_homepage(example, cache):
    made, _, _ = catalog.build(example, site(cache))
    chosen = homepage.plan(example, site(cache), catalog.photos(made))
    assert "assets/tube.svg" in chosen["files"]


def test_reviewed_collection_build_serializes_catalogue_after_all_homepages(example, cache, tmp_path):
    full, _, _ = catalog.build(example, site(cache))
    sku = full["cats"][0]["items"][0]["c"]
    images = cache / "example-steel/generated"
    images.mkdir()
    (images / "angled.webp").write_bytes(b"reviewed image")
    (images / "held.webp").write_bytes(b"private image")
    (images / "index.json").write_text(json.dumps({
        "sets": {"selected": ["angled.webp"], "held": ["held.webp"]},
        "items": {sku: "selected", "HELD-SKU": None}, "variantTypes": ["HELD-TYPE"],
    }))
    example["catalogueScope"] = "reviewed_images"
    out = tmp_path / "selected"
    build_preview.build_company(example, out)
    public = json.loads((out / "example-steel/rocoto/catalog.json").read_text())
    assert isinstance(public, dict)
    assert [item["c"] for category in public["cats"] for item in category["items"]] == [sku]
    assert (out / "example-steel/de/index.html").is_file()
    public_images = (out / "example-steel/rocoto/g/index.json").read_text()
    assert "HELD" not in public_images
    assert "held.webp" not in public_images
    assert json.loads(public_images)["items"] == {sku: "selected"}
    assert not (out / "example-steel/rocoto/g/held.webp").exists()
