"""Validate anonymous image observations before admitting catalogue material inputs.

Conservative lexical compatibility is an evidence check, not an alloy classifier.
Original blind payloads are immutable; catalogue facts never rewrite observations.
"""

import argparse
import hashlib
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

# Every shape needs each visible feature group; synonyms within a group are alternatives.
# "special" includes unrelated hardware and ornamental parts, requiring item-specific review.
SHAPES = {
    "sq_tube": (("square",), ("hollow", "opening", "bore")),
    "rect_tube": (("rectangular", "rectangle"), ("hollow", "opening", "bore")),
    "round_tube": (("circular", "round", "cylindrical"), ("hollow", "opening", "bore")),
    "ipe": (("flange", "flanges"), ("web",)),
    "hea": (("flange", "flanges"), ("web",)),
    "heb": (("flange", "flanges"), ("web",)),
    "flat": (("solid", "bar", "strip"), ("rectangular", "rectangle", "flat")),
    "chequer": (("plate", "sheet"), ("raised", "embossed", "tread", "chequer", "checker")),
    "sheet": (("sheet", "plate"),),
    "round": (("solid", "rod", "rods", "bar", "bars"), ("circular", "round", "cylindrical")),
    "square": (("solid", "bar", "bars"), ("square",)),
    "hex": (("solid", "bar", "bars"), ("hexagonal", "hexagon", "six sided")),
    "angle": (("l shaped", "l section", "right angle", "angle profile", "angle section"),),
    "angle_u": (("l shaped", "l section", "right angle", "angle profile", "angle section"),),
    "tee": (("t shaped", "t section", "tee"),),
    "upn": (("u shaped", "u section", "channel", "channels"),),
    "channel": (("u shaped", "u section", "channel", "channels"),),
}
MATERIALS = {
    "hr": ("steel", "ferrous", "iron"),
    "cr": ("steel", "ferrous", "iron"),
    "wrought": ("steel", "ferrous", "iron"),
    "galv": ("steel", "zinc", "galvanized", "galvanised"),
    "inox": ("stainless", "steel"),
    "copper": ("copper",),
    "alu": ("aluminium", "aluminum"),
    "brass": ("brass",),
    "bronze": ("bronze",),
    "lead": ("lead",),
}


def visible_term(text, term):
    normalized = re.sub(r"[-–—]", " ", text.lower())
    plural = "s?" if term in {"sheet", "plate", "strip", "rod", "bar", "opening", "bore"} else ""
    pattern = r"(?<![\w])" + re.escape(term) + plural + r"(?![\w])"
    return any(
        not re.search(r"\b(?:not|non|without)\s+$", normalized[max(0, hit.start()-16):hit.start()])
        for hit in re.finditer(pattern, normalized)
    )



def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate(payload, request, config, links, owners):
    """Reject confused IDs, modified bytes and shared/context-only material sources."""
    aid = request["asset_id"]
    if type(aid) is not int or type(payload.get("asset_id")) is not int or payload["asset_id"] != aid:
        raise ValueError("Exact numeric asset_id echo required")
    for key in config["description"]["required_fields"]:
        value = payload.get(key)
        if key == "asset_id":
            continue
        if key in ("material_hypotheses", "section_features", "uncertainties"):
            if not isinstance(value, list) or not all(isinstance(x, str) and x.strip() for x in value):
                raise ValueError("Invalid list field: " + key)
            if key != "uncertainties" and not value:
                raise ValueError("Empty field: " + key)
        elif not isinstance(value, str) or not value.strip():
            raise ValueError("Invalid text field: " + key)
    if digest(request["image"]) != request["sha256"] or digest(request["source"]) != request["sha256"]:
        raise ValueError("Source/input hash mismatch")
    allowed = set(config["identity"]["eligible_scopes"])
    eligible = [x for x in links if x["eligible"]]
    if any(x["scope"] not in allowed for x in eligible):
        raise ValueError("Context or parent marked eligible")
    # Callers supply links/owners for every asset sharing the source digest.
    codes = {x["product_code"] for x in eligible}
    if codes != {request["product_code"]}:
        raise ValueError("Material source requires one unique own-page owner")
    if not owners or any(
        x["product_code"] != request["product_code"] or x["state"] == "quarantined" for x in owners
    ):
        raise ValueError("Owner is missing, shared or quarantined")


