from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import uuid
from pathlib import Path
from typing import Any

from generate_data import TABLE_FIELDS


ENTITY_NAMES = {
    "customers": "Customer",
    "products": "Product",
    "subscriptions": "Subscription",
    "invoices": "Invoice",
    "payments": "Payment",
    "usage_monthly": "UsageMetric",
    "support_cases": "SupportCase",
    "cloud_costs": "CostAllocation",
    "renewal_forecasts": "RenewalForecast",
    "customer_finance_summary": "CustomerFinanceProfile",
}

ENTITY_KEYS = {
    "customers": "customer_id",
    "products": "product_id",
    "subscriptions": "subscription_id",
    "invoices": "invoice_id",
    "payments": "payment_id",
    "usage_monthly": "usage_id",
    "support_cases": "case_id",
    "cloud_costs": "cost_id",
    "renewal_forecasts": "forecast_id",
    "customer_finance_summary": "profile_id",
}

DISPLAY_PROPERTIES = {
    "customers": "customer_name",
    "products": "product_name",
    "subscriptions": "subscription_id",
    "invoices": "invoice_id",
    "payments": "payment_id",
    "usage_monthly": "usage_id",
    "support_cases": "case_title",
    "cloud_costs": "cost_id",
    "renewal_forecasts": "forecast_category",
    "customer_finance_summary": "customer_name",
}

DOUBLE_COLUMNS = {
    "list_price_arr", "arr", "amount", "adoption_rate", "compute_hours", "support_hours",
    "compute_cost", "storage_cost", "support_cost", "total_cost", "renewal_arr",
    "renewal_probability", "mrr", "billed_revenue_6m", "cash_collected_6m",
    "ar_outstanding", "overdue_ar", "cost_6m", "gross_margin_pct",
    "latest_adoption_rate", "usage_trend_pct",
}

BIGINT_COLUMNS = {"licensed_users", "active_users", "production_jobs", "open_critical_cases"}

DATETIME_COLUMNS = {
    "start_date", "renewal_date", "invoice_date", "due_date", "paid_date",
    "payment_date", "usage_month", "opened_date", "resolved_date", "cost_month",
}

RELATIONSHIPS = [
    ("Customer", "owns", "Subscription", "subscriptions", "customer_id", "subscription_id"),
    ("Product", "isLicensedBy", "Subscription", "subscriptions", "product_id", "subscription_id"),
    ("Customer", "receives", "Invoice", "invoices", "customer_id", "invoice_id"),
    ("Invoice", "isSettledBy", "Payment", "payments", "invoice_id", "payment_id"),
    ("Subscription", "records", "UsageMetric", "usage_monthly", "subscription_id", "usage_id"),
    ("Customer", "opens", "SupportCase", "support_cases", "customer_id", "case_id"),
    ("Subscription", "incurs", "CostAllocation", "cloud_costs", "subscription_id", "cost_id"),
    ("Subscription", "has", "RenewalForecast", "renewal_forecasts", "subscription_id", "forecast_id"),
    (
        "Customer",
        "hasFinancialProfile",
        "CustomerFinanceProfile",
        "customer_finance_summary",
        "customer_id",
        "profile_id",
    ),
]

AGENT_INSTRUCTIONS = """You are the SAS Finance and Customer Success Intelligence Agent.
Use only the supplied Fabric Lakehouse tables. Treat 2026-08-31 as the demo as-of date.

Business definitions:
- ARR is annual recurring revenue from active subscriptions.
- Gross margin percentage is (six-month billed revenue - six-month cloud and support cost) / billed revenue.
- At-risk renewal means renewal_probability < 0.60.
- Watch renewal means 0.60 <= renewal_probability < 0.75.
- Declining adoption means usage_trend_pct < -10.
- Overdue AR includes invoices whose status is Overdue; Open is outstanding but not overdue.

For executive questions, lead with the answer and quantify ARR, margin, receivables, adoption,
support risk, and renewal timing. Join tables using customer_id, subscription_id, invoice_id,
and product_id. Never invent missing financial values. State that all organizations and data
are synthetic. When recommending an action, cite the observed drivers and use the
recommended_action field when available."""

