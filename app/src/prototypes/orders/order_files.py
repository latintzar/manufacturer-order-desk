"""Private design-file staging and order attachment access.

Customer uploads are capabilities until the matching order transaction claims them. Bytes stay
beside the company database under mode-0600 opaque names and leave only through authenticated,
attachment-only routes.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import struct
import tempfile
import time
import unicodedata
import uuid
from contextlib import suppress
from datetime import datetime, timezone
from pathlib import Path

MAX_UPLOAD_BYTES = 15 * 1024 * 1024
# A laser check holds two unclaimed files, the drawing and its corrected copy, for up to a day when a
# visitor leaves without ordering; the byte ceiling below is what bounds the disk.
MAX_PENDING_FILES = 200
MAX_ORDER_FILES = 10
MAX_COMPANY_BYTES = 512 * 1024 * 1024
PENDING_TTL_SECONDS = 24 * 60 * 60
UPLOAD_ID = re.compile(r"[a-f0-9]{32}")
UPLOAD_KEY = re.compile(r"[A-Za-z0-9_-]{16,128}")
DISCARD_TOKEN = re.compile(r"[A-Za-z0-9_-]{43}")

SCHEMA = """
CREATE TABLE IF NOT EXISTS order_files(
 id TEXT PRIMARY KEY,
 upload_key TEXT NOT NULL UNIQUE,
 order_id TEXT REFERENCES orders(id),
 name TEXT NOT NULL,
 content_type TEXT NOT NULL,
 size INTEGER NOT NULL,
 sha256 TEXT NOT NULL,
 created_at REAL NOT NULL,
 claimed_at TEXT
);
CREATE INDEX IF NOT EXISTS order_files_order ON order_files(order_id,id);
CREATE TRIGGER IF NOT EXISTS immutable_claimed_order_file_update
 BEFORE UPDATE ON order_files WHEN OLD.order_id IS NOT NULL
 BEGIN SELECT RAISE(ABORT,'claimed order file is immutable'); END;
CREATE TRIGGER IF NOT EXISTS immutable_claimed_order_file_delete
 BEFORE DELETE ON order_files WHEN OLD.order_id IS NOT NULL
 BEGIN SELECT RAISE(ABORT,'claimed order file is immutable'); END;
