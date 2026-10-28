"""Two-lane, receipt-first queue; unknown submissions are held, never auto-retried."""

from __future__ import annotations

import json
import math
from pathlib import Path

from .schema import DELIVERY_SHOTS, check_inputs, encode, now, required_gates, sha256


def usage(connection):
    config = connection.execute("SELECT * FROM studio_config WHERE id=1").fetchone()
    if config is None:
        raise ValueError("Initialize the company budget first")
    rows = connection.execute(
        "SELECT * FROM studio_attempts WHERE state!='cancelled_before_submit'"
    ).fetchall()
    return {
        "calls": config["inherited_calls"] + len(rows),
        "known_usd": round(
            config["inherited_usd"]
            + sum(r["charged_usd"] if r["charged_usd"] is not None else r["quoted_usd"] or 0 for r in rows),
            6,
        ),
        "unknown_cost_calls": sum(r["charged_usd"] is None and r["quoted_usd"] is None for r in rows),
    }


def authorize(connection, job_ids, *, kind, evidence, allow_unknown_cost=False):
    """Record an already-given operator authorization for this exact immutable scope."""
    if kind not in ("pilot", "material_pilot", "full") or not job_ids or not evidence.strip():
        raise ValueError("Exact jobs, authorization kind and operator evidence required")
    job_ids = sorted(set(job_ids))
    products = {}
    for job_id in job_ids:
        row = connection.execute("SELECT * FROM studio_jobs WHERE id=?", (job_id,)).fetchone()
        if row is None or row["state"] not in ("draft", "authorized"):
            raise ValueError("Authorize only unsubmitted jobs")
        check_inputs(json.loads(row["payload"]))
        missing = required_gates(connection, row["product_code"], full=kind == "full")
        if missing:
            raise ValueError("Missing stage gates: " + ", ".join(missing))
        if kind == "pilot" and row["shot"] != "surface_macro":
            raise ValueError("Pilot scope is surface macro only")
        if kind == "material_pilot" and row["shot"] not in ("surface_macro", "cut_end"):
            raise ValueError("Material pilot scope is macro and cut end only")
        products.setdefault((row["product_code"], row["model"]), set()).add(row["shot"])
    if kind == "full" and any(shots != set(DELIVERY_SHOTS) for shots in products.values()):
        raise ValueError("Full scope requires one angled product image per product/model")
    with connection:
        aid = connection.execute(
            "INSERT INTO studio_authorizations(jobs,kind,evidence,allow_unknown_cost,at) VALUES(?,?,?,?,?)",
            (encode(job_ids), kind, evidence, int(allow_unknown_cost), now()),
        ).lastrowid
        connection.executemany(
            "UPDATE studio_jobs SET state='authorized' WHERE id=?", [(j,) for j in job_ids]
        )
    return aid


def reserve(connection, job_id, authorization_id, quote):
    if quote is not None and (type(quote) not in (int, float) or not math.isfinite(quote) or quote <= 0):
        raise ValueError("Provider quote must be finite and positive")
    connection.execute("BEGIN IMMEDIATE")
    try:
        auth = connection.execute(
            "SELECT * FROM studio_authorizations WHERE id=?", (authorization_id,)
        ).fetchone()
        job = connection.execute("SELECT * FROM studio_jobs WHERE id=?", (job_id,)).fetchone()
        if not auth or job_id not in json.loads(auth["jobs"]) or not job or job["state"] != "authorized":
            raise ValueError("Job is outside authorization or already submitted")
        if quote is None and not auth["allow_unknown_cost"]:
            raise ValueError("Native unknown-cost lane requires explicit budget authorization")
        if required_gates(connection, job["product_code"], full=auth["kind"] == "full"):
            raise ValueError("A required stage gate is held")
        payload = json.loads(job["payload"])
        check_inputs(payload)
        config = connection.execute("SELECT * FROM studio_config WHERE id=1").fetchone()
        used = usage(connection)
        if used["calls"] >= config["call_limit"]:
            raise ValueError("Call ceiling exhausted, including unknown submissions")
        if quote is not None and (
            quote > config["max_quote_usd"] + 1e-9 or used["known_usd"] + quote > config["usd_limit"] + 1e-9
        ):
            raise ValueError("Quote exceeds configured spend ceiling")
        if (
            connection.execute(
                "SELECT count(*) FROM studio_attempts WHERE state IN ('reserved','submitted')"
            ).fetchone()[0]
            >= 2
        ):
            raise ValueError("Two execution lanes already occupied")
        attempt = connection.execute(
            "INSERT INTO studio_attempts(job_id,authorization_id,state,quoted_usd,request,created,updated) VALUES(?,?,?,?,?,?,?)",
            (job_id, authorization_id, "reserved", quote, encode(payload), now(), now()),
        ).lastrowid
        connection.execute("UPDATE studio_jobs SET state='reserved' WHERE id=?", (job_id,))
        connection.commit()
        return attempt
    except Exception:
        connection.rollback()
        raise


def submitted(connection, attempt):
    with connection:
        changed = connection.execute(
            "UPDATE studio_attempts SET state='submitted',updated=? WHERE id=? AND state='reserved'",
            (now(), attempt),
        ).rowcount
        if changed != 1:
            raise ValueError("Submit only a reserved attempt")


def receive(connection, attempt, receipt, *, charged_usd=None):
    if not receipt or (
        charged_usd is not None
        and (type(charged_usd) not in (int, float) or not math.isfinite(charged_usd) or charged_usd < 0)
    ):
        raise ValueError("Receipt and valid actual cost required")
    with connection:
        changed = connection.execute(
            "UPDATE studio_attempts SET state='received',receipt=?,charged_usd=?,updated=? WHERE id=? AND state IN ('submitted','unknown')",
            (encode(receipt), charged_usd, now(), attempt),
        ).rowcount
        if changed != 1:
            raise ValueError("Receive only a submitted/unknown attempt")


