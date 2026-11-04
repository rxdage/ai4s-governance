from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ai4s_governance import demo, ingest, naming, selfcheck
from ai4s_governance.registry import load_registry


class IngestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "demo"
        demo.build(self.root, force=True)
        self.registry = load_registry(
            self.root / "registry",
            schema=naming.load_schema(self.root / "spec" / "filename-schema.yaml"),
        )
        self.library = self.root / "library"
        self.sr_data = self.root / "workspaces" / "owner-a" / "SR_DATA"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_demo_passes_and_verifies(self) -> None:
        manifest = ingest.manifest_sha_map(self.library)
        report = selfcheck.check_delivery(self.sr_data, self.registry, manifest=manifest, write=False)
        self.assertTrue(report.ok, selfcheck.format_summary(report))
        self.assertEqual(report.warnings, [])
        self.assertTrue(ingest.verify(self.library).ok)

    def test_dry_run_does_not_write(self) -> None:
        before = sorted(p.name for p in (self.library / "data").rglob("*") if p.is_file())
        result = ingest.copy(self.sr_data, self.library, self.registry, apply=False)
        after = sorted(p.name for p in (self.library / "data").rglob("*") if p.is_file())
        self.assertEqual(before, after)
        self.assertFalse(result.applied)
        self.assertTrue(all(i.status in {"new", "already"} for i in result.items))

    def test_conflict_is_not_overwritten(self) -> None:
        inbox = Path(self.tmp.name) / "inbox"
        inbox.mkdir()
        name = "R0001_W0001_D0001__MEAS__BUF1_DAQ1__T202603041030_RUN0000.csv"
        (inbox / name).write_text("different bytes\n", encoding="utf-8")
        result = ingest.plan(inbox, self.library, self.registry)
        self.assertEqual(result.items[0].status, "conflict")
        copy_result = ingest.copy(inbox, self.library, self.registry, apply=True)
        self.assertEqual(copy_result.conflicts, 1)
        stored = next((self.library / "data").rglob(name))
        self.assertNotEqual(stored.read_text(encoding="utf-8"), "different bytes\n")

    def test_missing_sidecar_fails(self) -> None:
        sidecars = list(self.sr_data.glob("*.meta.yaml"))
        self.assertEqual(len(sidecars), 1)
        sidecars[0].unlink()
        report = selfcheck.check_delivery(
            self.sr_data,
            self.registry,
            manifest=ingest.manifest_sha_map(self.library),
            write=False,
        )
        self.assertFalse(report.ok)
        self.assertIn("SIDECAR_MISSING", [f.code for f in report.errors])

        # the ingest tool must enforce the same gate, not only selfcheck
        plan = ingest.plan(self.sr_data, self.library, self.registry)
        derived = [i for i in plan.items if i.partition == "derived"]
        self.assertEqual(len(derived), 1)
        self.assertEqual(derived[0].status, "invalid")
        self.assertIn("SIDECAR_MISSING", derived[0].detail)

    def test_verify_detects_tampering(self) -> None:
        target = next((self.library / "data").rglob("*.csv"))
        target.chmod(0o644)
        target.write_text("tampered\n", encoding="utf-8")
        result = ingest.verify(self.library)
        self.assertFalse(result.ok)
        self.assertTrue(result.modified)

    def test_void_keeps_file(self) -> None:
        target = next((self.library / "data").rglob("*.csv"))
        ingest.void(self.library, target.name, "superseded by a later RUN", "Steward")
        self.assertTrue(target.exists())
        self.assertIn(target.name, ingest.verify(self.library).voided)


if __name__ == "__main__":
    unittest.main()
