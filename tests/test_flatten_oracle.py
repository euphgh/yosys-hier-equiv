from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from pathlib import Path

from yosys_hier_equiv import (
	HierarchicalConfig,
	OracleConfig,
	run_flatten_oracle,
	run_hierarchical_check,
)


ROOT = Path(__file__).resolve().parents[1]
CASES_DIR = ROOT / "tests" / "cases"


class FlattenOracleTests(unittest.TestCase):
	@classmethod
	def setUpClass(cls) -> None:
		cls.yosys = os.environ.get("YOSYS", "yosys")
		if shutil.which(cls.yosys) is None:
			raise unittest.SkipTest(f"Yosys executable not found: {cls.yosys}")

	def run_case(self, name: str, expected_equivalent: bool, seq: int = 2) -> None:
		case_dir = CASES_DIR / name
		common = case_dir / "common.v"
		with tempfile.TemporaryDirectory(prefix=f"hier-equiv-{name}-") as work_dir:
			result = run_flatten_oracle(
				OracleConfig(
					gold_sources=(case_dir / "gold.v",),
					gate_sources=(case_dir / "gate.v",),
					common_sources=(common,) if common.is_file() else (),
					top="top",
					seq=seq,
					work_dir=Path(work_dir),
					yosys=self.yosys,
				)
			)
			log = result.log_path.read_text(encoding="utf-8")
			self.assertEqual(
				result.equivalent,
				expected_equivalent,
				msg=f"unexpected result for {name}:\n{log[-6000:]}",
			)
			if expected_equivalent:
				self.assertIn("Equivalence successfully proven", log)
			else:
				self.assertIn("unproven $equiv", log)

	def test_equivalent_cases(self) -> None:
		for name in (
			"pass_identical",
			"pass_renamed_hierarchy",
			"pass_equivalent_rewrite",
			"pass_hierarchy_fallback",
			"pass_parent_context",
			"pass_reused_pair",
		):
			with self.subTest(name=name):
				self.run_case(name, True)

	def test_non_equivalent_cases(self) -> None:
		for name in (
			"fail_internal_logic",
			"fail_swapped_ports",
			"fail_missing_instance",
			"fail_parameter",
			"fail_sequential_connection",
		):
			with self.subTest(name=name):
				self.run_case(name, False)

	def test_hierarchical_results_match_oracle(self) -> None:
		cases = {
			"pass_identical": True,
			"pass_renamed_hierarchy": True,
			"pass_equivalent_rewrite": True,
			"pass_hierarchy_fallback": True,
			"pass_parent_context": True,
			"pass_reused_pair": True,
			"fail_internal_logic": False,
			"fail_swapped_ports": False,
			"fail_missing_instance": False,
			"fail_parameter": False,
			"fail_sequential_connection": False,
		}
		for name, expected_equivalent in cases.items():
			with self.subTest(name=name):
				case_dir = CASES_DIR / name
				common = case_dir / "common.v"
				with tempfile.TemporaryDirectory(
					prefix=f"hier-check-{name}-"
				) as work_dir:
					result = run_hierarchical_check(
						HierarchicalConfig(
							gold_sources=(case_dir / "gold.v",),
							gate_sources=(case_dir / "gate.v",),
							common_sources=(common,) if common.is_file() else (),
							top="top",
							seq=2,
							work_dir=Path(work_dir),
							yosys=self.yosys,
							validate_oracle=True,
						)
					)
					self.assertEqual(result.equivalent, expected_equivalent)
					self.assertTrue(result.oracle_consistent)
					self.assertTrue(result.report_path.is_file())
					if name == "pass_hierarchy_fallback":
						self.assertEqual(result.pairs[-1].method, "flatten-fallback")
					if name == "pass_parent_context":
						self.assertEqual(result.pairs[-1].method, "flatten-fallback")
					if name == "pass_reused_pair":
						self.assertEqual(len(result.pairs), 2)


if __name__ == "__main__":
	unittest.main()
