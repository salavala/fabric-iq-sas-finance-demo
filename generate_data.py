from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Iterable


AS_OF_DATE = date(2026, 8, 31)
MONTHS = (
    date(2026, 3, 1),
    date(2026, 4, 1),
    date(2026, 5, 1),
    date(2026, 6, 1),
    date(2026, 7, 1),
    date(2026, 8, 1),
)

CUSTOMERS = [
    ("C001", "Northstar Bank", "Financial Services", "United States", "Enterprise", "Avery Chen"),
    ("C002", "Contoso Health", "Healthcare", "United States", "Enterprise", "Maya Patel"),
    ("C003", "Fabrikam Retail", "Retail", "Canada", "Enterprise", "Noah Williams"),
    ("C004", "Alpine Insurance", "Insurance", "United Kingdom", "Enterprise", "Sophia Martin"),
    ("C005", "Blue Yonder Airlines", "Travel", "United States", "Strategic", "Liam Johnson"),
    ("C006", "Adventure Works", "Manufacturing", "Germany", "Commercial", "Emma Garcia"),
    ("C007", "Tailspin Energy", "Energy", "United States", "Strategic", "Ethan Brown"),
    ("C008", "Wide World Importers", "Distribution", "Netherlands", "Commercial", "Olivia Davis"),
    ("C009", "Proseware Telecom", "Telecommunications", "Australia", "Enterprise", "Lucas Wilson"),
    ("C010", "Woodgrove Public Sector", "Public Sector", "United States", "Enterprise", "Isabella Moore"),
    ("C011", "Fourth Coffee", "Consumer Goods", "France", "Commercial", "James Taylor"),
    ("C012", "Lucerne Publishing", "Media", "Switzerland", "Commercial", "Amelia Anderson"),
]

PRODUCTS = [
    ("P001", "SAS Viya Cloud", "Analytics Platform", 180000.0),
    ("P002", "SAS Risk Modeling", "Risk Analytics", 240000.0),
    ("P003", "SAS Customer Intelligence", "Customer Analytics", 150000.0),
    ("P004", "SAS Fraud Detection", "Fraud Analytics", 210000.0),
]

SUBSCRIPTION_SPECS = [
    ("S001", "C001", "P002", 480000.0, "2025-10-01", "2026-09-30", 650, "Enterprise"),
    ("S002", "C002", "P001", 360000.0, "2025-11-15", "2026-11-14", 500, "Enterprise"),
    ("S003", "C003", "P003", 300000.0, "2026-01-01", "2026-12-31", 450, "Enterprise"),
    ("S004", "C004", "P004", 420000.0, "2025-09-15", "2026-09-14", 550, "Enterprise"),
    ("S005", "C005", "P001", 720000.0, "2025-12-01", "2026-11-30", 1100, "Strategic"),
    ("S006", "C006", "P001", 216000.0, "2026-02-01", "2027-01-31", 300, "Commercial"),
    ("S007", "C007", "P002", 600000.0, "2025-10-15", "2026-10-14", 800, "Strategic"),
    ("S008", "C008", "P003", 180000.0, "2026-03-01", "2027-02-28", 250, "Commercial"),
    ("S009", "C009", "P004", 450000.0, "2025-11-01", "2026-10-31", 700, "Enterprise"),
    ("S010", "C010", "P001", 390000.0, "2026-01-15", "2027-01-14", 600, "Enterprise"),
    ("S011", "C011", "P003", 144000.0, "2026-04-01", "2027-03-31", 180, "Commercial"),
    ("S012", "C012", "P001", 168000.0, "2026-02-15", "2027-02-14", 220, "Commercial"),
]

