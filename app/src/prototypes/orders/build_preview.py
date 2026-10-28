#!/usr/bin/env python3
"""Build the orders preview: each company's homepage with its order page on top.

    python3 app/src/prototypes/orders/build_preview.py

For every folder under `companies/` this takes the company's homepage and that page's requisites
from the mirror cache, takes out analytics, makes forms and links inert, moves every URL under the
company's path prefix, adds the one script tag, builds the catalogue from the mirrored price list
and bundles the widget with the company's config. The preview's root page names Rocoto order pages
and lists nothing about any company.

Reads   <cache>/<company>/site/, <cache>/<company>/replace/, <cache>/<company>/posters/,
        <cache>/<company>/art/, <cache>/_vendor/three.min.js, companies/, widget/
Writes  app/dist-orders-preview/ (git-ignored by `app/dist*`), replacing the build before it
Prints  files and bytes per company against the homepage budget, and the package against the
        receiver's limits. Stops with a message when a mirror is missing or a limit is passed.

This is the `buildCommand` of deploy.preview.json. The packager runs it with a scrubbed
environment, so the cache is found through the account's home directory (pipeline/common.py).
"""
from __future__ import annotations

import argparse
import json
import runpy
import shutil
import sys
from collections import Counter
from pathlib import Path, PurePosixPath

sys.path.insert(0, str(Path(__file__).resolve().parent))
import laser_quote  # noqa: E402
from public_catalogue import image_projection  # noqa: E402
from public_catalogue import select as select_public_catalogue  # noqa: E402

from pipeline import ask, bundle, catalog, clean, common, homepage, prefix  # noqa: E402

