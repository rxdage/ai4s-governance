from __future__ import annotations

import csv
import unittest
from pathlib import Path

from ai4s_governance import ledger, naming

ROOT = Path(__file__).resolve().parents[1]


class ExampleTests(unittest.TestCase):
    def test_broken_names_file(self) -> None:
        path = ROOT / "examples" / "broken_names.csv"
        with path.open("r", encoding="utf-8", newline="") as fh:
            rows = list(csv.DictReader(fh))
        self.assertGreater(len(rows), 5)
        for row in rows:
            parsed = naming.parse(row["name"], check_registry=False)
            expected = row["expected_code"].strip()
            if expected:
                codes = [e.code for e in parsed.errors]
                self.assertIn(
                    expected,
                    codes,
                    f"{row['name']}: expected {expected}, got {codes}",
                )
            else:
                self.assertTrue(parsed.ok, parsed.errors)

    def test_example_ledger(self) -> None:
        issues = ledger.check(ROOT / "examples" / "ledger" / "deprecations.yaml")
        errors = [i for i in issues if i.severity == "ERROR"]
        self.assertEqual(errors, [], [i.to_dict() for i in errors])
        report = ledger.report(ROOT / "examples" / "ledger" / "deprecations.yaml")
        self.assertGreaterEqual(report["entries"], 5)


if __name__ == "__main__":
    unittest.main()