USAGE_TRAJECTORIES = {
    "S001": (0.81, 0.84, 0.86, 0.87, 0.89, 0.91),
    "S002": (0.79, 0.76, 0.72, 0.68, 0.61, 0.54),
    "S003": (0.62, 0.66, 0.70, 0.74, 0.77, 0.82),
    "S004": (0.74, 0.70, 0.66, 0.60, 0.52, 0.44),
    "S005": (0.88, 0.89, 0.91, 0.92, 0.94, 0.95),
    "S006": (0.58, 0.61, 0.64, 0.67, 0.69, 0.71),
    "S007": (0.86, 0.85, 0.83, 0.80, 0.75, 0.69),
    "S008": (0.48, 0.53, 0.58, 0.64, 0.70, 0.76),
    "S009": (0.83, 0.82, 0.80, 0.78, 0.76, 0.74),
    "S010": (0.67, 0.69, 0.72, 0.74, 0.78, 0.81),
    "S011": (0.55, 0.59, 0.63, 0.65, 0.68, 0.70),
    "S012": (0.72, 0.70, 0.67, 0.63, 0.60, 0.57),
}

RENEWAL_FORECASTS = {
    "S001": (0.91, "Expansion", "Strong adoption and executive sponsorship", "Prepare 10% analytics expansion proposal"),
    "S002": (0.48, "At Risk", "Usage declined 32% and two critical cases remain open", "Run executive value review and recovery plan"),
    "S003": (0.86, "Likely", "Usage and active users are growing", "Propose customer intelligence add-on"),
    "S004": (0.35, "At Risk", "Usage declined 41% near renewal and invoice is overdue", "Escalate support resolution and commercial intervention"),
    "S005": (0.96, "Expansion", "High adoption with increasing workloads", "Offer reserved capacity and platform expansion"),
    "S006": (0.79, "Likely", "Healthy adoption trajectory", "Continue enablement and identify risk use case"),
    "S007": (0.62, "Watch", "Compute cost rising while usage softens", "Complete architecture and margin optimization review"),
    "S008": (0.84, "Likely", "Rapid adoption after onboarding", "Introduce advanced customer analytics package"),
    "S009": (0.76, "Likely", "Stable adoption with one aging support case", "Close support action before renewal"),
    "S010": (0.90, "Likely", "Strong usage and payment history", "Start public-sector renewal process early"),
    "S011": (0.74, "Likely", "Moderate but improving adoption", "Deliver role-based enablement session"),
    "S012": (0.58, "Watch", "Usage declined for four consecutive months", "Schedule adoption workshop and success plan"),
}

SUPPORT_CASES = [
    ("CASE001", "C002", "S002", "Critical", "Open", "Model scoring latency", "2026-08-08", "", 31.0),
    ("CASE002", "C002", "S002", "High", "Open", "Identity synchronization failures", "2026-08-18", "", 17.0),
    ("CASE003", "C004", "S004", "Critical", "Open", "Fraud rules missing events", "2026-08-05", "", 38.0),
    ("CASE004", "C004", "S004", "Medium", "Resolved", "Dashboard refresh delay", "2026-07-02", "2026-07-07", 6.0),
    ("CASE005", "C007", "S007", "High", "Open", "Compute queue saturation", "2026-08-21", "", 14.0),
    ("CASE006", "C009", "S009", "Medium", "Open", "Alert configuration guidance", "2026-07-27", "", 8.0),
    ("CASE007", "C001", "S001", "Low", "Resolved", "New user onboarding", "2026-06-10", "2026-06-11", 2.0),
    ("CASE008", "C005", "S005", "Medium", "Resolved", "Capacity planning", "2026-08-02", "2026-08-04", 4.0),
    ("CASE009", "C012", "S012", "High", "Open", "Batch migration failures", "2026-08-14", "", 20.0),
]

