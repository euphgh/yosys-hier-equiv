"""Top-down compositional equivalence checking backed by Yosys."""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, TextIO

from .oracle import (
	OracleConfig,
	_validate_config,
	_write_read_commands,
	_yosys_quote,
	run_flatten_oracle,
)


_VERILOG_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]*$")


@dataclass(frozen=True)
class HierarchicalConfig:
	"""Inputs for one top-down hierarchical equivalence run."""

	gold_sources: tuple[Path, ...]
	gate_sources: tuple[Path, ...]
	common_sources: tuple[Path, ...] = ()
	include_dirs: tuple[Path, ...] = ()
	top: str = "top"
	seq: int = 2
	work_dir: Path = Path("build/hier-check")
	yosys: str = "yosys"
	system_verilog: bool = False
	validate_oracle: bool = False


@dataclass(frozen=True)
class PairResult:
	"""One compositional or fallback proof obligation."""

	gold_module: str
	gate_module: str
	equivalent: bool
	method: str
	reason: str
	children: tuple[tuple[str, str], ...]
	log_path: Path


@dataclass(frozen=True)
class HierarchicalResult:
	"""Hierarchical result plus optional Golden Oracle cross-check."""

	equivalent: bool
	pairs: tuple[PairResult, ...]
	report_path: Path
	oracle_equivalent: bool | None = None
	oracle_log_path: Path | None = None

	@property
	def oracle_consistent(self) -> bool:
		return self.oracle_equivalent is None or self.equivalent == self.oracle_equivalent


@dataclass(frozen=True)
class _Inventory:
	modules: dict[str, dict[str, Any]]
	json_path: Path


@dataclass
class _PairPlan:
	children: list[tuple[str, str, str, bool]] = field(default_factory=list)
	fallback_reason: str | None = None


def _as_oracle_config(config: HierarchicalConfig, work_dir: Path) -> OracleConfig:
	return OracleConfig(
		gold_sources=config.gold_sources,
		gate_sources=config.gate_sources,
		common_sources=config.common_sources,
		include_dirs=config.include_dirs,
		top=config.top,
		seq=config.seq,
		work_dir=work_dir,
		yosys=config.yosys,
		system_verilog=config.system_verilog,
	)


def _run_yosys(yosys: str, script_path: Path, log_path: Path) -> bool:
	with log_path.open("w", encoding="utf-8") as log_stream:
		completed = subprocess.run(
			[yosys, "-Q", "-s", str(script_path)],
			stdout=log_stream,
			stderr=subprocess.STDOUT,
			check=False,
		)
	return completed.returncode == 0


def _rtlil_identifier(name: str) -> str:
	"""Return one exact RTLIL identifier token for a Yosys command."""

	if "\n" in name or "\r" in name or any(character.isspace() for character in name):
		raise ValueError(f"unsupported RTLIL identifier: {name!r}")
	return "\\" + name


def _build_inventory(
	config: HierarchicalConfig,
	side_sources: tuple[Path, ...],
	side_name: str,
	work_dir: Path,
) -> _Inventory:
	script_path = work_dir / f"inventory-{side_name}.ys"
	log_path = work_dir / f"inventory-{side_name}.log"
	json_path = work_dir / f"inventory-{side_name}.json"
	with script_path.open("w", encoding="ascii") as stream:
		stream.write("design -reset-vlog\n")
		_write_read_commands(
			stream,
			(*config.common_sources, *side_sources),
			config.include_dirs,
			config.system_verilog,
		)
		stream.write(f"hierarchy -check -top {_rtlil_identifier(config.top)}\n")
		stream.write("proc\n")
		stream.write("memory\n")
		stream.write("opt_clean\n")
		stream.write(f"write_json {_yosys_quote(str(json_path))}\n")

	if not _run_yosys(config.yosys, script_path, log_path):
		raise RuntimeError(f"failed to inventory {side_name} design; log: {log_path}")
	with json_path.open(encoding="utf-8") as stream:
		data = json.load(stream)
	modules = data.get("modules")
	if not isinstance(modules, dict):
		raise RuntimeError(f"invalid Yosys JSON inventory: {json_path}")
	return _Inventory(modules=modules, json_path=json_path)


