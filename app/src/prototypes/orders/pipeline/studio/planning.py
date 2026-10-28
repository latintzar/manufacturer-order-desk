"""Adapter-independent ownership reconciliation and three-shot coverage planning."""

from .schema import SHOTS


def reconcile_links(occurrences):
    """Occurrences are adapter evidence, grouped by original asset hash (including aliases)."""
    grouped = {}
    for row in occurrences:
        grouped.setdefault(row["source_sha256"], []).append(dict(row))
    result = []
    for digest, rows in grouped.items():
        eligible = [
            r
            for r in rows
            if r.get("scope") == "own_page"
            and r.get("source_page") == r.get("product_page")
            and r.get("page_sha256")
            and r.get("dom_evidence")
        ]
        owners = {r["product_code"] for r in eligible}
        result.append(
            {
                "source_sha256": digest,
                "occurrences": rows,
                "status": "unique_owner" if len(owners) == 1 else "shared_owners" if owners else "ineligible",
                "owner": next(iter(owners)) if len(owners) == 1 else None,
            }
        )
    return result


def four_shot_plan(products, structural_refs):
    """Return explicit missing-input holds; dimensions come from supplied catalogue evidence."""
    return [
        {
            "product_code": p["product_code"],
            "shot": shot,
            "catalogue": dict(p),
            "structure": structural_refs.get(p["product_code"], {}).get(shot),
            "state": "ready_for_material_gate"
            if structural_refs.get(p["product_code"], {}).get(shot)
            else "held_missing_structure",
        }
        for p in products
        for shot in SHOTS
    ]
