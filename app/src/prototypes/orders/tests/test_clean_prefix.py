"""A mirrored page becomes a private preview page under its company prefix."""
from __future__ import annotations

from conftest import FIXTURES
from pipeline import clean, prefix

HOME = (FIXTURES / "example-steel" / "site" / "index.html").read_text(encoding="utf-8")
TOPS = {"assets", "products", "price-list", "de", "index.html", "rocoto"}


def test_trackers_leave_and_the_page_asks_search_engines_to_stay_away():
    cleaned, removed = clean.clean_html(HOME)
    assert "googletagmanager" not in cleaned and "gtag(" not in cleaned and "dataLayer" not in cleaned
    assert removed["script from googletagmanager.com"] == 1 and removed["inline tracking script"] == 1
    assert '<meta name="robots" content="noindex,nofollow">' in cleaned
    assert "index,follow" not in cleaned
    assert '<script src="/assets/site.js"></script>' in cleaned      # the site's own script stays


def test_every_link_is_inert_and_every_form_stays_on_the_page():
    cleaned, removed = clean.clean_html(HOME)
    assert removed["link made inert"] == 5 and removed["form made inert"] == 1
    assert 'href="/products/tubes/"' not in cleaned and "mailto:" not in cleaned and "target=" not in cleaned
    assert cleaned.count('href="#" data-rocoto-inert') == 5
    assert '<a href="#top">Top</a>' in cleaned                      # a jump inside the page is the page's own
    assert '<form data-rocoto-inert onsubmit="return false" action="/search/"' in cleaned
    assert "data-rocoto-guard" in cleaned and "preventDefault" in cleaned


def test_cleaning_twice_changes_nothing_more_and_drops_an_earlier_script_tag():
    once, _ = clean.clean_html(HOME + '<script src="/rocoto/configurator.js" data-rocoto="x" defer></script>')
    twice, removed = clean.clean_html(once)
    assert once == twice and not removed["link made inert"]
    assert "/rocoto/configurator.js" not in once


def test_html_attributes_srcset_inline_styles_and_scripts_move_under_the_prefix():
    cleaned, _ = clean.clean_html(HOME)
    moved, report = prefix.prefix_html(cleaned, "/example-steel", TOPS)
    assert '<link rel="stylesheet" href="/example-steel/assets/site.css?v=3">' in moved
    assert '<img class="logo" src="/example-steel/assets/logo.svg"' in moved
    assert 'srcset="/example-steel/assets/tube.svg 1x, /example-steel/assets/tube-2x.svg 2x"' in moved
    assert "url('/example-steel/assets/hero.svg')" in moved
    assert '<video poster="/example-steel/assets/hero.svg"><source src="/example-steel/assets/film.mp4"' in moved
    assert 'action="/example-steel/search/"' in moved
    assert '<!-- <img src="/assets/retired.svg" alt=""> -->' in moved          # a comment is left as written
    assert report["html attribute"] >= 7
    left = [line for line in moved.splitlines() if 'src="/assets' in line and "<!--" not in line]
    assert left == []


def test_other_hosts_and_protocol_relative_urls_stay_as_written():
    page = '<img src="//cdn.example/x.png"><img src="https://other.example/y.png"><a href="#" data-rocoto-inert>x</a>'
    moved, report = prefix.prefix_html(page, "/co", TOPS)
    assert moved == page and not report


def test_stylesheet_urls_move_and_relative_ones_stay():
    css = '@import "/assets/base.css"; a{background:url(/assets/a.svg)} b{background:url("../b.svg")} c{background:url(//x/y.svg)}'
    moved, report = prefix.prefix_css(css, "/co")
    assert moved == ('@import "/co/assets/base.css"; a{background:url(/co/assets/a.svg)} '
                     'b{background:url("../b.svg")} c{background:url(//x/y.svg)}')
    assert report["css url"] == 1 and report["css import"] == 1


def test_script_paths_of_the_site_move_and_unknown_ones_are_reported():
    script = (FIXTURES / "example-steel" / "site" / "assets" / "site.js").read_text(encoding="utf-8")
    moved, report = prefix.prefix_js(script, "/example-steel", TOPS)
    assert "var home = '/example-steel/products/tubes/';" in moved
    assert 'var endpoint = "/ajax/search";' in moved
    assert report["script path"] == 1
    assert report["left alone: script path /ajax/search"] == 1
    home, _ = prefix.prefix_js("location.href='/';", "/co", TOPS)
    assert home == "location.href='/co/';"


def test_an_attribute_the_rewriter_leaves_alone_is_reported():
    _, report = prefix.prefix_html('<div title="/assets/x.svg"></div><base href="/">', "/co", TOPS)
    assert report["left alone: title=/assets/x.svg"] == 1
    assert report["left alone: <base> tag"] == 1
