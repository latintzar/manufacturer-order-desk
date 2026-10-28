#!/usr/bin/env python3
"""Start a company folder from its website address.

    python3 pipeline/new_company.py <slug> <url>

Writes `companies/<slug>/` with a company.json to fill in, a mapping.py with every hook the
catalogue reader calls, and a NOTES.md for what is assumed and what only the company can answer.
The slug becomes the company's path on the preview: `https://orders.example.test/<slug>/`.
Each empty value in company.json is named by the next command that needs it.

Reads   nothing
Writes  companies/<slug>/company.json, mapping.py, NOTES.md (an existing folder is left alone)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline import common  # noqa: E402

MAPPING = '''"""{name}: our reading of the company's price list and site, as data.

Source: {url} (write the price-list address and the date you read it).
`pipeline/catalog.py` runs on these tables; every decision about this company's list is here.
"""
from __future__ import annotations

import re

# One price table: a pattern whose single group is the table's rows.
TABLE = r"<table[^>]*>(.*?)</table>"
# Our field: the column head exactly as the company prints it. Write one example row beside each.
COLUMNS = {{"code": "", "size": "", "price": "", "stock": "", "sold": "", "cut": "", "weight": ""}}
# Tables that wait for a later pass, with the reason.
PARKED: dict[str, str] = {{}}
# category code: (shape, surface, plate pattern, name in plain trade English)
# shapes: sq_tube rect_tube round_tube flat round square hex angle angle_u tee ipe hea heb channel upn
#         sheet chequer special    surfaces: hr cr galv inox alu copper brass bronze lead wrought
SHAPES: dict[str, tuple[str, str, str, str]] = {{}}
# The company's own navigation, in its order: (slug, its name, plain English).
METALS: list[tuple[str, str, str]] = []
FORMS: list[tuple[str, str, str]] = []
SHAPE_FORM: dict[str, str] = {{}}
MAT_METAL: dict[str, str] = {{}}
# Company-wide selling rules, each with the sentence it was read from and its page.
RULES: dict = {{"source": ""}}


def title(first_row: list[str]) -> tuple[str, str]:
    """A table's first row as (category code, category name)."""
    code, _, name = first_row[0].partition(" ")
    return code, name.strip()


def form_of(name: str) -> str:
    """The form a category belongs to when its shape names none."""
    return "other"


def tail_en(text: str) -> str:
    """The grade or finish text in English."""
    return text


def surface(default: str, raw: str, tail: str) -> str:
    """One row's own surface where its size text says so."""
    return default


def sale(raw: str, stock: float, shape: str) -> dict:
    """The "sold in" text as a selling rule; the kinds are listed in pipeline/catalog.py."""
    listed = [float(value) for value in re.findall(r"\\d+(?:\\.\\d+)?", raw)]
    if stock and listed:
        return {{"k": "len", "l": sorted({{value for value in listed if value <= stock}} | {{stock}})}}
    return {{"k": "whole"}}


def local_image(url: str) -> str:
    """A photo address as a root-relative path inside the mirror."""
    return url


def as_of(site) -> str:
    """The date the company prints beside its prices, as the company writes it."""
    return ""


def site_map(site, price_list: str) -> tuple[dict, dict]:
    """Join each price table to its product page.

    Returns ({{category code: page id}}, {{page id: {{language: {{form, metal, url, img}}}}}}).
    """
    return {{}}, {{}}
'''

NOTES = """# {name}: what is assumed, and what only the company can answer

Source: {url}

## Assumed

- (each value the site leaves open and the catalogue or the order page fills in, with its reason)

## Ask the company

1. (each question whose answer changes what the page charges or estimates)

## Rows left out

(paste the row accounting from `pipeline/catalog.py {slug}`: rows in = kept + left out)
"""


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__.strip().splitlines()[2].strip())
        return 2
    slug, url = argv[1], argv[2]
    parts = urlsplit(url)
    if not common.SLUG.fullmatch(slug) or slug in common.RESERVED:
        raise SystemExit(f"{slug}: a company slug is lowercase letters, digits and hyphens")
    if parts.scheme != "https" or not parts.hostname:
        raise SystemExit("the company's address starts with https://")
    folder = common.COMPANIES / slug
    if folder.exists():
        raise SystemExit(f"{folder} stands already; it is left as it is")
    folder.mkdir(parents=True)
    name = parts.hostname.removeprefix("www.")
    company = {
        "slug": slug, "name": {"en": ""}, "source": f"https://{parts.hostname}/",
        "priceList": {"url": "", "path": ""}, "currency": "EUR", "vat": 0,
        "languages": {"en": "/"}, "defaultLanguage": "en", "home": {"en": "index.html"},
        "accent": "", "logo": "", "tableHook": "", "orderPrefix": "", "delivery": 0,
        "hours": {}, "shop": {"backlog": 95, "perLine": 6, "perCut": 1.5, "perSheetCut": 2.5},
        "strings": {"en": {key: "" for key in common.ADDRESS_STRINGS}},
        "geo": {"regions": [], "origin": {}},
        "mirror": {"maxPages": 600, "maxBytes": 314572800, "first": []},
        "drop": [], "shrink": {}, "photos": {"width": 960, "quality": 80}, "keep": [],
        "check": {"search": "", "category": ""},
    }
    (folder / "company.json").write_text(json.dumps(company, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (folder / "mapping.py").write_text(MAPPING.format(name=name, url=url), encoding="utf-8")
    (folder / "NOTES.md").write_text(NOTES.format(name=name, url=url, slug=slug), encoding="utf-8")
    print(f"{folder} made. Next: python3 pipeline/mirror.py {slug} "
          "(it needs only `source`; the other empty values are named as each step asks for them)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
