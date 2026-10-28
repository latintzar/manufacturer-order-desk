"""Validate reviewed angled product images before installing a private company cache.

Usage: python3 -m pipeline.studio.delivery --manifest FILE --catalogue FILE --output NEW_DIR
The output is a new delivery directory; switching the cache is a separate local step.
"""

import argparse
import json
import shutil
from pathlib import Path

from .schema import sha256

SHOTS = ("angled",)


def validate(manifest_path, catalogue_path):
    manifest = json.loads(Path(manifest_path).read_text())
    catalogue = json.loads(Path(catalogue_path).read_text())
    index = json.loads(Path(manifest["export_index"]).read_text())
    studio = manifest.get("studio", {})
    reference = Path(studio.get("reference", ""))
    if not reference.is_file() or sha256(reference) != studio.get("sha256"):
        raise ValueError("A hash-verified shared studio reference is required")
    if studio.get("background") != "#E4E2DE":
        raise ValueError("The shared neutral-grey studio background is required")
    owners = {item["c"]: category["code"] for category in catalogue["cats"] for item in category["items"]}
    kept, files, families = {}, {}, {}
    for row in manifest["sets"]:
        if not row["passed"]:
            continue
        key = row["visual_key"]
        if key in kept:
            raise ValueError("Duplicate visual key")
        views = row["views"]
        if [view["shot"] for view in views] != list(SHOTS):
            raise ValueError("Each kept family requires one angled product image")
        names = []
        for view in views:
            if not view["passed"] or not all(
                view["review"].get(gate) is True
                for gate in ("geometry", "material", "lighting", "background")
            ):
                raise ValueError("Kept set includes a held review")
            source, export = Path(view["source"]), Path(view["export"])
            if sha256(source) != view["sha256"] or sha256(export) != view["export_sha256"]:
                raise ValueError("Reviewed image hash changed")
            if export.suffix != ".webp" or export.name in files:
                raise ValueError("Unique WebP exports required")
            files[export.name] = export
            names.append(export.name)
        kept[key] = names
        families[key] = row["type_code"]
    if index["sets"] != kept:
        raise ValueError("Public index does not match kept sets")
    variants = index["variantTypes"]
    if len(variants) != len(set(variants)) or set(variants) - set(owners.values()):
        raise ValueError("Unknown or duplicate variant family")
    for sku, key in index["items"].items():
        if sku not in owners or owners[sku] not in variants:
            raise ValueError("Unknown SKU or missing variant family")
        if key is not None and (key not in kept or owners[sku] != families[key]):
            raise ValueError("SKU is mapped to another product family")
    expected = {sku for sku, family in owners.items() if family in variants}
    if set(index["items"]) != expected:
        raise ValueError("Variant mapping must account for every SKU")
    return {"sets": kept, "items": index["items"], "variantTypes": variants}, files


def install(manifest_path, catalogue_path, output):
    return install_many([manifest_path], catalogue_path, output)


def install_many(manifest_paths, catalogue_path, output):
    """Combine reviewed batches, promoting explicit holds without replacing approved mappings."""
    if not manifest_paths:
        raise ValueError("Choose at least one reviewed manifest")
    index = {"sets": {}, "items": {}, "variantTypes": []}
    files, families = {}, {}
    studio_hash = None
    for manifest_path in manifest_paths:
        batch, exports = validate(manifest_path, catalogue_path)
        current_studio = json.loads(Path(manifest_path).read_text())["studio"]["sha256"]
        if studio_hash is not None and current_studio != studio_hash:
            raise ValueError("Batches must share the same reviewed studio reference")
        studio_hash = current_studio
        for row in json.loads(Path(manifest_path).read_text())["sets"]:
            if row["passed"]:
                key, family = row["visual_key"], row["type_code"]
                if key in families and families[key] != family:
                    raise ValueError("Conflicting visual family across batches")
                families[key] = family
        for key, views in batch["sets"].items():
            if key in index["sets"] and index["sets"][key] != views:
                raise ValueError("Conflicting visual key across batches")
            index["sets"][key] = views
        for name, source in exports.items():
            if name in files and sha256(files[name]) != sha256(source):
                raise ValueError("Conflicting image filename across batches")
            files[name] = source
        for sku, key in batch["items"].items():
            prior = index["items"].get(sku)
            if prior is not None and key is not None and prior != key:
                raise ValueError("Conflicting approved SKU mapping across batches")
            index["items"][sku] = prior or key
        index["variantTypes"] = sorted(set(index["variantTypes"]) | set(batch["variantTypes"]))
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    for name, source in files.items():
        shutil.copyfile(source, output / name)
    (output / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n")
    return {
        "directory": str(output.resolve()),
        "sets": len(index["sets"]),
        "images": len(files),
        "mapped_skus": sum(key is not None for key in index["items"].values()),
        "manifest_sha256": sha256(manifest_paths[0]) if len(manifest_paths) == 1 else None,
        "manifest_hashes": [sha256(path) for path in manifest_paths],
        "catalogue_sha256": sha256(catalogue_path),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, action="append")
    parser.add_argument("--catalogue", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    print(json.dumps(install_many(args.manifest, args.catalogue, args.output), indent=2))


if __name__ == "__main__":
    main()
