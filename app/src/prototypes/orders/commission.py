"""Initialize a company's persistent store from a reviewed built catalogue, once."""

from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from pathlib import Path

from store import CompanyStore

ALREADY_COMMISSIONED = "The company store is commissioned. Use the checked refresh workflow."


def commission(root: Path, state: Path, config_path: Path) -> dict:
    config = json.loads(config_path.read_text())
    slug = config["slug"]
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug):
        raise ValueError("Choose the company slug in the reviewed configuration.")
    built_config = root / slug / "rocoto/configuration.json"
    if built_config.is_file():
        config = json.loads(built_config.read_text())
        if not isinstance(config, dict) or config.get("slug") != slug:
            raise ValueError("Use this company's built configuration.")
    catalogue = root / slug / "rocoto/catalog.json"
    catalog = json.loads(catalogue.read_text())
    path = state / "companies" / slug / "company.db"
    if path.exists() or path.is_symlink():
        raise ValueError(ALREADY_COMMISSIONED)
    path.parent.mkdir(parents=True, exist_ok=True)
    # A private sibling ensures one filesystem for atomic, no-replace publication.
    with tempfile.TemporaryDirectory(prefix=".commission-", dir=path.parent) as temporary:
        candidate = Path(temporary) / "company.db"
        store = CompanyStore(candidate)
        try:
            result = store.ingest_catalog(catalog, config, actor="commission", evidence=str(catalogue))
            if store.export_catalog() != catalog:
                raise ValueError("Catalogue projection differs from its reviewed input.")
            if store.db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()[0]:
                raise ValueError("The candidate database checkpoint is busy.")
            # The final database is self-contained before its name becomes visible.
            store.db.execute("PRAGMA journal_mode=DELETE")
        finally:
            store.close()
        with candidate.open("rb") as handle:
            os.fsync(handle.fileno())
        try:
            os.link(candidate, path)
        except FileExistsError:
            raise ValueError(ALREADY_COMMISSIONED) from None
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(commission(args.root, args.state, args.config)))


if __name__ == "__main__":
    main()
