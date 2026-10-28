"""CLI for dry runs and one-family technical-reference renders."""

import argparse
import json
import os
import subprocess
from pathlib import Path

from .catalogue import plan_catalogue, write_manifest


def parser():
    result = argparse.ArgumentParser()
    result.add_argument("--catalogue", required=True)
    result.add_argument("--output", required=True)
    result.add_argument("--family", action="append", default=[])
    result.add_argument("--dry-run", action="store_true")
    result.add_argument("--blender", default=os.environ.get("BLENDER", "blender"))
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    plan = plan_catalogue(args.catalogue, args.output, args.family)
    if args.dry_run:
        print(json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if len(plan["jobs"]) != 1:
        raise SystemExit("render requires exactly one --family; use --dry-run to inspect a larger plan")
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    job = plan["jobs"][0]
    scene = Path(__file__).with_name("scene.py")
    command = [
        args.blender,
        "-b",
        "--factory-startup",
        "-P",
        str(scene),
        "--",
        "--shape",
        job["shape"],
        "--dims",
        ",".join(f"{value:g}" for value in job["dimensions_mm"]),
        "--mat",
        job["material"],
        "--rig",
        "grey",
        "--cam",
        "hero",
        "--out",
        job["output"],
        "--res",
        "900x600",
        "--samples",
        "24",
        "--threads",
        "2",
        "--pattern",
        job.get("pattern", ""),
    ]
    if job["seam"] == "none" and job["shape"] in {"sq_tube", "rect_tube", "round_tube"}:
        command += ["--weld-mode", "seamless"]
    elif job["seam"] == "spiral":
        command += ["--weld-mode", "spiral"]
    subprocess.run(command, check=True)
    manifest = output / "geometry-manifest.json"
    write_manifest(manifest, plan, plan["jobs"])
    print(manifest)
    return 0
