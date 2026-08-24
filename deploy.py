from __future__ import annotations

import argparse
import base64
import json
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests

from build_assets import build_data_agent, build_ontology, write_asset_tree
from generate_data import TABLE_FIELDS, write_tables


FABRIC_API = "https://api.fabric.microsoft.com/v1"
ONELAKE_DFS = "https://onelake.dfs.fabric.microsoft.com"
TERMINAL_JOB_STATES = {"Completed", "Failed", "Cancelled", "Deduped"}
TERMINAL_OPERATION_STATES = {"Succeeded", "Failed", "Cancelled"}


def azure_token(resource: str) -> str:
    azure_cli = shutil.which("az.cmd") or shutil.which("az")
    if not azure_cli:
        raise RuntimeError("Azure CLI was not found on PATH.")
    command = [
        azure_cli,
        "account",
        "get-access-token",
        "--resource",
        resource,
        "--query",
        "accessToken",
        "-o",
        "tsv",
    ]
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    return result.stdout.strip()


class FabricClient:
    def __init__(self, workspace_id: str) -> None:
        self.workspace_id = workspace_id
        self.fabric = requests.Session()
        self.fabric.headers.update(
            {
                "Authorization": f"Bearer {azure_token('https://api.fabric.microsoft.com')}",
                "Content-Type": "application/json",
            }
        )
        self.storage = requests.Session()
        self.storage.headers.update(
            {
                "Authorization": f"Bearer {azure_token('https://storage.azure.com/')}",
                "x-ms-version": "2023-11-03",
            }
        )

    @staticmethod
    def _raise(response: requests.Response) -> None:
        if response.ok:
            return
        try:
            detail = json.dumps(response.json(), indent=2)
        except ValueError:
            detail = response.text
        raise RuntimeError(f"{response.request.method} {response.url} failed ({response.status_code}): {detail}")

    def _poll_operation(self, response: requests.Response, timeout_seconds: int = 900) -> None:
        if response.status_code != 202:
            self._raise(response)
            return
        location = response.headers.get("Location")
        if not location:
            raise RuntimeError("Fabric accepted an operation without returning a Location header.")
        deadline = time.monotonic() + timeout_seconds
        delay = max(int(response.headers.get("Retry-After", "5")), 2)
        while time.monotonic() < deadline:
            time.sleep(min(delay, 15))
            operation = self.fabric.get(location)
            self._raise(operation)
            payload = operation.json()
            status = payload.get("status")
            if status in TERMINAL_OPERATION_STATES:
                if status != "Succeeded":
                    raise RuntimeError(f"Fabric operation ended with {status}: {json.dumps(payload, indent=2)}")
                return
            delay = max(int(operation.headers.get("Retry-After", str(delay))), 2)
        raise TimeoutError(f"Fabric operation did not complete within {timeout_seconds} seconds: {location}")

    def list_items(self, item_type: str | None = None) -> list[dict[str, Any]]:
        url = f"{FABRIC_API}/workspaces/{self.workspace_id}/items"
        params = {"type": item_type} if item_type else {}
        items: list[dict[str, Any]] = []
        while url:
            response = self.fabric.get(url, params=params)
            self._raise(response)
            payload = response.json()
            items.extend(payload.get("value", []))
            url = payload.get("continuationUri")
            params = {}
        return items

    def find_item(self, display_name: str, item_type: str) -> dict[str, Any] | None:
        matches = [
            item
            for item in self.list_items(item_type)
            if item["displayName"].casefold() == display_name.casefold()
        ]
        if len(matches) > 1:
            raise RuntimeError(f"Multiple {item_type} items are named {display_name!r}.")
        return matches[0] if matches else None

    def create_lakehouse(self, display_name: str) -> dict[str, Any]:
        existing = self.find_item(display_name, "Lakehouse")
        if existing:
            return existing
        response = self.fabric.post(
            f"{FABRIC_API}/workspaces/{self.workspace_id}/items",
            json={
                "displayName": display_name,
                "description": "Synthetic SAS finance and customer success intelligence demo.",
                "type": "Lakehouse",
            },
        )
        if response.status_code == 201:
            return response.json()
        self._poll_operation(response)
        item = self.find_item(display_name, "Lakehouse")
        if not item:
            raise RuntimeError(f"Lakehouse {display_name!r} was not visible after creation.")
        return item

    @staticmethod
    def _public_definition(asset: dict[str, Any], format_name: str | None = None) -> dict[str, Any]:
        definition: dict[str, Any] = {
            "parts": [
                {
                    "path": part["path"],
                    "payload": base64.b64encode(
                        json.dumps(part["content"], separators=(",", ":")).encode("utf-8")
                    ).decode("ascii"),
                    "payloadType": "InlineBase64",
                }
                for part in asset["parts"]
            ]
        }
        if format_name:
            definition["format"] = format_name
        return definition

    def upsert_item(
        self,
        display_name: str,
        item_type: str,
        description: str,
        definition: dict[str, Any],
        create_collection: str | None = None,
    ) -> dict[str, Any]:
        existing = self.find_item(display_name, item_type)
        if existing:
            response = self.fabric.post(
                f"{FABRIC_API}/workspaces/{self.workspace_id}/items/{existing['id']}/updateDefinition",
                json={"definition": definition},
            )
            self._poll_operation(response)
            return existing

        collection = create_collection or "items"
        body: dict[str, Any] = {
            "displayName": display_name,
            "description": description,
            "definition": definition,
        }
        if collection == "items":
            body["type"] = item_type
        response = self.fabric.post(
            f"{FABRIC_API}/workspaces/{self.workspace_id}/{collection}",
            json=body,
        )
        if response.status_code == 201:
            return response.json()
        self._poll_operation(response)
        item = self.find_item(display_name, item_type)
        if not item:
            raise RuntimeError(f"{item_type} {display_name!r} was not visible after creation.")
        return item

    def _storage_url(self, path: str, query: str = "") -> str:
        encoded = "/".join(quote(segment, safe="") for segment in path.split("/"))
        suffix = f"?{query}" if query else ""
        return f"{ONELAKE_DFS}/{self.workspace_id}/{encoded}{suffix}"

    def ensure_directory(self, lakehouse_id: str, relative_path: str) -> None:
        current = lakehouse_id
        for segment in relative_path.split("/"):
            current = f"{current}/{segment}"
            response = self.storage.put(self._storage_url(current, "resource=directory"))
            if response.status_code not in {201, 409}:
                self._raise(response)

    def upload_file(self, lakehouse_id: str, relative_path: str, content: bytes) -> None:
        path = f"{lakehouse_id}/{relative_path}"
        create = self.storage.put(self._storage_url(path, "resource=file"))
        if create.status_code == 409:
            delete = self.storage.delete(self._storage_url(path))
            self._raise(delete)
            create = self.storage.put(self._storage_url(path, "resource=file"))
        self._raise(create)
        append = self.storage.patch(
            self._storage_url(path, "action=append&position=0"),
            data=content,
            headers={"Content-Type": "application/octet-stream"},
        )
        self._raise(append)
        flush = self.storage.patch(
            self._storage_url(path, f"action=flush&position={len(content)}"),
            data=b"",
        )
        self._raise(flush)

    def run_notebook(self, notebook_id: str, lakehouse_id: str, timeout_seconds: int = 1800) -> dict[str, Any]:
        response = self.fabric.post(
            (
                f"{FABRIC_API}/workspaces/{self.workspace_id}/notebooks/{notebook_id}"
                "/jobs/execute/instances?beta=false"
            ),
            json={
                "executionData": {
                    "compute": "Spark",
                    "computeConfiguration": {
                        "defaultLakehouse": {
                            "referenceType": "ById",
                            "itemId": lakehouse_id,
                            "workspaceId": self.workspace_id,
                        }
                    },
                }
            },
        )
        self._raise(response)
        location = response.headers.get("Location")
        if not location:
            raise RuntimeError("Notebook run did not return a Location header.")
        deadline = time.monotonic() + timeout_seconds
        delay = max(int(response.headers.get("Retry-After", "30")), 5)
        while time.monotonic() < deadline:
            time.sleep(min(delay, 30))
            status_response = self.fabric.get(location)
            self._raise(status_response)
            status = status_response.json()
            if status.get("status") in TERMINAL_JOB_STATES:
                if status["status"] != "Completed":
                    raise RuntimeError(f"Notebook run failed: {json.dumps(status, indent=2)}")
                return status
            delay = max(int(status_response.headers.get("Retry-After", str(delay))), 5)
        raise TimeoutError(f"Notebook run did not finish within {timeout_seconds} seconds.")

    def validate_delta_table(self, lakehouse_id: str, table_name: str) -> int:
        query = (
            "resource=filesystem&recursive=true&"
            f"directory={quote(f'{lakehouse_id}/Tables/{table_name}', safe='/')}"
        )
        response = self.storage.get(f"{ONELAKE_DFS}/{self.workspace_id}?{query}")
        self._raise(response)
        paths = response.json().get("paths", [])
        if not any("_delta_log/" in entry.get("name", "") for entry in paths):
            raise RuntimeError(f"Delta table {table_name!r} has no transaction log in OneLake.")
        return len(paths)


