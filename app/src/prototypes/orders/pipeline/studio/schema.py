"""Versioned studio ledger. Company data and provider credentials remain outside Git."""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SHOTS = ("angled_product", "whole_piece", "cut_end", "surface_macro")
DELIVERY_SHOTS = ("angled_product",)
SOURCE_GATES = (
    "links_classified",
    "unique_material_owner",
    "blind_description",
    "catalogue_match",
    "material_crop_reviewed",
    "structure_reviewed",
    "surface_zones_verified",
)
SCHEMA = """
CREATE TABLE IF NOT EXISTS studio_config(id INTEGER PRIMARY KEY CHECK(id=1),company TEXT NOT NULL,
 call_limit INTEGER NOT NULL,usd_limit REAL NOT NULL,max_quote_usd REAL NOT NULL,
 inherited_calls INTEGER NOT NULL,inherited_usd REAL NOT NULL);
CREATE TABLE IF NOT EXISTS studio_jobs(id TEXT PRIMARY KEY,product_code TEXT NOT NULL,shot TEXT NOT NULL,
 model TEXT NOT NULL,revision TEXT NOT NULL,payload TEXT NOT NULL,state TEXT NOT NULL DEFAULT 'draft');
CREATE TABLE IF NOT EXISTS studio_gates(product_code TEXT,gate TEXT,passed INTEGER,evidence TEXT,at TEXT,
 PRIMARY KEY(product_code,gate));
CREATE TABLE IF NOT EXISTS studio_authorizations(id INTEGER PRIMARY KEY,jobs TEXT,kind TEXT,evidence TEXT,
 allow_unknown_cost INTEGER,at TEXT);
CREATE TABLE IF NOT EXISTS studio_attempts(id INTEGER PRIMARY KEY,job_id TEXT NOT NULL,authorization_id INTEGER,
 state TEXT NOT NULL,quoted_usd REAL,charged_usd REAL,request TEXT NOT NULL,receipt TEXT,
 output_path TEXT,output_sha256 TEXT,error TEXT,created TEXT,updated TEXT);
CREATE TABLE IF NOT EXISTS studio_reviews(attempt_id INTEGER PRIMARY KEY,geometry_ok INTEGER,
 material_ok INTEGER,studio_ok INTEGER,shot_ok INTEGER,verdict TEXT,evidence TEXT,at TEXT);
"""


def now():
    return datetime.now(timezone.utc).isoformat()