TABLE_FIELDS = {
    "customers": ["customer_id", "customer_name", "industry", "country", "segment", "account_owner"],
    "products": ["product_id", "product_name", "product_family", "list_price_arr"],
    "subscriptions": [
        "subscription_id", "customer_id", "product_id", "arr", "start_date", "renewal_date",
        "licensed_users", "contract_tier", "status",
    ],
    "invoices": [
        "invoice_id", "customer_id", "subscription_id", "invoice_date", "due_date",
        "amount", "status", "paid_date",
    ],
    "payments": ["payment_id", "invoice_id", "customer_id", "payment_date", "amount", "payment_method"],
    "usage_monthly": [
        "usage_id", "subscription_id", "customer_id", "usage_month", "licensed_users",
        "active_users", "adoption_rate", "compute_hours", "production_jobs",
    ],
    "support_cases": [
        "case_id", "customer_id", "subscription_id", "severity", "status", "case_title",
        "opened_date", "resolved_date", "support_hours",
    ],
    "cloud_costs": [
        "cost_id", "subscription_id", "customer_id", "cost_month", "compute_cost",
        "storage_cost", "support_cost", "total_cost",
    ],
    "renewal_forecasts": [
        "forecast_id", "subscription_id", "customer_id", "renewal_date", "renewal_arr",
        "renewal_probability", "forecast_category", "risk_reason", "recommended_action",
    ],
    "customer_finance_summary": [
        "profile_id", "customer_id", "customer_name", "arr", "mrr", "billed_revenue_6m",
        "cash_collected_6m", "ar_outstanding", "overdue_ar", "cost_6m", "gross_margin_pct",
        "latest_adoption_rate", "usage_trend_pct", "open_critical_cases", "renewal_date",
        "renewal_probability", "renewal_category", "risk_reason", "recommended_action",
    ],
}


def _as_dicts(fields: list[str], rows: Iterable[tuple[Any, ...]]) -> list[dict[str, Any]]:
    return [dict(zip(fields, row, strict=True)) for row in rows]


