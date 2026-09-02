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
	"""Configures one top-down hierarchical equivalence run.

	Attributes:
		gold_sources: Verilog source files for the Gold design, in read order.
		gate_sources: Verilog source files for the Gate design, in read order.
		common_sources: Source files read independently into both designs.
		include_dirs: Directories searched for Verilog include files.
		top: Top-level module name shared by both designs.
		seq: Sequential depth passed to ``equiv_simple``.
		work_dir: Root directory for inventories, pair proofs, and reports.
		yosys: Yosys executable name or path.
		system_verilog: Whether all sources are read as SystemVerilog.
		validate_oracle: Whether to compare the final result with the Oracle.
	"""

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
	"""Records one compositional or fallback proof obligation.

	Attributes:
		gold_module: Gold module participating in the obligation.
		gate_module: Gate module participating in the obligation.
		equivalent: Whether the final method proved this module pair.
		method: Proof method, such as ``leaf`` or ``flatten-fallback``.
		reason: Human-readable explanation of the selected method and result.
		children: Recursive child module pairs assumed by the parent proof.
		log_path: Yosys log for the final method used by this obligation.
		warnings: Reasons why a passing pair lacks a closed compositional
			proof; empty for fully compositional passes and for failures.
	"""

	gold_module: str
	gate_module: str
	equivalent: bool
	method: str
	reason: str
	children: tuple[tuple[str, str], ...]
	log_path: Path
	warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class HierarchicalResult:
	"""Describes a hierarchical run and its optional Oracle cross-check.

	Attributes:
		equivalent: Final equivalence result for the requested top module pair.
		pairs: Completed module-pair obligations, including cached children.
		report_path: Path to the generated JSON summary.
		oracle_equivalent: Oracle result, or ``None`` when it was not requested.
		oracle_log_path: Oracle log path, or ``None`` when it was not run.
	"""

	equivalent: bool
	pairs: tuple[PairResult, ...]
	report_path: Path
	oracle_equivalent: bool | None = None
	oracle_log_path: Path | None = None

	@property
	def oracle_consistent(self) -> bool:
		"""Return whether the hierarchical and Oracle results agree.

		Returns:
			``True`` when no Oracle was requested or both methods have the same
			result; otherwise ``False``.
		"""

		return self.oracle_equivalent is None or self.equivalent == self.oracle_equivalent

	@property
	def warnings(self) -> tuple[str, ...]:
		"""Collect all fallback warnings from the completed pairs.

		Returns:
			One entry per relaxed pass, in pair completion order, without
			deduplication.
		"""

		return tuple(warning for pair in self.pairs for warning in pair.warnings)


@dataclass(frozen=True)
class _Inventory:
	"""Stores the reachable module inventory for one design side.

	Attributes:
		modules: Module objects decoded from the Yosys JSON backend.
		json_path: Path to the retained inventory JSON file.
	"""

	modules: dict[str, dict[str, Any]]
	json_path: Path


@dataclass
class _PairPlan:
	"""Describes how to prove one candidate module pair.

	Attributes:
		children: Matched child tuples containing cell name, Gold type, Gate
			type, and whether the child implementation must be proved recursively.
		fallback_reason: Reason to flatten the current pair, or ``None`` when a
			compositional proof can be attempted.
	"""

	children: list[tuple[str, str, str, bool]] = field(default_factory=list)
	fallback_reason: str | None = None


def _as_oracle_config(config: HierarchicalConfig, work_dir: Path) -> OracleConfig:
	"""Convert hierarchical inputs into an Oracle configuration.

	Args:
		config: Hierarchical configuration supplying shared input options.
		work_dir: Artifact directory for the Oracle run.

	Returns:
		An Oracle configuration with the same sources and proof depth.
	"""

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
	"""Execute one generated Yosys script and capture its output.

	Args:
		yosys: Yosys executable name or path.
		script_path: Script passed to Yosys with ``-s``.
		log_path: Destination for combined stdout and stderr.

	Returns:
		``True`` when Yosys exits with status zero; otherwise ``False``.

	Raises:
		OSError: If the log or Yosys process cannot be opened.
	"""

	with log_path.open("w", encoding="utf-8") as log_stream:
		completed = subprocess.run(
			[yosys, "-Q", "-s", str(script_path)],
			stdout=log_stream,
			stderr=subprocess.STDOUT,
			check=False,
		)
	return completed.returncode == 0


def _rtlil_identifier(name: str) -> str:
	"""Return one exact RTLIL identifier token for a Yosys command.

	Args:
		name: Identifier as emitted by the Yosys JSON backend.

	Returns:
		The name prefixed with the RTLIL escape character.

	Raises:
		ValueError: If the name contains whitespace or line breaks.
	"""

	if "\n" in name or "\r" in name or any(character.isspace() for character in name):
		raise ValueError(f"unsupported RTLIL identifier: {name!r}")
	return "\\" + name


