#!/usr/bin/env python3
"""Bounded source refresh and deterministic ready-time maintenance for one company."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import math
import os
import re
import shutil
import sys
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
from store import CompanyStore, dump, stamp  # noqa: E402
from supply import quote_ready  # noqa: E402

from pipeline import catalog as catalogue  # noqa: E402
from pipeline import common, mirror

ACTOR = "source-refresh"


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def source_catalog(store):
    """Published facts before owner price overrides, used for source-to-source checks."""
    out = store.export_catalog()
    for cat in out["cats"]:
        cat["items"] = [
            json.loads(row["data"])
            for row in store.rows(
                "SELECT data FROM items WHERE type_id=? AND active=1 ORDER BY position", (cat["code"],)
            )
        ]
    return out


def check_candidate(previous, candidate, accounting, crawl=None):
    """Changes needing judgement are held with reasons; the last good DB stays live."""
    errors = []
    if crawl and (
        crawl.get("unexpected_failed", crawl.get("failed", 0))
        or any(crawl.get(k, 0) for k in ("refused", "left"))
    ):
        errors.append(
            "source crawl incomplete: new failures, critical failures, robots-refused or budget-limited URLs"
        )
    old_cats = {c["code"]: c for c in previous["cats"]}
    new_cats = {c["code"]: c for c in candidate["cats"]}
    if len(new_cats) != len(candidate["cats"]) or not new_cats:
        errors.append("empty or duplicate product types")
    if old_cats.keys() - new_cats.keys():
        errors.append("previous product types disappeared")
    old = {i["c"]: (c["code"], i) for c in previous["cats"] for i in c["items"]}
    new = {}
    for cat in candidate["cats"]:
        for item in cat["items"]:
            code = item["c"]
            if code in new:
                errors.append(f"duplicate item {code}")
            new[code] = (cat["code"], item)
            for field in ("p", "cut", "L", "w"):
                value = item.get(field)
                if value is not None and (
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not math.isfinite(value)
                    or value < 0
                ):
                    errors.append(f"{code}: invalid {field}")
            if not item.get("q") and not item.get("p", 0):
                errors.append(f"{code}: priced row requires a positive price")
    missing = old.keys() - new.keys()
    if missing:
        errors.append(f"{len(missing)} previous items disappeared: " + ",".join(sorted(missing)[:20]))
    if old and len(new) > max(len(old) * 1.2, len(old) + 20):
        errors.append("item growth exceeds the bounded automatic acceptance threshold")
    if accounting.get("rows", 0) != sum(accounting.get(k, 0) for k in catalogue.OUTCOMES):
        errors.append("source row accounting differs")
    if len(new) != accounting.get("priced items", 0) + accounting.get("price on request", 0):
        errors.append("parsed item count differs from source row accounting")
    for key in ("currency", "vat", "rules"):
        if previous.get(key) != candidate.get(key):
            errors.append(f"{key} changed; review the commercial basis")
    for code in old.keys() & new.keys():
        old_type, before = old[code]
        new_type, after = new[code]
        if old_type != new_type:
            errors.append(f"{code}: product type changed")
        for key in ("r", "L", "u", "priceBasis", "d", "s", "q"):
            if before.get(key) != after.get(key):
                errors.append(f"{code}: {key} changed; review the selling basis")
        if before.get("rate", [None, None])[1:] != after.get("rate", [None, None])[1:]:
            errors.append(f"{code}: rate unit changed")
        for basis in ("p", "cut"):
            a, b = before.get(basis), after.get(basis)
            if a == b:
                continue
            if (
                not isinstance(a, (float, int))
                or not isinstance(b, (float, int))
                or a <= 0
                or b <= 0
                or not 0.5 <= b / a <= 2
            ):
                errors.append(f"{code}: {basis} changed beyond the automatic rate threshold")
    return {
        "ok": not errors,
        "errors": errors,
        "types": len(new_cats),
        "items": len(new),
        "added": sorted(new.keys() - old.keys()),
        "removed": sorted(missing),
        "changed": sorted(k for k in old.keys() & new.keys() if old[k] != new[k]),
    }


def record(store, family, payload, evidence):
    return store.record(family, payload, ACTOR, evidence)


def promote(store, candidate, config, accounting, crawl=None, dry_run=False, evidence="fixture refresh"):
    """One transactional catalog ingest. Operational facts have separate ownership."""
    previous = source_catalog(store)
    check = check_candidate(previous, candidate, accounting, crawl)
    result = {
        **check,
        "mode": "dry-run" if dry_run else "apply",
        "status": "held" if not check["ok"] else ("checked" if dry_run else "applied"),
        "catalog_hash": digest(candidate),
        "source_hash_before": digest(previous),
        "checked_at": stamp(),
    }
    if not dry_run:
        if check["ok"]:
            clean_config = {k: v for k, v in config.items() if k != "dir"}
            store.ingest_catalog(
                candidate,
                clean_config,
                ACTOR,
                evidence,
                idempotency_key="source-refresh:" + digest([candidate, clean_config]),
            )
        else:
            record(store, "questions", {"kind": "source_refresh", "status": "open", **result}, evidence)
        record(store, "stage_runs", {"stage": "refresh", **result}, evidence)
    return result


@contextmanager
def locked(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        yield True


def source_seeds(config, previous):
    seeds = {config["source"], config["priceList"]["url"]}
    seeds.update(
        urljoin(config["source"], path.removesuffix("index.html")) for path in config.get("home", {}).values()
    )
    for cat in previous["cats"]:
        for value in cat.get("url", {}).values():
            if not value:
                continue
            prefix = "/" + config["slug"]
            path = value[len(prefix) :] if value.startswith(prefix + "/") else value
            seeds.add(urljoin(config["source"], path))
    return sorted(seeds)


def classify_failures(log_text, baseline, approved_site, config, previous):
    """A reviewed missing-link baseline never excuses losing previously available content."""
    allowed = {(row["url"], int(row["status"])) for row in baseline.get("failures", [])}
    critical = {config["source"], config["priceList"]["url"]}
    critical_paths = {"/" + path.removesuffix("index.html") for path in config.get("home", {}).values()}
    for cat in previous["cats"]:
        for value in cat.get("url", {}).values():
            path = urlsplit(value).path
            prefix = "/" + config["slug"]
            critical_paths.add(path[len(prefix) :] if path.startswith(prefix + "/") else path)
    successful = set(re.findall(r"^\s*200\s+\d+\s+(https?://\S+)", log_text, re.M))
    failures = []
    for line in log_text.splitlines():
        match = re.match(r"^\s*(\d+|lost)\s+(https?://\S+)(?:\s+(.*))?$", line)
        if not match:
            continue
        status = int(match[1]) if match[1] != "lost" else 0
        url = match[2]
        path = urlsplit(url).path
        had_content = any((approved_site / mirror.local_path(path, html)).is_file() for html in (True, False))
        is_critical = url in critical or path in critical_paths or had_content
        known = status == 404 and (url, status) in allowed and not is_critical
        normalized = re.sub(r"/{2,}", "/", path)
        canonical = urlsplit(url)._replace(path=normalized).geturl()
        resolved_alias = status == 404 and normalized != path and canonical in successful
        failures.append(
            {
                "url": url,
                "status": status,
                "reason": match[3] or ("oversize" if status == 200 else "HTTP refusal"),
                "known_dead_link": known,
                "critical": is_critical,
                "prior_content": had_content,
                "resolved_alias": resolved_alias,
                "canonical_success": canonical if resolved_alias else None,
            }
        )
    return failures


def refresh(store, config, cache, dry_run=False, get=mirror.fetch):
    """Keep the approved mirror intact; each candidate has its own bounded directory."""
    run_id = datetime.now().strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8]
    folder = cache / config["slug"] / "refresh" / run_id
    folder.mkdir(parents=True, mode=0o700)
    evidence = str(folder / "result.json")
    if not dry_run:
        record(store, "runs", {"kind": "source_refresh", "run_id": run_id, "status": "started"}, evidence)
    counts = None
    try:
        site = folder / "site"
        shutil.copytree(cache / config["slug"] / "site", site, copy_function=os.link)
        # Fresh pages/PDFs only: unreachable stale pages cannot conceal dropped catalogue rows.
        for path in site.rglob("*"):
            if path.is_file() and path.suffix.lower() in (".html", ".htm", ".pdf"):
                path.unlink()
        with (folder / "crawl.log").open("w", buffering=1) as log:
            settings = dict(config.get("mirror", {}))
            settings["maxPages"] = max(1, min(600, int(settings.get("maxPages", 600))))
            settings["maxBytes"] = max(1, min(300 * 2**20, int(settings.get("maxBytes", 300 * 2**20))))
            counts = mirror.mirror(
                {**config, "mirror": settings},
                site,
                get=get,
                refresh=True,
                seed_urls=source_seeds(config, source_catalog(store)),
                log=lambda line: log.write(line + "\n"),
            )
        baseline_path = cache / config["slug"] / "refresh-baseline.json"
        baseline = json.loads(baseline_path.read_text()) if baseline_path.is_file() else {"failures": []}
        failures = classify_failures(
            (folder / "crawl.log").read_text(),
            baseline,
            cache / config["slug"] / "site",
            config,
            source_catalog(store),
        )
        (folder / "crawl-failures.json").write_text(
            dump({"baseline": str(baseline_path), "baseline_hash": digest(baseline), "failures": failures})
        )
        counts["known_dead_links"] = sum(row["known_dead_link"] for row in failures)
        counts["resolved_aliases"] = sum(row["resolved_alias"] for row in failures)
        counts["unexpected_failed"] = (
            counts["failed"] - counts["known_dead_links"] - counts["resolved_aliases"]
        )
        if counts["resolved_aliases"] and not dry_run:
            aliases = [row for row in failures if row["resolved_alias"]]
            store.record(
                "questions",
                {"kind": "source_links", "status": "open", "aliases": aliases},
                ACTOR,
                evidence,
                idempotency_key="source-aliases:" + digest(aliases),
            )
        counts["failure_evidence"] = str(folder / "crawl-failures.json")
        candidate, accounting, _ = catalogue.build(
            config, site, common.prefix_of(config), output_dir=folder / "parsed"
        )
        (folder / "catalog.json").write_text(dump(candidate))
        result = promote(store, candidate, config, accounting, counts, dry_run, evidence)
        result["crawl"] = counts
    except (Exception, SystemExit) as error:
        result = {
            "status": "failed",
            "ok": False,
            "errors": [str(error)],
            "checked_at": stamp(),
            "crawl": counts,
        }
        if not dry_run:
            record(store, "questions", {"kind": "source_refresh", "status": "open", **result}, evidence)
            record(store, "stage_runs", {"stage": "refresh", **result}, evidence)
    (folder / "result.json").write_text(dump(result))
    # Retain the complete latest candidate plus small previous evidence, bounding disk growth.
    older = sorted(folder.parent.iterdir(), key=lambda p: p.name, reverse=True)[3:]
    for old in older:
        if (old / "site").is_dir():
            shutil.rmtree(old / "site")
    return {**result, "evidence": evidence}


def maintain(store, now=None):
    """Recompute requested estimates; accepted promises and reservations stay authoritative."""
    changed, errors = [], []
    evidence = "scheduled deterministic ready-time maintenance"
    for row in store.rows("SELECT id FROM orders WHERE state='requested' ORDER BY created_at LIMIT 500"):
        order = store.read_order(row["id"])
        try:
            lines = order["lines"]
            estimate = quote_ready(store, lines, now)
            previous = order["estimates"][-1]["data"] if order["estimates"] else None
            if estimate != previous:

                def update(oid=row["id"]):
                    current = store.read_order(oid)
                    if current["state"] != "requested":
                        return {"changed": False}
                    fresh = quote_ready(store, current["lines"], now)
                    if current["estimates"] and current["estimates"][-1]["data"] == fresh:
                        return {"changed": False}
                    event = store._event("estimates", fresh, ACTOR, evidence, order_id=oid, kind="estimate")
                    return {"changed": True, "id": event}

                updated = store._write(
                    "maintenance.estimate", {"order_id": row["id"]}, ACTOR, evidence, None, update
                )
                if updated["changed"]:
                    changed.append(row["id"])
        except ValueError as error:
            errors.append({"order_id": row["id"], "error": str(error)})
    pending = store.one("SELECT COUNT(*) AS n FROM orders WHERE state='requested'")["n"]
    if pending > 500:
        errors.append(
            {
                "kind": "maintenance_batch",
                "pending": pending,
                "error": "Requested-order queue exceeds the 500-order maintenance budget; expand the scheduler.",
            }
        )
    result = {
        "stage": "maintenance",
        "status": "held" if errors else "complete",
        "changed_estimates": changed,
        "errors": errors,
        "checked_at": stamp(),
        "engine": "deterministic",
        "batch_limit": 500,
    }
    if errors:
        record(store, "questions", {"kind": "ready_time_maintenance", "status": "open", **result}, evidence)
    record(store, "stage_runs", result, evidence)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("company")
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--cache", type=Path, default=common.cache_root())
    parser.add_argument("--candidate", type=Path, help="Validate a saved catalogue; never fetch")
    parser.add_argument(
        "--dry-run", action="store_true", help="Check source refresh without changing the database"
    )
    parser.add_argument(
        "--maintain", action="store_true", help="Recompute requested-order estimates without fetching"
    )
    args = parser.parse_args(argv)
    config = common.company(args.company)
    if args.dry_run and args.maintain:
        parser.error("--maintain writes estimate evidence; use a fixture DB for a maintenance trial")
    with locked(args.database.with_suffix(".refresh.lock")) as acquired:
        if not acquired:
            print(
                dump(
                    {
                        "status": "deferred",
                        "reason": "Company worker already running; next scheduled pass will retry.",
                    }
                )
            )
            return 0
        store = CompanyStore(args.database)
        try:
            if args.maintain:
                result = maintain(store)
            elif args.candidate:
                candidate = json.loads(args.candidate.read_text())
                items = [i for c in candidate["cats"] for i in c["items"]]
                accounting = {
                    "rows": len(items),
                    "priced items": sum(not i.get("q") for i in items),
                    "price on request": sum(bool(i.get("q")) for i in items),
                }
                result = promote(
                    store, candidate, config, accounting, dry_run=args.dry_run, evidence=str(args.candidate)
                )
            else:
                result = refresh(store, config, args.cache, args.dry_run)
            print(dump(result))
            return 0 if result.get("ok", result["status"] == "complete") else 1
        finally:
            store.close()


if __name__ == "__main__":
    raise SystemExit(main())
