"""Authenticated HTTPS boundary for the private transactional-mail outbox."""

from __future__ import annotations

import argparse
import hmac
import json
import os
import re
import secrets
import stat
import tempfile
from pathlib import Path

from customer_mail import ORIGIN, CustomerMail, UnrelatedReply
from store import dump, stamp

COMMANDS = frozenset({"scan", "status", "prepare", "receipt", "uncertain", "reply-record"})
MAX_REQUEST_BYTES = 256 * 1024
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
KEY = re.compile(r"[A-Za-z0-9_-]{43}")
MAIL_ID = re.compile(r"[a-f0-9]{32}")
COMPANY = re.compile(r"[a-z][a-z0-9-]{1,40}")
PROVIDER_ID = re.compile(r"[A-Za-z0-9_-]{1,200}")


def _private_text(path: Path) -> str:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise PermissionError("Use a private mail relay credential file.")
    return path.read_text().strip()


def _write_private(path: Path, text: str) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".mail-relay-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as output:
            output.write(text)
            output.flush()
            os.fsync(output.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def server_key_path(store) -> Path:
    return store.path.parent / "mail-relay.key"


def authenticated(store, presented: str) -> bool:
    """Compare a presented machine capability without leaking whether server setup exists."""
    candidate = presented if isinstance(presented, str) and KEY.fullmatch(presented) else "_" * 43
    try:
        expected = _private_text(server_key_path(store))
    except (OSError, PermissionError):
        expected = "!" * 43
    valid = bool(KEY.fullmatch(expected))
    return valid and hmac.compare_digest(expected, candidate)


def load_config(path: Path, company: str) -> dict:
    if not COMPANY.fullmatch(company):
        raise ValueError("Choose a company slug.")
    try:
        value = json.loads(_private_text(path))
    except (OSError, json.JSONDecodeError) as error:
        raise PermissionError("Use the commissioned private mail relay configuration.") from error
    if (
        not isinstance(value, dict)
        or set(value) != {"schema", "origin", "company", "key"}
        or value.get("schema") != 1
        or value.get("origin") != ORIGIN
        or value.get("company") != company
        or not isinstance(value.get("key"), str)
        or not KEY.fullmatch(value["key"])
    ):
        raise PermissionError("Use the commissioned private mail relay configuration.")
    return value


def reply_state_path(config: Path) -> Path:
    return config.with_name(config.name + ".state")


def load_reply_state(config: Path) -> dict:
    path = reply_state_path(config)
    if not path.exists():
        return {"schema": 1, "last_thread": None, "after": {}}
    try:
        value = json.loads(_private_text(path))
    except (OSError, json.JSONDecodeError) as error:
        raise PermissionError("Use the private mail relay reply checkpoint.") from error
    return _validated_reply_state(value)


def _validated_reply_state(value) -> dict:
    last_thread = value.get("last_thread") if isinstance(value, dict) else None
    after = value.get("after") if isinstance(value, dict) else None
    if (
        not isinstance(value, dict)
        or set(value) != {"schema", "last_thread", "after"}
        or value.get("schema") != 1
        or (last_thread is not None and (not isinstance(last_thread, str) or not PROVIDER_ID.fullmatch(last_thread)))
        or not isinstance(after, dict)
        or len(after) > 10000
        or any(
            not isinstance(thread, str)
            or not PROVIDER_ID.fullmatch(thread)
            or not isinstance(message, str)
            or not PROVIDER_ID.fullmatch(message)
            for thread, message in after.items()
        )
    ):
        raise PermissionError("Use the private mail relay reply checkpoint.")
    return value


def save_reply_state(config: Path, value: dict) -> None:
    checked = _validated_reply_state(value)
    _write_private(reply_state_path(config), json.dumps(checked, separators=(",", ":")))


def commission(company: str, config: Path, server_key: Path) -> None:
    """Create matching private local/server capability files without printing the secret."""
    if not COMPANY.fullmatch(company):
        raise ValueError("Choose a company slug.")
    if config.exists() or server_key.exists():
        raise FileExistsError("Relay capability files already exist; use an explicit rotation procedure.")
    key = secrets.token_urlsafe(32)
    if not KEY.fullmatch(key):  # pragma: no cover - token_urlsafe(32) is defined to be 43 URL-safe chars
        raise RuntimeError("Unable to create a mail relay capability.")
    _write_private(config, json.dumps({"schema": 1, "origin": ORIGIN, "company": company, "key": key}))
    _write_private(server_key, key + "\n")


def dispatch(store, command: str, mail_id, payload, authorization: str):
    """Execute the existing outbox operations, and nothing else."""
    if command not in COMMANDS:
        raise ValueError("Use a declared outbox operation.")
    if not isinstance(authorization, str) or not 1 <= len(authorization) <= 200:
        raise PermissionError("Record the approved sending authority.")
    needs_mail = command in {"prepare", "receipt", "uncertain", "reply-record"}
    if needs_mail and (not isinstance(mail_id, str) or not MAIL_ID.fullmatch(mail_id)):
        raise ValueError("Choose an outbox message ID.")
    if not needs_mail and mail_id is not None:
        raise ValueError("This outbox operation does not take a message ID.")
    if command in {"scan", "status", "prepare", "uncertain"} and payload is not None:
        raise ValueError("This outbox operation does not take a payload.")
    mail = CustomerMail(store, ORIGIN)
    if command == "scan":
        mail.sync_events()
        return {"synced": True}
    if command == "status":
        return mail.status()
    if command == "prepare":
        return mail.prepare(mail_id, authorization)
    if command == "receipt":
        return mail.settle(mail_id, payload, authorization)
    if command == "uncertain":
        mail.uncertain(mail_id)
        return {"id": mail_id, "state": "uncertain"}
    if not isinstance(payload, dict):
        raise ValueError("Record one provider reply object.")
    row = store.one("SELECT order_id FROM mail_outbox WHERE id=?", (mail_id,))
    if not row:
        raise ValueError("Unknown email.")
    try:
        mail.record_reply(row["order_id"], payload)
    except UnrelatedReply:
        provider_id = payload.get("id")
        store.db.execute(
            "INSERT INTO mail_events(mail_id,kind,data,created_at) VALUES(?,?,?,?)",
            (
                mail_id,
                "reply-skipped",
                dump(
                    {
                        "provider_id": provider_id
                        if isinstance(provider_id, str) and PROVIDER_ID.fullmatch(provider_id)
                        else "unverified",
                        "reason": "sender-mismatch",
                    }
                ),
                stamp(),
            ),
        )
        return {"id": mail_id, "recorded": False, "skipped": "sender-mismatch"}
    return {"id": mail_id, "recorded": True}


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare a private HTTPS mail-relay capability pair.")
    parser.add_argument("commission", choices=["commission"])
    parser.add_argument("--company", required=True)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--server-key", required=True, type=Path)
    args = parser.parse_args()
    commission(args.company, args.config, args.server_key)


if __name__ == "__main__":
    main()