def build_tables() -> dict[str, list[dict[str, Any]]]:
    customers = _as_dicts(TABLE_FIELDS["customers"], CUSTOMERS)
    products = _as_dicts(TABLE_FIELDS["products"], PRODUCTS)
    subscriptions = _as_dicts(
        TABLE_FIELDS["subscriptions"],
        [(*row, "Active") for row in SUBSCRIPTION_SPECS],
    )

    invoices: list[dict[str, Any]] = []
    payments: list[dict[str, Any]] = []
    usage: list[dict[str, Any]] = []
    costs: list[dict[str, Any]] = []
    invoice_sequence = 1
    payment_sequence = 1

    for sub_index, subscription in enumerate(subscriptions):
        subscription_id = subscription["subscription_id"]
        customer_id = subscription["customer_id"]
        monthly_amount = round(float(subscription["arr"]) / 12, 2)
        for month_index, month in enumerate(MONTHS):
            invoice_date = month
            due_date = month + timedelta(days=29)
            is_overdue_demo = subscription_id in {"S002", "S004"} and month_index == 4
            is_open_recent = month_index == 5 and subscription_id in {"S007", "S009", "S012"}
            paid_date = due_date - timedelta(days=8 - ((sub_index + month_index) % 6))
            status = "Overdue" if is_overdue_demo else "Open" if is_open_recent else "Paid"
            invoice_id = f"INV{invoice_sequence:04d}"
            invoices.append(
                {
                    "invoice_id": invoice_id,
                    "customer_id": customer_id,
                    "subscription_id": subscription_id,
                    "invoice_date": invoice_date.isoformat(),
                    "due_date": due_date.isoformat(),
                    "amount": monthly_amount,
                    "status": status,
                    "paid_date": "" if status != "Paid" else paid_date.isoformat(),
                }
            )
            if status == "Paid":
                payments.append(
                    {
                        "payment_id": f"PAY{payment_sequence:04d}",
                        "invoice_id": invoice_id,
                        "customer_id": customer_id,
                        "payment_date": paid_date.isoformat(),
                        "amount": monthly_amount,
                        "payment_method": ("ACH", "Wire", "Card")[sub_index % 3],
                    }
                )
                payment_sequence += 1
            invoice_sequence += 1

            adoption = USAGE_TRAJECTORIES[subscription_id][month_index]
            licensed_users = int(subscription["licensed_users"])
            active_users = round(licensed_users * adoption)
            compute_hours = round(active_users * (4.8 + (sub_index % 4) * 0.35), 1)
            production_jobs = round(compute_hours * (2.1 + (month_index % 3) * 0.1))
            usage.append(
                {
                    "usage_id": f"{subscription_id}-{month:%Y%m}",
                    "subscription_id": subscription_id,
                    "customer_id": customer_id,
                    "usage_month": month.isoformat(),
                    "licensed_users": licensed_users,
                    "active_users": active_users,
                    "adoption_rate": round(adoption, 4),
                    "compute_hours": compute_hours,
                    "production_jobs": production_jobs,
                }
            )

            support_load = 1.0
            if subscription_id in {"S002", "S004"}:
                support_load = 2.0
            elif subscription_id in {"S007", "S009", "S012"}:
                support_load = 1.4
            compute_cost = round(compute_hours * (5.0 + (sub_index % 3) * 0.4), 2)
            storage_cost = round(720 + (sub_index * 55) + (month_index * 18), 2)
            support_cost = round(1050 * support_load + month_index * 35, 2)
            costs.append(
                {
                    "cost_id": f"COST-{subscription_id}-{month:%Y%m}",
                    "subscription_id": subscription_id,
                    "customer_id": customer_id,
                    "cost_month": month.isoformat(),
                    "compute_cost": compute_cost,
                    "storage_cost": storage_cost,
                    "support_cost": support_cost,
                    "total_cost": round(compute_cost + storage_cost + support_cost, 2),
                }
            )

    support_cases = _as_dicts(TABLE_FIELDS["support_cases"], SUPPORT_CASES)
    renewal_forecasts = []
    for subscription in subscriptions:
        probability, category, reason, action = RENEWAL_FORECASTS[subscription["subscription_id"]]
        renewal_forecasts.append(
            {
                "forecast_id": f"RF-{subscription['subscription_id']}",
                "subscription_id": subscription["subscription_id"],
                "customer_id": subscription["customer_id"],
                "renewal_date": subscription["renewal_date"],
                "renewal_arr": subscription["arr"],
                "renewal_probability": probability,
                "forecast_category": category,
                "risk_reason": reason,
                "recommended_action": action,
            }
        )

    invoice_by_customer: dict[str, list[dict[str, Any]]] = defaultdict(list)
    payment_by_customer: dict[str, list[dict[str, Any]]] = defaultdict(list)
    cost_by_customer: dict[str, list[dict[str, Any]]] = defaultdict(list)
    usage_by_customer: dict[str, list[dict[str, Any]]] = defaultdict(list)
    cases_by_customer: dict[str, list[dict[str, Any]]] = defaultdict(list)
    forecast_by_customer = {row["customer_id"]: row for row in renewal_forecasts}
    subscription_by_customer = {row["customer_id"]: row for row in subscriptions}

    for row in invoices:
        invoice_by_customer[row["customer_id"]].append(row)
    for row in payments:
        payment_by_customer[row["customer_id"]].append(row)
    for row in costs:
        cost_by_customer[row["customer_id"]].append(row)
    for row in usage:
        usage_by_customer[row["customer_id"]].append(row)
    for row in support_cases:
        cases_by_customer[row["customer_id"]].append(row)

    summaries = []
    for customer in customers:
        customer_id = customer["customer_id"]
        subscription = subscription_by_customer[customer_id]
        customer_invoices = invoice_by_customer[customer_id]
        customer_payments = payment_by_customer[customer_id]
        customer_costs = cost_by_customer[customer_id]
        customer_usage = sorted(usage_by_customer[customer_id], key=lambda row: row["usage_month"])
        forecast = forecast_by_customer[customer_id]
        billed = round(sum(float(row["amount"]) for row in customer_invoices), 2)
        collected = round(sum(float(row["amount"]) for row in customer_payments), 2)
        outstanding = round(sum(float(row["amount"]) for row in customer_invoices if row["status"] != "Paid"), 2)
        overdue = round(sum(float(row["amount"]) for row in customer_invoices if row["status"] == "Overdue"), 2)
        total_cost = round(sum(float(row["total_cost"]) for row in customer_costs), 2)
        usage_trend = round(
            (float(customer_usage[-1]["adoption_rate"]) / float(customer_usage[0]["adoption_rate"]) - 1) * 100,
            2,
        )
        gross_margin = round((billed - total_cost) / billed * 100, 2)
        summaries.append(
            {
                "profile_id": f"FP-{customer_id}",
                "customer_id": customer_id,
                "customer_name": customer["customer_name"],
                "arr": subscription["arr"],
                "mrr": round(float(subscription["arr"]) / 12, 2),
                "billed_revenue_6m": billed,
                "cash_collected_6m": collected,
                "ar_outstanding": outstanding,
                "overdue_ar": overdue,
                "cost_6m": total_cost,
                "gross_margin_pct": gross_margin,
                "latest_adoption_rate": customer_usage[-1]["adoption_rate"],
                "usage_trend_pct": usage_trend,
                "open_critical_cases": sum(
                    1
                    for row in cases_by_customer[customer_id]
                    if row["status"] == "Open" and row["severity"] == "Critical"
                ),
                "renewal_date": forecast["renewal_date"],
                "renewal_probability": forecast["renewal_probability"],
                "renewal_category": forecast["forecast_category"],
                "risk_reason": forecast["risk_reason"],
                "recommended_action": forecast["recommended_action"],
            }
        )

    return {
        "customers": customers,
        "products": products,
        "subscriptions": subscriptions,
        "invoices": invoices,
        "payments": payments,
        "usage_monthly": usage,
        "support_cases": support_cases,
        "cloud_costs": costs,
        "renewal_forecasts": renewal_forecasts,
        "customer_finance_summary": summaries,
    }