def _port_signature(module: dict[str, Any]) -> dict[str, tuple[str, int]]:
	return {
		name: (port["direction"], len(port["bits"]))
		for name, port in module.get("ports", {}).items()
	}


def _hierarchical_cells(
	module: dict[str, Any], inventory: _Inventory
) -> dict[str, dict[str, Any]]:
	return {
		name: cell
		for name, cell in module.get("cells", {}).items()
		if cell.get("type") in inventory.modules
	}


def _is_blackbox(module: dict[str, Any]) -> bool:
	attributes = module.get("attributes", {})
	return bool(attributes.get("blackbox") or attributes.get("whitebox"))


def _plan_pair(
	gold_module: dict[str, Any],
	gate_module: dict[str, Any],
	gold_inventory: _Inventory,
	gate_inventory: _Inventory,
) -> _PairPlan:
	if _port_signature(gold_module) != _port_signature(gate_module):
		return _PairPlan(fallback_reason="module interfaces differ")

	gold_cells = _hierarchical_cells(gold_module, gold_inventory)
	gate_cells = _hierarchical_cells(gate_module, gate_inventory)
	if set(gold_cells) != set(gate_cells):
		return _PairPlan(fallback_reason="hierarchical instance sets differ")

	plan = _PairPlan()
	for cell_name in sorted(gold_cells):
		gold_type = gold_cells[cell_name]["type"]
		gate_type = gate_cells[cell_name]["type"]
		gold_child = gold_inventory.modules[gold_type]
		gate_child = gate_inventory.modules[gate_type]
		if _port_signature(gold_child) != _port_signature(gate_child):
			return _PairPlan(
				fallback_reason=f"child interface differs at instance {cell_name}"
			)
		recurse = True
		if _is_blackbox(gold_child) or _is_blackbox(gate_child):
			if gold_type != gate_type or not (
				_is_blackbox(gold_child) and _is_blackbox(gate_child)
			):
				return _PairPlan(
					fallback_reason=f"black-box identity differs at instance {cell_name}"
				)
			recurse = False
		plan.children.append((cell_name, gold_type, gate_type, recurse))
	return plan


def _verilog_identifier(name: str) -> str:
	if _VERILOG_IDENTIFIER_RE.fullmatch(name):
		return name
	return "\\" + name + " "


def _write_stubs(
	path: Path,
	children: list[tuple[str, str, str, bool]],
	gold_inventory: _Inventory,
) -> dict[str, str]:
	stub_names: dict[str, str] = {}
	with path.open("w", encoding="ascii") as stream:
		for index, (cell_name, gold_type, _, _) in enumerate(children):
			stub_name = f"__hier_equiv_stub_{index}"
			stub_names[cell_name] = stub_name
			ports = gold_inventory.modules[gold_type].get("ports", {})
			stream.write(f"(* blackbox *) module {stub_name}(\n")
			declarations: list[str] = []
			for port_name, port in ports.items():
				width = len(port["bits"])
				range_text = "" if width == 1 else f"[{width - 1}:0] "
				declarations.append(
					f"  {port['direction']} {range_text}{_verilog_identifier(port_name)}"
				)
			stream.write(",\n".join(declarations))
			stream.write("\n);\nendmodule\n\n")
	return stub_names


