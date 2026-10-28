#!/usr/bin/env python3
"""The orders preview's server: the built pages, and the capped address search beside them.

    python3 serve.py --root <built folder> --port <port> [--state <directory>] [--log]

Serves the folder `build_preview.py` writes, on the loopback address only; the host's Caddy route
is the public door. Standard library only. Every answer carries `X-Robots-Tag: noindex, nofollow`.

  /healthz                                  "ok", for the unit's health check
  /<company>/rocoto/api/places?q=&session=&lang=    address suggestions, as JSON
  /<company>/rocoto/api/place?id=&session=&lang=    one chosen address with its coordinates
  /<company>/rocoto/api/here?lat=&lng=&lang=         the address at the customer's own position
  /<company>/rocoto/api/mail-relay                  authenticated private outbox operations
  /<company>/rocoto/api/laser                       POST {"upload": id}: an uploaded drawing read for laser cutting
  /<company>/rocoto/api/laser/<id>                  that reading again; /fixed.dxf is its corrected drawing
  anything else                             a file under the root; a folder answers with its index.html

The two `api` routes are the only ones that call out, through places.py and its ceilings. They
answer {"ok": true, ...} or {"ok": false, "reason": "cap|off|key|rate|short|upstream"}; the page
shows its plain address fields for every refusal. `--state` holds the call ledger; with it absent
the address search answers `off`.
"""
from __future__ import annotations

import argparse
import json
import os
import posixpath
import re
import sqlite3
import sys
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
import configurator_versions  # noqa: E402
import customer_details  # noqa: E402
import customer_mail  # noqa: E402
import customer_page  # noqa: E402
import laser  # noqa: E402
import laser_quote  # noqa: E402
import mail_transport  # noqa: E402
import order_assistant  # noqa: E402
import order_files  # noqa: E402
import propose  # noqa: E402
import quote as pricing_quote  # noqa: E402
import spec  # noqa: E402
from public_catalogue import for_site as public_catalogue_for_site  # noqa: E402
from store import CompanyStore  # noqa: E402
from supply import public_ready, quote_ready  # noqa: E402

import places  # noqa: E402

TYPES = {
    ".html": "text/html; charset=utf-8", ".htm": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8", ".mjs": "text/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8", ".txt": "text/plain; charset=utf-8",
    ".xml": "application/xml; charset=utf-8", ".svg": "image/svg+xml", ".png": "image/png",
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp",
    ".avif": "image/avif", ".ico": "image/x-icon", ".woff": "font/woff", ".woff2": "font/woff2",
    ".ttf": "font/ttf", ".otf": "font/otf", ".eot": "application/vnd.ms-fontobject", ".mp4": "video/mp4",
    ".webm": "video/webm", ".pdf": "application/pdf", ".map": "application/json; charset=utf-8",
}
FRESH = (".html", ".htm", ".json", ".js")            # asked for again on every visit
SLUG = re.compile(r"[a-z][a-z0-9-]{1,40}")
API = re.compile(r"/([a-z][a-z0-9-]{1,40})/rocoto/api/(places|place|here)")
COMPANY_API = re.compile(r"/([a-z][a-z0-9-]{1,40})/rocoto/api/(supply|quote|orders|claims|manage|uploads|laser|spec|propose)")
LASER_READ = re.compile(r"/([a-z][a-z0-9-]{1,40})/rocoto/api/laser/([a-f0-9]{32})(/fixed\.dxf)?")
LASER_PER_MINUTE = 12                                # drawings one client may have read in a minute
MAIL_RELAY = re.compile(r"/([a-z][a-z0-9-]{1,40})/rocoto/api/mail-relay")
UPLOAD_DELETE = re.compile(
    r"/([a-z][a-z0-9-]{1,40})/rocoto/api/uploads/([a-f0-9]{32})"
)
CUSTOMER_FILE = re.compile(
    r"/([a-z][a-z0-9-]{1,40})/rocoto/api/manage/orders/([a-f0-9]{32})/files/([a-f0-9]{32})"
)
PLATFORM = re.compile(r"/([a-z][a-z0-9-]{1,40})/rocoto/api/(configurator-version|platform-state|platform-orders)")
CONFIGURATOR = re.compile(r"/([a-z][a-z0-9-]{1,40})/rocoto/configurator\.js")
CATALOG = re.compile(r"/([a-z][a-z0-9-]{1,40})/rocoto/catalog.json")
RANGE = re.compile(r"bytes=(\d*)-(\d*)")
NOT_FOUND = (b"<!doctype html><meta charset=utf-8><meta name=robots content=noindex,nofollow>"
             b"<title>Rocoto order pages</title><body style=\"font-family:system-ui;margin:3rem\">"
             b"<h1 style=\"font-weight:600\">Rocoto order pages</h1><p>This address holds no page.</p>")


