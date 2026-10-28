#!/usr/bin/env python3
"""Read a company's published price list into the catalogue the order page ships with.

    python3 pipeline/catalog.py <company> [--out FILE]     print the row accounting; optionally save

This file is the part every company shares: the price-table reader, the size reader for standard
metal sections, the row accounting and the catalogue's shape. What differs per company lives in
`companies/<slug>/mapping.py`: where the tables are, what each column means, how the "sold in"
text decodes, and how a table joins the company's own product pages.

The purchase rules, as data. Each item carries one selling rule `r`:
  {"k": "len", "l": [3, 6]}            sold in these lengths, in metres; the longest is the stock bar
  {"k": "len", "l": [6], "nocut": 1}   sold whole, uncut
  {"k": "any"}                          sold to any length; the price is per metre
  {"k": "strip"}                        a strip across the full sheet width, any length
  {"k": "half"}                         half sheets and whole sheets
  {"k": "whole"}                        whole pieces only
and the catalogue carries the company-wide rules once under `rules` (part-length surcharges, strip
surcharge, saw kerf, cut factors), each with the sentence it was read from.

A price is read, never estimated: a row with no price is counted as "on request" and stays out.
Rows in always equal rows kept plus rows left out, and the run fails when they differ.

Reads   <cache>/<company>/site/ (the mirrored price list and product pages)
Writes  the file named by --out, when given
"""
from __future__ import annotations

import collections
import html as htmllib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline import common  # noqa: E402

NUMBER = r"(\d+(?:\.\d+)?)"
FIELDS = ("code", "size", "price", "stock", "sold", "cut", "weight")
OUTCOMES = ("priced items", "price on request", "size unread", "blank row", "parked table row",
            "row with other columns")


def number(text: str | None) -> float:
    text = (text or "").replace(",", ".").strip()
    try:
        return float(text)
    except ValueError:
        return 0.0


def cells(row: str) -> list[str]:
    """The text of each cell in one table row."""
    return [htmllib.unescape(re.sub(r"<[^>]+>", "", cell)).replace("\xa0", " ").strip()
            for cell in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S)]


def tables(page: str, pattern: str) -> list[list[list[str]]]:
    """Every price table on a page, as rows of cell text. Commented-out markup is left out."""
    page = re.sub(r"<!--.*?-->", "", page, flags=re.S)
    return [[cells(row) for row in re.findall(r"<tr[^>]*>(.*?)</tr>", table, re.S)]
            for table in re.findall(pattern, page, re.S)]


def normal(size: str) -> str:
    """A size as typed by a person, in one spelling: Latin x, decimal points, single spaces."""
    size = size.replace("х", "x").replace("Х", "x").replace("X", "x").replace("×", "x")
    size = re.sub(r"(\d),(\d)", r"\1.\2", size)
    size = re.sub(r"\s*x\s*", "x", size)
    return re.sub(r"\s+", " ", size).strip()


def sizes(shape: str, raw: str) -> tuple[list[float] | None, str]:
    """A size text split into numbers for its shape, and the tail (grade, finish, standard)."""
    text = normal(raw)
    if shape in ("sq_tube", "rect_tube", "angle", "angle_u", "tee", "channel", "flat", "square"):
        match = re.match(r"^" + NUMBER + "x" + NUMBER + "(?:x" + NUMBER + r")?\s*(.*)$", text)
        if match:
            found = [float(match.group(1)), float(match.group(2))]
            return found + ([float(match.group(3))] if match.group(3) else []), match.group(4).strip()
    if shape in ("round_tube", "round"):
        match = re.match(r"^[ФFØ]\s*" + NUMBER + r"\.?(?:x\s*" + NUMBER + r")?\s*(.*)$", text)
        if match:
            found = [float(match.group(1))] + ([float(match.group(2))] if match.group(2) else [])
            return found, match.group(3).strip(" -")
    if shape == "hex":
        match = re.match(r"^S\s*" + NUMBER + r"\s*(.*)$", text)
        if match:
            return [float(match.group(1))], match.group(2).strip()
    if shape in ("ipe", "hea", "heb"):
        match = re.match(r"^(\d+)\s*(.*)$", text)
        if match:
            return [float(match.group(1))], ""
    if shape == "upn":
        match = re.match(r"^(?:UPN\s*)?" + NUMBER + "x" + NUMBER + r"\s*(.*)$", text)
        if match:
            return [float(match.group(1)), float(match.group(2))], match.group(3).strip()
    if shape in ("sheet", "chequer"):
        match = re.match(r"^" + NUMBER + "x" + NUMBER + "x" + NUMBER + r"\s*(.*)$", text)
        if match:
            return [float(match.group(1)), float(match.group(2)), float(match.group(3))], match.group(4).strip(" -")
    return None, text