FEW_SHOTS = [
    (
        "Which customers are at risk of renewal?",
        "SELECT customer_name, arr, renewal_date, renewal_probability, usage_trend_pct, "
        "open_critical_cases, overdue_ar, risk_reason, recommended_action "
        "FROM customer_finance_summary WHERE renewal_probability < 0.60 "
        "ORDER BY renewal_probability ASC;",
    ),
    (
        "Which customers have declining usage and open critical support cases?",
        "SELECT customer_name, arr, latest_adoption_rate, usage_trend_pct, "
        "open_critical_cases, renewal_probability, recommended_action "
        "FROM customer_finance_summary WHERE usage_trend_pct < -10 "
        "AND open_critical_cases > 0 ORDER BY arr DESC;",
    ),
    (
        "Show customer profitability and negative margin accounts.",
        "SELECT customer_name, billed_revenue_6m, cost_6m, gross_margin_pct, arr "
        "FROM customer_finance_summary ORDER BY gross_margin_pct ASC;",
    ),
    (
        "Which overdue invoices are linked to renewal risk?",
        "SELECT c.customer_name, i.invoice_id, i.amount, i.due_date, "
        "f.renewal_date, f.renewal_probability, f.forecast_category "
        "FROM invoices i JOIN customers c ON i.customer_id = c.customer_id "
        "JOIN renewal_forecasts f ON i.subscription_id = f.subscription_id "
        "WHERE i.status = 'Overdue' ORDER BY f.renewal_probability ASC;",
    ),
]


def _numeric_id(name: str) -> str:
    digest = hashlib.sha256(name.encode("utf-8")).digest()
    return str(int.from_bytes(digest[:8], "big") & ((1 << 63) - 1) or 1)


def _stable_uuid(name: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"https://example.com/sas-finance-iq/{name}"))


def _value_type(column: str) -> str:
    if column in DOUBLE_COLUMNS:
        return "Double"
    if column in BIGINT_COLUMNS:
        return "BigInt"
    if column in DATETIME_COLUMNS:
        return "DateTime"
    return "String"


def build_ontology(workspace_id: str, lakehouse_id: str) -> dict[str, Any]:
    parts: list[dict[str, Any]] = [
        {"path": "definition.json", "content": {}},
        {
            "path": ".platform",
            "content": {
                "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
                "metadata": {
                    "type": "Ontology",
                    "displayName": "SAS Finance Customer Intelligence",
                    "description": "Synthetic customer finance, adoption, cost, support, and renewal ontology.",
                },
                "config": {"version": "2.0", "logicalId": _stable_uuid("ontology")},
            },
        },
    ]
    entity_info: dict[str, dict[str, Any]] = {}

    for table_name, entity_name in ENTITY_NAMES.items():
        entity_id = _numeric_id(f"entity:{entity_name}")
        properties = []
        property_ids = {}
        for column in TABLE_FIELDS[table_name]:
            property_id = _numeric_id(f"property:{entity_name}:{column}")
            property_ids[column] = property_id
            properties.append(
                {
                    "id": property_id,
                    "name": column,
                    "redefines": None,
                    "baseTypeNamespaceType": None,
                    "valueType": _value_type(column),
                }
            )
        key_property_id = property_ids[ENTITY_KEYS[table_name]]
        entity_info[entity_name] = {
            "id": entity_id,
            "properties": property_ids,
            "table": table_name,
        }
        parts.append(
            {
                "path": f"EntityTypes/{entity_id}/definition.json",
                "content": {
                    "id": entity_id,
                    "namespace": "usertypes",
                    "baseEntityTypeId": None,
                    "name": entity_name,
                    "entityIdParts": [key_property_id],
                    "displayNamePropertyId": property_ids[DISPLAY_PROPERTIES[table_name]],
                    "namespaceType": "Custom",
                    "visibility": "Visible",
                    "properties": properties,
                    "timeseriesProperties": [],
                },
            }
        )
        binding_id = _stable_uuid(f"binding:{entity_name}")
        parts.append(
            {
                "path": f"EntityTypes/{entity_id}/DataBindings/{binding_id}.json",
                "content": {
                    "id": binding_id,
                    "dataBindingConfiguration": {
                        "dataBindingType": "NonTimeSeries",
                        "propertyBindings": [
                            {
                                "sourceColumnName": column,
                                "targetPropertyId": property_ids[column],
                            }
                            for column in TABLE_FIELDS[table_name]
                        ],
                        "sourceTableProperties": {
                            "sourceType": "LakehouseTable",
                            "workspaceId": workspace_id,
                            "itemId": lakehouse_id,
                            "sourceTableName": table_name,
                            "sourceSchema": "dbo",
                        },
                    },
                },
            }
        )

    for source_name, relationship_name, target_name, table_name, source_key, target_key in RELATIONSHIPS:
        relationship_id = _numeric_id(f"relationship:{source_name}:{relationship_name}:{target_name}")
        contextualization_id = _stable_uuid(
            f"context:{source_name}:{relationship_name}:{target_name}"
        )
        parts.append(
            {
                "path": f"RelationshipTypes/{relationship_id}/definition.json",
                "content": {
                    "namespace": "usertypes",
                    "id": relationship_id,
                    "name": relationship_name,
                    "namespaceType": "Custom",
                    "source": {"entityTypeId": entity_info[source_name]["id"]},
                    "target": {"entityTypeId": entity_info[target_name]["id"]},
                },
            }
        )
        parts.append(
            {
                "path": (
                    f"RelationshipTypes/{relationship_id}/Contextualizations/"
                    f"{contextualization_id}.json"
                ),
                "content": {
                    "id": contextualization_id,
                    "dataBindingTable": {
                        "workspaceId": workspace_id,
                        "itemId": lakehouse_id,
                        "sourceTableName": table_name,
                        "sourceSchema": "dbo",
                        "sourceType": "LakehouseTable",
                    },
                    "sourceKeyRefBindings": [
                        {
                            "sourceColumnName": source_key,
                            "targetPropertyId": entity_info[source_name]["properties"][source_key],
                        }
                    ],
                    "targetKeyRefBindings": [
                        {
                            "sourceColumnName": target_key,
                            "targetPropertyId": entity_info[target_name]["properties"][target_key],
                        }
                    ],
                },
            }
        )
    return {"parts": parts}


