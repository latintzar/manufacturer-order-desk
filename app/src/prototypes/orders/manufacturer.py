"""The executable manufacturer stage contract and its generated readable playbook.

An agent reads `next` and executes the declared goal with its tools. `check` evaluates the
stage's machine gate. The agent records successful gates through run tools. Approval
artifacts are supplied by the operator; a stage never writes its own approval.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

PACK = Path(__file__).parent / "packs/manufacturer"

MANAGED_RECIPE = "catalogue_readiness"
MANAGED_ROLES = {
    "catalogue_reader": {
        "profile": "reader",
        "title": "Catalogue reader",
        "job": "Read catalogue coverage and source evidence for a manufacturer run.",
        "instructions": "prompts/catalogue-reader.md",
        "tools": ["catalog_find", "catalog_read", "run_stage_plan", "run_read"],
        "limit_cents": 20,
    },
    "readiness_judge": {
        "profile": "judge",
        "title": "Readiness judge",
        "job": "Judge catalogue and operational readiness from recorded evidence.",
        "instructions": "prompts/readiness-judge.md",
        "tools": ["catalog_read", "quote_ready", "run_stage_plan", "run_read"],
        "limit_cents": 30,
    },
}


def contract() -> dict:
    return json.loads((PACK / "stages.json").read_text())


def stage_plan(stage_id: str | None = None) -> dict:
    """Load one reviewed stage on demand without accepting a file path or running it."""
    data = contract()
    role_by_stage = {"catalogue": "catalogue_reader", "store": "readiness_judge"}
    result = {"revision": data["revision"], "model_selection": "planning_only"}
    if stage_id is None:
        result["stages"] = [
            {
                **{key: stage[key] for key in ("id", "depends_on", "model_profile")},
                "declared_managed_role": role_by_stage.get(stage["id"]),
            }
            for stage in data["stages"]
        ]
        return result
    stage = next((row for row in data["stages"] if row["id"] == stage_id), None)
    if stage is None:
        raise ValueError("Unknown manufacturer stage.")
    result.update(stage=stage, model_profile=data["model_profiles"][stage["model_profile"]])
    if stage["id"] in role_by_stage:
        result["declared_managed_role"] = role_by_stage[stage["id"]]
    result["model_binding"] = data["model_binding"]
    result["orchestration"] = data["orchestration"]
    return result


def managed_roles(data: dict) -> list[dict]:
    roles = []
    for role_id, declared in MANAGED_ROLES.items():
        profile = data["model_profiles"][declared["profile"]]
        roles.append(
            {
                "id": role_id,
                "title": declared["title"],
                "job": declared["job"],
                "instructions": declared["instructions"],
                "launched_by": ["organization", "office"],
                "tools": declared["tools"],
                "model": profile["managed_model"],
                "effort": profile.get("reasoning", "high"),
                "limit_cents": declared["limit_cents"],
                "timeout_seconds": 180,
                "per_turn": 1,
            }
        )
    return roles


def managed_recipe(data: dict) -> list[dict]:
    stages = {stage["id"]: stage for stage in data["stages"]}
    catalogue, store = stages["catalogue"], stages["store"]
    return [
        {
            "id": MANAGED_RECIPE,
            "revision": f"{MANAGED_RECIPE}-1",
            "title": "Catalogue and readiness review",
            "job": "Review catalogue evidence and operational readiness without changing company records.",
            "instructions": "prompts/catalogue-readiness.md",
            "launched_by": ["organization", "office"],
            "steps": [
                {
                    "id": "catalogue",
                    "title": "Read catalogue evidence",
                    "instructions": catalogue["goal"],
                    "agent": "catalogue_reader",
                    "tools": MANAGED_ROLES["catalogue_reader"]["tools"],
                    "after": [],
                    "done_when": (
                        "The catalogue gate has been evaluated against recorded source evidence; "
                        "conflicts and missing evidence remain explicit."
                    ),
                },
                {
                    "id": "readiness",
                    "title": "Judge operational readiness",
                    "instructions": (
                        "Evaluate existing evidence for the store stage without ingesting facts, "
                        "reserving stock, booking capacity or changing company records. Read the "
                        f"source goal as the subject of review: {store['goal']} Verify every original "
                        "dependency in run_stage_plan before judging its gate."
                    ),
                    "agent": "readiness_judge",
                    "tools": MANAGED_ROLES["readiness_judge"]["tools"],
                    "after": ["catalogue"],
                    "done_when": (
                        "The store gate and every dependency in the original stage plan have current "
                        "evidence, or readiness is recorded as blocked with the missing evidence."
                    ),
                },
            ],
            "done_when": (
                "Catalogue coverage and operational readiness are recorded from current evidence, "
                "with unresolved gates left blocked."
            ),
        }
    ]


def managed_manifest(legacy: dict) -> dict:
    manifest = json.loads(json.dumps(legacy))
    manifest["schema"] = "rocoto.vertical.v1"
    manifest["revision"] = "manufacturer-2026-10-12-2"
    manifest["product"]["business"] = manifest["product"].pop("segment")
    manifest["tile_sets"] = []
    manifest["recipes"] = "recipes/catalogue-readiness.json"
    manifest["sub_agents"] = "sub_agents.json"
    manifest["ready_agents"] = manifest.pop("agent_templates")
    manifest["builtin_capabilities"] = {}
    return manifest


def check(stage: dict, state: Path, database: Path | None = None) -> dict:
    gate = stage["gate"]
    try:
        if "sql" in gate:
            if database is None:
                raise ValueError("A company database is required.")
            with sqlite3.connect(f"file:{database.resolve()}?mode=ro", uri=True) as connection:
                connection.execute("PRAGMA query_only=ON")
                actual = connection.execute(gate["sql"]).fetchone()[0]
        else:
            actual = json.loads((state / gate["artifact"]).read_text())
            for key in gate["path"].split("."):
                actual = actual[key]
        passed = actual == gate["expected"] if gate["operator"] == "eq" else actual >= gate["expected"]
        return {"stage": stage["id"], "passed": passed, "actual": actual, "expected": gate["expected"]}
    except (OSError, KeyError, TypeError, ValueError, sqlite3.Error) as exc:
        return {"stage": stage["id"], "passed": False, "reason": str(exc)}


def generate() -> None:
    data = contract()
    manifest_path = PACK / "pack.json"
    manifest = json.loads(manifest_path.read_text())
    for flow in manifest["flow"]:
        stage = next(s for s in data["stages"] if s["id"].replace("-", "_") == flow["stage"])
        flow["does"] = stage.get("summary", stage["goal"].split(". ")[0])
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    (PACK / "vertical.json").write_text(json.dumps(managed_manifest(manifest), indent=2) + "\n")
    (PACK / "sub_agents.json").write_text(json.dumps(managed_roles(data), indent=2) + "\n")
    recipes = PACK / "recipes"
    recipes.mkdir(exist_ok=True)
    (recipes / "catalogue-readiness.json").write_text(json.dumps(managed_recipe(data), indent=2) + "\n")
    lines = [
        "# Manufacturer run",
        "",
        "Generated from `stages.json` by `manufacturer.py generate`.",
        "",
        "One company URL starts the run. Each stage produces evidence and passes its gate before "
        "the next begins.",
        "",
        "## Models",
        "",
    ]
    for name, profile in data["model_profiles"].items():
        lines.append(f"- {name}: {profile['session_model']}. {profile['purpose']}.")
    lines += ["", data["model_binding"], "", "## Orchestration", ""]
    for instruction in data.get("orchestration", {}).values():
        lines += [instruction, ""]
    lines += ["## Stages", ""]
    for number, stage in enumerate(data["stages"], 1):
        lines += [
            f"### {number}. {stage['id']}",
            "",
            stage["goal"],
            "",
            f"Model profile: {stage['model_profile']}. Record: {', '.join(stage['record'])}.",
            "",
            "Gate: `" + json.dumps(stage["gate"], separators=(",", ":")) + "`.",
            "",
        ]
    imagery = json.loads((PACK / "imagery.json").read_text())
    geometry = imagery["geometry"]
    lines += [
        "## Picture geometry and framing",
        "",
        "Generated from `imagery.json`. Produce one consistent part across these views: "
        + ", ".join(imagery["sets"]["shots"])
        + ".",
        geometry["whole_piece"]["length"],
        geometry["whole_piece"]["framing"],
        "Shared studio: " + imagery["sets"]["studio"]["background"] + ".",
        imagery["sets"]["studio"]["reference"],
        imagery["sets"]["studio"]["lighting"],
        imagery["sets"]["studio"]["consistency"],
        "Record master geometry: " + ", ".join(geometry["master_geometry"]["fields"]) + ".",
        "Keep the same mesh across views; change cameras only. Check "
        + ", ".join(geometry["master_geometry"]["minimum_checks"])
        + ".",
        geometry["qa"]["before_generation"],
        geometry["qa"]["after_generation"],
        geometry["cost_discipline"],
        "",
    ]
    lines += [
        "## Execution",
        "",
        "Run `python manufacturer.py next --state <evidence-dir> --database <company.db>`.",
        "Carry out that stage using the declared tools and company-specific adapters. Record actor, "
        "actual model, calls, cost, retries and evidence in stage_runs. Use null for measurements "
        "the runtime does not expose.",
        "Run `python manufacturer.py check <stage> --state <evidence-dir> --database <company.db>` "
        "before marking a stage complete.",
        "Source facts, image references, company adapters and decisions live with that company's "
        "store. The template remains reusable.",
        "",
    ]
    text = "\n".join(lines)
    (PACK / "PLAYBOOK.md").write_text(text)
    (PACK / "prompts/onboarding.md").write_text(
        "# Manufacturer run\n\n"
        "Generated from stages.json by manufacturer.py generate.\n\n"
        "Read run_stage_plan with empty arguments for the stage index. Read run_read(stage_runs) "
        "for this company's recorded progress, then request run_stage_plan(stage=<id>) for the "
        "first unfinished stage whose dependencies have verified evidence. Load one stage at a time.\n\n"
        "Carry out that stage with the available tools and reviewed company adapters. A plan read "
        "does not execute its actions or pass its gate. Record missing capabilities as an office "
        "question; preserve the stage as unfinished. Evaluate the declared gate against its actual "
        "evidence before recording completion. A recorded narrative alone is not gate evidence.\n\n"
        "The pinned b512 runtime treats returned model profiles as planning metadata. The current "
        "managed runtime binds only the declared catalogue_reader and readiness_judge roles to "
        "their manifest models. Record actual model, calls, costs, retries and evidence; "
        "keep unexposed measurements null. Use the operator's current delivery scope. Keep "
        "the full private source catalogue and the public sales selection distinct. Sending, "
        "publication and spending use their existing explicit grants.\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("command", choices=["generate", "next", "check"])
    parser.add_argument("stage", nargs="?")
    parser.add_argument("--state", type=Path)
    parser.add_argument("--database", type=Path)
    args = parser.parse_args()
    if args.command == "generate":
        generate()
        return 0
    if args.state is None:
        parser.error("--state is required")
    data = contract()
    for stage in data["stages"]:
        if args.command == "check" and stage["id"] != args.stage:
            continue
        result = check(stage, args.state, args.database)
        if args.command == "check":
            print(json.dumps(result))
            return 0 if result["passed"] else 1
        if not result["passed"]:
            print(
                json.dumps(
                    {"stage": stage, "model": data["model_profiles"][stage["model_profile"]], "gate": result},
                    indent=2,
                )
            )
            return 0
    if args.command == "check":
        parser.error("unknown stage")
    print(json.dumps({"complete": True}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
