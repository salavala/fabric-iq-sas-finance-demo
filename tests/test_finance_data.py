from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from pathlib import Path


DEMO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DEMO_ROOT))

from generate_data import build_tables, validate_tables, write_tables  # noqa: E402


class FinanceDataTests(unittest.TestCase):
    def test_data_reconciles(self) -> None:
        report = validate_tables(build_tables())

        self.assertEqual(report["table_rows"]["customers"], 12)
        self.assertEqual(report["table_rows"]["invoices"], 72)
        self.assertGreater(report["billed_revenue_6m"], report["cash_collected_6m"])
        self.assertGreater(report["at_risk_arr"], 0)

    def test_risk_scenarios_are_explainable(self) -> None:
        tables = build_tables()
        profiles = {row["customer_id"]: row for row in tables["customer_finance_summary"]}

        self.assertLess(profiles["C002"]["usage_trend_pct"], -25)
        self.assertEqual(profiles["C002"]["open_critical_cases"], 1)
        self.assertGreater(profiles["C004"]["overdue_ar"], 0)
        self.assertEqual(profiles["C004"]["renewal_category"], "At Risk")

    def test_csv_output_preserves_all_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            report = write_tables(Path(temp_dir))
            for table_name, expected_rows in report["table_rows"].items():
                with (Path(temp_dir) / f"{table_name}.csv").open(encoding="utf-8") as handle:
                    self.assertEqual(sum(1 for _ in csv.DictReader(handle)), expected_rows)


if __name__ == "__main__":
    unittest.main()