def build(config: dict, site: Path, prefix: str = "", *, output_dir: Path | None = None) -> tuple[dict, collections.Counter, list]:
    """The catalogue, the row accounting and the rows left out with their reasons."""
    mapping = common.mapping(config)
    adapter = Path(config["dir"]) / "catalogue.py"
    if adapter.is_file():
        import contextlib
        import importlib.util
        import io
        spec = importlib.util.spec_from_file_location("company_catalogue", adapter)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        output = output_dir or common.cache_root() / config["slug"] / "catalogue"
        with contextlib.redirect_stdout(io.StringIO()):
            made, accounting, dropped = module.read_catalogue(site, config["priceList"]["path"], output)
        made["rules"] = mapping.RULES
        for category in made["cats"]:
            if category.get("img"):
                category["img"] = prefix + category["img"]
        count = collections.Counter({"rows": sum(len(c["items"]) for c in made["cats"]) + len(dropped),
                                     "priced items": sum(not i.get("q") for c in made["cats"] for i in c["items"]),
                                     "price on request": sum(bool(i.get("q")) for c in made["cats"] for i in c["items"]),
                                     "blank row": len(dropped)})
        if count["rows"] != sum(count[k] for k in OUTCOMES):
            raise ValueError("company adapter row accounting differs")
        return made, count, dropped
    price_list = site / config["priceList"]["path"]
    if not price_list.is_file():
        raise SystemExit(f"{config['slug']}: the price list {price_list} is missing from the mirror")
    page = price_list.read_text(encoding="utf-8", errors="replace")
    ids, pages = mapping.site_map(site, page)
    count: collections.Counter = collections.Counter()
    left_out, categories = [], []
    column = mapping.COLUMNS
    for table in tables(page, mapping.TABLE):
        code, name = mapping.title(table[0])
        head, rows = table[1], table[2:]
        count["rows"] += len(rows)
        if code in mapping.PARKED:
            count["parked table row"] += len(rows)
            left_out += [(code, (row + [""] * 2)[1], mapping.PARKED[code]) for row in rows]
            continue
        shape, surface, pattern, english = mapping.SHAPES[code]
        product = ids.get(code)
        linked = pages.get(product) or {}
        local = linked.get(config["defaultLanguage"]) or {}
        metal = local.get("metal") or mapping.MAT_METAL[surface]
        form = local.get("form") or mapping.SHAPE_FORM.get(shape) or mapping.form_of(name)
        if not linked:
            linked = pages.get(f"@{form}/{metal}") or {}
            local = linked.get(config["defaultLanguage"]) or {}
        items = []
        for row in rows:
            if len(row) != len(head):
                count["row with other columns"] += 1
                left_out.append((code, " | ".join(row)[:80], "columns differ from the table head"))
                continue
            read = dict(zip(head, row, strict=True))
            raw = read[column["size"]].strip()
            price, stock, weight = number(read[column["price"]]), number(read[column["stock"]]), number(read[column["weight"]])
            if not raw or raw == "0":
                count["blank row"] += 1
                left_out.append((code, raw, "blank"))
                continue
            if price <= 0:
                count["price on request"] += 1
                left_out.append((code, raw, "no price"))
                continue
            found, tail = sizes(shape, raw)
            if found is None and shape != "special":
                count["size unread"] += 1
                left_out.append((code, raw, "size"))
                continue
            item_surface = mapping.surface(surface, raw, tail)
            item = {"c": read[column["code"]].strip(), "s": raw, "p": price, "L": stock,
                    "r": mapping.sale(read[column["sold"]], stock, shape),
                    "cut": number(read[column["cut"]]), "w": weight}
            if found:
                item["d"] = [int(value) if float(value).is_integer() else value for value in found]
            if tail:
                item["t"] = tail
            translated = mapping.tail_en(tail) if tail else ""
            if translated and translated != tail:
                item["te"] = translated
            if item_surface != surface:
                item["m"] = item_surface
            if shape == "special":
                item["se"] = mapping.tail_en(raw)
            items.append(item)
            count["priced items"] += 1
        if not items:
            count["tables with nothing priced"] += 1
            continue
        def at(language: str, key: str) -> str:
            return (linked.get(language) or {}).get(key, "")
        picture = mapping.local_image(at(config["defaultLanguage"], "img"))
        categories.append({
            "code": code, "pid": product, "metal": metal, "form": form, "shape": shape, "mat": surface,
            "pat": pattern, config["defaultLanguage"]: name, "en": english,
            "img": prefix + picture if picture else "",
            "url": {language: (prefix + at(language, "url")) if at(language, "url") else ""
                    for language in config["languages"]},
            "items": items,
        })
    if not count["rows"]:
        raise SystemExit(f"{config['slug']}: {price_list} holds no price table that TABLE in mapping.py matches")
    accounted = sum(count[outcome] for outcome in OUTCOMES)
    if accounted != count["rows"]:
        raise SystemExit(f"{config['slug']}: {count['rows']} rows in, {accounted} accounted for")
    metal_order = {entry[0]: index for index, entry in enumerate(mapping.METALS)}
    form_order = {entry[0]: index for index, entry in enumerate(mapping.FORMS)}
    categories.sort(key=lambda c: (metal_order.get(c["metal"], 99), form_order.get(c["form"], 99), c["code"]))

    def used(table: list, key: str) -> list[dict]:
        local = config["defaultLanguage"]
        named = [{"id": slug, local: own, "en": english} for slug, own, english in table
                 if any(category[key] == slug for category in categories)]
        extra = sorted({category[key] for category in categories} - {entry[0] for entry in table})
        return named + [{"id": slug, local: slug, "en": slug} for slug in extra]

    catalog = {
        "company": config["name"], "asOf": mapping.as_of(site), "currency": config.get("currency", "EUR"),
        "vat": config.get("vat", 0), "source": config["priceList"]["url"],
        "metals": used(mapping.METALS, "metal"), "forms": used(mapping.FORMS, "form"),
        "rules": mapping.RULES, "cats": categories,
    }
    return catalog, count, left_out


