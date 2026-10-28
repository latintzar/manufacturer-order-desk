"""Refresh invariants: operational ownership survives source changes and failed reads."""

import copy
import json

from refresh import check_candidate, maintain, promote, source_catalog
from store import CompanyStore
from test_store import store as store
from test_store import submit

from pipeline import mirror


def accounting(candidate):
    items = [i for c in candidate["cats"] for i in c["items"]]
    return {
        "rows": len(items),
        "priced items": sum(not i.get("q") for i in items),
        "price on request": sum(bool(i.get("q")) for i in items),
    }


def test_owner_prices_and_operational_facts_survive_refresh(store):
    candidate = source_catalog(store)
    store.set_price("A", 17, "owner", "contract")
    store.set_selling("A", 2, 2, 2, "owner", "verified")
    store.record_stock("A", 20, "owner", "counted")
    order = submit(store)
    store.accept_order(order["id"], "owner", "verified", "accept")
    preserved = {
        t: store.rows(f"SELECT * FROM {t}")
        for t in (
            "selling",
            "stock",
            "stock_events",
            "capacity_load",
            "orders",
            "order_lines",
            "order_events",
        )
    }
    candidate["cats"][0]["items"][0]["p"] = 14
    result = promote(store, candidate, {"slug": "example"}, accounting(candidate))
    assert result["ok"] and result["status"] == "applied"
    assert store.item("A")["item"]["p"] == 17
    assert store.export_catalog()["cats"][0]["items"][0]["p"] == 17
    assert source_catalog(store)["cats"][0]["items"][0]["p"] == 14
    assert store.rows("SELECT amount FROM prices WHERE basis='p' ORDER BY id") == [
        {"amount": 12.345},
        {"amount": 17},
        {"amount": 14},
    ]
    for table, rows in preserved.items():
        assert store.rows(f"SELECT * FROM {table}") == rows


def test_legacy_owner_override_is_migrated(store):
    store.set_price("A", 17, "owner", "contract")
    store.db.execute("DROP TABLE price_overrides")
    other = CompanyStore(store.path)
    try:
        candidate = source_catalog(other)
        candidate["cats"][0]["items"][0]["p"] = 14
        promote(other, candidate, {"slug": "example"}, accounting(candidate))
        assert other.item("A")["item"]["p"] == 17
    finally:
        other.close()


def test_failed_candidate_retains_catalog_and_records_office_question(store):
    before = store.export_catalog()
    candidate = copy.deepcopy(before)
    candidate["cats"][0]["items"] = []
    result = promote(store, candidate, {"slug": "example"}, accounting(candidate))
    assert not result["ok"] and result["status"] == "held"
    assert store.export_catalog() == before
    question = json.loads(store.one("SELECT data FROM questions ORDER BY id DESC")["data"])
    assert question["kind"] == "source_refresh"
    assert question["removed"] == ["A"]


def test_dry_run_has_no_database_effect(store):
    before = store.db.total_changes
    candidate = source_catalog(store)
    candidate["cats"][0]["items"][0]["p"] = 14
    assert promote(store, candidate, {"slug": "example"}, accounting(candidate), dry_run=True)["ok"]
    assert store.db.total_changes == before
    assert store.item("A")["item"]["p"] == 12.345


def test_incomplete_crawl_and_commercial_basis_changes_hold(store):
    old = source_catalog(store)
    changes = [("p", 100), ("p", float("nan")), ("r", {"k": "whole"}), ("L", 12), ("q", 1)]
    for key, value in changes:
        candidate = copy.deepcopy(old)
        candidate["cats"][0]["items"][0][key] = value
        assert not check_candidate(old, candidate, accounting(candidate))["ok"]
    for reason in ("failed", "refused", "left"):
        assert not check_candidate(old, old, accounting(old), {reason: 1})["ok"]
    bad_count = accounting(old)
    bad_count["rows"] += 1
    assert not check_candidate(old, old, bad_count)["ok"]


def test_requested_estimates_change_but_accepted_promises_stay(store):
    order = submit(store)
    first_count = store.one("SELECT COUNT(*) n FROM estimates")["n"]
    result = maintain(store, now="2026-10-20T09:00:00+03:00")
    assert result["changed_estimates"] == [order["id"]]
    assert store.one("SELECT COUNT(*) n FROM estimates")["n"] == first_count + 1
    assert maintain(store, now="2026-10-20T09:00:00+03:00")["changed_estimates"] == []
    store.record_stock("A", 20, "owner", "counted")
    store.accept_order(order["id"], "owner", "accepted", "accept")
    before = store.read_order(order["id"])["estimates"]
    assert maintain(store, now="2026-10-21T09:00:00+03:00")["changed_estimates"] == []
    assert store.read_order(order["id"])["estimates"] == before


def test_mirror_refresh_updates_pages_and_pdf_but_reuses_images(tmp_path):
    site = tmp_path / "site"
    site.mkdir()
    (site / "index.html").write_text("old")
    (site / "list.pdf").write_bytes(b"old pdf")
    (site / "image.jpg").write_bytes(b"image")
    called = []

    def get(url):
        called.append(url)
        if url.endswith("robots.txt"):
            return 200, "text/plain", b"User-agent: *\nAllow: /"
        if url.endswith("list.pdf"):
            return 200, "application/pdf", b"new pdf"
        return 200, "text/html", b'<a href="/list.pdf">PDF</a><img src="/image.jpg">new'

    result = mirror.mirror(
        {"source": "https://example.test/"},
        site,
        get=get,
        sleep=lambda _: None,
        log=lambda _: None,
        refresh=True,
    )
    assert result["failed"] == 0
    assert (site / "list.pdf").read_bytes() == b"new pdf"
    assert b"new" in (site / "index.html").read_bytes()
    assert (site / "image.jpg").read_bytes() == b"image"
    assert all(not url.endswith("image.jpg") for url in called)


