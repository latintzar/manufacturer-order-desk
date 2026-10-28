import copy
import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from pipeline import imagery


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        path = Path(self.temp.name) / "image"
        path.write_bytes(b"original image bytes")
        self.request = dict(
            asset_id=72,
            product_code="001",
            image=str(path),
            source=str(path),
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        )
        self.payload = dict(
            asset_id=72,
            visible_section="hollow square tube",
            material_hypotheses=["steel or aluminium"],
            surface_finish="matte",
            colour="grey",
            section_features=["square hollow section"],
            condition="marked",
            uncertainties=["alloy uncertain"],
        )
        self.config = {
            "description": {"required_fields": list(self.payload)},
            "identity": {"eligible_scopes": ["type_main", "type_body"]},
        }
        self.links = [dict(eligible=1, scope="type_main", product_code="001")]
        self.owners = [dict(product_code="001", state="candidate")]

    def validate(self):
        imagery.validate(self.payload, self.request, self.config, self.links, self.owners)

    def test_accept_unique_preserves_uncertainty(self):
        self.validate()
        before = copy.deepcopy(self.payload)
        result = imagery.compare(self.payload, dict(shape="sq_tube", mat="hr"))
        self.assertEqual(result["state"], "compatible_with_uncertainty")
        self.assertEqual(self.payload, before)
        self.assertEqual(result["uncertainties"], ["alloy uncertain"])

    def test_wrong_or_string_echo_rejected(self):
        for aid in (73, "72", True):
            with self.subTest(aid=aid):
                self.payload["asset_id"] = aid
                with self.assertRaisesRegex(ValueError, "numeric"):
                    self.validate()

    def test_modified_input_rejected(self):
        Path(self.request["image"]).write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "hash"):
            self.validate()

    def test_parent_never_eligible(self):
        self.links[0]["scope"] = "parent"
        with self.assertRaisesRegex(ValueError, "parent"):
            self.validate()

    def test_shared_source_other_owner_rejected(self):
        self.links.append(dict(eligible=1, scope="type_body", product_code="005"))
        with self.assertRaisesRegex(ValueError, "unique"):
            self.validate()

    def test_context_occurrence_does_not_create_owner(self):
        self.links.append(dict(eligible=0, scope="parent", product_code="005"))
        self.validate()

    def test_missing_or_malformed_description_rejected(self):
        self.payload["material_hypotheses"] = "steel"
        with self.assertRaisesRegex(ValueError, "list"):
            self.validate()

    def test_shape_material_mismatch_and_unknown_quarantine(self):
        for shape, mat in [("round_tube", "hr"), ("sq_tube", "copper"), ("unknown", "hr")]:
            self.assertEqual(
                imagery.compare(self.payload, dict(shape=shape, mat=mat))["state"], "quarantined"
            )

    def test_other_visible_sections_keep_geometry_and_material_checks_separate(self):
        cases = [
            ("hex", "brass", "solid hexagonal bar", "brass", True),
            ("angle", "alu", "L-shaped right-angle profile", "aluminium", True),
            ("round", "copper", "solid round rods", "copper", True),
            ("sheet", "hr", "stacked rectangular plates", "ferrous metal", True),
            ("round_tube", "copper", "solid round rods", "copper", False),
            ("sq_tube", "hr", "square hollow tube", "non-ferrous aluminium", False),
            ("sq_tube", "hr", "square hollow tube", "not steel; aluminium", False),
            ("special", "hr", "pliers and screwdrivers", "steel", False),
        ]
        for shape, material, visible, hypothesis, expected in cases:
            with self.subTest(shape=shape, hypothesis=hypothesis):
                payload = {**self.payload, "visible_section": visible, "section_features": [visible],
                           "material_hypotheses": [hypothesis]}
                result = imagery.compare(payload, {"shape": shape, "mat": material})
                self.assertEqual(result["state"] == "compatible_with_uncertainty", expected)

    def database(self):
        connection = sqlite3.connect(":memory:")
        self.addCleanup(connection.close)
        connection.executescript("""
            CREATE TABLE assets(id INTEGER, sha1 TEXT);
            CREATE TABLE products(code TEXT, page_bg TEXT, shape TEXT, mat TEXT);
            CREATE TABLE link_provenance(asset_id INTEGER, product_code TEXT, eligible INTEGER, scope TEXT, source_page TEXT, page_sha256 TEXT, dom_location TEXT);
            CREATE TABLE material_owners(asset_id INTEGER, sha1 TEXT, product_code TEXT, state TEXT);
            CREATE TABLE blind_descriptions(asset_id INTEGER PRIMARY KEY, input_sha256 TEXT, model TEXT, payload TEXT, saved_at TEXT);
            CREATE TABLE material_checks(asset_id INTEGER PRIMARY KEY, product_code TEXT, state TEXT, evidence TEXT, checked_at TEXT);
        """)
        sha1 = hashlib.sha1(Path(self.request["source"]).read_bytes()).hexdigest()
        connection.execute("insert into assets values(72,?)", (sha1,))
        connection.execute("insert into products values('001','/own','sq_tube','hr')")
        connection.execute(
            "insert into link_provenance values(72,'001',1,'type_main','/own','pagehash','product.detail')"
        )
        connection.execute("insert into material_owners values(72,?,'001','candidate')", (sha1,))
        self.config["description"]["model"] = "gpt-6-astra"
        return connection

    def test_ingestion_is_idempotent_and_preserves_saved_observation(self):
        connection = self.database()
        imagery.ingest(connection, self.request, self.payload, self.config)
        imagery.ingest(connection, self.request, self.payload, self.config)
        self.assertEqual(connection.execute("select count(*) from blind_descriptions").fetchone()[0], 1)
        self.payload["colour"] = "rewritten after seeing catalogue"
        with self.assertRaisesRegex(ValueError, "immutable"):
            imagery.ingest(connection, self.request, self.payload, self.config)
        saved = connection.execute("select payload from blind_descriptions").fetchone()[0]
        self.assertEqual(json.loads(saved)["colour"], "grey")

    def test_cross_asset_duplicate_hash_owner_is_rejected(self):
        connection = self.database()
        connection.execute("insert into assets select 99,sha1 from assets where id=72")
        connection.execute(
            "insert into link_provenance values(99,'002',1,'type_main','/other','hash','detail')"
        )
        with self.assertRaisesRegex(ValueError, "unique"):
            imagery.ingest(connection, self.request, self.payload, self.config)

    def test_claimed_own_page_must_match_catalogue_page(self):
        connection = self.database()
        connection.execute("update link_provenance set source_page='/family'")
        with self.assertRaisesRegex(ValueError, "Own-page"):
            imagery.ingest(connection, self.request, self.payload, self.config)
        self.assertEqual(connection.execute("select count(*) from blind_descriptions").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
