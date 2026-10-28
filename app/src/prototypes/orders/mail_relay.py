"""Private HTTPS-to-Gmail relay; OAuth remains with the commissioned local operator."""

from __future__ import annotations

import argparse
import base64
import http.client
import json
import re
from contextlib import suppress
from pathlib import Path
from urllib.parse import urlsplit

from customer_mail import NativeGmail
from mail_transport import (
    COMMANDS,
    MAX_REQUEST_BYTES,
    MAX_RESPONSE_BYTES,
    load_config,
    load_reply_state,
    save_reply_state,
)


class RemoteOutbox:
    def __init__(self, company, authorization, config, connection_factory=None):
        if not re.fullmatch(r"[a-z][a-z0-9-]{1,40}", company):
            raise ValueError("Choose a company slug.")
        if not isinstance(authorization, str) or not 1 <= len(authorization) <= 200:
            raise PermissionError("Record the approved sending authority.")
        self.company, self.authorization = company, authorization
        self.config = Path(config)
        configured = load_config(self.config, company)
        parsed = urlsplit(configured["origin"])
        self.host, self.key = parsed.netloc, configured["key"]
        self.connection_factory = connection_factory or http.client.HTTPSConnection

    def reply_state(self):
        return load_reply_state(self.config)

    def save_reply_state(self, value):
        save_reply_state(self.config, value)

    def call(self, command, mail=None, payload=None):
        if command not in COMMANDS:
            raise ValueError("Use a declared outbox operation.")
        if mail:
            if not re.fullmatch(r"[a-f0-9]{32}", mail):
                raise ValueError("Choose an outbox message ID.")
        body = json.dumps(
            {"command": command, "mail": mail, "payload": payload, "authorization": self.authorization},
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode()
        if len(body) > MAX_REQUEST_BYTES:
            raise ValueError("Keep the remote outbox request within its private transport limit.")
        connection = self.connection_factory(self.host, timeout=30)
        try:
            connection.request(
                "POST",
                f"/{self.company}/rocoto/api/mail-relay",
                body,
                {
                    "Authorization": "Bearer " + self.key,
                    "Content-Type": "application/json",
                    "Content-Length": str(len(body)),
                },
            )
            response = connection.getresponse()
            declared = response.getheader("Content-Length")
            if declared and int(declared) > MAX_RESPONSE_BYTES:
                raise RuntimeError("Remote outbox needs review; retained mail state prevents replay.")
            raw = response.read(MAX_RESPONSE_BYTES + 1)
        finally:
            connection.close()
        if response.status != 200 or len(raw) > MAX_RESPONSE_BYTES:
            raise RuntimeError("Remote outbox needs review; retained mail state prevents replay.")
        try:
            result = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise RuntimeError("Remote outbox needs review; retained mail state prevents replay.") from error
        if not isinstance(result, dict) or result.get("ok") is not True or set(result) != {"ok", "result"}:
            raise RuntimeError("Remote outbox needs review; retained mail state prevents replay.")
        return result["result"]


def relay_one(remote, provider, mail_id):
    prepared = remote.call("prepare", mail_id)
    try:
        receipt = provider.send(base64.urlsafe_b64decode(prepared["raw"]), prepared.get("threadId"))
        settled = remote.call("receipt", mail_id, receipt)
        return {key: settled.get(key) for key in ("id", "state", "provider_id", "provider_thread_id")}
    except BaseException:
        # A durable sending row is held too; preserve the original failure.
        with suppress(Exception):
            remote.call("uncertain", mail_id)
        raise


def reconcile_rows(remote, provider, rows, selected_mail, limit):
    results = []
    selected = [
        row
        for row in rows
        if row["state"] in {"sending", "uncertain"} and (not selected_mail or row["id"] == selected_mail)
    ]
    for row in selected[:limit]:
        receipt = provider.lookup(row["message_id"])
        if receipt:
            settled = remote.call("receipt", row["id"], receipt)
            results.append({"id": row["id"], "state": settled["state"]})
        else:
            remote.call("uncertain", row["id"])
            results.append({"id": row["id"], "state": "uncertain"})
    return results


def sync_reply_rows(remote, provider, rows, limit):
    """Resume a bounded, chronological round-robin pass across provider threads."""
    unique = []
    seen = set()
    for row in rows:
        thread = row.get("provider_thread_id")
        if thread and thread not in seen:
            seen.add(thread)
            unique.append(row)
    if not unique:
        return {"threads_checked": 0, "replies_checked": 0}
    state = remote.reply_state()
    threads = [row["provider_thread_id"] for row in unique]
    start = (threads.index(state["last_thread"]) + 1) % len(threads) if state["last_thread"] in threads else 0
    ordered = unique[start:] + unique[:start]
    visited = recorded = 0
    for row in ordered:
        if visited >= limit or recorded >= limit:
            break
        thread = row["provider_thread_id"]
        replies = list(provider.replies(thread))
        dated = all(str(reply.get("internalDate", "")).isdigit() for reply in replies)
        if replies and not dated and any("SENT" not in reply.get("labelIds", []) for reply in replies):
            raise ValueError("Provider reply chronology requires review.")
        if dated:
            replies.sort(key=lambda reply: int(reply["internalDate"]))
        after = state["after"].get(thread)
        if after:
            position = next((index for index, reply in enumerate(replies) if reply.get("id") == after), None)
            if position is not None:
                replies = replies[position + 1 :]
        for reply in replies:
            identity = reply.get("id")
            if not isinstance(identity, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", identity):
                raise ValueError("Provider reply ID requires review.")
            if "SENT" not in reply.get("labelIds", []):
                remote.call("reply-record", row["id"], reply)
                recorded += 1
            state["after"][thread] = identity
            if recorded >= limit:
                break
        visited += 1
        state["last_thread"] = thread
        remote.save_reply_state(state)
    return {"threads_checked": visited, "replies_checked": recorded}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--company", required=True)
    parser.add_argument("--authorization", required=True)
    parser.add_argument("--relay-config", required=True, type=Path)
    parser.add_argument("--mail")
    parser.add_argument("--limit", type=int, default=1)
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--reconcile", action="store_true")
    parser.add_argument("--sync-replies", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.limit <= 20:
        parser.error("--limit must be 1..20")
    remote = RemoteOutbox(args.company, args.authorization, args.relay_config)
    remote.call("scan")
    rows = remote.call("status")
    if args.status:
        print(json.dumps(rows))
        return
    provider = NativeGmail()
    if args.reconcile:
        for result in reconcile_rows(remote, provider, rows, args.mail, args.limit):
            print(json.dumps(result))
        return
    if args.sync_replies:
        print(json.dumps(sync_reply_rows(remote, provider, rows, args.limit)))
        return
    selected = [
        row
        for row in rows
        if row["state"] == "held" and not row.get("preview") and (not args.mail or row["id"] == args.mail)
    ]
    for row in selected[: args.limit]:
        print(json.dumps(relay_one(remote, provider, row["id"])), flush=True)


if __name__ == "__main__":
    main()
