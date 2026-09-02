"""Regression tests for the flatten Oracle and hierarchical checker."""

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
	"""Checks handwritten RTL fixtures against both equivalence strategies."""

	@classmethod
	def setUpClass(cls) -> None:
		"""Locate Yosys once or skip the class when it is unavailable.

		Raises:
			unittest.SkipTest: If the configured Yosys executable is not found.
		"""

		cls.yosys = os.environ.get("YOSYS", "yosys")
		if shutil.which(cls.yosys) is None:
			raise unittest.SkipTest(f"Yosys executable not found: {cls.yosys}")

	def run_case(self, name: str, expected_equivalent: bool, seq: int = 2) -> None:
		"""Run one fixture through the full-flatten Oracle.

		Args:
			name: Fixture directory name under ``tests/cases``.
			expected_equivalent: Expected functional equivalence result.
			seq: Sequential depth passed to ``equiv_simple``.
		"""

		case_dir = CASES_DIR / name
		common = case_dir / "common.v"
		include_dir = case_dir / "include"
		with tempfile.TemporaryDirectory(prefix=f"hier-equiv-{name}-") as work_dir:
			result = run_flatten_oracle(
				OracleConfig(
					gold_sources=(case_dir / "gold.v",),
					gate_sources=(case_dir / "gate.v",),
					common_sources=(common,) if common.is_file() else (),
					include_dirs=(include_dir,) if include_dir.is_dir() else (),
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
		"""Verify that all positive fixtures are proven equivalent."""

		for name in (
			"pass_identical",
			"pass_renamed_hierarchy",
			"pass_equivalent_rewrite",
			"pass_hierarchy_fallback",
			"pass_parent_context",
			"pass_reused_pair",
			"pass_blackbox_common",
			"pass_multilevel_renamed",
			"pass_fallback_below_top",
			"pass_child_interface_diff",
			"pass_include_header",
		):
			with self.subTest(name=name):
				self.run_case(name, True)

	def test_non_equivalent_cases(self) -> None:
		"""Verify that all negative fixtures leave unproven equivalence cells."""

		for name in (
			"fail_internal_logic",
			"fail_swapped_ports",
			"fail_missing_instance",
			"fail_parameter",
			"fail_sequential_connection",
			"fail_blackbox_mismatch",
		):
			with self.subTest(name=name):
				self.run_case(name, False)

	@unittest.expectedFailure
	def test_implicit_blackbox_connection_mismatch(self) -> None:
		"""Require undefined black-box boundary connections to be compared.

		This pending test distinguishes a functional mismatch from an input error:
		both strategies must complete and report non-equivalence when the same
		undefined module input is connected to ``a`` on Gold and ``b`` on Gate.
		"""

		case_dir = CASES_DIR / "fail_implicit_blackbox_connection"
		problems: list[str] = []
		with tempfile.TemporaryDirectory(
			prefix="implicit-blackbox-oracle-"
		) as oracle_work_dir:
			oracle = run_flatten_oracle(
				OracleConfig(
					gold_sources=(case_dir / "gold.v",),
					gate_sources=(case_dir / "gate.v",),
					top="top",
					work_dir=Path(oracle_work_dir),
					yosys=self.yosys,
				)
			)
			oracle_log = oracle.log_path.read_text(encoding="utf-8")
			if oracle.equivalent or "unproven $equiv" not in oracle_log:
				problems.append(
					"Oracle did not complete a functional non-equivalence proof"
				)

		with tempfile.TemporaryDirectory(
			prefix="implicit-blackbox-hier-"
		) as hierarchy_work_dir:
			try:
				hierarchy = run_hierarchical_check(
					HierarchicalConfig(
						gold_sources=(case_dir / "gold.v",),
						gate_sources=(case_dir / "gate.v",),
						top="top",
						work_dir=Path(hierarchy_work_dir),
						yosys=self.yosys,
					)
				)
			except RuntimeError as error:
				problems.append(f"hierarchical inventory failed: {error}")
			else:
				if hierarchy.equivalent:
					problems.append("hierarchical check accepted mismatched connections")

		self.assertEqual(problems, [])

	def test_hierarchical_results_match_oracle(self) -> None:
		"""Require hierarchical conclusions and special paths to match the Oracle."""

		cases = {
			"pass_identical": True,
			"pass_renamed_hierarchy": True,
			"pass_equivalent_rewrite": True,
			"pass_hierarchy_fallback": True,
			"pass_parent_context": True,
			"pass_reused_pair": True,
			"pass_blackbox_common": True,
			"pass_multilevel_renamed": True,
			"pass_fallback_below_top": True,
			"pass_child_interface_diff": True,
			"pass_include_header": True,
			"fail_internal_logic": False,
			"fail_swapped_ports": False,
			"fail_missing_instance": False,
			"fail_parameter": False,
			"fail_sequential_connection": False,
			"fail_blackbox_mismatch": False,
		}
		for name, expected_equivalent in cases.items():
			with self.subTest(name=name):
				case_dir = CASES_DIR / name
				common = case_dir / "common.v"
				include_dir = case_dir / "include"
				with tempfile.TemporaryDirectory(
					prefix=f"hier-check-{name}-"
				) as work_dir:
					result = run_hierarchical_check(
						HierarchicalConfig(
							gold_sources=(case_dir / "gold.v",),
							gate_sources=(case_dir / "gate.v",),
							common_sources=(common,) if common.is_file() else (),
							include_dirs=(
								(include_dir,) if include_dir.is_dir() else ()
							),
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
					if not expected_equivalent:
						self.assertEqual(result.warnings, ())
					if name == "pass_hierarchy_fallback":
						self.assertEqual(result.pairs[-1].method, "flatten-fallback")
						self.assertEqual(len(result.pairs[-1].warnings), 1)
						self.assertIn(
							"pass relies on local flattening",
							result.pairs[-1].warnings[0],
						)
					if name == "pass_parent_context":
						self.assertEqual(result.pairs[-1].method, "flatten-fallback")
						self.assertEqual(len(result.pairs[-1].warnings), 1)
						self.assertIn(
							"(gold_stage, gate_stage)",
							result.pairs[-1].warnings[0],
						)
						child = next(
							pair
							for pair in result.pairs
							if pair.gold_module == "gold_stage"
						)
						self.assertFalse(child.equivalent)
						self.assertEqual(child.warnings, ())
						self.assertEqual(result.warnings, result.pairs[-1].warnings)
					if name == "pass_reused_pair":
						self.assertEqual(len(result.pairs), 2)
					if name == "pass_blackbox_common":
						self.assertEqual(len(result.pairs), 1)
						self.assertEqual(result.pairs[-1].method, "compositional")
						self.assertEqual(result.pairs[-1].children, ())
					if name == "pass_multilevel_renamed":
						self.assertEqual(len(result.pairs), 3)
						self.assertTrue(all(pair.equivalent for pair in result.pairs))
						self.assertEqual(result.pairs[-1].method, "compositional")
					if name == "pass_fallback_below_top":
						self.assertEqual(len(result.pairs), 3)
						top_pair = result.pairs[-1]
						self.assertEqual(top_pair.method, "compositional")
						self.assertEqual(top_pair.warnings, ())
						wrap_pair = next(
							pair
							for pair in result.pairs
							if pair.gold_module == "gold_wrap"
						)
						self.assertEqual(wrap_pair.method, "flatten-fallback")
						self.assertTrue(wrap_pair.equivalent)
						self.assertEqual(len(wrap_pair.warnings), 1)
						self.assertIn(
							"(gold_stage, gate_stage)", wrap_pair.warnings[0]
						)
						stage_pair = next(
							pair
							for pair in result.pairs
							if pair.gold_module == "gold_stage"
						)
						self.assertFalse(stage_pair.equivalent)
						self.assertEqual(result.warnings, wrap_pair.warnings)
					if name == "pass_child_interface_diff":
						self.assertEqual(result.pairs[-1].method, "flatten-fallback")
						self.assertEqual(len(result.pairs[-1].warnings), 1)


if __name__ == "__main__":
	unittest.main()