def _build_inventory(
	config: HierarchicalConfig,
	side_sources: tuple[Path, ...],
	side_name: str,
	work_dir: Path,
) -> _Inventory:
	"""Build and load the reachable-module inventory for one design side.

	Args:
		config: Shared hierarchical run configuration.
		side_sources: Gold or Gate source files.
		side_name: Stable label used in artifact filenames.
		work_dir: Directory receiving the script, log, and JSON inventory.

	Returns:
		The decoded module mapping and retained JSON path.

	Raises:
		OSError: If an artifact or Yosys process cannot be accessed.
		RuntimeError: If Yosys fails or emits JSON without a module mapping.
		ValueError: If the top module name cannot be represented safely.
	"""

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
	"""Extract the comparable interface signature of a Yosys JSON module.

	Args:
		module: One module object from a Yosys JSON inventory.

	Returns:
		A mapping from each port name to its direction and bit width.
	"""

	return {
		name: (port["direction"], len(port["bits"]))
		for name, port in module.get("ports", {}).items()
	}


def _hierarchical_cells(
	module: dict[str, Any], inventory: _Inventory
) -> dict[str, dict[str, Any]]:
	"""Select cells whose types are reachable implementation modules.

	Args:
		module: Parent module containing candidate cells.
		inventory: Inventory defining the implementation module types.

	Returns:
		A mapping of hierarchical cell names to their JSON descriptions.
	"""

	return {
		name: cell
		for name, cell in module.get("cells", {}).items()
		if cell.get("type") in inventory.modules
	}


def _is_blackbox(module: dict[str, Any]) -> bool:
	"""Check whether a Yosys JSON module is an abstract box.

	Args:
		module: Module object containing Yosys attributes.

	Returns:
		``True`` for modules marked ``blackbox`` or ``whitebox``.
	"""

	attributes = module.get("attributes", {})
	return bool(attributes.get("blackbox") or attributes.get("whitebox"))


def _plan_pair(
	gold_module: dict[str, Any],
	gate_module: dict[str, Any],
	gold_inventory: _Inventory,
	gate_inventory: _Inventory,
) -> _PairPlan:
	"""Plan matched child obligations or request a conservative fallback.

	Args:
		gold_module: Gold parent module from its JSON inventory.
		gate_module: Gate parent module from its JSON inventory.
		gold_inventory: Reachable Gold modules.
		gate_inventory: Reachable Gate modules.

	Returns:
		A pair plan containing same-name child matches, or a reason to flatten
		the current module pair.
	"""

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
	"""Format a name as a regular or escaped Verilog identifier.

	Args:
		name: Identifier from a Yosys module or port object.

	Returns:
		The unchanged regular identifier, or an escaped identifier terminated
		by the whitespace required by Verilog syntax.
	"""

	if _VERILOG_IDENTIFIER_RE.fullmatch(name):
		return name
	return "\\" + name + " "


