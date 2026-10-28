import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from pipeline.studio import queue, schema
from pipeline.studio.frames import frame_prompt
from pipeline.studio.planning import reconcile_links
from pipeline.studio.transport import execute


class StudioTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = self.root / "studio.db"
        self.c = schema.connect(self.db, "example")
        self.addCleanup(self.c.close)
        schema.initialize(self.c, "example", inherited_calls=3, inherited_usd=0.6)
        source = self.root / "source.png"
        source.write_bytes(b"source")
        refs = [
            {"role": role, "path": str(source), "sha256": schema.sha256(source), "asset_id": 72}
            for role in ("STRUCTURE", "MATERIAL")
        ]
        self.payload = {
            "product_code": "001",
            "shot": "surface_macro",
            "prompt": "saved frame",
            "prompt_sha256": hashlib.sha256(b"saved frame").hexdigest(),
            "inputs": refs,
        }
        self.manifest = {
            "revision": "v1",
            "pairs": [
                {
                    "product_code": "001",
                    "pair": [
                        {**self.payload, "model_requested": model}
                        for model in ("gpt_image_native", "ideogram")
                    ],
                }
            ],
        }
        self.jobs = schema.import_manifest(self.c, self.manifest)

    def authorize(self):
        for gate in schema.SOURCE_GATES:
            schema.record_gate(self.c, "001", gate, True, "saved evidence")
        return queue.authorize(
            self.c, self.jobs, kind="pilot", evidence="operator scope", allow_unknown_cost=True
        )

    def test_company_and_budget_immutable(self):
        with self.assertRaises(ValueError):
            schema.connect(self.db, "another")
        with self.assertRaises(ValueError):
            schema.initialize(self.c, "example")

    def test_mismatched_pair_and_changed_input(self):
        manifest = copy.deepcopy(self.manifest)
        manifest["pairs"][0]["pair"][1]["prompt"] = "different"
        with self.assertRaises(ValueError):
            schema.import_manifest(self.c, manifest)
        (self.root / "source.png").write_bytes(b"changed")
        with self.assertRaises(ValueError):
            schema.import_manifest(self.c, self.manifest)

    def test_stage_gates_and_full_scope(self):
        with self.assertRaises(ValueError):
            queue.authorize(self.c, self.jobs, kind="pilot", evidence="operator")
        self.authorize()
        schema.record_gate(self.c, "001", "macro_operator_approval", True, "operator review")
        with self.assertRaises(ValueError):
            queue.authorize(self.c, self.jobs, kind="full", evidence="operator")

    def test_unknown_submission_counts_and_cannot_repeat(self):
        aid = self.authorize()
        request = queue.native_handoff(self.c, self.jobs[0], aid)
        queue.hold(self.c, request["attempt_id"], "lost reply")
        self.assertEqual(queue.usage(self.c)["calls"], 4)
        self.assertEqual(queue.usage(self.c)["unknown_cost_calls"], 1)
        with self.assertRaises(ValueError):
            queue.native_handoff(self.c, self.jobs[0], aid)

    def test_native_receipt_hash_and_actual_model(self):
        aid = self.authorize()
        request = queue.native_handoff(self.c, self.jobs[0], aid)
        output = self.root / "output.png"
        output.write_bytes(b"render")
        result = {
            "company": "example",
            "attempt_id": request["attempt_id"],
            "job_id": self.jobs[0],
            "prompt_sha256": request["prompt_sha256"],
            "input_sha256": [x["sha256"] for x in request["inputs"]],
            "output_path": str(output),
            "output_sha256": "wrong",
            "provider_receipt": {"id": "native"},
            "model_actual": None,
        }
        with self.assertRaises(ValueError):
            queue.import_native(self.c, result)
        result["output_sha256"] = schema.sha256(output)
        queue.import_native(self.c, result)
        receipt = json.loads(self.c.execute("SELECT receipt FROM studio_attempts").fetchone()[0])
        self.assertIsNone(receipt["model_actual"])
        queue.review(
            self.c,
            request["attempt_id"],
            geometry_ok=True,
            material_ok=True,
            studio_ok=True,
            shot_ok=True,
            evidence="viewed individually",
        )
        self.assertIn("angled_product", queue.delivery_audit(self.c)["products"][0]["missing_shots"])
        output.write_bytes(b"altered")
        with self.assertRaisesRegex(ValueError, "bytes changed"):
            queue.review(
                self.c, request["attempt_id"], geometry_ok=True, material_ok=True,
                studio_ok=True, shot_ok=True, evidence="rechecked altered file",
            )

    def test_download_failure_preserves_receipt_without_retry(self):
        class Adapter:
            def quote(self, payload):
                return 0.22

            def generate(self, payload):
                return {"id": "provider-id", "cost_usd": 0.22}

            def fetch(self, receipt, path):
                raise OSError("download failed")

        aid = self.authorize()
        with self.assertRaises(OSError):
            execute(self.c, self.jobs[1], aid, Adapter(), self.root / "output.png")
        attempt = self.c.execute("SELECT * FROM studio_attempts").fetchone()
        self.assertEqual(attempt["state"], "received")
        self.assertEqual(json.loads(attempt["receipt"])["id"], "provider-id")
        self.assertEqual(queue.usage(self.c)["calls"], 4)

    def test_reconcile_parent_and_shared_aliases(self):
        row = {
            "source_sha256": "hash",
            "scope": "parent",
            "source_page": "/a",
            "product_page": "/a",
            "page_sha256": "page",
            "dom_evidence": "selector",
            "product_code": "001",
        }
        self.assertEqual(reconcile_links([row])[0]["status"], "ineligible")
        row["scope"] = "own_page"
        self.assertEqual(reconcile_links([row, {**row, "product_code": "002"}])[0]["status"], "shared_owners")

    def test_frame_exact_edit(self):
        result = frame_prompt(
            "A piece on grey.",
            [("grey", "warm beige")],
            shot="surface_macro",
            geometry="corner",
            finish="steel",
            condition="microtexture unresolved",
        )
        self.assertTrue(result["prompt"].startswith("A piece on warm beige."))
        with self.assertRaises(ValueError):
            frame_prompt(
                "grey grey",
                [("grey", "beige")],
                shot="stack",
                geometry="corner",
                finish="steel",
                condition="unknown",
            )

    def test_two_lanes_and_inherited_call_ceiling(self):
        aid = self.authorize()
        queue.reserve(self.c, self.jobs[0], aid, None)
        queue.reserve(self.c, self.jobs[1], aid, 0.22)
        other = copy.deepcopy(self.manifest)
        other["revision"] = "v2"
        jobs = schema.import_manifest(self.c, other)
        auth = queue.authorize(
            self.c, jobs, kind="pilot", evidence="second authorized scope", allow_unknown_cost=True
        )
        with self.assertRaisesRegex(ValueError, "Two execution lanes"):
            queue.reserve(self.c, jobs[0], auth, None)
        self.assertEqual(queue.usage(self.c)["calls"], 5)
        self.assertEqual(
            self.c.execute("SELECT state FROM studio_jobs WHERE id=?", (jobs[0],)).fetchone()[0], "authorized"
        )

    def test_material_zones_require_evidence_and_reject_photo_grade(self):
        from pipeline.studio.materials import FIELDS, ZONES, material_clause, validate_zones

        contract = {
            "product_code": "001",
            "expert_review_evidence": "manufacturer review",
            "grade_verified_by": "unknown",
            "zones": {
                z: {
                    "applicability": "unknown",
                    "unknowns": ["spec pending"],
                    **{f: {"status": "unknown"} for f in FIELDS},
                }
                for z in ZONES
            },
        }
        self.assertIn("raw cut face", material_clause(contract))
        contract["zones"]["cut_face"]["different_bulk_metal"] = True
        with self.assertRaises(ValueError):
            validate_zones(contract)
        contract["zones"]["cut_face"]["different_bulk_metal_evidence"] = "manufacturer cladding specification"
        contract["grade_verified_by"] = "photograph"
        with self.assertRaises(ValueError):
            validate_zones(contract)

    def test_zone_prompt_is_compact_and_preserves_cut_face_difference(self):
        from pipeline.studio.materials import FIELDS, ZONES, material_clause

        contract = {
            "product_code": "006",
            "expert_review_evidence": "source URL stays in manifest",
            "grade_verified_by": "unknown",
            "zones": {
                z: {
                    "applicability": "unknown",
                    "unknowns": ["unknown microtexture"],
                    **{f: {"status": "unknown"} for f in FIELDS},
                }
                for z in ZONES
            },
        }
        contract["zones"]["outside"]["render_intent"] = "Thin zinc skin on exterior faces."
        contract["zones"]["cut_face"]["render_intent"] = "Raw steel substrate at cut plane."
        clause = material_clause(contract)
        self.assertIn("Thin zinc skin", clause)
        self.assertIn("Raw steel substrate", clause)
        self.assertNotIn("source URL", clause)
        self.assertNotIn("unknown microtexture", clause)
        self.assertLess(len(clause), 850)

    def test_production_import_uses_one_model_with_zone_contract(self):
        from pipeline.studio.materials import FIELDS, ZONES

        contract = {
            "product_code": "001",
            "expert_review_evidence": "manufacturer review",
            "grade_verified_by": "unknown",
            "zones": {
                z: {"applicability": "unknown", "unknowns": [], **{f: {"status": "unknown"} for f in FIELDS}}
                for z in ZONES
            },
        }
        payload = {**self.payload, "model_requested": "gpt_image_native", "material_zones": contract}
        manifest = {"revision": "production1", "mode": "production", "jobs": [payload]}
        self.assertEqual(len(schema.import_manifest(self.c, manifest)), 1)
        payload["model_requested"] = "ideogram"
        with self.assertRaises(ValueError):
            schema.import_manifest(self.c, manifest)
