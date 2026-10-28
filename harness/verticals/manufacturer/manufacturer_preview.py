"""Isolated previews of saved configurator documents using a pinned real widget renderer.

The preview never invokes order, upload, address or provider APIs. Its fetch adapter reads
only the saved catalogue and pinned public image indexes. The original widget stays owned
by the Orders product; this adapter changes its configuration, not its implementation.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import secrets
import urllib.request
from pathlib import Path

from origin_config import configured_origin
ORIGIN = configured_origin()
MAX_RENDERER = 2_000_000
SLUG = re.compile(r"[a-z][a-z0-9-]{1,40}")


async def render_preview(extension, version):
    """Read the pinned renderer off the request loop; the host rechecks membership afterward."""
    from starlette.concurrency import run_in_threadpool

    settings = version.get("settings", {})
    slug = settings.get("company_slug", "sample-hardware")
    return await run_in_threadpool(html, extension.selected["state"], slug, version["document"], settings)


def _json(value):
    return (
        json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


class FixedOriginRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("Use the commissioned configurator origin directly.")


def _fetch(url, limit):
    if not url.startswith(ORIGIN + "/"):
        raise ValueError("Use the commissioned configurator origin.")
    request = urllib.request.Request(url, headers={"User-Agent": "Rocoto-Manufacturer-Preview/1"})
    with urllib.request.build_opener(FixedOriginRedirect()).open(request, timeout=15) as response:
        value = response.read(limit + 1)
    if len(value) > limit:
        raise ValueError("The configurator preview exceeds its saved-asset limit.")
    return value


def _pin(path, value):
    """Publish a complete immutable file; concurrent first readers agree on the winner."""
    temporary = path.with_name(path.name + "-" + secrets.token_hex(8) + ".tmp")
    temporary.write_bytes(value)
    temporary.chmod(0o600)
    try:
        os.link(temporary, path)
    except FileExistsError:
        pass
    finally:
        temporary.unlink(missing_ok=True)


def _read_renderer(folder, entry):
    digest = entry.get("sha256", "")
    if not re.fullmatch(r"[a-f0-9]{64}", digest):
        raise ValueError("The saved preview renderer needs verification.")
    body = (folder / (digest + ".js")).read_bytes()
    if hashlib.sha256(body).hexdigest() != digest:
        raise ValueError("The saved preview renderer needs verification.")
    return {**entry, "script": body.decode("utf-8")}


def _complete_bundle(script):
    # The public one-tag bundle contains pick.js and pick.css inline, before shop.js.
    return "window.RocotoPick=" in script and "window.RocotoPick.ui" in script and ".pick-entry" in script


def renderer(state, slug, fetch=_fetch, *, snapshot_sha=None):
    if not isinstance(slug, str) or not SLUG.fullmatch(slug):
        raise ValueError("Use the bound company configurator.")
    if snapshot_sha is not None and not re.fullmatch(r"[a-f0-9]{64}", snapshot_sha):
        raise ValueError("Use a verified configurator snapshot.")
    folder = Path(state) / "manufacturer-preview" / slug
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    # v1 pinned the pre-picker renderer. Keep its manifest and bytes for provenance;
    # v2 requires the complete public bundle and additionally pins each full snapshot.
    manifest = folder / "renderer-v2.json"
    snapshot = folder / ("snapshot-" + snapshot_sha + ".json") if snapshot_sha else None
    if snapshot and snapshot.is_file():
        return _read_renderer(folder, json.loads(snapshot.read_text()))
    if manifest.is_file():
        pinned = _read_renderer(folder, json.loads(manifest.read_text()))
    else:
        legacy = folder / "renderer.json"
        pinned = _read_renderer(folder, json.loads(legacy.read_text())) if legacy.is_file() else None
        if not pinned or not _complete_bundle(pinned["script"]):
            base = f"{ORIGIN}/{slug}/rocoto/"
            body = fetch(base + "configurator.js", MAX_RENDERER)
            text = body.decode("utf-8")
            match = re.search(r"window\.RocotoConfig=(\{[^\n]*\});", text)
            if not match or not _complete_bundle(text):
                raise ValueError("The configurator renderer needs the complete picker bundle.")
            indexes = {}
            for path in ("g/index.json", "t/index.json"):
                try:
                    indexes[path] = json.loads(fetch(base + path, 500_000))
                except (OSError, ValueError):
                    indexes[path] = {}
            digest = hashlib.sha256(body).hexdigest()
            _pin(folder / (digest + ".js"), body)
            pinned = {
                "sha256": digest,
                "config": json.loads(match.group(1)),
                "indexes": indexes,
                "source": base + "configurator.js",
                "script": text,
            }
        entry = {key: value for key, value in pinned.items() if key != "script"}
        entry["schema"] = 2
        _pin(manifest, _json(entry).encode())
        pinned = _read_renderer(folder, json.loads(manifest.read_text()))
    if not _complete_bundle(pinned["script"]):
        raise ValueError("The saved preview renderer needs the complete picker bundle.")
    if snapshot:
        _pin(snapshot, _json({key: value for key, value in pinned.items() if key != "script"}).encode())
        pinned = _read_renderer(folder, json.loads(snapshot.read_text()))
    return pinned


def html(state, slug, snapshot, settings=None, *, fetch=_fetch):
    """Return HTML and CSP for a fully isolated saved-version iframe."""
    document = snapshot.get("document", snapshot)
    snapshot_sha = hashlib.sha256(
        _json({"document": document, "settings": settings or {}}).encode()
    ).hexdigest()
    pinned = renderer(state, slug, fetch, snapshot_sha=snapshot_sha)
    configuration = document.get("configuration", {})
    catalogue = copy.deepcopy(document.get("catalogue", {}))
    if not isinstance(catalogue, dict) or not isinstance(catalogue.get("cats"), list):
        catalogue = {
            "cats": [],
            "forms": [],
            "metals": [],
            "company": {"en": "Sample Hardware", "bg": "Sample Hardware"},
            "currency": "EUR",
            "vat": 0.2,
            "rules": {},
        }
    for category in catalogue.get("cats", []):
        for record in [category, *category.get("items", [])]:
            for key in ("img", "picture", "image"):
                value = record.get(key)
                if isinstance(value, str) and value.startswith("/") and not value.startswith("//"):
                    record[key] = ORIGIN + value
    config = copy.deepcopy(pinned["config"])
    # Optional business modules belong to the saved document, not to today's bundle defaults.
    for key in (
        "picker",
        "questionnaire",
        "drawings",
        "turnaround",
        "checkout",
        "geo",
        "headline",
        "description",
        "button_label",
        "theme",
        "texts",
        "assets",
    ):
        config.pop(key, None)
    for key in (
        "accent",
        "questionnaire",
        "picker",
        "drawings",
        "turnaround",
        "checkout",
        "strings",
        "hours",
        "shop",
        "geo",
        "headline",
        "description",
        "button_label",
        "theme",
        "texts",
        "assets",
        "delivery",
    ):
        if key in configuration:
            config[key] = configuration[key]
    language = configuration.get("defaultLanguage") or configuration.get("lang") or config.get("lang", "bg")
    language = language if language in {"bg", "en"} else "bg"
    config["lang"] = language
    base = f"{ORIGIN}/{slug}/rocoto/"
    prefix = f"{ORIGIN}/{slug}"
    config.update(
        {"base": base, "root": prefix, "key": "manufacturer-version-preview", "table": "", "preview": True}
    )
    for key in ("logo", "art"):
        if config.get(key, "").startswith("/"):
            config[key] = ORIGIN + config[key]
    config["logos"] = {
        key: ORIGIN + value if value.startswith("/") else value
        for key, value in config.get("logos", {}).items()
    }
    settings = settings or {}
    for key in ("accent", "headline", "description", "button_label"):
        if key in settings:
            config[key] = settings[key]
    for string_language in ("en", "bg"):
        strings = dict(config.get("strings", {}).get(string_language, {}))
        if settings.get("button_label"):
            strings["go"] = settings["button_label"]
            strings["launchGo"] = settings["button_label"]
        config.setdefault("strings", {})[string_language] = strings
    if settings.get("headline") and isinstance(config.get("questionnaire"), dict):
        config["questionnaire"] = {
            **config["questionnaire"],
            "title": {"en": settings["headline"], "bg": settings["headline"]},
        }
    if settings.get("description") and isinstance(config.get("questionnaire"), dict):
        config["questionnaire"]["help"] = {"en": settings["description"], "bg": settings["description"]}
    match = re.search(r"window\.RocotoConfig=(\{[^\n]*\});", pinned["script"])
    script = (
        pinned["script"][: match.start()]
        + "window.RocotoConfig="
        + _json(config)
        + ";"
        + pinned["script"][match.end() :]
    )
    nonce = secrets.token_urlsafe(24)
    initial = {"catalogue": catalogue, "indexes": pinned["indexes"], "settings": settings}
    adapter = (Path(__file__).parent / "web/manufacturer-preview.js").read_text()
    css = (
        "html,body{margin:0;min-height:100%;background:#fff}body{font-family:system-ui}"
        "#preview-status{padding:24px;color:#555;font-size:14px}"
    )
    content = (
        f'<!doctype html><html lang="{language}"><head><meta charset="utf-8"><meta name="viewport" '
        'content="width=device-width,initial-scale=1"><title>'
        + ("Преглед на конфигуратора" if language == "bg" else "Configurator version preview")
        + '</title>'
        '<style nonce="'
        + nonce
        + '">'
        + css
        + '</style></head><body><p id="preview-status">'
        + ("Зареждане на конфигуратора…" if language == "bg" else "Opening saved configurator…")
        + '</p>'
    )
    content += (
        '<script nonce="'
        + nonce
        + '">window.__manufacturerPreview='
        + _json(initial)
        + ";"
        + adapter.replace("</script", "<\\/script")
        + "</script>"
    )
    content += (
        '<script nonce="'
        + nonce
        + '">'
        + script.replace("</script", "<\\/script")
        + "</script></body></html>"
    )
    policy = (
        f"default-src 'none'; script-src 'nonce-{nonce}'; style-src 'unsafe-inline'; "
        f"img-src https: data: blob: {ORIGIN}; font-src https: data: {ORIGIN}; connect-src 'none'; "
        "frame-src 'none'; form-action 'none'; base-uri 'none'"
    )
    return content, {
        "Content-Security-Policy": policy,
        "Cache-Control": "private, no-store",
        "Referrer-Policy": "no-referrer",
        "X-Content-Type-Options": "nosniff",
        "X-Configurator-Renderer": pinned["sha256"],
    }
