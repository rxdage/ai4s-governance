from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ai4s_governance import demo
from ai4s_governance.bot import BotCore


class BotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "demo"
        demo.build(self.root, force=True)
        self.core = BotCore(self.root / "lab.yaml", dry_run=True)
        self.core.open_receipt(
            "20260305-01",
            [
                {"id": "1", "text": "凭据是刚跑的吗？", "options": ["已做", "未做"]},
                {"id": "2", "text": "WARN 都答了吗？", "options": ["已做", "未做"]},
            ],
            ["owner-a"],
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_receipt_accepts_only_given_options(self) -> None:
        reply = self.core.handle("owner-a", "回执 20260305-01 1 已做")
        self.assertTrue(reply.recorded)
        bad = self.core.handle("owner-a", "回执 20260305-01 2 差不多吧")
        self.assertFalse(bad.recorded)
        self.assertIn("只认", bad.text)

    def test_receipt_is_person_scoped(self) -> None:
        reply = self.core.handle("steward", "回执 owner-a 20260305-01 1 已做")
        self.assertTrue(reply.recorded)
        # the owner sees the steward-filed answer
        self.assertIn("第1题：已做", self.core.handle("owner-a", "状态").text)
        reply = self.core.handle("owner-a", "回执 20990101-01 1 已做")
        self.assertFalse(reply.recorded)

    def test_release_is_steward_only(self) -> None:
        denied = self.core.handle("owner-a", "放行 owner-a 依据 我觉得可以")
        self.assertFalse(denied.recorded)
        allowed = self.core.handle("steward", "放行 owner-a 依据 凭据 PASS")
        self.assertTrue(allowed.recorded)
        self.assertIn("ingest copy", allowed.text)

    def test_waiver_needs_valid_date(self) -> None:
        bad = self.core.handle("steward", "豁免 owner-a CRED 到 明天 先放着")
        self.assertFalse(bad.recorded)
        ok = self.core.handle("steward", "豁免 owner-a CRED 到 2026-12-31 设备维修")
        self.assertTrue(ok.recorded)

    def test_status_shows_unanswered_as_not_done(self) -> None:
        text = self.core.handle("owner-a", "状态").text
        self.assertIn("未回（按未做算）", text)


if __name__ == "__main__":
    unittest.main()
