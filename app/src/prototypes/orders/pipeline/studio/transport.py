"""Provider adapter execution boundary; persist receipt before fetching output bytes."""

import json

from . import queue


def execute(connection, job_id, authorization_id, adapter, output):
    """Adapter owns company credentials, quote(payload), generate(payload), fetch(receipt,path).

    Call from at most two workers, each with its own SQLite connection. Unknown
    submissions stay held. A persisted receipt can be downloaded again without
    issuing another provider generation. Never include credentials in receipts.
    """
    job = connection.execute("SELECT * FROM studio_jobs WHERE id=?", (job_id,)).fetchone()
    if not job:
        raise ValueError("Unknown job")
    payload = json.loads(job["payload"])
    if payload["model_requested"] == "gpt_image_native":
        raise ValueError("Native GPT uses the native-request/native-result manifest lane")
    quote = adapter.quote(payload)
    attempt = queue.reserve(connection, job_id, authorization_id, quote)
    try:
        queue.submitted(connection, attempt)
        receipt = adapter.generate(payload)
        queue.receive(connection, attempt, receipt, charged_usd=receipt.get("cost_usd"))
        adapter.fetch(receipt, output)
        queue.complete(connection, attempt, output)
    except Exception:
        queue.hold(connection, attempt, "Provider or download failure; inspect receipt before recovery")
        raise
    return attempt
