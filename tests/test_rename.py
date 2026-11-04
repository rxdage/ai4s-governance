from __future__ import annotations

import csv
import shutil
import tempfile
import unittest
from pathlib import Path

from ai4s_governance import demo, naming, rename
from ai4s_governance.registry import load_registry


class RenameTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "demo"
        demo.build(self.root, force=True)
        self.registry = load_registry(
            self.root / "registry",
            schema=naming.load_schema(self.root / "spec" / "filename-schema.yaml"),
        )
        self.dir = Path(self.tmp.name) / "rename"
        self.dir.mkdir()
        self.old = "R0001_W0001_D0001__MEAS__BUF1_DAQ1__T202603041030_RUN0000.csv"
        shutil.copyfile(
            next((self.root / "workspaces" / "owner-a" / "SR_DATA").glob("*.csv")),
            self.dir / self.old,
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _plan(self, rows):
        path = Path(self.tmp.name) / "plan.csv"
        with path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(["old", "new", "确认改身份"])
            for row in rows:
                writer.writerow(row)
        return path

    def test_rename_type_only(self) -> None:
        new = "R0001_W0001_D0001__CALIB__BUF1_DAQ1__T202603041030_RUN0000.csv"
        rows = rename.build_plan(self.dir, rename.load_plan(self._plan([(self.old, new, "")])), self.registry)
        self.assertTrue(rows[0].ok, rows[0].reasons)
        dry = rename.apply_plan(self.dir, rows, dry_run=True)
        self.assertEqual(dry["applied"], 0)
        self.assertTrue((self.dir / self.old).exists())
        result = rename.apply_plan(self.dir, rows, dry_run=False)
        self.assertEqual(result["applied"], 1)
        self.assertFalse((self.dir / self.old).exists())
        self.assertTrue((self.dir / new).exists())
        self.assertTrue(Path(result["log"]).exists())

    def test_identity_change_needs_confirmation(self) -> None:
        new = "R0001_W0001_D0002__MEAS__BUF1_DAQ1__T202603041030_RUN0000.csv"
        rows = rename.build_plan(self.dir, rename.load_plan(self._plan([(self.old, new, "")])), self.registry)
        self.assertFalse(rows[0].ok)
        self.assertTrue(any("身份区变化" in r for r in rows[0].reasons))
        result = rename.apply_plan(self.dir, rows, dry_run=False)
        self.assertEqual(result["rejected"], 1)
        self.assertTrue((self.dir / self.old).exists())

    def test_extension_change_rejected(self) -> None:
        new = "R0001_W0001_D0001__MEAS__BUF1_DAQ1__T202603041030_RUN0000.txt"
        rows = rename.build_plan(self.dir, rename.load_plan(self._plan([(self.old, new, "")])), self.registry)
        self.assertFalse(rows[0].ok)
        self.assertTrue(any("扩展名变化" in r for r in rows[0].reasons))

    def test_all_or_nothing(self) -> None:
        good = "R0001_W0001_D0001__CALIB__BUF1_DAQ1__T202603041030_RUN0000.csv"
        bad = "R0001_W0001_D0002__MEAS__BUF1_DAQ1__T202603041030_RUN0000.csv"
        rows = rename.build_plan(
            self.dir,
            rename.load_plan(self._plan([(self.old, good, ""), (self.old, bad, "")])),
            self.registry,
        )
        self.assertTrue(any(not r.ok for r in rows))
        result = rename.apply_plan(self.dir, rows, dry_run=False)
        self.assertEqual(result["applied"], 0)
        self.assertTrue((self.dir / self.old).exists())


if __name__ == "__main__":
    unittest.main()