ROOT_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>Rocoto order pages</title>
<style>
:root { color-scheme: light dark; font-family: system-ui, -apple-system, "Segoe UI", sans-serif; line-height: 1.5; }
body { margin: 0; min-height: 100vh; display: grid; place-items: center; background: Canvas; color: CanvasText; }
main { max-width: 34rem; padding: 2rem 1.5rem; }
h1 { font-size: 1.75rem; line-height: 1.2; margin: 0 0 .75rem; font-weight: 600; }
p { margin: 0 0 .75rem; }
a { color: inherit; }
</style>
</head>
<body>
<main>
<h1>Rocoto order pages</h1>
<p>An order page for a manufacturer with a published price list, added to the company's own website with one script tag. Customers configure and submit an order request at any hour; the company's salesperson accepts it by e-mail.</p>
<p>Each company's preview has its own address, sent by Rocoto. <a href="https://atelierneyra.com">soyrocoto.com</a></p>
</main>
</body>
</html>
"""


def secret_path():
    contract = runpy.run_path(str(common.REPO / "deploy/development/contract.py"))
    return contract["secret_path"]


def tagged(html: str, tag: str) -> str:
    at = html.lower().rfind("</body>")
    return html[:at] + tag + html[at:] if at >= 0 else html + tag


def copy_tree(source: Path, target: Path) -> int:
    count = 0
    for path in sorted(source.rglob("*")):
        if path.is_file() and not path.is_symlink():
            (target / path.relative_to(source)).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target / path.relative_to(source))
            count += 1
    return count


def build_company(config: dict, out: Path) -> dict:
    """One company's folder in the build, and what went into it."""
    slug = config["slug"]
    site = common.site_dir(slug)
    if not site.is_dir():
        raise SystemExit(
            f"{slug}: its mirror is missing at {site}.\n"
            f"Make it with: python3 app/src/prototypes/orders/pipeline/mirror.py {slug}")
    root, url_prefix = out / slug, common.prefix_of(config)
    made, count, left_out = catalog.build(config, site, url_prefix)
    public_catalogue = made
    if config.get("catalogueScope") == "reviewed_images":
        image_index = json.loads((common.cache_root() / slug / "generated/index.json").read_text())
        public_catalogue = select_public_catalogue(made, image_index)
    asked = ask.check(config, public_catalogue, catalog.photos(public_catalogue, url_prefix))   # questionnaire hook
    chosen = homepage.plan(config, site, catalog.photos(public_catalogue, url_prefix))
    tops = prefix.tops_of(site)
    notes: Counter = Counter()
    for published, source in chosen["pages"].items():
        html, removed = clean.clean_html(common.read(source))
        html, moved = prefix.prefix_html(html, url_prefix, tops)
        notes.update(removed)
        notes.update(moved)
        common.write(root / published, tagged(html, bundle.tag(config)))
    for path, source in chosen["files"].items():
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        kind = path.lower().rsplit(".", 1)[-1]
        if kind == "css":
            text, moved = prefix.prefix_css(common.read(source), url_prefix)
        elif kind in ("js", "mjs"):
            text, moved = prefix.prefix_js(common.read(source), url_prefix, tops)
        else:
            shutil.copyfile(source, target)
            continue
        notes.update(moved)
        common.write(target, text)
    widget = root / "rocoto"
    widget.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(common.REPO / "app/public/inter.woff2", widget / "inter.woff2")
    cache = common.cache_root()
    posters = cache / slug / "posters"
    has_posters = config.get("catalogueScope") != "reviewed_images" and (posters / "index.json").is_file()
    if has_posters:
        copy_tree(posters, widget / "t")
    generated = cache / slug / "generated"
    if generated.is_dir():
        if config.get("catalogueScope") == "reviewed_images":
            public_images = image_projection(public_catalogue, image_index)
            for name in {name for images in public_images["sets"].values() for name in images}:
                source = (generated / name).resolve()
                if not source.is_relative_to(generated.resolve()) or Path(name).is_absolute():
                    raise ValueError("Reviewed image must belong to the company's generated directory")
                destination = widget / "g" / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, destination)
            (widget / "g/index.json").write_text(json.dumps(public_images, indent=2) + "\n")
        else:
            copy_tree(generated, widget / "g")
    else:
        # every page asks for the picture index: a company without studio pictures answers with an empty one
        (widget / "g").mkdir(parents=True, exist_ok=True)
        (widget / "g/index.json").write_text('{"sets": {}, "items": {}, "variantTypes": []}\n')
    art = cache / slug / "art"
    if art.is_dir():
        copy_tree(art, widget / "img")
    sent = "img/order-sent.webp" if (widget / "img" / "order-sent.webp").is_file() else ""
    three = cache / "_vendor" / "three.min.js"
    if not three.is_file():
        raise SystemExit("three.min.js is missing from the cache.\n"
                         "Fetch it with: python3 app/src/prototypes/orders/pipeline/bundle.py --three")
    shutil.copyfile(bundle.three(), widget / "three.min.js")
    (widget / "catalog.json").write_text(catalog.dump(public_catalogue), encoding="utf-8")
    # Commission and refresh use the exact complete configuration that built this widget.
    public_config = {key: value for key, value in config.items() if key != "dir"}
    (widget / "configuration.json").write_text(json.dumps(public_config, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    (widget / "configurator.js").write_text(bundle.bundle(config, has_posters, sent), encoding="utf-8")
    (widget / "embed.html").write_text(
        '<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>Order configurator</title><style>html,body{margin:0;background:transparent}</style></head>'
        '<body><script src="configurator.js" defer></script></body></html>', encoding="utf-8")
    # What the preview server needs to know about this company; nothing in it is private.
    (widget / "site.json").write_text(json.dumps({
        "slug": slug, "name": config["name"], "source": config["source"],
        "languages": list(config["home"]), "geo": config.get("geo") or {},
        "catalogueScope": config.get("catalogueScope", "full"),
        # Laser cutting, for a company that offers it: materials, thicknesses and the tariff of the estimate.
        **({"laser": laser_quote.block(config["laser"])} if config.get("laser") else {}),
    }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    files = [path for path in root.rglob("*") if path.is_file()]
    return {"slug": slug, "files": len(files), "bytes": sum(path.stat().st_size for path in files),
            "budget": config.get("mediaBudgetBytes"),
            "pages": len(chosen["pages"]), "left_out": chosen["left_out"], "missing": chosen["missing"],
            "renditions": chosen["renditions"],
            "notes": notes, "catalog": catalog.report(made, count, left_out) + ("\n" + ask.line(asked) if asked else "")}


def build(out: Path, companies: Path) -> list[dict]:
    slugs = sorted(path.parent.name for path in companies.glob("*/company.json"))
    if not slugs:
        raise SystemExit(f"{companies} holds no company")
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    results = [build_company(common.company(slug, companies / slug), out) for slug in slugs]
    (out / "index.html").write_text(ROOT_PAGE, encoding="utf-8")
    (out / "health").write_text("ok\n", encoding="utf-8")
    (out / "robots.txt").write_text("User-agent: *\nDisallow: /\n", encoding="utf-8")
    refused = secret_path()
    for path in out.rglob("*"):
        relative = PurePosixPath(path.relative_to(out).as_posix())
        if path.is_symlink() or (path.is_file() and refused(relative)):
            raise SystemExit(f"{relative}: the packager refuses this name (deploy/development/contract.py). "
                             "List the file under drop in company.json.")
    return results


def summary(results: list[dict], out: Path) -> tuple[str, bool]:
    lines, ok = [], True
    for result in results:
        budget = result.get("budget") or common.COMPANY_BYTES
        share = result["bytes"] / budget
        lines.append(f"{result['slug']}: {result['pages']} pages, {result['files']} files, "
                     f"{result['bytes'] / 2**20:.2f} MiB of {budget // 2**20} MiB ({share:.0%})")
        lines.append("  " + result["catalog"].replace("\n", "\n  "))
        for path, size, why in result["left_out"]:
            lines.append(f"  left out: {path} ({size / 1e6:.1f} MB; {why})")
        if result["renditions"]:
            lines.append("  " + homepage.renditions_line(result["renditions"]))
        for path in result["missing"]:
            lines.append(f"  the page asks for {path} and the mirror has no such file")
        for name, number in sorted(result["notes"].items()):
            lines.append(f"  {number:5d}  {name}")
        if result["bytes"] > budget:
            ok = False
            lines.append("  OVER the homepage budget: add the heaviest files to drop or shrink in company.json")
    files = [path for path in out.rglob("*") if path.is_file()]
    total = sum(path.stat().st_size for path in files)
    lines.append(f"package: {len(files) + 1} files of {common.PACKAGE_FILES:,}, "
                 f"{total / 2**20:.2f} MiB of {common.PACKAGE_BYTES // 2**20} MiB (receiver limits)")
    if len(files) + 1 > common.PACKAGE_FILES or total > common.PACKAGE_BYTES:
        ok = False
        lines.append("OVER the receiver's limits")
    return "\n".join(lines), ok


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", type=Path, default=common.DIST)
    parser.add_argument("--companies", type=Path, default=common.COMPANIES)
    args = parser.parse_args()
    results = build(args.out, args.companies)
    text, ok = summary(results, args.out)
    print(text)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
