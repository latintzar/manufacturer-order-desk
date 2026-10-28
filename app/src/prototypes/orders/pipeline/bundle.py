#!/usr/bin/env python3
"""Bundle the shared widget with one company's config into a single script.

    python3 pipeline/bundle.py <company> [--out FILE]     print the config and the bundle size
    python3 pipeline/bundle.py --three                    fetch the pinned three.js build into the cache

The widget source in `widget/` is the same for every company. What makes a bundle a company's own
is the `window.RocotoConfig` object written at its top, built here from `company.json` and the
company's path prefix. The page then needs one tag:

    <script src="/<company>/rocoto/configurator.js" data-rocoto="<company>" defer></script>

Reads   widget/*.js, widget/shop.css, widget/icons.json, laser_quote.mjs, companies/<slug>/company.json,
        <cache>/_config/maps-embed-key (optional: the browser key for the map)
Writes  the file named by --out, when given; <cache>/_vendor/three.min.js with --three
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline import common  # noqa: E402

ORDER = ("pricing.js", "geom.js", "core.js", "laser.js", "ask.js", "pick.js")   # then the interface, which needs all five
LASER_QUOTE = common.WIDGET.parent / "laser_quote.mjs"     # the estimate's formula, shared with the server


def tag(config: dict) -> str:
    slug = config["slug"]
    return f'<script src="/{slug}/rocoto/configurator.js" data-rocoto="{slug}" defer></script>'


def maps_key() -> str:
    """The browser key for the embedded map. It lives outside the repository and is public in the
    page by nature, so the key itself must be restricted to the preview host in Google's console."""
    path = common.cache_root() / "_config" / "maps-embed-key"
    key = path.read_text(encoding="utf-8").strip() if path.is_file() else ""
    if key and not re.fullmatch(r"[A-Za-z0-9_-]{20,80}", key):
        raise SystemExit(f"{path} holds something other than a browser key")
    return key


def widget_config(config: dict, posters: bool = False, art: str = "") -> dict:
    """`window.RocotoConfig` for this company, served under its prefix."""
    prefix = common.prefix_of(config)
    default = config["defaultLanguage"]
    widget = {
        "base": f"{prefix}/rocoto/", "root": prefix, "logo": prefix + config["logo"],
        "accent": config["accent"], "key": f"rocoto-basket-{config['slug']}", "prefix": config["orderPrefix"],
        "preview": True, "delivery": config["delivery"], "lang": default,
        # The default language is served at the company's root; each other one under its own code.
        "langs": {language: f"/{language}/" for language in config["home"] if language != default},
        "table": config.get("tableHook", ""), "hours": config["hours"], "shop": config.get("shop") or {},
        "strings": config["strings"], "posters": posters, "art": art,
    }
    if config.get("logos"):
        widget["logos"] = {language: prefix + path for language, path in config["logos"].items()}
    key = maps_key()
    if key:
        widget["mapsKey"] = key
    if config.get("geo"):
        widget["geo"] = config["geo"]
    # Optional company settings. Without `turnaround` the page words the time «on confirmation»;
    # `laser` only says the company offers it: materials and tariff arrive with each check.
    for key in ("turnaround", "checkout"):
        if isinstance(config.get(key), dict):
            widget[key] = config[key]
    if config.get("laser"):
        widget["laser"] = True
    if config.get("questionnaire"):                    # questionnaire hook: the company's guided questions
        widget["questionnaire"] = config["questionnaire"]
    # Picker assets belong to the company and travel inside the one-tag bundle.
    folder = Path(config.get("dir") or common.COMPANIES / config["slug"])
    for asset in ("picker", "questionnaire"):
        path = folder / f"{asset}.json"
        if config.get(asset) is not None:
            widget[asset] = config[asset]
        elif path.is_file():
            widget[asset] = json.loads(path.read_text(encoding="utf-8"))
    if config.get("drawings") is not None:
        widget["drawings"] = config["drawings"]
    elif (folder / "drawings").is_dir():
        widget["drawings"] = {path.stem: path.read_text(encoding="utf-8") for path in sorted((folder / "drawings").glob("*.svg"))}
    return widget


def bundle(config: dict, posters: bool = False, art: str = "") -> str:
    """The script the company's page loads: config, price engine, 3D engine, core, interface."""
    missing = [name for name in (*common.WIDGET_FILES, *ORDER, "embed.js") if not (common.WIDGET / name).is_file()]
    if not LASER_QUOTE.is_file():
        missing.append(f"../{LASER_QUOTE.name}")
    if missing:
        raise SystemExit("widget/ is missing " + ", ".join(missing))

    def read(name: str) -> str:
        return (common.WIDGET / name).read_text(encoding="utf-8")

    css = re.sub(r"\s*\n\s*", "", re.sub(r"/\*.*?\*/", "", read("shop.css") + read("ask.css") + read("pick.css"), flags=re.S))  # questionnaire hook
    icons = json.dumps(json.loads(read("icons.json")), separators=(",", ":"))
    interface = read("shop.js").replace("__ICONS__", icons).replace("__CSS__", json.dumps(css))
    head = f"/* Rocoto order page for {config['name'].get('en') or config['slug']}. One script tag on the host page. */"
    settings = "window.RocotoConfig=" + json.dumps(widget_config(config, posters, art), ensure_ascii=False) + ";"
    formula = LASER_QUOTE.read_text(encoding="utf-8")
    return "\n".join([head, "(function(){", settings, read("embed.js"), "if(window.RocotoEmbed())return;",
                      *(read(name) for name in ORDER), formula, interface, "})();"])


def three() -> Path:
    """The pinned three.js build, fetched once into the cache and checked against its SHA-256."""
    target = common.cache_root() / "_vendor" / "three.min.js"
    target.parent.mkdir(parents=True, exist_ok=True)
    bundled = common.OWNER / 'vendor/three.min.js'
    if not target.is_file() and bundled.is_file():
        body = bundled.read_bytes()
        if hashlib.sha256(body).hexdigest() != common.THREE_SHA256:
            raise SystemExit('Bundled three.js differs from the pinned build')
        target.write_bytes(body)
    if not target.is_file():
        target.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(common.THREE_URL, timeout=60) as response:  # noqa: S310 - pinned https URL
            body = response.read()
        if hashlib.sha256(body).hexdigest() != common.THREE_SHA256:
            raise SystemExit("three.min.js differs from the pinned build")
        target.write_bytes(body)
    elif hashlib.sha256(target.read_bytes()).hexdigest() != common.THREE_SHA256:
        raise SystemExit(f"{target} differs from the pinned build: remove it and run bundle.py --three")
    return target


def main(argv: list[str]) -> int:
    if argv[1:] == ["--three"]:
        print(three())
        return 0
    if len(argv) not in (2, 4) or (len(argv) == 4 and argv[2] != "--out"):
        print("\n".join(line.strip() for line in __doc__.strip().splitlines()[2:4]))
        return 2
    config = common.company(argv[1])
    shown = widget_config(config)
    if "mapsKey" in shown:
        shown["mapsKey"] = "(set)"
    print(json.dumps(shown, ensure_ascii=False, indent=2))
    script = bundle(config)
    print(f"bundle: {len(script.encode())} bytes; tag: {tag(config)}")
    if len(argv) == 4:
        Path(argv[3]).write_text(script, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