def _write_prepared_side(
	stream: TextIO,
	config: HierarchicalConfig,
	side_sources: tuple[Path, ...],
	target_module: str,
	result_module: str,
	stub_path: Path | None,
	stub_names: dict[str, str],
	flatten: bool,
) -> None:
	stream.write("design -reset-vlog\n")
	_write_read_commands(
		stream,
		(*config.common_sources, *side_sources),
		config.include_dirs,
		config.system_verilog,
	)
	stream.write(f"hierarchy -check -top {_rtlil_identifier(config.top)}\n")
	stream.write("proc\n")
	stream.write("memory\n")
	stream.write("opt_clean\n")
	if stub_path is not None:
		stream.write(f"read_verilog {_yosys_quote(str(stub_path))}\n")
		for cell_name, stub_name in stub_names.items():
			stream.write(f"cd {_rtlil_identifier(target_module)}\n")
			stream.write(
				f"chtype -set {stub_name} {_rtlil_identifier(cell_name)}\n"
			)
			stream.write("cd\n")
	stream.write(f"hierarchy -check -top {_rtlil_identifier(target_module)}\n")
	if flatten:
		stream.write("flatten\n")
		stream.write("opt_clean\n")
	stream.write(
		f"rename {_rtlil_identifier(target_module)} "
		f"{_rtlil_identifier(result_module)}\n"
	)
	stream.write(f"design -stash {result_module}_store\n\n")


def _run_pair_proof(
	config: HierarchicalConfig,
	gold_module: str,
	gate_module: str,
	children: list[tuple[str, str, str, bool]],
	gold_inventory: _Inventory,
	pair_dir: Path,
	flatten: bool,
) -> tuple[bool, Path]:
	pair_dir.mkdir(parents=True, exist_ok=True)
	script_path = pair_dir / "equiv.ys"
	log_path = pair_dir / "equiv.log"
	stub_path: Path | None = None
	stub_names: dict[str, str] = {}
	if children and not flatten:
		stub_path = pair_dir / "stubs.v"
		stub_names = _write_stubs(stub_path, children, gold_inventory)

	with script_path.open("w", encoding="ascii") as stream:
		_write_prepared_side(
			stream,
			config,
			config.gold_sources,
			gold_module,
			"gold",
			stub_path,
			stub_names,
			flatten,
		)
		_write_prepared_side(
			stream,
			config,
			config.gate_sources,
			gate_module,
			"gate",
			stub_path,
			stub_names,
			flatten,
		)
		stream.write("design -reset\n")
		stream.write("design -copy-from gold_store gold\n")
		stream.write("design -copy-from gate_store gate\n")
		if stub_path is not None:
			stream.write(f"read_verilog {_yosys_quote(str(stub_path))}\n")
		stream.write("equiv_make -inames gold gate equiv\n")
		stream.write("hierarchy -top equiv\n")
		stream.write(f"equiv_simple -seq {config.seq}\n")
		stream.write("equiv_status -assert\n")

	return _run_yosys(config.yosys, script_path, log_path), log_path