"""

EXTENSIONS = {
    ".pdf": "application/pdf",
    ".csv": "text/csv",
    ".txt": "text/plain",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".stl": "model/stl",
    ".obj": "model/obj",
    ".step": "model/step",
    ".stp": "model/step",
    ".dxf": "image/vnd.dxf",
    ".dwg": "image/vnd.dwg",
    ".svg": "image/svg+xml",
}
# A drawing is lines and curves. An SVG that carries a script, a handler, embedded markup or an
# entity declaration is refused; every stored file leaves as an attachment of opaque bytes.
SVG_SHAPE = re.compile(r"<(?:[A-Za-z_][\w.-]*:)?(?:path|polyline|polygon|line|circle|ellipse|rect)\b")
SVG_ACTIVE = re.compile(
    r"<(?:[A-Za-z_][\w.-]*:)?(?:script|foreignobject|iframe|embed|object|handler|listener)\b"
    r"|<!entity|\bon[a-z]+\s*=|javascript:|data:text/html",
    re.IGNORECASE,
)


def ensure_schema(store) -> None:
    store.db.executescript(SCHEMA)


def _safe_name(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("Choose a design file.")
    value = unicodedata.normalize("NFKC", value).replace("\\", "/").rsplit("/", 1)[-1]
    value = "".join(character for character in value if unicodedata.category(character)[0] != "C")
    value = re.sub(r"\s+", " ", value).strip(" .")
    if not value:
        raise ValueError("Choose a design file.")
    suffix = Path(value).suffix.lower()
    if suffix not in EXTENSIONS:
        raise ValueError("Choose a PDF, Word, Excel, image, DXF, DWG, SVG, STEP, STL or OBJ design file.")
    if len(value) > 120:
        stem = Path(value).stem[: 119 - len(suffix)].rstrip(" .") or "design"
        value = stem + suffix
    return value


def _text(body: bytes) -> str:
    if b"\x00" in body:
        raise ValueError("The design file format does not match its name.")
    try:
        return body.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("The design file format does not match its name.") from error


def _identify(name: str, body: bytes) -> str:
    if not body or len(body) > MAX_UPLOAD_BYTES:
        raise ValueError("Choose a design file up to 15 MB.")
    if body.startswith((b"MZ", b"\x7fELF", b"#!")):
        raise ValueError("Choose a supported design file.")
    suffix = Path(name).suffix.lower()
    valid = False
    if suffix in (".csv", ".txt"):
        text = _text(body)
        valid = bool(text.strip()) and not any(ord(c) < 32 and c not in "\r\n\t" for c in text)
    elif suffix == ".pdf":
        valid = body.startswith(b"%PDF-") and b"%%EOF" in body[-2048:]
    elif suffix in (".docx", ".xlsx"):
        from spec import archive
        with archive(body) as zipped:
            required = "word/document.xml" if suffix == ".docx" else "xl/workbook.xml"
            valid = required in zipped.namelist() and "[Content_Types].xml" in zipped.namelist()
    elif suffix == ".png":
        valid = body.startswith(b"\x89PNG\r\n\x1a\n")
    elif suffix in (".jpg", ".jpeg"):
        valid = body.startswith(b"\xff\xd8\xff") and body.endswith(b"\xff\xd9")
    elif suffix == ".webp":
        valid = len(body) >= 12 and body[:4] == b"RIFF" and body[8:12] == b"WEBP"
    elif suffix == ".stl":
        binary = len(body) >= 84 and 84 + 50 * struct.unpack("<I", body[80:84])[0] == len(body)
        sample = body[:2048].lstrip().lower()
        ascii_stl = sample.startswith(b"solid") and b"facet normal" in sample
        valid = binary or ascii_stl
    elif suffix == ".obj":
        text = _text(body)
        lines = [line.lstrip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")]
        valid = any(line.startswith("v ") for line in lines) and any(line.startswith("f ") for line in lines)
    elif suffix in (".step", ".stp"):
        text = _text(body).upper()
        valid = "ISO-10303-21;" in text[:512] and "END-ISO-10303-21;" in text[-1024:]
    elif suffix == ".dxf":
        # Older DXF versions write their text in the drawing's own code page; the structure is ASCII.
        if b"\x00" in body:
            raise ValueError("The design file format does not match its name.")
        text = body.decode("utf-8", errors="replace").upper()
        valid = "SECTION" in text[:4096] and "ENTITIES" in text and text.rstrip().endswith("EOF")
    elif suffix == ".svg":
        text = _text(body)
        valid = (
            "<svg" in text[:4096].lower()
            and SVG_SHAPE.search(text) is not None
            and SVG_ACTIVE.search(text) is None
        )
    elif suffix == ".dwg":
        valid = len(body) >= 64 and re.fullmatch(rb"AC10\d{2}", body[:6]) is not None
    if not valid:
        raise ValueError("The design file format does not match its name.")
    return EXTENSIONS[suffix]


def _directory(store) -> Path:
    root = store.path.parent / "order-files"
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(root, 0o700)
    return root


def _private_key(store) -> bytes:
    path = store.path.parent / "order-files.key"
    if not path.exists():
        fd, temporary = tempfile.mkstemp(prefix=".order-files-", dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as output:
                output.write(secrets.token_bytes(32))
                output.flush()
                os.fsync(output.fileno())
            with suppress(FileExistsError):
                os.link(temporary, path)
        finally:
            os.unlink(temporary)
    info = path.lstat()
    if path.is_symlink() or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise PermissionError("Use the private company order-file key.")
    key = path.read_bytes()
    if len(key) != 32:
        raise ValueError("The company order-file key requires review.")
    return key


def _discard_token(store, identifier: str) -> str:
    import base64

    digest = hmac.new(_private_key(store), identifier.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


def _metadata(row: dict | sqlite3.Row, store=None) -> dict:
    result = {
        "id": row["id"],
        "name": row["name"],
        "content_type": row["content_type"],
        "size": row["size"],
        "sha256": row["sha256"],
    }
    if store is not None and row["order_id"] is None:
        result["discard_token"] = _discard_token(store, row["id"])
    return result


def _cleanup_pending(store, now: float) -> None:
    for row in store.rows(
        "SELECT id FROM order_files WHERE order_id IS NULL AND created_at<?", (now - PENDING_TTL_SECONDS,)
    ):
        (_directory(store) / row["id"]).unlink(missing_ok=True)
        store.db.execute("DELETE FROM order_files WHERE id=? AND order_id IS NULL", (row["id"],))


def stage(store, filename: str, body: bytes, upload_key: str) -> dict:
    """Validate and durably stage one unclaimed customer upload."""
    if not UPLOAD_KEY.fullmatch(upload_key or ""):
        raise ValueError("Refresh the form and choose the file again.")
    name = _safe_name(filename)
    content_type = _identify(name, body)
    digest = hashlib.sha256(body).hexdigest()
    ensure_schema(store)
    identifier = uuid.uuid4().hex
    root = _directory(store)
    target = root / identifier
    temporary = root / ("." + identifier + ".upload")
    try:
        store.db.execute("BEGIN IMMEDIATE")
        _cleanup_pending(store, time.time())
        existing = store.one("SELECT * FROM order_files WHERE upload_key=?", (upload_key,))
        if existing:
            if existing["sha256"] != digest or existing["name"] != name or existing["size"] != len(body):
                raise ValueError("Upload key reused with a different file.")
            store.db.execute("COMMIT")
            return _metadata(existing, store)
        pending = store.one("SELECT COUNT(*) AS n FROM order_files WHERE order_id IS NULL")["n"]
        used = store.one("SELECT COALESCE(SUM(size),0) AS n FROM order_files")["n"]
        if pending >= MAX_PENDING_FILES:
            raise ValueError("Submit or remove a staged design file before adding another.")
        if used + len(body) > MAX_COMPANY_BYTES:
            raise ValueError("Design-file storage is full. Contact the workshop.")
        with temporary.open("xb") as output:
            os.chmod(temporary, 0o600)
            output.write(body)
            output.flush()
            os.fsync(output.fileno())
        temporary.replace(target)
        store.db.execute(
            "INSERT INTO order_files(id,upload_key,order_id,name,content_type,size,sha256,created_at,claimed_at) "
            "VALUES(?,?,NULL,?,?,?,?,?,NULL)",
            (identifier, upload_key, name, content_type, len(body), digest, time.time()),
        )
        store.db.execute("COMMIT")
    except BaseException:
        if store.db.in_transaction:
            store.db.execute("ROLLBACK")
        temporary.unlink(missing_ok=True)
        target.unlink(missing_ok=True)
        raise
    return _metadata(store.one("SELECT * FROM order_files WHERE id=?", (identifier,)), store)


def discard(store, identifier: str, token: str) -> None:
    """Delete one unclaimed upload when its browser presents the matching capability."""
    if not UPLOAD_ID.fullmatch(identifier or "") or not DISCARD_TOKEN.fullmatch(token or ""):
        raise PermissionError("Choose the design file again.")
    ensure_schema(store)
    target = _directory(store) / identifier
    try:
        store.db.execute("BEGIN IMMEDIATE")
        row = store.one("SELECT id,order_id FROM order_files WHERE id=?", (identifier,))
        expected = _discard_token(store, identifier)
        if row is None or not hmac.compare_digest(expected, token) or row["order_id"] is not None:
            raise PermissionError("Choose the design file again.")
        if target.is_symlink():
            raise PermissionError("Order file custody check failed.")
        target.unlink(missing_ok=True)
        changed = store.db.execute(
            "DELETE FROM order_files WHERE id=? AND order_id IS NULL", (identifier,)
        ).rowcount
        if changed != 1:
            raise PermissionError("Choose the design file again.")
        store.db.execute("COMMIT")
    except BaseException:
        if store.db.in_transaction:
            store.db.execute("ROLLBACK")
        raise


def pending(store, identifier: str) -> dict | None:
    """One unclaimed, unexpired upload with its discard capability, or None."""
    if not isinstance(identifier, str) or not UPLOAD_ID.fullmatch(identifier):
        return None
    ensure_schema(store)
    row = store.one("SELECT * FROM order_files WHERE id=?", (identifier,))
    if not row or row["order_id"] is not None or row["created_at"] < time.time() - PENDING_TTL_SECONDS:
        return None
    return _metadata(row, store)


def read_pending(store, identifier: str) -> bytes:
    """The bytes of one unclaimed upload, after the custody check every stored file passes."""
    if pending(store, identifier) is None:
        raise ValueError("Choose the design file again.")
    row = store.one("SELECT id,name,content_type,size,sha256,order_id FROM order_files WHERE id=?", (identifier,))
    return _resolve(store.path.resolve(strict=True), row)[0].read_bytes()


def read_staged(store, identifier: str) -> tuple[Path, dict]:
    """One stored file by its own id, pending or claimed. The caller holds the capability that names it."""
    if not isinstance(identifier, str) or not UPLOAD_ID.fullmatch(identifier):
        raise ValueError("Unknown order file.")
    ensure_schema(store)
    return _resolve(
        store.path.resolve(strict=True),
        store.one("SELECT id,name,content_type,size,sha256,order_id FROM order_files WHERE id=?", (identifier,)),
    )


# The file a custom line is made from, and the customer's own drawing behind a corrected one.
LINE_UPLOADS = (("upload_id", "file"), ("source_upload_id", "source_file"))


def validate_pending(store, lines: list[dict]) -> None:
    """Reject invented, expired or already claimed upload capabilities before quoting."""
    ensure_schema(store)
    seen: set[str] = set()
    for line in lines:
        for key, _ in LINE_UPLOADS if line.get("kind") == "custom" else ():
            identifier = line.get(key)
            if identifier is None:
                continue
            if not isinstance(identifier, str) or not UPLOAD_ID.fullmatch(identifier) or identifier in seen:
                raise ValueError("Choose the design file again.")
            seen.add(identifier)
            row = store.one("SELECT id,order_id,created_at FROM order_files WHERE id=?", (identifier,))
            if not row or row["order_id"] is not None or row["created_at"] < time.time() - PENDING_TTL_SECONDS:
                raise ValueError("Choose the design file again.")
    if len(seen) > MAX_ORDER_FILES:
        raise ValueError(f"An order can include up to {MAX_ORDER_FILES} design files.")


def claim_line(store, order_id: str, line: dict) -> dict:
    """Claim a line's uploads inside the caller's order transaction and return safe line metadata."""
    presented = [(line.pop(key, None), kept) for key, kept in LINE_UPLOADS]
    for identifier, kept in presented:
        line = _claim(store, order_id, line, identifier, kept)
    return line


def claim_specification(store, order_id, identifier):
    """Retain a customer specification inside the same atomic order transaction."""
    if identifier:
        existing = store.one('SELECT order_id FROM order_files WHERE id=?', (identifier,))
        if not existing or existing['order_id'] != order_id:
            _claim(store, order_id, {}, identifier, 'specification')
        # Recheck durable bytes before completing the order transaction. Only this
        # server-derived metadata becomes the retained specification snapshot.
        try:
            return read_for_customer(store, order_id, identifier)[1]
        except OSError as error:
            raise ValueError('Choose the specification file again.') from error
    return None


def _claim(store, order_id: str, line: dict, identifier, key: str) -> dict:
    if identifier is None:
        return line
    if not isinstance(identifier, str) or not UPLOAD_ID.fullmatch(identifier):
        raise ValueError("Choose the design file again.")
    row = store.one("SELECT * FROM order_files WHERE id=?", (identifier,))
    if not row or row["order_id"] is not None or row["created_at"] < time.time() - PENDING_TTL_SECONDS:
        raise ValueError("Choose the design file again.")
    count = store.one("SELECT COUNT(*) AS n FROM order_files WHERE order_id=?", (order_id,))["n"]
    if count >= MAX_ORDER_FILES:
        raise ValueError(f"An order can include up to {MAX_ORDER_FILES} design files.")
    changed = store.db.execute(
        "UPDATE order_files SET order_id=?,claimed_at=? WHERE id=? AND order_id IS NULL",
        (order_id, datetime.now(timezone.utc).isoformat(), identifier),
    ).rowcount
    if changed != 1:
        raise ValueError("Choose the design file again.")
    line[key] = _metadata(row)
    return line


def list_for_order(store, order_id: str) -> list[dict]:
    try:
        rows = store.rows(
            "SELECT id,name,content_type,size,sha256 FROM order_files WHERE order_id=? ORDER BY created_at,id",
            (order_id,),
        )
    except sqlite3.OperationalError as error:
        if "no such table" in str(error):
            return []
        raise
    return [_metadata(row) for row in rows]


def _resolve(path: Path, row: dict | sqlite3.Row | None) -> tuple[Path, dict]:
    if row is None:
        raise ValueError("Unknown order file.")
    file_path = path.parent / "order-files" / row["id"]
    info = file_path.lstat()
    if not file_path.is_file() or file_path.is_symlink() or info.st_mode & 0o077 or info.st_nlink != 1:
        raise PermissionError("Order file custody check failed.")
    digest = hashlib.sha256()
    with file_path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    if info.st_size != row["size"] or digest.hexdigest() != row["sha256"]:
        raise PermissionError("Order file custody check failed.")
    return file_path, _metadata(row)


def read_for_customer(store, order_id: str, file_id: str) -> tuple[Path, dict]:
    """Resolve a claimed file after the caller has verified the order's customer capability."""
    if not UPLOAD_ID.fullmatch(file_id or "") or not re.fullmatch(r"[a-f0-9]{32}", order_id or ""):
        raise ValueError("Unknown order file.")
    return _resolve(
        store.path.resolve(strict=True),
        store.one(
            "SELECT id,name,content_type,size,sha256 FROM order_files WHERE id=? AND order_id=?",
            (file_id, order_id),
        ),
    )


def read_for_operator(database: Path, company: str, order_id: str, file_id: str) -> tuple[Path, dict]:
    """Resolve bytes only after the native host has admitted a company operator."""
    if not UPLOAD_ID.fullmatch(file_id or "") or not re.fullmatch(r"[a-f0-9]{32}", order_id or ""):
        raise ValueError("Unknown order file.")
    path = Path(database).resolve(strict=True)
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=5) as database_handle:
        database_handle.row_factory = sqlite3.Row
        owner = database_handle.execute("SELECT id FROM company").fetchall()
        if len(owner) != 1 or owner[0]["id"] != company:
            raise PermissionError("Open the bound manufacturer workspace.")
        try:
            row = database_handle.execute(
                "SELECT id,name,content_type,size,sha256 FROM order_files WHERE id=? AND order_id=?",
                (file_id, order_id),
            ).fetchone()
        except sqlite3.OperationalError as error:
            if "no such table" in str(error):
                row = None
            else:
                raise
    return _resolve(path, row)
