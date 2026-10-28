#!/usr/bin/env python3
"""Prepare one private native manufacturer harness artifact without starting a model turn."""

from __future__ import annotations

import argparse
import importlib.util
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
PACK = HERE / "packs" / "manufacturer"
MARKER = ".rocoto-manufacturer-artifact"


def _load_builder(source: Path):
    path = source / "deploy" / "build_preview.py"
    if not path.is_file():
        raise ValueError("Choose a native harness source with deploy/build_preview.py.")
    spec = importlib.util.spec_from_file_location("manufacturer_native_build_preview", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _reset_output(output: Path) -> None:
    if output.exists():
        if output.is_symlink() or not (output / MARKER).is_file():
            raise ValueError("The build output must be a previously prepared manufacturer artifact.")
        shutil.rmtree(output)
    output.mkdir(mode=0o700, parents=True)
    (output / MARKER).write_text("native manufacturer harness\n", encoding="utf-8")


def _install_output(prepared: Path, output: Path) -> None:
    backup = output.with_name(output.name + ".previous")
    if backup.exists():
        if backup.is_symlink() or not (backup / MARKER).is_file():
            raise ValueError("The previous build path is not a manufacturer artifact.")
        shutil.rmtree(backup)
    moved = False
    try:
        if output.exists():
            if output.is_symlink() or not (output / MARKER).is_file():
                raise ValueError("The build output is not a manufacturer artifact.")
            os.replace(output, backup)
            moved = True
        os.replace(prepared, output)
    except BaseException:
        if moved and not output.exists():
            os.replace(backup, output)
        raise
    if backup.exists():
        shutil.rmtree(backup)


def _manufacturer_files(template) -> set[Path]:
    files = {PACK / "pack.json"}
    files.update(PACK / name for name in template.files)
    files.update(path for path in PACK.rglob("*.py") if "__pycache__" not in path.parts)
    files.update(PACK.rglob("*.json"))
    web = PACK / "web"
    if web.is_dir():
        files.update(path for path in web.rglob("*") if path.is_file())
    return files


def _copy_manufacturer(template, destination: Path) -> int:
    count = 0
    for source in sorted(_manufacturer_files(template)):
        if source.is_symlink() or source.resolve() != source.absolute() or not source.is_file():
            raise ValueError(f"Manufacturer pack file must be a regular file: {source}")
        target = destination / source.relative_to(PACK)
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        shutil.copy2(source, target)
        count += 1
    return count


def _run(command: list[str], *, environment: dict[str, str] | None = None) -> None:
    subprocess.run(command, check=True, env=environment)


def prepare(args) -> dict:
    source = args.harness_source.resolve(strict=True)
    database = args.database.resolve(strict=True)
    output = args.output.resolve()
    prepared = output.with_name(output.name + ".preparing")
    state = args.state.resolve()
    if output.is_relative_to(source) or output.is_relative_to(REPO):
        raise ValueError("Keep the private build outside both source checkouts.")
    _reset_output(prepared)
    state.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(state, 0o700)

    builder = _load_builder(source)
    layout = builder.source_layout(source, "bare")
    selected, missing = builder.artifact_files(layout.REPO, source, vertical_id="bare")
    if missing:
        raise ValueError("Track the complete native harness runtime: " + ", ".join(missing))
    shared_count = builder.copy_artifact(layout.REPO, prepared, selected)

    import pack

    template = pack.load(PACK)
    artifact_harness = prepared / builder.ARTIFACT_ROOT
    vertical = artifact_harness / "verticals" / "manufacturer"
    manufacturer_count = _copy_manufacturer(template, vertical)

    environment = {
        **os.environ,
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": os.pathsep.join((str(REPO), str(artifact_harness))),
        "ROCOTO_VERTICAL": "manufacturer",
    }
    _run(
        [
            sys.executable,
            "-c",
            "import layout; layout.install(); import pack; "
            "p=pack.load('manufacturer'); p.import_host(); p.import_tool_families()",
        ],
        environment=environment,
    )
    _run(
        [
            sys.executable,
            str(HERE / "harness_launcher.py"),
            "--harness-source",
            str(artifact_harness),
            "--database",
            str(database),
            "--company",
            args.company,
            "--workspace",
            str(state),
            "--actor",
            args.principal,
            "--role",
            "operator",
            "check",
        ],
        environment=environment,
    )

    final_harness = output / builder.ARTIFACT_ROOT
    start = prepared / "start-native.sh"
    command = [
        sys.executable,
        str(final_harness / "run.py"),
        "server",
        "--state",
        str(state),
        "--port",
        str(args.port),
    ]
    start.write_text(
        "#!/bin/sh\nset -eu\n"
        + f"export PYTHONPATH={shlex.quote(os.pathsep.join((str(REPO), str(final_harness))))}\n"
        + "export ROCOTO_VERTICAL=manufacturer\n"
        + "export ROCOTO_AGENT_AUTH_MODE=founder_local_chatgpt\n"
        + "exec "
        + " ".join(shlex.quote(value) for value in command)
        + "\n",
        encoding="utf-8",
    )
    start.chmod(0o700)
    _install_output(prepared, output)
    return {
        "artifact": final_harness,
        "state": state,
        "start": output / "start-native.sh",
        "shared_files": shared_count,
        "manufacturer_files": manufacturer_count,
    }


def main(argv=None) -> int:
    root = REPO / ".local/native-manufacturer"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--harness-source",
        type=Path,
        default=REPO / "harness",
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=REPO / ".local/first-result/orders/companies/sample-hardware/company.db",
    )
    parser.add_argument("--company", default="sample-hardware")
    parser.add_argument("--principal", default="sample-owner")
    parser.add_argument("--output", type=Path, default=root / "build")
    parser.add_argument("--state", type=Path, default=root / "state")
    parser.add_argument("--port", type=int, default=18580)
    args = parser.parse_args(argv)
    result = prepare(args)
    print(
        f"Prepared {result['shared_files']} shared and {result['manufacturer_files']} manufacturer "
        f"files. Start script: {result['start']}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1) from None