def notebook_definition(
    source_path: Path,
    workspace_id: str,
    lakehouse_id: str,
    lakehouse_name: str,
) -> dict[str, Any]:
    lakehouse_root = (
        f"abfss://{workspace_id}@onelake.dfs.fabric.microsoft.com/{lakehouse_id}"
    )
    source = source_path.read_text(encoding="utf-8").replace(
        "__LAKEHOUSE_ROOT__",
        lakehouse_root,
    )
    lakehouse = {
        "default_lakehouse": lakehouse_id,
        "default_lakehouse_name": lakehouse_name,
        "default_lakehouse_workspace_id": workspace_id,
    }
    notebook = {
        "nbformat": 4,
        "nbformat_minor": 5,
        "cells": [
            {
                "cell_type": "code",
                "source": [line + "\n" for line in source.splitlines()],
                "execution_count": None,
                "outputs": [],
                "metadata": {},
            }
        ],
        "metadata": {
            "language_info": {"name": "python"},
            "kernelspec": {
                "name": "synapse_pyspark",
                "display_name": "Synapse PySpark",
                "language": "Python",
            },
            "trident": {"lakehouse": lakehouse},
        },
    }
    payload = base64.b64encode(json.dumps(notebook).encode("utf-8")).decode("ascii")
    return {
        "format": "ipynb",
        "parts": [
            {
                "path": "artifact.content.ipynb",
                "payload": payload,
                "payloadType": "InlineBase64",
            }
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Deploy the SAS finance Fabric IQ demo.")
    parser.add_argument("--workspace-id", required=True)
    parser.add_argument("--workspace-name", default="test_02_airflow")
    parser.add_argument("--lakehouse-name", default="SASFinanceLakehouse")
    parser.add_argument("--notebook-name", default="Load SAS Finance Demo")
    parser.add_argument("--ontology-name", default="SAS_Finance_Customer_Intelligence")
    parser.add_argument("--data-agent-name", default="SAS Finance Intelligence Agent")
    parser.add_argument("--skip-notebook-run", action="store_true")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent
    data_dir = root / "data"
    quality = write_tables(data_dir)
    client = FabricClient(args.workspace_id)

    lakehouse = client.create_lakehouse(args.lakehouse_name)
    client.ensure_directory(lakehouse["id"], "Files/raw")
    for table_name in TABLE_FIELDS:
        source = data_dir / f"{table_name}.csv"
        client.upload_file(lakehouse["id"], f"Files/raw/{source.name}", source.read_bytes())
    client.upload_file(
        lakehouse["id"],
        "Files/raw/quality_report.json",
        (data_dir / "quality_report.json").read_bytes(),
    )

    notebook = client.upsert_item(
        args.notebook_name,
        "Notebook",
        "Loads synthetic SAS finance CSV data into managed Delta tables.",
        notebook_definition(
            root / "fabric" / "load_finance_tables.py",
            args.workspace_id,
            lakehouse["id"],
            args.lakehouse_name,
        ),
    )
    notebook_run = None
    table_validation: dict[str, int] = {}
    if not args.skip_notebook_run:
        notebook_run = client.run_notebook(notebook["id"], lakehouse["id"])
        table_validation = {
            table_name: client.validate_delta_table(lakehouse["id"], table_name)
            for table_name in TABLE_FIELDS
        }

    ontology_asset = build_ontology(args.workspace_id, lakehouse["id"])
    data_agent_asset = build_data_agent(args.workspace_id, lakehouse["id"], args.lakehouse_name)
    write_asset_tree(ontology_asset, root / "generated" / "ontology")
    write_asset_tree(data_agent_asset, root / "generated" / "data-agent")

    ontology = client.upsert_item(
        args.ontology_name,
        "Ontology",
        "Finance, adoption, support, cost, and renewal ontology for a synthetic SAS demo.",
        client._public_definition(ontology_asset),
        create_collection="ontologies",
    )
    data_agent = client.upsert_item(
        args.data_agent_name,
        "DataAgent",
        "Answers finance and customer-success questions over synthetic SAS demo data.",
        client._public_definition(data_agent_asset),
        create_collection="dataAgents",
    )

    state = {
        "workspace": {"id": args.workspace_id, "name": args.workspace_name},
        "lakehouse": lakehouse,
        "notebook": notebook,
        "notebook_run": notebook_run,
        "ontology": ontology,
        "data_agent": data_agent,
        "quality": quality,
        "delta_table_files": table_validation,
        "ontology_mcp_endpoint": (
            f"{FABRIC_API}/mcp/dataPlane/workspaces/{args.workspace_id}/items/"
            f"{ontology['id']}/ontologyEndpoint"
        ),
        "data_agent_mcp_endpoint": (
            f"{FABRIC_API}/mcp/workspaces/{args.workspace_id}/dataagents/"
            f"{data_agent['id']}/agent"
        ),
    }
    (root / "deployment-state.json").write_text(
        json.dumps(state, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(state, indent=2))


if __name__ == "__main__":
    main()
