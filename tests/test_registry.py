from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import yaml

from ai4s_governance import naming
from ai4s_governance.registry import Registry, load_registry, scaffold


class RegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name) / "registry"
        scaffold(self.dir)
        self.schema = naming.load_schema()
        self.reg = load_registry(self.dir, schema=self.schema)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _types_path(self) -> Path:
        return self.dir / "types.yaml"

    def test_unsigned_entry_is_not_usable(self) -> None:
        result = self.reg.check()
        self.assertTrue(result.ok, [e.to_dict() for e in result.errors])
        self.assertEqual(naming.effective_status(self.reg.types["MEAS"]), "PROPOSED")

    def test_sign_then_verify(self) -> None:
        self.reg.sign("type", ["MEAS"], "Li Ming", "2026-03-04", apply=True)
        self.reg.sign("class", ["COND"], "Li Ming", "2026-03-04", apply=True)
        self.reg.sign("code", ["COND1"], "Li Ming", "2026-03-04", apply=True)
        reloaded = load_registry(self.dir, schema=self.schema)
        self.assertEqual(naming.effective_status(reloaded.types["MEAS"]), "APPROVED")
        self.assertTrue(reloaded.check().ok, [e.to_dict() for e in reloaded.check().errors])

    def test_editing_signed_entry_invalidates_signature(self) -> None:
        self.reg.sign("type", ["MEAS"], "Li Ming", "2026-03-04", apply=True)
        data = yaml.safe_load(self._types_path().read_text(encoding="utf-8"))
        data["types"]["MEAS"]["description"] = "changed after signing"
        self._types_path().write_text(
            yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8"
        )
        reloaded = load_registry(self.dir, schema=self.schema)
        codes = [e.code for e in reloaded.check().errors]
        self.assertIn("SIGNATURE_STALE", codes)
        self.assertEqual(naming.effective_status(reloaded.types["MEAS"]), "SIGNATURE_STALE")

    def test_title_cannot_sign(self) -> None:
        with self.assertRaises(ValueError):
            self.reg.sign("type", ["MEAS"], "合伙人", "2026-03-04", apply=False)

    def test_duplicate_instance_rejected(self) -> None:
        data = yaml.safe_load((self.dir / "codes.yaml").read_text(encoding="utf-8"))
        data["codes"]["COND2"] = dict(data["codes"]["COND1"], **{"class": "COND"})
        (self.dir / "codes.yaml").write_text(
            yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8"
        )
        reloaded = load_registry(self.dir, schema=self.schema)
        codes = [e.code for e in reloaded.check().errors]
        self.assertIn("DUPLICATE_INSTANCE", codes)

    def test_revoke(self) -> None:
        self.reg.sign("type", ["MEAS"], "Li Ming", "2026-03-04", apply=True)
        self.reg.revoke("type", "MEAS", "Li Ming", "2026-03-05", "wrong code", apply=True)
        reloaded = load_registry(self.dir, schema=self.schema)
        self.assertEqual(naming.effective_status(reloaded.types["MEAS"]), "PROPOSED")


if __name__ == "__main__":
    unittest.main()
