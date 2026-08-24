from __future__ import annotations

import sys
import base64
import json
import unittest
from pathlib import Path


DEMO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DEMO_ROOT))

from build_assets import build_data_agent, build_ontology  # noqa: E402
from deploy import notebook_definition  # noqa: E402


WORKSPACE_ID = "11111111-1111-1111-1111-111111111111"
LAKEHOUSE_ID = "22222222-2222-2222-2222-222222222222"


class FabricAssetTests(unittest.TestCase):
    def test_ontology_contains_all_entities_and_relationships(self) -> None:
        ontology = build_ontology(WORKSPACE_ID, LAKEHOUSE_ID)
        paths = {part["path"] for part in ontology["parts"]}

        entity_definitions = [
            path
            for path in paths
            if path.startswith("EntityTypes/") and path.endswith("/definition.json")
        ]
        relationship_definitions = [
            path
            for path in paths
            if path.startswith("RelationshipTypes/") and path.endswith("/definition.json")
        ]
        self.assertEqual(len(entity_definitions), 10)
        self.assertEqual(len(relationship_definitions), 9)
        self.assertIn("definition.json", paths)
        self.assertIn(".platform", paths)

    def test_all_ontology_bindings_target_requested_lakehouse(self) -> None:
        ontology = build_ontology(WORKSPACE_ID, LAKEHOUSE_ID)
        bindings = [
            part["content"]
            for part in ontology["parts"]
            if "/DataBindings/" in part["path"]
        ]

        self.assertEqual(len(bindings), 10)
        for binding in bindings:
            source = binding["dataBindingConfiguration"]["sourceTableProperties"]
            self.assertEqual(source["workspaceId"], WORKSPACE_ID)
            self.assertEqual(source["itemId"], LAKEHOUSE_ID)

    def test_data_agent_contains_draft_and_published_configuration(self) -> None:
        data_agent = build_data_agent(WORKSPACE_ID, LAKEHOUSE_ID, "SASFinanceLakehouse")
        paths = {part["path"] for part in data_agent["parts"]}

        self.assertIn("Files/Config/draft/stage_config.json", paths)
        self.assertIn("Files/Config/published/stage_config.json", paths)
        self.assertIn("Files/Config/publish_info.json", paths)
        datasource = next(
            part["content"]
            for part in data_agent["parts"]
            if part["path"].endswith("/draft/lakehouse-SASFinanceLakehouse/datasource.json")
        )
        self.assertEqual(datasource["artifactId"], LAKEHOUSE_ID)
        self.assertEqual(len(datasource["elements"][0]["children"]), 10)

    def test_notebook_persists_default_lakehouse(self) -> None:
        definition = notebook_definition(
            DEMO_ROOT / "fabric" / "load_finance_tables.py",
            WORKSPACE_ID,
            LAKEHOUSE_ID,
            "SASFinanceLakehouse",
        )
        content = json.loads(
            base64.b64decode(definition["parts"][0]["payload"]).decode("utf-8")
        )

        self.assertEqual(
            content["metadata"]["trident"]["lakehouse"]["default_lakehouse"],
            LAKEHOUSE_ID,
        )
        self.assertEqual(
            content["metadata"]["trident"]["lakehouse"]["default_lakehouse_workspace_id"],
            WORKSPACE_ID,
        )
        source = "".join(content["cells"][0]["source"])
        self.assertIn(
            f"abfss://{WORKSPACE_ID}@onelake.dfs.fabric.microsoft.com/{LAKEHOUSE_ID}",
            source,
        )
        self.assertNotIn("__LAKEHOUSE_ROOT__", source)


if __name__ == "__main__":
    unittest.main()
