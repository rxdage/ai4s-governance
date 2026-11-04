from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ai4s_governance import audit, demo, naming
from ai4s_governance.registry import load_registry


class AuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "demo"
        demo.build(self.root, force=True)
        self.registry = load_registry(
            self.root / "registry",
            schema=naming.load_schema(self.root / "spec" / "filename-schema.yaml"),
        )
        self.sr_data = self.root / "workspaces" / "owner-a" / "SR_DATA"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_demo_is_clean(self) -> None:
        result = audit.audit(self.sr_data, registry=self.registry, label="Demo Lab")
        self.assertEqual(result.files, 4)  # 3 raw + 1 derived; sidecar excluded
        self.assertEqual(result.sidecars, 1)
        self.assertEqual(result.syntax_ok, 4)
        self.assertEqual(result.syntax_ok_pct, 100.0)
        self.assertEqual(result.registry_ok, 4)
        self.assertEqual(result.duplicates, [])
        self.assertTrue(result.recommendations)

    def test_report_and_no_mutation(self) -> None:
        before = sorted(p.name for p in self.sr_data.rglob("*") if p.is_file())
        out = Path(self.tmp.name) / "report.md"
        result = audit.audit(self.sr_data, registry=self.registry, label="Demo Lab")
        audit.write_report(result, out)
        after = sorted(p.name for p in self.sr_data.rglob("*") if p.is_file())
        self.assertEqual(before, after)
        text = out.read_text(encoding="utf-8")
        self.assertIn("Lab data health check", text)
        self.assertIn("No files were modified", text)
        self.assertIn("Demo Lab", text)

    def test_broken_names_are_counted(self) -> None:
        broken = Path(self.tmp.name) / "broken"
        broken.mkdir()
        names = [
            "final_v2.csv",
            "R37_W1_D2__MEAS__NA__T202603041430_RUN0000.csv",
            "R0007_W0012_D0003__MEAS__NA__T202603041430_RUN0000",
            "R0007 W0012 D0003__MEAS__NA__T202603041430_RUN0000.csv",
            "R0007_W0012_D0003__MEAS__NA__T202603041430_RUN0000.csv",
        ]
        for name in names:
            (broken / name).write_text("x", encoding="utf-8")
        (broken / "sub").mkdir()
        (broken / "sub" / names[-1]).write_text("x", encoding="utf-8")

        result = audit.audit(broken)
        self.assertEqual(result.files, 6)
        self.assertEqual(result.syntax_ok, 2)
        self.assertGreater(result.legacy.get("space", 0), 0)
        self.assertGreater(result.legacy.get("version", 0), 0)
        self.assertTrue(result.error_counts)
        self.assertEqual(len(result.duplicates), 1)
        self.assertIn("space", result.legacy)

    def test_names_file_mode(self) -> None:
        names = Path(self.tmp.name) / "names.txt"
        names.write_text(
            "\n".join(
                [
                    "_交付清单.csv",
                    "lab-a/_验收凭据.txt",
                    "lab-a/final_v2.csv",
                    "lab-a/R0007_W0012_D0003__MEAS__NA__T202603041430_RUN0000.csv",
                    "lab-b/R0007_W0012_D0003__MEAS__NA__T202603041430_RUN0000.csv",
                    "lab-b/Channel_01_for_filterData_2026-07-22-17-00-31.csv",
                ]
            ),
            encoding="utf-8",
        )
        result = audit.audit(names_file=names, label="Names only")
        self.assertEqual(result.files, 4)
        self.assertEqual(result.syntax_ok, 2)
        self.assertEqual(len(result.duplicates), 1)
        self.assertEqual(result.root, str(names.resolve()))

    def test_missing_path_raises(self) -> None:
        with self.assertRaises(FileNotFoundError):
            audit.audit(Path(self.tmp.name) / "nope")


if __name__ == "__main__":
    unittest.main()