def complete(connection, attempt, output):
    output = Path(output).resolve()
    digest = sha256(output)
    with connection:
        row = connection.execute("SELECT * FROM studio_attempts WHERE id=?", (attempt,)).fetchone()
        if not row or row["state"] != "received":
            raise ValueError("Persist receipt before completing download")
        connection.execute(
            "UPDATE studio_attempts SET state='complete',output_path=?,output_sha256=?,updated=? WHERE id=?",
            (str(output), digest, now(), attempt),
        )
        connection.execute("UPDATE studio_jobs SET state='needs_judgement' WHERE id=?", (row["job_id"],))
    return digest


def hold(connection, attempt, error):
    with connection:
        row = connection.execute("SELECT * FROM studio_attempts WHERE id=?", (attempt,)).fetchone()
        if not row or row["state"] not in ("reserved", "submitted", "received"):
            raise ValueError("Only in-flight attempts can be held")
        state = (
            "unknown"
            if row["state"] == "submitted"
            else "received"
            if row["state"] == "received"
            else "cancelled_before_submit"
        )
        connection.execute(
            "UPDATE studio_attempts SET state=?,error=?,updated=? WHERE id=?",
            (state, str(error)[:1000], now(), attempt),
        )
        connection.execute("UPDATE studio_jobs SET state='held' WHERE id=?", (row["job_id"],))


def native_handoff(connection, job_id, authorization_id):
    """Export one manual native-tool request. The reservation counts even if the tool reply is lost."""
    row = connection.execute("SELECT * FROM studio_jobs WHERE id=?", (job_id,)).fetchone()
    if not row or row["model"] != "gpt_image_native":
        raise ValueError("Native handoff requires the native GPT model lane")
    attempt = reserve(connection, job_id, authorization_id, None)
    submitted(connection, attempt)
    payload = json.loads(row["payload"])
    config = connection.execute("SELECT company FROM studio_config WHERE id=1").fetchone()
    return {
        "schema": "rocoto.studio.native-request.v1",
        "company": config["company"],
        "attempt_id": attempt,
        "job_id": job_id,
        **payload,
        "instructions": "Use this exact prompt and ordered local files. Return the provider receipt, output path, output SHA256, prompt SHA256 and ordered input SHA256 values. Preserve original output.",
    }


def import_native(connection, result):
    row = connection.execute("SELECT * FROM studio_attempts WHERE id=?", (result["attempt_id"],)).fetchone()
    config = connection.execute("SELECT company FROM studio_config WHERE id=1").fetchone()
    if not row or row["state"] not in ("submitted", "unknown") or result.get("company") != config["company"]:
        raise ValueError("Native receipt belongs to an active attempt in this company")
    request = json.loads(row["request"])
    if request["model_requested"] != "gpt_image_native" or result.get("job_id") != row["job_id"]:
        raise ValueError("Native receipt job/model mismatch")
    if result["prompt_sha256"] != request["prompt_sha256"] or result["input_sha256"] != [
        r["sha256"] for r in request["inputs"]
    ]:
        raise ValueError("Native receipt does not match the exported prompt/inputs")
    if sha256(result["output_path"]) != result["output_sha256"]:
        raise ValueError("Native output hash mismatch")
    # Actual model/cost may be unknown: preserve null instead of inventing provider metadata.
    receive(
        connection,
        row["id"],
        {"provider_receipt": result["provider_receipt"], "model_actual": result.get("model_actual")},
        charged_usd=result.get("cost_usd"),
    )
    return complete(connection, row["id"], result["output_path"])


def review(connection, attempt, *, geometry_ok, material_ok, studio_ok, shot_ok, evidence):
    flags = (geometry_ok, material_ok, studio_ok, shot_ok)
    row = connection.execute("SELECT * FROM studio_attempts WHERE id=?", (attempt,)).fetchone()
    if (
        not row
        or row["state"] != "complete"
        or not evidence.strip()
        or any(type(x) is not bool for x in flags)
    ):
        raise ValueError("Downloaded output, direct visual evidence and four boolean checks required")
    if sha256(row["output_path"]) != row["output_sha256"]:
        raise ValueError("Reviewed output bytes changed")
    verdict = "keep" if all(flags) else "retry"
    with connection:
        connection.execute(
            "INSERT OR REPLACE INTO studio_reviews VALUES(?,?,?,?,?,?,?,?)",
            (attempt, *map(int, flags), verdict, evidence, now()),
        )
        connection.execute("UPDATE studio_jobs SET state=? WHERE id=?", (verdict, row["job_id"]))
    return verdict


def delivery_audit(connection):
    products = {r[0] for r in connection.execute("SELECT DISTINCT product_code FROM studio_jobs")}
    result = []
    for code in sorted(products):
        kept = {
            r["shot"]
            for r in connection.execute(
                "SELECT j.shot,a.output_path,a.output_sha256 FROM studio_jobs j JOIN studio_attempts a ON a.job_id=j.id JOIN studio_reviews r ON r.attempt_id=a.id WHERE j.product_code=? AND j.state='keep' AND r.verdict='keep'",
                (code,),
            )
            if Path(r["output_path"]).is_file() and sha256(r["output_path"]) == r["output_sha256"]
        }
        result.append(
            {
                "product_code": code,
                "missing_shots": sorted(set(DELIVERY_SHOTS) - kept),
                "held_gates": required_gates(connection, code, full=True),
            }
        )
    return {
        "products": result,
        "complete": bool(result) and all(not r["missing_shots"] and not r["held_gates"] for r in result),
        "usage": usage(connection),
    }