def _element_id(path: str) -> str:
    return _stable_uuid(f"data-agent:{path}")


def build_data_agent(workspace_id: str, lakehouse_id: str, lakehouse_name: str) -> dict[str, Any]:
    table_children = []
    for table_name, fields in TABLE_FIELDS.items():
        table_children.append(
            {
                "id": _element_id(table_name),
                "is_selected": True,
                "display_name": table_name,
                "type": "lakehouse_tables.table",
                "description": f"Synthetic finance demo table for {ENTITY_NAMES[table_name]}.",
                "children": [
                    {
                        "id": _element_id(f"{table_name}.{column}"),
                        "is_selected": True,
                        "display_name": column,
                        "type": "lakehouse_tables.column",
                        "data_type": _value_type(column).lower(),
                    }
                    for column in fields
                ],
            }
        )

    datasource = {
        "$schema": "1.0.0",
        "artifactId": lakehouse_id,
        "workspaceId": workspace_id,
        "displayName": lakehouse_name,
        "type": "lakehouse_tables",
        "userDescription": "Synthetic SAS customer finance and success intelligence data.",
        "dataSourceInstructions": AGENT_INSTRUCTIONS,
        "elements": [
            {
                "id": _element_id("dbo"),
                "is_selected": True,
                "display_name": "dbo",
                "type": "lakehouse_tables.schema",
                "children": table_children,
            }
        ],
    }
    fewshots = {
        "$schema": "1.0.0",
        "fewShots": [
            {
                "id": _stable_uuid(f"fewshot:{index}"),
                "question": question,
                "query": query,
            }
            for index, (question, query) in enumerate(FEW_SHOTS, start=1)
        ],
    }
    source_folder = f"lakehouse-{lakehouse_name}"
    return {
        "parts": [
            {"path": "Files/Config/data_agent.json", "content": {"$schema": "2.1.0"}},
            {
                "path": "Files/Config/draft/stage_config.json",
                "content": {"$schema": "1.0.0", "aiInstructions": AGENT_INSTRUCTIONS},
            },
            {
                "path": f"Files/Config/draft/{source_folder}/datasource.json",
                "content": datasource,
            },
            {
                "path": f"Files/Config/draft/{source_folder}/fewshots.json",
                "content": fewshots,
            },
            {
                "path": "Files/Config/published/stage_config.json",
                "content": {"$schema": "1.0.0", "aiInstructions": AGENT_INSTRUCTIONS},
            },
            {
                "path": f"Files/Config/published/{source_folder}/datasource.json",
                "content": datasource,
            },
            {
                "path": f"Files/Config/published/{source_folder}/fewshots.json",
                "content": fewshots,
            },
            {
                "path": "Files/Config/publish_info.json",
                "content": {
                    "$schema": "1.0.0",
                    "description": "SAS Finance Intelligence Agent demo publication.",
                },
            },
        ]
    }


def write_asset_tree(asset: dict[str, Any], root: Path) -> None:
    if root.exists():
        shutil.rmtree(root)
    for part in asset["parts"]:
        target = root / Path(part["path"])
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(part["content"], indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Fabric Ontology and Data Agent assets.")
    parser.add_argument("--workspace-id", required=True)
    parser.add_argument("--lakehouse-id", required=True)
    parser.add_argument("--lakehouse-name", default="SASFinanceLakehouse")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parent / "generated",
    )
    args = parser.parse_args()
    write_asset_tree(
        build_ontology(args.workspace_id, args.lakehouse_id),
        args.output / "ontology",
    )
    write_asset_tree(
        build_data_agent(args.workspace_id, args.lakehouse_id, args.lakehouse_name),
        args.output / "data-agent",
    )
    print(f"Wrote Fabric assets to {args.output}")


if __name__ == "__main__":
    main()