def test_refresh_candidate_is_separate_and_held_on_source_outage(example, cache, tmp_path, monkeypatch):
    from urllib.parse import urlsplit

    from refresh import refresh

    from pipeline import catalog, common

    baseline_site = cache / example["slug"] / "site"
    original = (baseline_site / "price-list/index.html").read_bytes()
    source, _, _ = catalog.build(example, baseline_site, common.prefix_of(example))
    db = CompanyStore(tmp_path / "runtime/company.db")
    db.ingest_catalog(source, {k: v for k, v in example.items() if k != "dir"})
    monkeypatch.setattr(mirror, "DELAY", 0)

    def get(url):
        path = urlsplit(url).path
        if path == "/robots.txt":
            return 200, "text/plain", b"User-agent: *\nAllow: /"
        if path == "/price-list/":
            return 503, "text/html", b"unavailable"
        local = baseline_site / mirror.local_path(path, mirror.is_page(path))
        if local.is_file():
            return (
                200,
                "text/html" if local.suffix == ".html" else "application/octet-stream",
                local.read_bytes(),
            )
        return 404, "", b""

    try:
        result = refresh(db, example, cache, get=get)
        assert not result["ok"]
        assert db.export_catalog() == source
        assert (baseline_site / "price-list/index.html").read_bytes() == original
        assert db.one("SELECT COUNT(*) n FROM questions")["n"] >= 1
        assert db.one("SELECT COUNT(*) n FROM stage_runs")["n"] == 1
        assert result["evidence"].startswith(str(cache / example["slug"] / "refresh"))
    finally:
        db.close()


def test_known_missing_links_never_excuse_lost_critical_or_previous_content(tmp_path):
    from refresh import classify_failures

    site = tmp_path / "site"
    site.mkdir()
    (site / "old.html").write_text("previous content")
    urls = [
        "https://example.test/dead/1",
        "https://example.test/price-list/",
        "https://example.test/old.html",
    ]
    baseline = {"failures": [{"url": url, "status": 404} for url in urls]}
    config = {"slug": "example", "source": "https://example.test/", "priceList": {"url": urls[1]}, "home": {}}
    failures = classify_failures(
        "\n".join("404 " + url for url in urls), baseline, site, config, {"cats": []}
    )
    assert [row["known_dead_link"] for row in failures] == [True, False, False]
    changed_status = classify_failures("503 " + urls[0], baseline, site, config, {"cats": []})
    assert not changed_status[0]["known_dead_link"]
    unseen = classify_failures("404 https://example.test/new/1", baseline, site, config, {"cats": []})
    assert not unseen[0]["known_dead_link"]


def test_overlapping_scheduled_worker_defers_without_touching_database(tmp_path, monkeypatch, capsys):
    import refresh as worker

    database = tmp_path / "company.db"
    monkeypatch.setattr(worker.common, "company", lambda _: {"slug": "example"})

    def fail_if_opened(_):
        raise AssertionError("busy worker must leave the database alone")

    monkeypatch.setattr(worker, "CompanyStore", fail_if_opened)
    with worker.locked(database.with_suffix(".refresh.lock")) as acquired:
        assert acquired
        assert worker.main(["example", "--database", str(database), "--maintain"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "deferred"
    assert not database.exists()


def test_failed_page_attempts_consume_crawl_budget(tmp_path):
    def get(url):
        if url.endswith("robots.txt"):
            return 200, "text/plain", b"User-agent: *\nAllow: /"
        if url == "https://example.test/":
            return (
                200,
                "text/html",
                "".join(f'<a href="/missing-{i}/">broken</a>' for i in range(10)).encode(),
            )
        return 404, "", b""

    result = mirror.mirror(
        {"source": "https://example.test/", "mirror": {"maxPages": 3}},
        tmp_path,
        get=get,
        sleep=lambda _: None,
        log=lambda _: None,
    )
    assert result["fetched"] == 3
    assert result["failed"] == 2
    assert result["left"] == 8


def test_broken_alias_is_resolved_only_by_same_run_canonical_success(tmp_path):
    from refresh import classify_failures

    config = {
        "slug": "example",
        "source": "https://example.test/",
        "priceList": {"url": "https://example.test/prices/"},
        "home": {},
    }
    log = "200 123 https://example.test/services/\n404 https://example.test/services//"
    rows = classify_failures(log, {"failures": []}, tmp_path, config, {"cats": []})
    assert len(rows) == 1 and rows[0]["resolved_alias"]
    assert rows[0]["canonical_success"] == "https://example.test/services/"
    unresolved = classify_failures(log.splitlines()[1], {"failures": []}, tmp_path, config, {"cats": []})
    assert not unresolved[0]["resolved_alias"]


def test_unlinked_catalogue_pages_are_seeded_and_fetched(tmp_path):
    from refresh import source_seeds

    config = {
        "slug": "example",
        "source": "https://example.test/",
        "priceList": {"url": "https://example.test/prices/"},
        "home": {},
    }
    previous = {"cats": [{"url": {"en": "/example/unlinked/"}}]}
    seeds = source_seeds(config, previous)
    assert "https://example.test/unlinked/" in seeds
    called = []

    def get(url):
        called.append(url)
        if url.endswith("robots.txt"):
            return 200, "text/plain", b"User-agent: *\nAllow: /"
        return 200, "text/html", b"<h1>Public source page</h1>"

    result = mirror.mirror(
        config, tmp_path, get=get, sleep=lambda _: None, log=lambda _: None, seed_urls=seeds
    )
    assert result["pages"] == 3
    assert "https://example.test/unlinked/" in called
