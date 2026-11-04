from __future__ import annotations

import unittest

from ai4s_governance import naming


class NamingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.schema = naming.load_schema()

    def test_selftest(self) -> None:
        self.assertEqual(naming.selftest(), 0)

    def test_parse_roundtrip(self) -> None:
        name = naming.sample_name()
        parsed = naming.parse(name, schema=self.schema, check_registry=False)
        self.assertTrue(parsed.ok, parsed.errors)
        self.assertEqual(parsed.batch, 7)
        self.assertEqual(parsed.sample, "W0012")
        self.assertEqual(parsed.unit, "D0003")
        self.assertEqual(parsed.type_code, "MEAS")
        self.assertEqual(parsed.conditions, ["BUF1"])
        self.assertEqual(parsed.run, 0)

    def test_library_and_all(self) -> None:
        name = "R0000_ALL_ALL__SUMMARY__NA__T202603041430_RUN0000.csv"
        parsed = naming.parse(name, schema=self.schema, check_registry=False)
        self.assertTrue(parsed.ok, parsed.errors)

    def test_all_mix_rejected(self) -> None:
        name = "R0007_ALL_D0003__MEAS__NA__T202603041430_RUN0000.csv"
        parsed = naming.parse(name, schema=self.schema, check_registry=False)
        self.assertIn("ZONE1_ALL_MIX", [e.code for e in parsed.errors])

    def test_byte_limit(self) -> None:
        long_type = "A" * 15
        conditions = "_".join(f"ABCDEFGHIJKL{i}" for i in range(11))
        name = (
            "R0007_W0000_D0000__"
            + long_type
            + "__"
            + conditions
            + "__T202603041430_RUN0000.csv"
        )
        self.assertGreater(len(name.encode("utf-8")), 200)
        parsed = naming.parse(name, schema=self.schema, check_registry=False)
        self.assertIn("NAME_TOO_LONG", [e.code for e in parsed.errors])

    def test_timestamp_must_be_real(self) -> None:
        name = "R0007_W0012_D0003__MEAS__NA__T202602301430_RUN0000.csv"
        parsed = naming.parse(name, schema=self.schema, check_registry=False)
        self.assertIn("TIME_INVALID", [e.code for e in parsed.errors])

    def test_condition_order_is_warning_not_error(self) -> None:
        name = "R0007_W0012_D0003__MEAS__DAQ1_BUF1__T202603041430_RUN0000.csv"
        parsed = naming.parse(name, schema=self.schema, check_registry=False)
        self.assertTrue(parsed.ok)
        self.assertIn("COND_ORDER", [w.code for w in parsed.warnings])


if __name__ == "__main__":
    unittest.main()