def _write_stubs(
	path: Path,
	children: list[tuple[str, str, str, bool]],
	gold_inventory: _Inventory,
) -> dict[str, str]:
	"""Write common black-box modules for matched child instances.

	Each child instance receives a distinct stub type so separate instances do
	not accidentally share an abstract identity in the parent proof.

	Args:
		path: Destination Verilog file.
		children: Planned child matches for the current module pair.
		gold_inventory: Inventory used to obtain the agreed child interfaces.

	Returns:
		A mapping from child cell names to generated stub module names.

	Raises:
		OSError: If the stub file cannot be created or written.
	"""

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
	"""Write commands that prepare one module for a pair proof.

	Args:
		stream: Text stream receiving Yosys commands.
		config: Shared hierarchical run configuration.
		side_sources: Gold or Gate source files.
		target_module: Module to isolate as the current proof top.
		result_module: Canonical ``gold`` or ``gate`` module name.
		stub_path: Common stub source, or ``None`` for an unabstracted proof.
		stub_names: Mapping from child cell names to common stub types.
		flatten: Whether to flatten the target module subtree before comparison.

	Raises:
		ValueError: If an identifier or path cannot be represented safely.
	"""

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
	"""Generate and execute one module-pair proof.

	Args:
		config: Shared hierarchical run configuration.
		gold_module: Gold module selected as the local proof top.
		gate_module: Gate module selected as the local proof top.
		children: Child matches to abstract when ``flatten`` is false.
		gold_inventory: Inventory supplying child interfaces for stubs.
		pair_dir: Directory retaining this proof's artifacts.
		flatten: Whether to compare fully flattened local subtrees.

	Returns:
		A tuple containing the Yosys success flag and retained log path.

	Raises:
		OSError: If an artifact or Yosys process cannot be accessed.
		ValueError: If an identifier or path cannot be represented safely.
	"""

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
	"""Recursively proves and caches module-pair obligations.

	Attributes:
		config: Shared hierarchical run configuration.
		gold_inventory: Reachable modules in the Gold design.
		gate_inventory: Reachable modules in the Gate design.
		work_dir: Root directory for pair-specific artifacts.
		results: Completed obligations keyed by module pair.
		active: Obligations currently on the recursion stack.
		next_pair_index: Monotonic index used for artifact directory names.
	"""

	def __init__(
		self,
		config: HierarchicalConfig,
		gold_inventory: _Inventory,
		gate_inventory: _Inventory,
		work_dir: Path,
	) -> None:
		"""Initialize a recursive proof runner.

		Args:
			config: Shared hierarchical run configuration.
			gold_inventory: Reachable modules in the Gold design.
			gate_inventory: Reachable modules in the Gate design.
			work_dir: Root directory for pair-specific artifacts.
		"""

		self.config = config
		self.gold_inventory = gold_inventory
		self.gate_inventory = gate_inventory
		self.work_dir = work_dir
		self.results: dict[tuple[str, str], PairResult] = {}
		self.active: set[tuple[str, str]] = set()
		self.next_pair_index = 0

	def prove(self, gold_name: str, gate_name: str) -> PairResult:
		"""Prove one module pair using composition or local flattening.

		Completed pairs are returned from the cache. A compositional proof first
		checks the parent with common child stubs, then recursively closes every
		child obligation. Ambiguous hierarchy or failed obligations trigger a
		full flatten of the current module subtree. A pair that only passes
		through flattening records warnings naming the proof obligations that
		stayed open.

		Args:
			gold_name: Gold module name from the Gold inventory.
			gate_name: Gate module name from the Gate inventory.

		Returns:
			The final result and artifact path for this module pair.

		Raises:
			OSError: If proof artifacts or Yosys cannot be accessed.
			RuntimeError: If the hierarchy is recursive or a module is missing.
			ValueError: If an identifier cannot be represented safely.
		"""

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

		warnings: tuple[str, ...] = ()

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
			if equivalent:
				warnings = (
					f"({gold_name}, {gate_name}): pass relies on local "
					f"flattening ({plan.fallback_reason})",
				)
			result = PairResult(
				gold_module=gold_name,
				gate_module=gate_name,
				equivalent=equivalent,
				method="flatten-fallback",
				reason=plan.fallback_reason,
				children=(),
				log_path=log_path,
				warnings=warnings,
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
			failed_children: list[tuple[str, str]] = []
			if local_equivalent:
				for _, child_gold, child_gate, recurse in plan.children:
					if not recurse:
						continue
					if not self.prove(child_gold, child_gate).equivalent:
						children_equivalent = False
						failed_children.append((child_gold, child_gate))
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
				if fallback_equivalent:
					if not local_equivalent:
						warnings = (
							f"({gold_name}, {gate_name}): parent compositional "
							"proof failed; equivalence proven by locally "
							"flattening the module subtree",
						)
					else:
						warnings = tuple(
							f"({gold_name}, {gate_name}): child pair "
							f"({child_gold}, {child_gate}) is not equivalent in "
							"isolation; equivalence only holds under this "
							"module's connection context"
							for child_gold, child_gate in failed_children
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
					warnings=warnings,
				)

		self.active.remove(key)
		self.results[key] = result
		return result


def _write_report(result: HierarchicalResult) -> None:
	"""Serialize a hierarchical result as stable, readable JSON.

	Args:
		result: Completed run containing pair and optional Oracle results.

	Raises:
		OSError: If the report file cannot be created or written.
	"""

	report = {
		"equivalent": result.equivalent,
		"oracle_equivalent": result.oracle_equivalent,
		"oracle_consistent": result.oracle_consistent,
		"oracle_log_path": (
			str(result.oracle_log_path) if result.oracle_log_path is not None else None
		),
		"warnings": list(result.warnings),
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
	"""Run top-down checks and optionally cross-check the Oracle.

	Args:
		config: Sources, top module, proof depth, output, and validation options.

	Returns:
		The top-level result, all completed pair obligations, and report paths.

	Raises:
		OSError: If source files, artifacts, or Yosys cannot be accessed.
		RuntimeError: If inventory generation or recursive proof setup fails.
		ValueError: If the shared input configuration is invalid.
	"""

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
