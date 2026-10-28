"""Evidence-backed surface-zone contract shared by all three product views."""

ZONES = ("outside", "inside", "cut_face", "coating_or_cladding")
FIELDS = (
    "bulk_grade_alloy",
    "manufacturing_route",
    "finish",
    "coating_material",
    "coating_thickness",
    "grain_orientation",
    "cut_method",
    "expected_appearance",
)


def validate_zones(contract):
    if not contract.get("product_code") or not contract.get("expert_review_evidence"):
        raise ValueError("Product identity and expert review evidence required")
    if set(contract.get("zones", {})) != set(ZONES):
        raise ValueError("Declare outside, inside, cut_face and coating_or_cladding zones")
    for name, zone in contract["zones"].items():
        if zone.get("applicability") not in ("applicable", "not_applicable", "unknown"):
            raise ValueError(f"{name}: explicit applicability required")
        for field in FIELDS:
            item = zone.get(field, {})
            if item.get("status") not in ("documented", "unknown", "not_applicable"):
                raise ValueError(f"{name}.{field}: evidence status required")
            if item["status"] == "documented" and (not item.get("value") or not item.get("sources")):
                raise ValueError(f"{name}.{field}: documented values need source evidence")
        if not isinstance(zone.get("unknowns"), list):
            raise ValueError(f"{name}: unknowns list required")
        if zone.get("different_bulk_metal") and not zone.get("different_bulk_metal_evidence"):
            raise ValueError("A different cut-face bulk metal requires documented construction evidence")
    grade = contract.get("grade_verified_by")
    if grade not in ("manufacturer_specification", "material_certificate", "unknown"):
        raise ValueError("Images cannot certify grade or alloy")
    return contract


def material_clause(contract):
    """Compile compact photographic instructions; evidence remains in the manifest."""
    validate_zones(contract)
    lines = [
        "Keep the same material zones across all three views. Exterior finish and raw cut face have distinct surface treatment; bulk alloy remains shared unless documented construction says otherwise."
    ]
    for name, zone in contract["zones"].items():
        if zone["applicability"] == "not_applicable":
            continue
        clauses = []
        for field in ("finish", "coating_material", "grain_orientation", "cut_method", "expected_appearance"):
            item = zone[field]
            if item["status"] == "documented":
                clauses.append(str(item["value"]))
        if zone.get("render_intent"):
            clauses.append(zone["render_intent"])
        if clauses:
            lines.append(name.replace("_", " ") + ": " + "; ".join(dict.fromkeys(clauses)))
    lines.append(
        "Preserve unspecified grade, coating thickness and cutting method as unknown; avoid invented layers, coating on raw cut faces or exaggerated microscopic damage."
    )
    return "\n".join(lines)


def material_review_plan(products):
    """All supplied catalogue types, including hardware, enter the same pre-generation hold."""
    return [
        {
            "product_code": p["product_code"],
            "catalogue": dict(p),
            "state": "held_pending_surface_zone_expert_review",
            "required_zones": list(ZONES),
            "required_evidence": [
                "manufacturer specifications or standards",
                "owned product photos",
                "expert reconciliation of knowns and unknowns",
            ],
            "shots": ["whole_piece", "cut_end", "surface_macro"],
        }
        for p in products
    ]
