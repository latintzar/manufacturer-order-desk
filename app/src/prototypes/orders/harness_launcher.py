#!/usr/bin/env python3
"""Isolated manufacturer tool host using the native harness's actual pack and registry.

check validates pack/registry; specs prints native dynamic tools; call dispatches once;
stdio dispatches one JSON object per line. This is a local authenticated tool bridge,
not the video UI, an LLM runner or a scheduler. Run from the checkout root.
"""

from __future__ import annotations

import argparse
import importlib
import importlib.util
import json
import os
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace

# The source checkout is read-only even when its pure contract modules import helpers.
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
from app.src.prototypes.orders import orders_tools as family  # noqa: E402
from app.src.prototypes.orders.store import CompanyStore  # noqa: E402

if sys.modules.setdefault("orders_tools", family) is not family:
    raise RuntimeError("orders_tools already names another module in this process.")


def load_contract(harness_source):
    source = Path(harness_source).resolve()
    layered = (source / "layout.py").is_file() and (source / "sdk" / "pack.py").is_file()
    path = source / "sdk" / "pack.py" if layered else source / "pack.py"
    if not path.is_file():
        raise ValueError("Choose a harness source containing layout.py plus sdk/pack.py, or legacy pack.py.")
    if layered:
        layout_path = source / "layout.py"
        existing = sys.modules.get("layout")
        if existing is not None and Path(existing.__file__).resolve() != layout_path:
            raise RuntimeError("layout already names another harness source in this process.")
        if existing is None:
            layout_spec = importlib.util.spec_from_file_location("layout", layout_path)
            layout = importlib.util.module_from_spec(layout_spec)
            sys.modules["layout"] = layout
            layout_spec.loader.exec_module(layout)
        else:
            layout = existing
        layout.install()
        contract = importlib.import_module("pack")
        if Path(contract.__file__).resolve() != path:
            raise RuntimeError("pack already names another harness source in this process.")
        return contract
    spec = importlib.util.spec_from_file_location("orders_harness_pack_contract", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def check_pack(harness_source):
    contract = load_contract(harness_source)
    template = contract.load(HERE / "packs" / "manufacturer")
    # Load the actual registry in this new process; no service or store is started.
    source = str(Path(harness_source).resolve())
    if source not in sys.path:
        sys.path.append(source)
    try:
        monitoring = importlib.import_module("monitoring_tools")
    except ModuleNotFoundError as error:
        if error.name != "monitoring_tools":
            raise
        tool_families = importlib.import_module("tool_families")
        monitoring = SimpleNamespace(
            registry=tool_families.validate_families,
            declared=lambda registered, name, args: registered.business._validate(
                args, registered.business.REGISTRY[name]["parameters"]
            ),
        )
    vertical_source = str(HERE / "packs" / "manufacturer")
    if vertical_source not in sys.path:
        sys.path.insert(0, vertical_source)
    declared = template.import_tool_families()
    if (
        not declared
        or set(declared[0].READ_NAMES) != set(family.READ_NAMES)
        or set(declared[0].WRITE_NAMES) != set(family.WRITE_NAMES)
    ):
        raise ValueError("Manufacturer pack must name its orders-owned tool adapter first.")
    monitoring.registry(declared)
    specs = [spec for registered in declared for spec in registered.specs(True)]
    names = [row["name"] for row in specs]
    tile_check = getattr(template, "check_tile_sets", None) or template.check_recipes
    problems = template.check_tools(names) + tile_check(specs)
    problems += [f"{skill}: missing {missing}" for skill, missing in template.skill_tool_gaps(names).items()]
    if problems:
        raise ValueError("; ".join(problems))
    return contract, template, monitoring


def open_store(database, company, writes=False):
    path = Path(database).resolve(strict=True)
    # Check existing company identity through a read-only connection before any schema open.
    probe = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    try:
        rows = probe.execute("SELECT id FROM company").fetchall()
        if rows != [(company,)]:
            raise PermissionError("The database belongs to another company.")
    finally:
        probe.close()
    if writes:
        return CompanyStore(path)
    # CompanyStore's read methods operate on this connection without initialization writes.
    store = object.__new__(CompanyStore)
    store.path = path
    store.db = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    store.db.row_factory = sqlite3.Row
    store.db.execute("PRAGMA query_only=ON")
    return store


def bind_workspace(contract, template, workspace, company, harness_source, database=None):
    workspace = Path(workspace).resolve()
    if workspace.is_relative_to(Path(harness_source).resolve()) or workspace.is_relative_to(HERE):
        raise ValueError("Use a private state directory outside the source checkouts.")
    marker = workspace / ".manufacturer-company.json"
    old = json.loads(marker.read_text()) if marker.exists() else None
    if old and old.get("company") != company:
        raise PermissionError("This harness workspace belongs to another company.")
    contract.bind(workspace, template)
    if database is None:
        if old is None:
            raise ValueError("Bind the manufacturer workspace to its company database.")
        return workspace
    database = Path(database).resolve(strict=True)
    probe = sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)
    try:
        if probe.execute("SELECT id FROM company").fetchall() != [(company,)]:
            raise PermissionError("The database belongs to another company.")
    finally:
        probe.close()
    value = {
        "schema": "rocoto.manufacturer-workspace.v2",
        "company": company,
        "database": str(database),
    }
    if old == value:
        if marker.stat().st_mode & 0o077:
            raise PermissionError("Keep the manufacturer company binding private.")
        return workspace
    if old and old.get("schema") != "rocoto.manufacturer-workspace.v1":
        raise PermissionError("This harness workspace has another company database binding.")
    try:
        temporary = marker.with_name(marker.name + ".tmp")
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, marker)
    except FileExistsError:
        raise PermissionError("Remove the stale manufacturer binding update file.") from None
    return workspace


