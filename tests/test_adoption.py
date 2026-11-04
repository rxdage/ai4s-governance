from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ai4s_governance import adoption, demo
from ai4s_governance.bot import BotCore


class AdoptionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "demo"
        demo.build(self.root, force=True)
        self.config = self.root / "lab.yaml"
        self.state = self.root / "state"
        self.state.mkdir(exist_ok=True)

        base = datetime(2026, 3, 4, 10, 0, tzinfo=timezone(timedelta(hours=8)))
        rows = [
            {"at": base.strftime("%Y-%m-%d %H:%M:%S%z"), "person": "owner-a", "trigger": "self",
             "root": str(self.root / "workspaces/owner-a/SR_DATA"), "files": 3, "errors": 5,
             "warnings": 0, "answered": 0, "ok": False, "snapshot": "a"},
            {"at": (base + timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S%z"), "person": "owner-a",
             "trigger": "self", "root": str(self.root / "workspaces/owner-a/SR_DATA"),
             "files": 3, "errors": 0, "warnings": 0, "answered": 0, "ok": True, "snapshot": "b"},
            {"at": (base + timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S%z"), "person": "owner-a",
             "trigger": "self", "root": str(self.root / "workspaces/owner-a/SR_DATA"),
             "files": 3, "errors": 0, "warnings": 0, "answered": 0, "ok": True, "snapshot": "c"},
        ]
        with (self.state / "selfcheck_runs.jsonl").open("w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")

        # a receipt reply from the owner
        core = BotCore(self.config)
        core.open_receipt(
            "20260305-01",
            [{"id": "1", "text": "凭据是刚跑的吗？", "options": ["已做", "未做"]}],
            ["owner-a"],
        )
        core.handle("owner-a", "回执 20260305-01 1 已做")

        # a registry proposal
        proposal = self.root / "workspaces" / "owner-a" / "REGISTRY" / "proposal.yaml"
        proposal.parent.mkdir(parents=True, exist_ok=True)
        proposal.write_text(
            "codes:\n"
            "  BUF9:\n"
            "    class: BUF\n"
            "    instance: demo proposal\n"
            "    proposer: owner-a\n"
            "    proposed_at: 2026-03-06\n"
            "    status: PROPOSED\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_milestones(self) -> None:
        report = adoption.run(self.config)
        owner = next(p for p in report.people if p.id == "owner-a")
        self.assertEqual(owner.m1_source, "log")
        self.assertIsNotNone(owner.m1)
        self.assertEqual(owner.rounds, 2)
        self.assertAlmostEqual(owner.days_to_first_pass, 1.0, places=1)
        self.assertIsNotNone(owner.m2)
        self.assertIsNotNone(owner.m3)
        self.assertEqual(owner.status, "M4")
        self.assertEqual(report.summary["m1"], 1)

    def test_report_is_written(self) -> None:
        report = adoption.run(self.config)
        out = Path(self.tmp.name) / "adoption.md"
        adoption.write_report(report, out)
        text = out.read_text(encoding="utf-8")
        self.assertIn("Adoption report", text)
        self.assertIn("M1", text)
        self.assertIn("owner-a" if "owner-a" in text else "Owner A", text)

    def test_empty_log_warns(self) -> None:
        (self.state / "selfcheck_runs.jsonl").unlink()
        report = adoption.run(self.config)
        self.assertTrue(report.warnings)
        owner = next(p for p in report.people if p.id == "owner-a")
        # falls back to the latest credential mtime
        self.assertIsNotNone(owner.m1)
        self.assertEqual(owner.m1_source, "credential-mtime")


if __name__ == "__main__":
    unittest.main()