class _HierarchyRunner:
	def __init__(
		self,
		config: HierarchicalConfig,
		gold_inventory: _Inventory,
		gate_inventory: _Inventory,
		work_dir: Path,
	) -> None:
		self.config = config
		self.gold_inventory = gold_inventory
		self.gate_inventory = gate_inventory
		self.work_dir = work_dir
		self.results: dict[tuple[str, str], PairResult] = {}
		self.active: set[tuple[str, str]] = set()
		self.next_pair_index = 0

	def prove(self, gold_name: str, gate_name: str) -> PairResult:
		key = (gold_name, gate_name)
		if key in self.results:
			return self.results[key]
		if key in self.active:
			raise RuntimeError(f"recursive module hierarchy detected: {key}")
		self.active.add(key)

		gold_module = self.gold_inventory.modules.get(gold_name)
		gate_module = self.gate_inventory.modules.get(gate_name)
		if gold_module is None or gate_module is None:
			raise RuntimeError(f"module pair is missing from inventory: {key}")
		plan = _plan_pair(
			gold_module,
			gate_module,
			self.gold_inventory,
			self.gate_inventory,
		)
		pair_dir = self.work_dir / "pairs" / f"{self.next_pair_index:04d}"
		self.next_pair_index += 1

		if plan.fallback_reason is not None:
			equivalent, log_path = _run_pair_proof(
				self.config,
				gold_name,
				gate_name,
				[],
				self.gold_inventory,
				pair_dir,
				flatten=True,
			)
			result = PairResult(
				gold_module=gold_name,
				gate_module=gate_name,
				equivalent=equivalent,
				method="flatten-fallback",
				reason=plan.fallback_reason,
				children=(),
				log_path=log_path,
			)
		else:
			local_equivalent, log_path = _run_pair_proof(
				self.config,
				gold_name,
				gate_name,
				plan.children,
				self.gold_inventory,
				pair_dir,
				flatten=False,
			)
			child_pairs = tuple(
				(gold, gate) for _, gold, gate, recurse in plan.children if recurse
			)
			children_equivalent = True
			if local_equivalent:
				for _, child_gold, child_gate, recurse in plan.children:
					if not recurse:
						continue
					if not self.prove(child_gold, child_gate).equivalent:
						children_equivalent = False
			if local_equivalent and children_equivalent:
				result = PairResult(
					gold_module=gold_name,
					gate_module=gate_name,
					equivalent=True,
					method="compositional" if plan.children else "leaf",
					reason="parent and all child obligations proven",
					children=child_pairs,
					log_path=log_path,
				)
			else:
				fallback_equivalent, fallback_log = _run_pair_proof(
					self.config,
					gold_name,
					gate_name,
					[],
					self.gold_inventory,
					pair_dir / "fallback",
					flatten=True,
				)
				result = PairResult(
					gold_module=gold_name,
					gate_module=gate_name,
					equivalent=fallback_equivalent,
					method="flatten-fallback",
					reason=(
						"compositional parent proof failed"
						if not local_equivalent
						else "one or more child obligations failed"
					),
					children=child_pairs,
					log_path=fallback_log,
				)

		self.active.remove(key)
		self.results[key] = result
		return result


def _write_report(result: HierarchicalResult) -> None:
	report = {
		"equivalent": result.equivalent,
		"oracle_equivalent": result.oracle_equivalent,
		"oracle_consistent": result.oracle_consistent,
		"oracle_log_path": (
			str(result.oracle_log_path) if result.oracle_log_path is not None else None
		),
		"pairs": [
			{
				**asdict(pair),
				"log_path": str(pair.log_path),
			}
			for pair in result.pairs
		],
	}
	with result.report_path.open("w", encoding="utf-8") as stream:
		json.dump(report, stream, indent=2, sort_keys=True)
		stream.write("\n")


def run_hierarchical_check(config: HierarchicalConfig) -> HierarchicalResult:
	"""Run top-down compositional checks and optionally cross-check the Oracle."""

	_validate_config(_as_oracle_config(config, config.work_dir))
	work_dir = config.work_dir.resolve()
	work_dir.mkdir(parents=True, exist_ok=True)
	gold_inventory = _build_inventory(config, config.gold_sources, "gold", work_dir)
	gate_inventory = _build_inventory(config, config.gate_sources, "gate", work_dir)
	runner = _HierarchyRunner(config, gold_inventory, gate_inventory, work_dir)
	top_result = runner.prove(config.top, config.top)

	oracle_equivalent: bool | None = None
	oracle_log_path: Path | None = None
	if config.validate_oracle:
		oracle = run_flatten_oracle(_as_oracle_config(config, work_dir / "oracle"))
		oracle_equivalent = oracle.equivalent
		oracle_log_path = oracle.log_path

	result = HierarchicalResult(
		equivalent=top_result.equivalent,
		pairs=tuple(runner.results.values()),
		report_path=work_dir / "report.json",
		oracle_equivalent=oracle_equivalent,
		oracle_log_path=oracle_log_path,
	)
	_write_report(result)
	return result