def validate_tables(tables: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    ids = {
        "customers": {row["customer_id"] for row in tables["customers"]},
        "products": {row["product_id"] for row in tables["products"]},
        "subscriptions": {row["subscription_id"] for row in tables["subscriptions"]},
        "invoices": {row["invoice_id"] for row in tables["invoices"]},
    }
    for row in tables["subscriptions"]:
        assert row["customer_id"] in ids["customers"]
        assert row["product_id"] in ids["products"]
    for table_name in ("invoices", "usage_monthly", "support_cases", "cloud_costs", "renewal_forecasts"):
        for row in tables[table_name]:
            assert row["customer_id"] in ids["customers"]
            assert row["subscription_id"] in ids["subscriptions"]
    for row in tables["payments"]:
        assert row["invoice_id"] in ids["invoices"]
        assert row["customer_id"] in ids["customers"]

    billed = round(sum(float(row["amount"]) for row in tables["invoices"]), 2)
    collected = round(sum(float(row["amount"]) for row in tables["payments"]), 2)
    outstanding = round(sum(float(row["amount"]) for row in tables["invoices"] if row["status"] != "Paid"), 2)
    summary_billed = round(sum(float(row["billed_revenue_6m"]) for row in tables["customer_finance_summary"]), 2)
    summary_outstanding = round(sum(float(row["ar_outstanding"]) for row in tables["customer_finance_summary"]), 2)
    assert billed == summary_billed
    assert outstanding == summary_outstanding
    assert round(billed - collected, 2) == outstanding
    return {
        "as_of_date": AS_OF_DATE.isoformat(),
        "table_rows": {name: len(rows) for name, rows in tables.items()},
        "billed_revenue_6m": billed,
        "cash_collected_6m": collected,
        "ar_outstanding": outstanding,
        "at_risk_arr": round(
            sum(
                float(row["renewal_arr"])
                for row in tables["renewal_forecasts"]
                if float(row["renewal_probability"]) < 0.6
            ),
            2,
        ),
    }


def write_tables(output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    tables = build_tables()
    quality = validate_tables(tables)
    for table_name, rows in tables.items():
        with (output_dir / f"{table_name}.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=TABLE_FIELDS[table_name])
            writer.writeheader()
            writer.writerows(rows)
    (output_dir / "quality_report.json").write_text(
        json.dumps(quality, indent=2) + "\n",
        encoding="utf-8",
    )
    return quality


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate deterministic SAS finance demo data.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parent / "data",
        help="Directory for generated CSV files.",
    )
    args = parser.parse_args()
    report = write_tables(args.output)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