def content_type(path: Path) -> str:
    return TYPES.get(path.suffix.lower(), "application/octet-stream")


def locate(root: Path, url_path: str) -> Path | None:
    """The file a URL path names under the root, or None. A path that climbs out is refused."""
    path = unquote(url_path)
    if "\x00" in path or "\\" in path:
        return None
    parts = [part for part in path.split("/") if part]
    if any(part in (".", "..") for part in parts):
        return None
    target = root.joinpath(*parts) if parts else root
    try:
        resolved = target.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError):
        return None
    return resolved


class Handler(BaseHTTPRequestHandler):
    server_version = "RocotoOrders"
    sys_version = ""
    protocol_version = "HTTP/1.1"
    timeout = 30
    root: Path
    service: places.Places
    logging = False
    state: Path | None = None
    rate_lock = threading.Lock()
    requests: dict = {}
    relay_requests: dict = {}
    relay_failures: dict = {}
    laser_requests: dict = {}
    assistant_requests: dict = {}
    assistant: order_assistant.Assistant
    bridge: configurator_versions.Bridge

    def json_answer(self, status: int, body: dict) -> None:
        self.answer(status, json.dumps(body, ensure_ascii=False, allow_nan=False).encode(),
                    TYPES[".json"], {"Cache-Control": "no-store"})

    def company_store(self, company: str) -> CompanyStore:
        if self.state is None or not (self.root / company / "rocoto/site.json").is_file():
            raise ValueError("The company order service is being prepared.")
        path = self.state / "companies" / company / "company.db"
        if not path.is_file():
            raise ValueError("The company order service is being prepared.")
        return CompanyStore(path)

    def public_catalogue(self, store: CompanyStore, company: str) -> dict:
        active = self.bridge.active(company)
        if active:
            return configurator_versions.catalogue(active['document'])
        return public_catalogue_for_site(store.export_catalog(), self.root / company / "rocoto")

    def company_config(self, store, company):
        active = self.bridge.active(company)
        return active['document']['configuration'] if active else json.loads(store.one("SELECT config FROM company")["config"])

    def site(self, company: str) -> dict:
        """What the build wrote about this company; empty when the company is unknown."""
        try:
            about = json.loads((self.root / company / "rocoto" / "site.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return about if isinstance(about, dict) else {}

    def laser_block(self, company: str) -> dict | None:
        """The company's laser cutting: materials and tariff. None when it offers none."""
        try:
            return laser_quote.block(self.site(company).get("laser"))
        except ValueError:
            return None

    def allow_request(self) -> bool:
        return self._allow(self.requests, self.client(), 30)

    def allow_relay_request(self, company: str, authenticated: bool) -> bool:
        bucket = self.relay_requests if authenticated else self.relay_failures
        return self._allow(bucket, (company, self.client()), 60 if authenticated else 15)

    def _allow(self, bucket: dict, client, limit: int) -> bool:
        now = time.monotonic()
        with self.rate_lock:
            for key in list(bucket):
                if bucket[key][-1] < now - 60:
                    del bucket[key]
            entries = [stamp for stamp in bucket.get(client, []) if stamp > now - 60]
            if len(entries) >= limit or len(bucket) >= 10000:
                return False
            bucket[client] = entries + [now]
        return True

    def platform_api(self, company, action):
        def error(status, message):
            # Native clients consume detail; existing Orders clients consume message.
            message = message[:240]
            return self.json_answer(status, {'ok': False, 'message': message, 'detail': message})

        if not self.bridge.authorized(company, self.headers.get('Authorization', ''), self.headers.get('X-Rocoto-Company', '')):
            return error(403, 'Use the connected company platform.')
        if not self._allow(self.relay_requests, ('platform', company, self.client()), 180):
            return error(429, 'Please try again in a minute.')
        store = None
        try:
            store = self.company_store(company)
            owner = store.one('SELECT id FROM company')
            if owner is None or owner['id'] != company:
                return error(403, 'Use the connected company platform.')
            if action == 'platform-orders' and self.command == 'POST':
                import platform_orders
                size = int(self.headers.get('Content-Length', '0'))
                if self.headers.get('Content-Type', '').split(';')[0].strip() != 'application/json' or not 1 <= size <= platform_orders.MAX_REQUEST_BYTES:
                    self.close_connection = True
                    raise ValueError('Choose an order with a document up to 4 MB.')
                def invalid_number(value):
                    raise ValueError('Enter valid quantities.')
                value = json.loads(self.rfile.read(size), parse_constant=invalid_number)
                result, replay = platform_orders.create(store, value, self.public_catalogue(store, company), self.company_config(store, company))
                return self.json_answer(200 if replay else 201, result)
            if action == 'configurator-version' and self.command == 'POST':
                size = int(self.headers.get('Content-Length', '0'))
                if self.headers.get('Content-Type', '').split(';')[0] != 'application/json' or not 1 <= size <= configurator_versions.MAX_BYTES + 50000:
                    self.close_connection = True
                    raise ValueError('Publish a bounded JSON snapshot.')
                value = json.loads(self.rfile.read(size))
                if not isinstance(value, dict):
                    raise ValueError('Publish a saved configuration object.')
                document = (value.get('version') or {}).get('document')
                configurator_versions.validate(document, company)
                known = {row['id'] for row in store.rows('SELECT id FROM items WHERE active=1')}
                requested = {item['c'] for category in document['catalogue'].get('cats', []) for item in category['items']}
                if requested - known:
                    raise ValueError('Register new source-backed articles in the company catalogue before publishing this version.')
                configurator_versions.catalogue(document)
                return self.json_answer(200, self.bridge.publish(company, value))
            if action == 'platform-state' and self.command == 'GET':
                from platform_source import file_for_order, read
                query = parse_qs(urlsplit(self.path).query)
                resource = (query.get('resource') or ['company'])[0]
                order_id = (query.get('id') or [''])[0]
                if resource == 'file':
                    path, metadata = file_for_order(store, order_id, (query.get('file_id') or [''])[0])
                    return self.answer(200, path.read_bytes(), 'application/octet-stream', {
                        'Cache-Control': 'private, no-store',
                        'Content-Disposition': "attachment; filename*=UTF-8''" + quote(metadata['name'], safe=''),
                        'X-File-Content-Type': metadata['content_type'],
                        'X-Content-SHA256': metadata['sha256'],
                        'Content-Security-Policy': "default-src 'none'; sandbox",
                    })
                active = self.bridge.active(company)
                result = read(store, resource,
                              order_id=order_id, limit=int((query.get('limit') or ['100'])[0]),
                              offset=int((query.get('offset') or ['0'])[0]),
                              document=active['document'] if active else None)
                return self.json_answer(200, {'ok': True, **result})
            return self.json_answer(405, {'ok': False})
        except LookupError:
            return error(404, 'Choose a company order.')
        except configurator_versions.Conflict as exc:
            return error(409, str(exc))
        except (ValueError, TypeError, KeyError) as exc:
            return error(400, str(exc))
        except (OSError, sqlite3.Error):
            return error(503, 'The company platform is reconnecting.')
        finally:
            if store:
                store.close()

    def do_POST(self) -> None:  # noqa: N802
        platform = PLATFORM.fullmatch(urlsplit(self.path).path)
        if platform:
            return self.platform_api(*platform.groups())
        relay = MAIL_RELAY.fullmatch(urlsplit(self.path).path)
        if relay:
            return self.relay_api(relay.group(1))
        route = COMPANY_API.fullmatch(urlsplit(self.path).path)
        if not route or route.group(2) == "supply":
            return self.refuse()
        action = route.group(2)
        named = action == "laser"                    # the laser check names a reason with every refusal
        origin = self.headers.get("Origin")
        if (origin and urlsplit(origin).netloc != self.headers.get("Host")) or self.headers.get("Sec-Fetch-Site") == "cross-site":
            return self.json_answer(403, {"ok": False, **({"reason": "request"} if named else {}),
                                          "message": "Submit from the company order page."})
        if not self.allow_request():
            return self.json_answer(429, {"ok": False, **({"reason": "rate"} if named else {}),
                                          "message": "Please try again in a minute."})
        store = None
        if action == "laser":
            return self.laser_check(route.group(1))
        if action == "uploads":
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 1 <= size <= order_files.MAX_UPLOAD_BYTES:
                    self.close_connection = True
                    raise ValueError("Choose a design file up to 15 MB.")
                encoded_name = self.headers.get("X-File-Name", "")
                if len(encoded_name) > 720:
                    raise ValueError("Use a shorter design file name.")
                filename = unquote(encoded_name)
                key = self.headers.get("Idempotency-Key", "")
                store = self.company_store(route.group(1))
                upload = order_files.stage(store, filename, self.rfile.read(size), key)
                return self.json_answer(201, {"ok": True, "upload": upload})
            except (ValueError, TypeError, KeyError) as exc:
                return self.json_answer(400, {"ok": False, "message": str(exc)[:240]})
            except sqlite3.Error:
                return self.json_answer(503, {"ok": False, "message": "The order service is busy. Please try again."})
            finally:
                if store is not None:
                    store.close()
        if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
            return self.json_answer(415, {"ok": False, "message": "Use the order form."})
        try:
            size = int(self.headers.get("Content-Length", "0"))
            maximum = 512 * 1024 if action == 'orders' else 65536
            if not 1 <= size <= maximum:
                raise ValueError(f"Keep the order request within {maximum // 1024} KB.")
            def invalid_number(value):
                raise ValueError("Use finite numeric quantities.")
            data = json.loads(self.rfile.read(size), parse_constant=invalid_number)
            if not isinstance(data, dict):
                raise ValueError("Use an order request object.")
            store = self.company_store(route.group(1))
            if action in ("spec", "propose"):
                if not self._allow(self.assistant_requests, (route.group(1), self.client()), 8):
                    return self.json_answer(429, {"ok": False, "message": "Please try again in a minute."})
                config = self.company_config(store, route.group(1))
                picker_path = self.root / route.group(1) / "rocoto/picker.json"
                if picker_path.is_file():
                    config["picker"] = json.loads(picker_path.read_text())
                catalogue = self.public_catalogue(store, route.group(1))
                if action == "spec":
                    result = spec.read(data, catalogue, config, store=store, assistant=self.assistant, demo=route.group(1) == "sample-hardware")
                    import spec_receipts
                    result = spec_receipts.record(store, data, result)
                else:
                    result = propose.read(data, catalogue, config, assistant=self.assistant if config.get('checkout', {}).get('proposalNarration', True) else None)
                return self.json_answer(200, result)
            if action == "manage":
                customer = customer_mail.CustomerMail(store)
                authorization = self.headers.get("Authorization", "")
                token = authorization[7:] if authorization.startswith("Bearer ") else ""
                order_id = data.get("order_id", "")
                if not isinstance(order_id, str) or len(order_id) > 64:
                    raise PermissionError("Open the private link from your order email.")
                if data.get("action") == "read":
                    return self.json_answer(200, {"ok": True, "order": customer.projection(order_id, token)})
                result = customer.change(
                    order_id,
                    token,
                    data.get("action"),
                    data.get("body", ""),
                    data.get("idempotency_key"),
                    data.get("review_id"),
                )
                return self.json_answer(200, {"ok": True, **result})
            actor, evidence = "public-order-page", "company order form"
            key = self.headers.get("Idempotency-Key", "")
            if action != "quote" and not re.fullmatch(r"[A-Za-z0-9_-]{16,128}", key):
                raise ValueError("Refresh the form and try again.")
            request = {"lines": data.get("lines"), "customer": data.get("customer"),
                       "fulfilment": data.get("fulfilment", "pickup")}
            if action == "orders":
                replayed = store.replay("orders.submit", {"request": request}, actor, key)
                if replayed is not None:
                    if not store.read_order(replayed["id"])["customer"].get("is_demo"):
                        customer_mail.CustomerMail(store).queue(replayed["id"])
                    replayed = {**replayed, "ready": public_ready(replayed["ready"])}
                    return self.json_answer(200, {"ok": True, **replayed})
            if action == "claims":
                email, name = data.get("email", ""), data.get("name", "")
                if not isinstance(email, str) or not re.fullmatch(r"[^\s@]{1,64}@[^\s@]{1,190}\.[^\s@]{2,24}", email):
                    raise ValueError("Enter your company email address.")
                if not isinstance(name, str) or not 1 <= len(name.strip()) <= 200:
                    raise ValueError("Enter your name.")
                result = store.request_claim(email, name.strip(), actor, evidence, key)
            else:
                catalogue = self.public_catalogue(store, route.group(1))
                about, buyer = self.site(route.group(1)), data.get("customer")
                language = buyer.get("language") if isinstance(buyer, dict) else None
                if language not in ("bg", "en"):
                    spoken = about.get("languages")
                    language = spoken[0] if isinstance(spoken, list) and spoken else "en"
                cutting = self.laser_block(route.group(1))
                priced = pricing_quote.quote(
                    catalogue,
                    data.get("lines"),
                    laser=lambda chosen: laser.order_line(
                        store, cutting, chosen, language, currency=catalogue["currency"], vat=catalogue["vat"]
                    ),
                )
                order_files.validate_pending(store, priced["lines"])
                ready = quote_ready(store, priced["lines"])
                priced["quote"]["ready"] = public_ready(ready)
                if action == "quote":
                    return self.json_answer(200, {"ok": True, **priced, "ready": public_ready(ready)})
                config = self.company_config(store, route.group(1))
                customer = customer_details.validate(data.get("customer"), config)
                customer = spec.validate_demo_order(store, customer, config)
                import spec_receipts
                customer = spec_receipts.validate(store, customer, priced["lines"])
                fulfilment = data.get("fulfilment", "pickup")
                if fulfilment not in ("pickup", "delivery"):
                    raise ValueError("Choose pickup or delivery.")
                priced["quote"]["fulfilment"] = fulfilment
                result = store.submit_order(customer, priced["lines"], priced["quote"], key, actor, evidence,
                                            request=request)
                if not customer.get("is_demo"):
                    customer_mail.CustomerMail(store).queue(result["id"])
                result = {**result, "ready": public_ready(result["ready"])}
            return self.json_answer(201, {"ok": True, **result})
        except PermissionError:
            return self.json_answer(403, {"ok": False, "message": "Open the private link from your order email."})
        except (ValueError, TypeError, KeyError) as exc:
            return self.json_answer(400, {"ok": False, "message": str(exc)[:240]})
        except sqlite3.Error:
            return self.json_answer(503, {"ok": False, "message": "The order service is busy. Please try again."})
        finally:
            if store is not None:
                store.close()

    def laser_check(self, company: str) -> None:
        """Read one uploaded drawing for laser cutting. Every refusal names its reason."""
        store = None
        try:
            if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
                self.close_connection = True
                return self.json_answer(415, {"ok": False, "reason": "request", "message": "Use the order form."})
            size = int(self.headers.get("Content-Length", "0"))
            if not 1 <= size <= 4096:
                self.close_connection = True
                raise ValueError("Keep the laser request within 4 KB.")
            data = json.loads(self.rfile.read(size))
            if not isinstance(data, dict):
                raise ValueError("Use a laser request object.")
            block = self.laser_block(company)
            if block is None:
                raise laser.Refusal("off")
            if not self._allow(self.laser_requests, self.client(), LASER_PER_MINUTE):
                raise laser.Refusal("rate")
            try:
                store = self.company_store(company)
            except ValueError:
                raise laser.Refusal("off") from None
            return self.json_answer(200, laser.check(store, block, data.get("upload")))
        except laser.Refusal as refusal:
            return self.json_answer(refusal.status, refusal.body())
        except (ValueError, TypeError, KeyError) as exc:
            return self.json_answer(400, {"ok": False, "reason": "request", "message": str(exc)[:240]})
        except (OSError, sqlite3.Error):
            return self.json_answer(
                503, {"ok": False, "reason": "busy", "message": "The order service is busy. Please try again."}
            )
        finally:
            if store is not None:
                store.close()

    def laser_read(self, company: str, identifier: str, corrected: bool) -> None:
        """An earlier reading again, or its corrected drawing as a download. The id is the capability."""
        store = None
        try:
            block = self.laser_block(company)
            if block is None:
                raise laser.Refusal("off")
            if not self.allow_request():
                raise laser.Refusal("rate")
            try:
                store = self.company_store(company)
            except ValueError:
                raise laser.Refusal("off") from None
            if not corrected:
                return self.json_answer(200, laser.reread(store, block, identifier))
            path, metadata = laser.corrected_file(store, identifier)
            return self.answer(
                200,
                path.read_bytes(),
                "application/octet-stream",
                {
                    "Cache-Control": "private, no-store",
                    "Content-Disposition": "attachment; filename*=UTF-8''" + quote(metadata["name"], safe=""),
                    "X-Content-SHA256": metadata["sha256"],
                },
            )
        except laser.Refusal as refusal:
            return self.json_answer(refusal.status, refusal.body())
        except (ValueError, PermissionError, OSError):
            return self.json_answer(404, {"ok": False, "reason": "upload", "message": laser.MESSAGE["upload"]})
        except sqlite3.Error:
            return self.json_answer(
                503, {"ok": False, "reason": "busy", "message": "The order service is busy. Please try again."}
            )
        finally:
            if store is not None:
                store.close()

    def relay_api(self, company: str) -> None:
        """Run only authenticated outbox operations for the private dev relay."""
        if self.headers.get("Origin") or self.headers.get("Sec-Fetch-Site"):
            self.close_connection = True
            return self.json_answer(403, {"ok": False, "message": "Private relay authentication required."})
        store = None
        try:
            store = self.company_store(company)
            authorization = self.headers.get("Authorization", "")
            token = authorization[7:] if authorization.startswith("Bearer ") else ""
            if not mail_transport.authenticated(store, token):
                self.close_connection = True
                if not self.allow_relay_request(company, False):
                    return self.json_answer(429, {"ok": False, "message": "Please try again in a minute."})
                raise PermissionError("Private relay authentication required.")
            if not self.allow_relay_request(company, True):
                return self.json_answer(429, {"ok": False, "message": "Please try again in a minute."})
            if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
                return self.json_answer(415, {"ok": False, "message": "Use the private relay client."})
            size = int(self.headers.get("Content-Length", "0"))
            if not 1 <= size <= mail_transport.MAX_REQUEST_BYTES:
                self.close_connection = True
                raise ValueError("Keep the private relay request within its transport limit.")
            data = json.loads(self.rfile.read(size))
            if not isinstance(data, dict) or set(data) != {"command", "mail", "payload", "authorization"}:
                raise ValueError("Use one declared private relay operation.")
            result = mail_transport.dispatch(
                store, data["command"], data["mail"], data["payload"], data["authorization"]
            )
            response = json.dumps(
                {"ok": True, "result": result}, ensure_ascii=False, allow_nan=False, separators=(",", ":")
            ).encode()
            if len(response) > mail_transport.MAX_RESPONSE_BYTES:
                if data["command"] == "prepare" and isinstance(data["mail"], str):
                    customer_mail.CustomerMail(store).uncertain(
                        data["mail"], "Private relay response exceeded its transport limit"
                    )
                raise ValueError("Private relay response exceeds its transport limit.")
            return self.answer(200, response, TYPES[".json"], {"Cache-Control": "no-store"})
        except PermissionError:
            return self.json_answer(403, {"ok": False, "message": "Private relay authentication required."})
        except (ValueError, TypeError, KeyError, json.JSONDecodeError) as error:
            return self.json_answer(400, {"ok": False, "message": str(error)[:240]})
        except (OSError, sqlite3.Error):
            return self.json_answer(503, {"ok": False, "message": "The private relay is busy."})
        finally:
            if store is not None:
                store.close()

    def do_DELETE(self) -> None:  # noqa: N802
        route = UPLOAD_DELETE.fullmatch(urlsplit(self.path).path)
        if route is None:
            return self.refuse()
        origin = self.headers.get("Origin")
        if (origin and urlsplit(origin).netloc != self.headers.get("Host")) or self.headers.get(
            "Sec-Fetch-Site"
        ) == "cross-site":
            return self.json_answer(403, {"ok": False, "message": "Submit from the company order page."})
        if not self.allow_request():
            return self.json_answer(429, {"ok": False, "message": "Please try again in a minute."})
        store = None
        try:
            store = self.company_store(route.group(1))
            order_files.discard(store, route.group(2), self.headers.get("Upload-Capability", ""))
            return self.json_answer(200, {"ok": True})
        except PermissionError:
            return self.json_answer(403, {"ok": False, "message": "Choose the design file again."})
        except (OSError, ValueError, sqlite3.Error):
            return self.json_answer(
                503, {"ok": False, "message": "The order service is busy. Please try again."}
            )
        finally:
            if store is not None:
                store.close()

    def log_message(self, format, *args):  # noqa: A002 - the base class names it
        if self.logging:
            super().log_message(format, *args)

    def answer(self, status: int, body: bytes, kind: str, extra: dict | None = None, total: int | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body) if total is None else total))
        self.send_header("X-Robots-Tag", "noindex, nofollow")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        for name, value in (extra or {}).items():
            self.send_header(name, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def client(self) -> str:
        """Who is asking. Behind the host's proxy that is the last address it appended."""
        forwarded = self.headers.get("X-Forwarded-For", "")
        if forwarded and self.client_address[0] in ("127.0.0.1", "::1"):
            return forwarded.split(",")[-1].strip()[:64] or self.client_address[0]
        return self.client_address[0]

    def api(self, company: str, route: str, query: dict) -> None:
        def one(name: str) -> str:
            return (query.get(name) or [""])[0]

        described = self.root / company / "rocoto" / "site.json"
        try:
            if not described.is_file():
                raise places.Refusal("off")
            about = json.loads(described.read_text(encoding="utf-8"))
            language = one("lang") if one("lang") in about.get("languages", []) else "en"
            if route == "places":
                geo = about.get("geo")
                near = re.fullmatch(r"(-?\d{1,2}(?:\.\d{1,6})?),(-?\d{1,3}(?:\.\d{1,6})?)", one("near"))
                if near and abs(float(near[1])) <= 90 and abs(float(near[2])) <= 180:
                    # the customer's own position, when they share it, brings nearby streets first
                    geo = {**(geo or {}), "origin": {"lat": float(near[1]), "lng": float(near[2])}}
                body = self.service.suggestions(one("q"), one("session"), language, self.client(), geo)
            elif route == "here":
                try:
                    latitude, longitude = float(one("lat")), float(one("lng"))
                except ValueError:
                    raise places.Refusal("short") from None
                body = self.service.here(latitude, longitude, language, self.client())
            else:
                body = self.service.place(one("id"), one("session"), language, self.client())
            status = 200
        except places.Refusal as refusal:
            body, status = {"ok": False, "reason": refusal.reason}, refusal.status
        self.answer(status, json.dumps(body, ensure_ascii=False).encode(), TYPES[".json"], {"Cache-Control": "no-store"})

    def do_GET(self) -> None:  # noqa: N802 - the base class names it
        url = urlsplit(self.path)
        platform = PLATFORM.fullmatch(url.path)
        if platform:
            return self.platform_api(*platform.groups())
        configurator = CONFIGURATOR.fullmatch(url.path)
        if configurator:
            active = self.bridge.active(configurator.group(1))
            if active:
                found = locate(self.root, url.path)
                if found and found.is_file():
                    script = configurator_versions.script(found.read_text(), active['document'])
                    return self.answer(200, script.encode(), TYPES['.js'], {'Cache-Control': 'no-store',
                                       'X-Configurator-Version': active['id'], 'X-Configurator-SHA256': active['sha256']})
        if url.path == "/healthz":
            return self.answer(200, b"ok\n", TYPES[".txt"], {"Cache-Control": "no-store"})
        customer_file = CUSTOMER_FILE.fullmatch(url.path)
        if customer_file:
            store = None
            try:
                store = self.company_store(customer_file.group(1))
                authorization = self.headers.get("Authorization", "")
                token = authorization[7:] if authorization.startswith("Bearer ") else ""
                customer_mail.CustomerMail(store).projection(customer_file.group(2), token)
                path, metadata = order_files.read_for_customer(
                    store, customer_file.group(2), customer_file.group(3)
                )
                disposition = "attachment; filename*=UTF-8''" + quote(metadata["name"], safe="")
                return self.answer(
                    200,
                    path.read_bytes(),
                    "application/octet-stream",
                    {
                        "Cache-Control": "private, no-store",
                        "Content-Disposition": disposition,
                        "X-Content-SHA256": metadata["sha256"],
                    },
                )
            except PermissionError:
                return self.json_answer(403, {"ok": False, "message": "Open the private link from your order email."})
            except (ValueError, OSError):
                return self.json_answer(404, {"ok": False, "message": "Unknown order file."})
            finally:
                if store is not None:
                    store.close()
        manage = re.fullmatch(r"/([a-z][a-z0-9-]{1,40})/manage/", url.path)
        if manage and (self.root / manage.group(1) / "rocoto/site.json").is_file():
            company = manage.group(1)
            about = json.loads((self.root / company / "rocoto/site.json").read_text())
            try:
                store = self.company_store(company)
                try:
                    about = json.loads(store.one("SELECT config FROM company")["config"])
                finally:
                    store.close()
            except ValueError:
                pass
            logo = about.get("logos", {}).get("en", about.get("logo", "/_public/images/logo_en.png"))
            return self.answer(200, customer_page.page(company, f"/{company}/{logo.lstrip('/')}", about),
                               TYPES[".html"], {"Cache-Control": "no-store", "Content-Security-Policy":
                               "default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'"})
        drawing = LASER_READ.fullmatch(url.path)
        if drawing:
            return self.laser_read(drawing.group(1), drawing.group(2), bool(drawing.group(3)))
        company_api = COMPANY_API.fullmatch(url.path)
        if company_api:
            if company_api.group(2) != "supply":
                return self.json_answer(405, {"ok": False})
            store = None
            try:
                store = self.company_store(company_api.group(1))
                public = self.public_catalogue(store, company_api.group(1))
                item_ids = {item["c"] for category in public["cats"] for item in category["items"]}
                supply = store.public_supply_projection()
                supply["items"] = {
                    item_id: value for item_id, value in supply["items"].items() if item_id in item_ids
                }
                return self.json_answer(200, supply)
            except ValueError:
                return self.json_answer(503, {"ok": False, "message": "The company order service is being prepared."})
            finally:
                if store is not None:
                    store.close()
        live_catalog = CATALOG.fullmatch(url.path)
        if live_catalog and self.state:
            store = None
            try:
                store = self.company_store(live_catalog.group(1))
                return self.json_answer(
                    200,
                    self.public_catalogue(store, live_catalog.group(1)),
                )
            except ValueError:
                pass
            finally:
                if store is not None:
                    store.close()
        route = API.fullmatch(url.path)
        if route:
            return self.api(route.group(1), route.group(2), parse_qs(url.query))
        found = locate(self.root, url.path)
        if found is not None and found.is_dir():
            if not url.path.endswith("/"):
                where = posixpath.normpath(url.path) + "/" + (f"?{url.query}" if url.query else "")
                return self.answer(HTTPStatus.MOVED_PERMANENTLY, b"", TYPES[".txt"], {"Location": where})
            found = found / "index.html"
        if found is None or not found.is_file():
            return self.answer(404, NOT_FOUND, TYPES[".html"], {"Cache-Control": "no-store"})
        size = found.stat().st_size
        headers = {"Accept-Ranges": "bytes",
                   "Cache-Control": "no-cache" if found.suffix.lower() in FRESH else "public, max-age=3600"}
        start, end, status = 0, size - 1, 200
        wanted = RANGE.fullmatch(self.headers.get("Range", "").strip())
        if wanted and (wanted.group(1) or wanted.group(2)) and size:
            if wanted.group(1):
                start, end = int(wanted.group(1)), min(int(wanted.group(2) or size - 1), size - 1)
            else:
                start = max(size - int(wanted.group(2)), 0)
            if start > end or start >= size:
                return self.answer(416, b"", content_type(found), {"Content-Range": f"bytes */{size}"})
            status, headers["Content-Range"] = 206, f"bytes {start}-{end}/{size}"
        length = end - start + 1 if size else 0
        self.answer(status, b"", content_type(found), headers, total=length)
        if self.command == "HEAD" or not length:
            return
        with found.open("rb") as stream:
            stream.seek(start)
            left = length
            while left > 0:
                chunk = stream.read(min(64 * 1024, left))
                if not chunk:
                    break
                self.wfile.write(chunk)
                left -= len(chunk)

    do_HEAD = do_GET  # noqa: N815

    def refuse(self) -> None:
        self.answer(405, b"", TYPES[".txt"], {"Allow": "GET, HEAD", "Connection": "close"})
        self.close_connection = True

    do_PUT = do_PATCH = do_OPTIONS = refuse  # noqa: N815


def server(root: Path, port: int, state: Path | None = None, *, service: places.Places | None = None,
           logging: bool = False, host: str = "127.0.0.1", assistant=None, bridge=None) -> ThreadingHTTPServer:
    """Loopback by default; an explicit private host enables a tailnet preview."""
    root = root.resolve()
    if not root.is_dir():
        raise SystemExit(f"{root} is missing: build it with build_preview.py")
    handler = type("OrdersHandler", (Handler,), {
        "root": root, "logging": logging,
        "state": state,
        "service": service or places.from_environment(state),
        "assistant": assistant or order_assistant.from_environment(state),
        "bridge": bridge or configurator_versions.from_environment(state),
    })
    httpd = ThreadingHTTPServer((host, port), handler)
    httpd.daemon_threads = True
    return httpd


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--state", type=Path)
    parser.add_argument("--log", action="store_true", help="write one line per request")
    args = parser.parse_args()
    httpd = server(args.root, args.port, args.state, logging=args.log, host=args.host)
    print(f"orders preview on http://{args.host}:{httpd.server_address[1]}/ (pid {os.getpid()})", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
