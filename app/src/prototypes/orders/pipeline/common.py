"""Shared paths and company loading for the orders pipeline.

Reads   companies/<slug>/company.json and companies/<slug>/mapping.py
Writes  nothing

The cache holds what never enters this repository: each company's mirrored site, its posters and
the shared three.js build. Its default location comes from the account's home directory in the
password database, because the preview packager runs the build with HOME pointed at a temporary
directory (deploy/development/package.py). ROCOTO_ORDERS_CACHE selects another location.
"""
from __future__ import annotations

import importlib.util
import json
import os
import pwd
import re
from pathlib import Path

OWNER = Path(__file__).resolve().parents[1]          # app/src/prototypes/orders
REPO = OWNER.parents[3]
COMPANIES = OWNER / "companies"
WIDGET = OWNER / "widget"
DIST = REPO / "app" / "dist-orders-preview"
CHECK_OUT = REPO / "app" / "dist-orders-check"
CACHE_ENV = "ROCOTO_ORDERS_CACHE"
SLUG = re.compile(r"^[a-z][a-z0-9-]{1,40}$")
RESERVED = {"rocoto", "health", "healthz", "index", "robots", "static", "assets"}
COMPANY_BYTES = 16 * 1024 * 1024                      # one company in the package: homepage, requisites, widget
PACKAGE_BYTES = 256 * 1024 * 1024                     # deploy/development/receive.py refuses more
PACKAGE_FILES = 10_000
THREE_URL = "https://cdnjs.cloudflare.com/ajax/libs/three.js/0.160.0/three.min.js"
THREE_SHA256 = "170c6789f43217c96b3170f4b42fafe135de7f7cd48497a4218f9757ee1d49fa"
WIDGET_FILES = ("pricing.js", "geom.js", "core.js", "ask.js", "pick.js", "shop.js", "shop.css", "ask.css", "pick.css", "icons.json")
REQUIRED = ("slug", "name", "source", "priceList", "home", "accent", "logo", "languages", "defaultLanguage",
            "orderPrefix", "delivery", "hours", "strings")
ADDRESS_STRINGS = ("pickup", "pickSub", "pickAddr", "delFee")   # the widget lines that name a place


def cache_root() -> Path:
    chosen = os.environ.get(CACHE_ENV)
    if chosen:
        return Path(chosen).expanduser().resolve()
    return Path(pwd.getpwuid(os.getuid()).pw_dir) / ".local/state/manufacturer-order-desk/orders-cache"


def site_dir(slug: str) -> Path:
    return cache_root() / slug / "site"


def slugs() -> list[str]:
    return sorted(p.parent.name for p in COMPANIES.glob("*/company.json"))


def company(slug: str, folder: Path | None = None, *, complete: bool = True) -> dict:
    """One company's config, checked. A missing value stops the run with the field named.

    The mirror needs the address alone (`complete=False`); every later step needs the rest.
    """
    folder = folder or COMPANIES / slug
    if not SLUG.fullmatch(slug) or slug in RESERVED:
        raise SystemExit(f"{slug}: a company slug is lowercase letters, digits and hyphens")
    path = folder / "company.json"
    if not path.is_file():
        raise SystemExit(f"{slug}: {path} is missing. Start with pipeline/new_company.py {slug} <url>")
    config = json.loads(path.read_text(encoding="utf-8"))
    def empty(value: object) -> bool:
        return value in (None, "", {}, []) or (isinstance(value, dict) and all(empty(v) for v in value.values()))

    missing = [key for key in (REQUIRED if complete else ("source",)) if empty(config.get(key))]
    if complete and "priceList" not in missing:
        missing += [f"priceList.{key}" for key in ("url", "path") if not config["priceList"].get(key)]
    if config.get("slug") != slug:
        missing.append("slug (must equal the folder name)")
    for language in (config.get("home") or {}) if complete else ():
        for key in ADDRESS_STRINGS:
            if not ((config.get("strings") or {}).get(language) or {}).get(key):
                missing.append(f"strings.{language}.{key}")
    if complete and config.get("defaultLanguage") not in (config.get("home") or {}):
        missing.append("home.<defaultLanguage>")
    if missing:
        raise SystemExit(f"{slug}: company.json needs " + ", ".join(missing))
    # Hydrate the complete company document for build, commissioning and version snapshots.
    for asset in ("questionnaire", "picker"):
        source = folder / f"{asset}.json"
        if source.is_file():
            config[asset] = json.loads(source.read_text(encoding="utf-8"))
    drawings = folder / "drawings"
    if drawings.is_dir():
        config["drawings"] = {source.stem: source.read_text(encoding="utf-8") for source in sorted(drawings.glob("*.svg"))}
    config["dir"] = folder
    return config


def mapping(config: dict):
    """The company's own reading of its price list, as a module."""
    path = Path(config["dir"]) / "mapping.py"
    spec = importlib.util.spec_from_file_location(f"orders_mapping_{config['slug'].replace('-', '_')}", path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"{config['slug']}: {path} is missing")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def prefix_of(config: dict) -> str:
    return "/" + config["slug"]


def read(path: Path) -> str:
    """A mirrored text file exactly as fetched: its own line endings, any stray bytes kept."""
    with open(path, encoding="utf-8", errors="surrogateescape", newline="") as handle:
        return handle.read()


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", errors="surrogateescape", newline="") as handle:
        handle.write(text)