def prompt(template):
    return "\n\n".join(
        [
            template.prompt("system"),
            template.prompt("fixed_chat_common") or "",
            (HERE / "packs/manufacturer/prompts/onboarding.md").read_text(),
        ]
    )


def dispatch(context, request, monitoring):
    if not isinstance(request, dict) or set(request) != {"name", "arguments"}:
        raise ValueError("Use exactly name and arguments; the host fixes identity and company.")
    name, args = request["name"], request["arguments"]
    if not isinstance(name, str) or not isinstance(args, dict):
        raise ValueError("Use a tool name string and an arguments object.")
    if name not in {row["name"] for row in family.available(context)}:
        raise PermissionError("The authenticated company capability does not expose this tool.")
    monitoring.declared(family, name, args)
    return family.read(context, name, args) if name in family.READ_NAMES else family.call(context, name, args)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--harness-source", required=True, type=Path)
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--company", required=True)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--actor", default=f"local-uid:{os.getuid()}")
    parser.add_argument(
        "--role",
        choices=["public", "operator", "owner", "admin"],
        default="public",
        help="Trusted local startup authority; never an agent/request field.",
    )
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--evidence", default="")
    parser.add_argument("command", choices=["check", "specs", "prompt", "call", "stdio"])
    parser.add_argument("--request", help="JSON object for one call; stdio takes one object per line.")
    args = parser.parse_args(argv)
    if args.write and not args.evidence:
        parser.error("--write requires host-supplied --evidence")
    contract, template, monitoring = check_pack(args.harness_source)
    store = open_store(args.database, args.company, args.write)
    try:
        workspace = bind_workspace(
            contract, template, args.workspace, args.company, args.harness_source, args.database
        )
        context = family.CompanyContext(store, args.company, args.actor, args.role, args.evidence, args.write)
        if args.command == "check":
            result = {
                "ok": True,
                "pack": template.id,
                "revision": template.revision,
                "company": context.company,
                "actor": context.actor,
                "role": context.role,
                "workspace": str(workspace),
                "reads": len(family.READ_NAMES),
                "writes": len(family.WRITE_NAMES),
                "available_tools": len(family.available(context)),
                "host_only_tools": sorted(family.HOST_ONLY),
                "registry": "native family validator and declared argument schema",
                "runtime": "local tool bridge; video UI, model execution and scheduling remain separate",
            }
        elif args.command == "specs":
            result = family.available(context)
        elif args.command == "prompt":
            print(prompt(template))
            return 0
        elif args.command == "call":
            result = dispatch(context, json.loads(args.request or "{}"), monitoring)
        else:
            for line in sys.stdin:
                if not line.strip():
                    continue
                try:
                    value = {"ok": True, "result": dispatch(context, json.loads(line), monitoring)}
                except (ValueError, PermissionError, KeyError, sqlite3.Error) as error:
                    value = {"ok": False, "error": str(error)}
                print(json.dumps(value, ensure_ascii=False, allow_nan=False), flush=True)
            return 0
        print(json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2))
    finally:
        store.close()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, PermissionError, OSError, sqlite3.Error) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1) from None
