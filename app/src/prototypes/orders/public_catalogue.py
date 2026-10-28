"""Select the reviewed sales collection while preserving the full company catalogue."""

from __future__ import annotations

import copy
import json
from pathlib import Path


def select(catalogue: dict, image_index: dict) -> dict:
    """Expose only exact SKU mappings with a single reviewed angled image."""
    sets = image_index.get("sets", {})
    approved = {
        sku for sku, key in image_index.get("items", {}).items()
        if key is not None and isinstance(sets.get(key), list) and len(sets[key]) == 1
    }
    result = copy.deepcopy(catalogue)
    categories = []
    for category in result.get("cats", []):
        category["items"] = [item for item in category["items"] if item["c"] in approved]
        if category["items"]:
            categories.append(category)
    if not categories:
        raise ValueError("The reviewed sales collection is empty")
    result["cats"] = categories
    # Avoid empty filter choices and leaking held product titles through those choices.
    for key, field in (("metals", "metal"), ("forms", "form")):
        used = {category.get(field) for category in categories}
        if isinstance(result.get(key), dict):
            result[key] = {code: value for code, value in result[key].items() if code in used}
        elif isinstance(result.get(key), list):
            result[key] = [value for value in result[key] if value.get("id") in used]
    return result


def for_site(catalogue: dict, widget_root: Path) -> dict:
    """Apply the immutable release's selection policy to fresh database prices."""
    policy = json.loads((widget_root / "site.json").read_text())
    if policy.get("catalogueScope") != "reviewed_images":
        return catalogue
    try:
        index = json.loads((widget_root / "g/index.json").read_text())
        return select(catalogue, index)
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ValueError("The reviewed sales collection is being prepared") from exc


def image_projection(catalogue: dict, image_index: dict) -> dict:
    """Publish only selected mappings; private holds and unused sets stay private."""
    skus = {item["c"] for category in catalogue["cats"] for item in category["items"]}
    items = {sku: key for sku, key in image_index.get("items", {}).items()
             if sku in skus and key is not None}
    keys = set(items.values())
    result = {"sets": {key: value for key, value in image_index["sets"].items() if key in keys},
              "items": items,
              "variantTypes": [category["code"] for category in catalogue["cats"]]}
    if "bg" in image_index:
        result["bg"] = image_index["bg"]
    return result
