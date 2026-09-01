"""Command-line interface for yosys-hier-equiv."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Sequence

from .hierarchy import HierarchicalConfig, run_hierarchical_check
from .oracle import OracleConfig, run_flatten_oracle


def _add_common_arguments(parser: argparse.ArgumentParser) -> None:
	parser.add_argument("--gold", action="append", required=True, type=Path)
	parser.add_argument("--gate", action="append", required=True, type=Path)
	parser.add_argument("--common", action="append", default=[], type=Path)
	parser.add_argument("-I", "--include-dir", action="append", default=[], type=Path)
	parser.add_argument("--top", default="top")
	parser.add_argument("--seq", type=int, default=2)
	parser.add_argument("--yosys", default=os.environ.get("YOSYS", "yosys"))
	parser.add_argument("--sv", action="store_true", help="read all sources as SystemVerilog")


def _build_parser() -> argparse.ArgumentParser:
	parser = argparse.ArgumentParser(prog="yosys-hier-equiv")
	subparsers = parser.add_subparsers(dest="command", required=True)

	oracle = subparsers.add_parser(
		"flatten-oracle",
		help="flatten both designs and run Yosys equivalence checking",
	)
	_add_common_arguments(oracle)
	oracle.add_argument("--work-dir", type=Path, default=Path("build/flatten-oracle"))

	hierarchy = subparsers.add_parser(
		"hier-check",
		help="recursively prove matching hierarchy and locally flatten ambiguous pairs",
	)
	_add_common_arguments(hierarchy)
	hierarchy.add_argument("--work-dir", type=Path, default=Path("build/hier-check"))
	hierarchy.add_argument(
		"--validate-oracle",
		action="store_true",
		help="also run the full-flatten Oracle and reject inconsistent results",
	)
	return parser


def main(argv: Sequence[str] | None = None) -> int:
	parser = _build_parser()
	args = parser.parse_args(argv)

	try:
		if args.command == "flatten-oracle":
			result = run_flatten_oracle(
				OracleConfig(
					gold_sources=tuple(args.gold),
					gate_sources=tuple(args.gate),
					common_sources=tuple(args.common),
					include_dirs=tuple(args.include_dir),
					top=args.top,
					seq=args.seq,
					work_dir=args.work_dir,
					yosys=args.yosys,
					system_verilog=args.sv,
				)
			)
		else:
			result = run_hierarchical_check(
				HierarchicalConfig(
					gold_sources=tuple(args.gold),
					gate_sources=tuple(args.gate),
					common_sources=tuple(args.common),
					include_dirs=tuple(args.include_dir),
					top=args.top,
					seq=args.seq,
					work_dir=args.work_dir,
					yosys=args.yosys,
					system_verilog=args.sv,
					validate_oracle=args.validate_oracle,
				)
			)
	except (OSError, RuntimeError, ValueError) as error:
		parser.exit(1, f"error: {error}\n")

	if args.command == "hier-check":
		if not result.oracle_consistent:
			print(
				"ERROR: hierarchical result disagrees with the full-flatten Oracle; "
				f"report: {result.report_path}"
			)
			return 3
		if result.equivalent:
			print(
				f"PASS: equivalent across {len(result.pairs)} module pair(s); "
				f"report: {result.report_path}"
			)
			return 0
		print(
			f"FAIL: equivalence not proven across {len(result.pairs)} module pair(s); "
			f"report: {result.report_path}"
		)
		return 1

	if result.equivalent:
		print(f"PASS: equivalent; log: {result.log_path}")
		return 0

	print(f"FAIL: equivalence not proven; log: {result.log_path}")
	return 1
