#!/usr/bin/env python3
"""Validate company-owned picker data, source coverage and self-contained drawings.

    python3 pipeline/pick.py <company> <catalogue.json>

Unlike questionnaire matches, family and facet matching is strict: missing values
are never evidence of compatibility. Clarifications record customer observations
and do not manufacture catalogue attributes.
"""

from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class Invalid(ValueError):
    """A picker dependency or a source-backed option needs correction."""


def listed(value):
    return [] if value is None else value if isinstance(value, list) else [value]


def values(category, item, key):
    return listed(category.get("form") if key == "form" else item.get("a", {}).get(key))


def matches(category, item, filters):
    return all(
        any(str(value) == str(wanted) for value in values(category, item, key) for wanted in listed(allowed))
        for key, allowed in filters.items()
    )


def words(value, where):
    if not isinstance(value, dict) or not all(
        isinstance(value.get(lang), str) and value[lang].strip() for lang in ("en", "bg")
    ):
        raise Invalid(f"{where} needs English and Bulgarian words.")


def svg(name, source):
    """Permit only the small local vector vocabulary used by the company drawings."""
    allowed = {
        "svg",
        "g",
        "path",
        "rect",
        "circle",
        "ellipse",
        "line",
        "polyline",
        "polygon",
        "defs",
        "linearGradient",
        "radialGradient",
        "stop",
    }
    try:
        if not isinstance(source, str) or len(source.encode()) > 4096 or "<!" in source:
            raise ValueError("size or declaration")
        root = ET.fromstring(source)
        if root.tag.rsplit("}", 1)[-1] != "svg":
            raise ValueError("root")
        for node in root.iter():
            if node.tag.rsplit("}", 1)[-1] not in allowed or (node.text or "").strip():
                raise ValueError("element")
            for attribute, value in node.attrib.items():
                local = attribute.rsplit("}", 1)[-1].lower()
                if local.startswith("on") or local in {"href", "style"} or "javascript:" in value.lower():
                    raise ValueError("attribute")
                if "url(" in value.lower() and not re.fullmatch(r"url\(#[A-Za-z][\w-]*\)", value):
                    raise ValueError("reference")
    except (ET.ParseError, TypeError, ValueError) as error:
        raise Invalid(f'Drawing "{name}" contains unsafe SVG or exceeds 4096 bytes.') from error


def validate(definition, catalogue, drawings):
    if not isinstance(definition, dict) or not definition.get("families"):
        raise Invalid("The picker needs at least one family.")
    all_rows = [(cat, item) for cat in catalogue["cats"] for item in cat["items"]]
    photos = {cat["code"] for cat in catalogue["cats"] if cat.get("img")}
    for name, source in drawings.items():
        svg(name, source)
    used_drawings, reached, families, facets = set(), set(), set(), 0

    def drawing(name):
        if not name or name not in drawings:
            raise Invalid(f'The picker names drawing "{name}", which the company does not hold.')
        used_drawings.add(name)

    def photo(name, where):
        if name not in photos:
            raise Invalid(f'{where} needs a catalogue photograph, "{name}".')

    def options(entries, where, kind, known=None):
        seen = set()
        if not entries:
            raise Invalid(f"{where} needs options.")
        for choice in entries:
            value = str(choice.get("value", ""))
            if not value or value in seen:
                raise Invalid(f"{where} needs a unique value for every option.")
            seen.add(value)
            words(choice.get("label"), f'{where} option "{value}"')
            if known is not None and value not in known:
                raise Invalid(f'{where} option "{value}" matches zero articles.')
            if kind == "model":
                photo(choice.get("photo"), where)
            else:
                drawing(choice.get("drawing"))
            if kind == "swatch" and not re.fullmatch(r"#[0-9a-fA-F]{6}", choice.get("swatch", "")):
                raise Invalid(f'{where} option "{value}" needs a six-digit colour.')
        if known is not None and known - seen:
            raise Invalid(f'{where} omits source value "{sorted(known - seen)[0]}".')

    helpers = definition.get("help", {})
    for name, helper in helpers.items():
        words(helper.get("title"), f'Help "{name}"')
        words(helper.get("text"), f'Help "{name}"')
        drawing(helper.get("drawing"))
    for family in definition["families"]:
        name = family.get("id")
        if not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9-]*", name) or name in families:
            raise Invalid("Every picker family needs a unique id.")
        families.add(name)
        where = f'Family "{name}"'
        words(family.get("title"), where)
        photo(family.get("photo"), where)
        filters = family.get("match")
        if not isinstance(filters, dict) or not filters:
            raise Invalid(f"{where} needs source attributes to match.")
        rows = [(cat, item) for cat, item in all_rows if matches(cat, item, filters)]
        if not rows:
            raise Invalid(f"{where} matches zero articles.")
        reached.update(item["c"] for _, item in rows)
        keys = set()
        for facet in family.get("facets", []):
            key, kind = facet.get("key"), facet.get("kind")
            spot = f'{where} facet "{key}"'
            if not key or key in keys or kind not in {"pict", "cells", "swatch", "model"}:
                raise Invalid(f"{spot} needs a unique key and a supported display kind.")
            keys.add(key)
            words(facet.get("title"), spot)
            known = {str(value) for cat, item in rows for value in values(cat, item, key)}
            options(facet.get("options"), spot, kind, known)
            if facet.get("help") and facet["help"] not in helpers:
                raise Invalid(f"{spot} names an unknown help entry.")
            facets += 1
    for _, item in all_rows:
        if item["c"] not in reached:
            raise Invalid(f'Article "{item["c"]}" needs a picker family.')
    clarifications = set()
    for entry in definition.get("clarify", []):
        name = entry.get("id")
        where = f'Clarification "{name}"'
        if not name or name in clarifications or not entry.get("key"):
            raise Invalid(f"{where} needs a unique id and an observation key.")
        clarifications.add(name)
        words(entry.get("title"), where)
        options(entry.get("options"), where, "pict")
        if entry.get("when") and not any(matches(cat, item, entry["when"]) for cat, item in all_rows):
            raise Invalid(f"{where} condition matches zero articles.")
    return {
        "families": len(families),
        "facets": facets,
        "rows": len(all_rows),
        "drawings": len(used_drawings),
    }


def check(config, catalogue):
    """Optional build hook; all inputs are company-owned files or commissioned config."""
    from pipeline import common

    folder = Path(config.get("dir") or common.COMPANIES / config["slug"])
    path = folder / "picker.json"
    definition = json.loads(path.read_text()) if path.is_file() else config.get("picker")
    if not definition:
        return None
    drawings = {path.stem: path.read_text() for path in (folder / "drawings").glob("*.svg")}
    if not drawings and isinstance(config.get("drawings"), dict):
        drawings = config["drawings"]
    try:
        return validate(definition, catalogue, drawings)
    except Invalid as error:
        raise SystemExit(f"{config['slug']}: picker: {error}") from error


def line(report):
    return (
        f"{report['families']} families, {report['facets']} facets, "
        f"{report['rows']} reachable articles and {report['drawings']} drawings."
    )


if __name__ == "__main__":
    from pipeline import common

    result = check(common.company(sys.argv[1]), json.loads(Path(sys.argv[2]).read_text()))
    print(line(result) if result else "The company uses the catalogue without a picker.")