def encode(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def connect(path, company):
    connection = sqlite3.connect(path, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout=30000")
    connection.executescript(SCHEMA)
    config = connection.execute("SELECT * FROM studio_config WHERE id=1").fetchone()
    if config and config["company"] != company:
        connection.close()
        raise ValueError("Studio database belongs to another company")
    return connection


def initialize(
    connection,
    company,
    *,
    call_limit=700,
    usd_limit=154.0,
    max_quote_usd=0.22,
    inherited_calls=0,
    inherited_usd=0.0,
):
    values = (company, call_limit, usd_limit, max_quote_usd, inherited_calls, inherited_usd)
    if any(
        type(x) not in (int, float) or not math.isfinite(x) for x in (usd_limit, max_quote_usd, inherited_usd)
    ):
        raise ValueError("Finite budget values required")
    if not company or type(call_limit) is not int or type(inherited_calls) is not int:
        raise ValueError("Company and integer call counts required")
    if call_limit < 1 or not 0 <= inherited_calls <= call_limit or not 0 <= inherited_usd <= usd_limit:
        raise ValueError("Invalid inherited usage or budget")
    if not 0 < max_quote_usd <= usd_limit:
        raise ValueError("Invalid quote ceiling")
    old = connection.execute("SELECT * FROM studio_config WHERE id=1").fetchone()
    if old and tuple(old)[1:] != values:
        raise ValueError("Existing budget baseline is immutable")
    connection.execute("INSERT OR IGNORE INTO studio_config VALUES(1,?,?,?,?,?,?)", values)
    connection.commit()


def check_inputs(payload):
    if not isinstance(payload.get("prompt"), str) or not payload["prompt"].strip():
        raise ValueError("Prompt required")
    expected = hashlib.sha256(payload["prompt"].encode()).hexdigest()
    if payload.get("prompt_sha256") != expected:
        raise ValueError("Prompt hash changed")
    refs = payload.get("inputs", [])
    if len(refs) != 2 or [r["role"] for r in refs] != ["STRUCTURE", "MATERIAL"]:
        raise ValueError("Inputs must be ordered STRUCTURE then MATERIAL")
    if type(refs[1].get("asset_id")) is not int:
        raise ValueError("Material input requires its exact numeric asset ID")
    for ref in refs:
        if not Path(ref["path"]).is_absolute() or sha256(ref["path"]) != ref["sha256"]:
            raise ValueError("Input path/hash changed")


def import_manifest(connection, manifest, *, revision=None):
    """Snapshot reviewed pair inputs. Reimporting the same job is idempotent."""
    revision = revision or manifest.get("revision") or manifest.get("schema")
    if not revision:
        raise ValueError("Revision required")
    jobs = []
    production = manifest.get("mode") == "production"
    rows = (
        [{"product_code": p["product_code"], "pair": [p]} for p in manifest.get("jobs", [])]
        if production
        else manifest["pairs"]
    )
    for row in rows:
        pair = row["pair"]
        if not production and (
            len(pair) != 2 or pair[0]["inputs"] != pair[1]["inputs"] or pair[0]["prompt"] != pair[1]["prompt"]
        ):
            raise ValueError("Comparison requires two models with identical inputs and prompt")
        if not production and pair[0]["model_requested"] == pair[1]["model_requested"]:
            raise ValueError("Comparison requires distinct models")
        for payload in pair:
            if payload["product_code"] != row["product_code"] or payload["shot"] not in SHOTS:
                raise ValueError("Product/shot identity mismatch")
            check_inputs(payload)
            if production:
                from .materials import validate_zones

                if payload["model_requested"] != "gpt_image_native":
                    raise ValueError("Production uses the native GPT model")
                validate_zones(payload.get("material_zones", {}))
            snapshot = {
                key: payload[key]
                for key in ("product_code", "shot", "model_requested", "inputs", "prompt", "prompt_sha256")
            }
            snapshot["revision"] = revision
            if production:
                snapshot["material_zones"] = payload["material_zones"]
                snapshot["mode"] = "production"
            key = hashlib.sha256(encode(snapshot).encode()).hexdigest()
            jobs.append(
                (
                    key,
                    snapshot["product_code"],
                    snapshot["shot"],
                    snapshot["model_requested"],
                    revision,
                    encode(snapshot),
                )
            )
    # Validate the whole manifest before recording any jobs.
    with connection:
        connection.executemany(
            "INSERT OR IGNORE INTO studio_jobs(id,product_code,shot,model,revision,payload) VALUES(?,?,?,?,?,?)",
            jobs,
        )
    return [row[0] for row in jobs]


def record_gate(connection, product_code, gate, passed, evidence):
    if (
        gate not in (*SOURCE_GATES, "macro_operator_approval")
        or not evidence.strip()
        or type(passed) is not bool
    ):
        raise ValueError("Known gate, boolean result and evidence required")
    connection.execute(
        "INSERT OR REPLACE INTO studio_gates VALUES(?,?,?,?,?)",
        (product_code, gate, int(passed), evidence, now()),
    )
    connection.commit()


def required_gates(connection, product_code, *, full=False):
    wanted = (*SOURCE_GATES, "macro_operator_approval") if full else SOURCE_GATES
    records = {
        r["gate"]: r
        for r in connection.execute("SELECT * FROM studio_gates WHERE product_code=?", (product_code,))
    }
    return [g for g in wanted if g not in records or not records[g]["passed"]]