def photos(catalog: dict, prefix: str = "") -> set[str]:
    """The site paths of the company's own photo for each category; the order page shows them."""
    return {category["img"][len(prefix):].lstrip("/") for category in catalog["cats"] if category["img"]}


def report(catalog: dict, count: collections.Counter, left_out: list) -> str:
    lines = [f"{len(catalog['cats'])} categories, {count['priced items']} priced sizes, "
             f"prices valid on {catalog['asOf'] or 'a date the site leaves unstated'}",
             f"rows in {count['rows']} = " + " + ".join(f"{count[o]} {o}" for o in OUTCOMES if count[o])]
    lines += [f"category {c['code']} has no page on the site" for c in catalog["cats"]
              if not any(c["url"].values())]
    lines += [f"category {c['code']} has no photo" for c in catalog["cats"] if not c["img"]]
    return "\n".join(lines)


def dump(catalog: dict) -> str:
    return json.dumps(catalog, ensure_ascii=False, separators=(",", ":"))


def main(argv: list[str]) -> int:
    if len(argv) not in (2, 4) or (len(argv) == 4 and argv[2] != "--out"):
        print(__doc__.strip().splitlines()[2].strip())
        return 2
    config = common.company(argv[1])
    catalog, count, left_out = build(config, common.site_dir(config["slug"]), common.prefix_of(config))
    print(report(catalog, count, left_out))
    if len(argv) == 4:
        Path(argv[3]).write_text(dump(catalog), encoding="utf-8")
        print(f"written to {argv[3]} ({len(dump(catalog).encode())} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