def compare(payload, product):
    text = " ".join([payload["visible_section"], *payload["section_features"]]).lower()
    shape_terms = SHAPES.get(product["shape"])
    material_terms = MATERIALS.get(product["mat"])
    hypotheses = " ".join(payload["material_hypotheses"]).lower()
    shape_ok = bool(shape_terms) and all(any(visible_term(text, term) for term in group) for group in shape_terms)
    material_ok = bool(material_terms) and any(visible_term(hypotheses, term) for term in material_terms)
    return {
        "state": "compatible_with_uncertainty" if shape_ok and material_ok else "quarantined",
        "shape_compatible": shape_ok,
        "material_compatible": material_ok,
        "catalogue_shape": product["shape"],
        "catalogue_material": product["mat"],
        "observed_shape": payload["visible_section"],
        "observed_material_hypotheses": payload["material_hypotheses"],
        "uncertainties": payload["uncertainties"],
        "limitation": "Compatibility supports catalogue association; photographs do not establish alloy, coating, grade or dimensions.",
    }


def ingest(connection, request, payload, config):
    connection.row_factory = sqlite3.Row
    row = connection.execute("select sha1 from assets where id=?", (request["asset_id"],)).fetchone()
    if row is None:
        raise ValueError("Unknown asset")
    if hashlib.sha1(Path(request["source"]).read_bytes()).hexdigest() != row["sha1"]:
        raise ValueError("Input differs from inventoried asset hash")
    links = connection.execute(
        "select p.* from link_provenance p join assets a on a.id=p.asset_id where a.sha1=?", (row["sha1"],)
    ).fetchall()
    owners = connection.execute("select * from material_owners where sha1=?", (row["sha1"],)).fetchall()
    validate(payload, request, config, links, owners)
    for link in links:
        if link["eligible"]:
            page = connection.execute(
                "select page_bg from products where code=?", (link["product_code"],)
            ).fetchone()
            if (
                not page
                or link["source_page"] != page["page_bg"]
                or not link["page_sha256"]
                or not link["dom_location"]
            ):
                raise ValueError("Own-page provenance incomplete")
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    old = connection.execute(
        "select * from blind_descriptions where asset_id=?", (request["asset_id"],)
    ).fetchone()
    if old and (json.loads(old["payload"]) != payload or old["input_sha256"] != request["sha256"]):
        raise ValueError("Saved blind observation is immutable")
    now = datetime.now(timezone.utc).isoformat()
    connection.execute(
        "insert or ignore into blind_descriptions values(?,?,?,?,?)",
        (request["asset_id"], request["sha256"], config["description"]["model"], encoded, now),
    )
    # Persist blind record before opening catalogue facts.
    connection.commit()
    product = connection.execute("select * from products where code=?", (request["product_code"],)).fetchone()
    result = compare(payload, product)
    connection.execute(
        "insert or replace into material_checks values(?,?,?,?,?)",
        (request["asset_id"], request["product_code"], result["state"], json.dumps(result), now),
    )
    connection.commit()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--db", required=True)
    parser.add_argument("--ownership", required=True)
    parser.add_argument("--descriptions", required=True)
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text())
    with sqlite3.connect(args.db) as connection:
        results = []
        for request in json.loads(Path(args.ownership).read_text()):
            payload = json.loads((Path(args.descriptions) / f"{request['asset_id']}.json").read_text())
            result = ingest(connection, request, payload, config)
            results.append({"asset_id": request["asset_id"], **result})
        print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
