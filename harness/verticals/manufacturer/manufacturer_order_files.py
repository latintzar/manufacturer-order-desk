"""Read original order attachments through the workspace's exact company binding."""

from __future__ import annotations

import hashlib
import os
import re
import stat
import subprocess
import sys
import threading
from pathlib import Path
from urllib.parse import quote

from manufacturer_store import Missing, SourceUnavailable

MAX_FILE = 16 * 1024 * 1024


def validate_metadata(value):
    if (
        not isinstance(value, dict)
        or not re.fullmatch(r"[a-f0-9]{32}", str(value.get("id", "")))
        or not isinstance(value.get("name"), str)
        or not 0 < len(value["name"]) <= 255
        or type(value.get("size")) is not int
        or not 0 < value["size"] <= MAX_FILE
        or not re.fullmatch(r"[a-f0-9]{64}", str(value.get("sha256", "")))
    ):
        raise SourceUnavailable("The original file needs verification.")
    return {key: value[key] for key in ("id", "name", "size", "sha256")} | {
        "content_type": str(value.get("content_type", "application/octet-stream"))[:150]
    }


def local_files(source, order_id):
    source.order(order_id)
    with source.connect() as db:
        exists = db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='order_files'"
        ).fetchone()
        return (
            [
                validate_metadata(dict(row))
                for row in db.execute(
                    "SELECT id,name,content_type,size,sha256 FROM order_files WHERE order_id=? ORDER BY created_at,id",
                    (order_id,),
                )
            ]
            if exists
            else []
        )


def local_file(source, order_id, file_id):
    selected = next((item for item in local_files(source, order_id) if item["id"] == file_id), None)
    if selected is None:
        raise Missing("Choose a file attached to this order.")
    path = Path(source.binding()["database"]).parent / "order-files" / file_id
    try:
        if path.parent.is_symlink():
            raise ValueError()
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(descriptor, "rb") as stream:
            info = os.fstat(stream.fileno())
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_nlink != 1
                or info.st_mode & 0o077
                or info.st_size != selected["size"]
            ):
                raise ValueError()
            raw = stream.read(MAX_FILE + 1)
        if len(raw) != selected["size"] or hashlib.sha256(raw).hexdigest() != selected["sha256"]:
            raise ValueError()
        return selected, raw
    except (OSError, ValueError):
        raise Missing("The original file is temporarily unavailable.") from None


def files(workspace, actor, order_id):
    workspace.member(actor)
    source = workspace.source
    values = source.order_files(order_id) if hasattr(source, "order_files") else local_files(source, order_id)
    values = [validate_metadata(value) for value in values]
    workspace.member(actor)
    prefix = "/api/manufacturer/orders/" + quote(order_id, safe="") + "/files/"
    return {"files": [{**value, "url": prefix + value["id"]} for value in values]}


def original(workspace, actor, order_id, file_id, download=False):
    workspace.member(actor)
    source = workspace.source
    metadata, raw = (
        source.order_file(order_id, file_id)
        if hasattr(source, "order_file")
        else local_file(source, order_id, file_id)
    )
    metadata = validate_metadata(metadata)
    workspace.member(actor)
    mime = "application/octet-stream"
    if metadata["content_type"] == "application/pdf" and raw.startswith(b"%PDF-"):
        mime = "application/pdf"
    elif metadata["content_type"] in {"text/plain", "text/csv"}:
        mime = "text/plain; charset=utf-8"
    disposition = "attachment" if download or mime == "application/octet-stream" else "inline"
    headers = {
        "Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "default-src 'none'; sandbox; frame-ancestors 'self'",
        "Content-Disposition": disposition + "; filename*=UTF-8''" + quote(metadata["name"], safe=""),
        "X-Content-SHA256": metadata["sha256"],
    }
    return raw, mime, headers


PDF_SLOT = threading.BoundedSemaphore(1)


def pdf_page(workspace, actor, order_id, file_id, page):
    from manufacturer_store import Invalid

    if type(page) is not int or not 1 <= page <= 10000:
        raise Missing("Choose a page in this specification.")
    if not PDF_SLOT.acquire(blocking=False):
        raise SourceUnavailable("The document preview is preparing. Try again shortly.")
    try:
        raw, mime, headers = original(workspace, actor, order_id, file_id)
        if mime != "application/pdf":
            raise Missing("Choose a PDF specification.")
        try:
            result = subprocess.run(
                [
                    sys.executable,
                    str(Path(__file__).with_name("manufacturer_source_reader.py")),
                    ".pdf-page",
                    str(page),
                ],
                input=raw,
                capture_output=True,
                timeout=25,
                check=False,
            )
            if result.returncode or len(result.stdout) > 10 * 1024 * 1024:
                raise ValueError()
            count, image = result.stdout.split(b"\n", 1)
            if not count.isdigit() or not image.startswith(b"\x89PNG\r\n\x1a\n"):
                raise ValueError()
        except (OSError, ValueError, subprocess.TimeoutExpired):
            raise Invalid("Download the original specification to review this page.") from None
        workspace.member(actor)
        return image, {
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
            "X-Total-Pages": str(min(int(count), 10000)),
            "Content-Disposition": "inline",
        }
    finally:
        PDF_SLOT.release()
