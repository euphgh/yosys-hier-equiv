"""Full-flatten equivalence oracle implemented with Yosys."""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import TextIO


_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]*$")


@dataclass(frozen=True)
class OracleConfig:
	"""Configures one full-flatten equivalence run.

	Attributes:
		gold_sources: Verilog source files for the Gold design, in read order.
		gate_sources: Verilog source files for the Gate design, in read order.
		common_sources: Source files read independently into both designs.
		include_dirs: Directories searched for Verilog include files.
		top: Top-level module name shared by both designs.
		seq: Sequential depth passed to ``equiv_simple``.
		work_dir: Directory used for the generated script and log.
		yosys: Yosys executable name or path.
		system_verilog: Whether all sources are read as SystemVerilog.
	"""

	gold_sources: tuple[Path, ...]
	gate_sources: tuple[Path, ...]
	common_sources: tuple[Path, ...] = ()
	include_dirs: tuple[Path, ...] = ()
	top: str = "top"
	seq: int = 2
	work_dir: Path = Path("build/flatten-oracle")
	yosys: str = field(default_factory=lambda: os.environ.get("YOSYS", "yosys"))
	system_verilog: bool = False


@dataclass(frozen=True)
class OracleResult:
	"""Describes the result and retained artifacts of an Oracle run.

	Attributes:
		equivalent: Whether Yosys completed the equivalence script successfully.
		returncode: Exit status returned by the Yosys process.
		script_path: Path to the generated Yosys script.
		log_path: Path to the combined Yosys stdout and stderr log.
	"""

	equivalent: bool
	returncode: int
	script_path: Path
	log_path: Path


def _yosys_quote(value: str) -> str:
	"""Quote a string for use as one Yosys command argument.

	Args:
		value: Raw string to quote.

	Returns:
		A double-quoted string with backslashes and quotes escaped.

	Raises:
		ValueError: If ``value`` contains a newline that could inject a command.
	"""

	if "\n" in value or "\r" in value:
		raise ValueError("Yosys script values must not contain newlines")
	return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _validate_config(config: OracleConfig) -> None:
	"""Validate required sources and scalar Oracle options.

	Args:
		config: Oracle configuration to validate.

	Raises:
		ValueError: If sources are missing, paths are invalid, the top name is
			unsupported, or the sequential depth is less than one.
	"""

	if not config.gold_sources:
		raise ValueError("at least one Gold source is required")
	if not config.gate_sources:
		raise ValueError("at least one Gate source is required")
	if not _IDENTIFIER_RE.fullmatch(config.top):
		raise ValueError(f"unsupported top module identifier: {config.top!r}")
	if config.seq < 1:
		raise ValueError("seq must be at least 1")

	for source in (*config.common_sources, *config.gold_sources, *config.gate_sources):
		if not source.is_file():
			raise ValueError(f"source file not found: {source}")
	for include_dir in config.include_dirs:
		if not include_dir.is_dir():
			raise ValueError(f"include directory not found: {include_dir}")


def _write_read_commands(
	stream: TextIO,
	sources: tuple[Path, ...],
	include_dirs: tuple[Path, ...],
	system_verilog: bool,
) -> None:
	"""Write one ``read_verilog`` command for each source file.

	Args:
		stream: Text stream receiving Yosys commands.
		sources: Source files to read in order.
		include_dirs: Directories passed through ``read_verilog -I``.
		system_verilog: Whether to add the ``-sv`` option.

	Raises:
		ValueError: If a source or include path cannot be safely quoted.
	"""

	options: list[str] = []
	if system_verilog:
		options.append("-sv")
	for include_dir in include_dirs:
		options.append("-I" + _yosys_quote(str(include_dir.resolve())))

	prefix = "read_verilog"
	if options:
		prefix += " " + " ".join(options)
	for source in sources:
		stream.write(f"{prefix} {_yosys_quote(str(source.resolve()))}\n")


def _write_side(
	stream: TextIO,
	config: OracleConfig,
	side_sources: tuple[Path, ...],
	result_name: str,
) -> None:
	"""Write the preparation commands for one side of the Oracle.

	The generated commands read, elaborate, flatten, normalize, rename, and
	stash one design so that Gold and Gate never share a live namespace.

	Args:
		stream: Text stream receiving Yosys commands.
		config: Shared Oracle configuration.
		side_sources: Gold or Gate source files.
		result_name: Module and design snapshot name for the prepared side.
	"""

	stream.write("design -reset-vlog\n")
	_write_read_commands(
		stream,
		(*config.common_sources, *side_sources),
		config.include_dirs,
		config.system_verilog,
	)
	stream.write(f"hierarchy -check -top {config.top}\n")
	stream.write("flatten\n")
	stream.write("proc\n")
	stream.write("memory\n")
	stream.write("opt_clean\n")
	stream.write(f"rename {config.top} {result_name}\n")
	stream.write(f"design -stash {result_name}\n\n")


def render_flatten_oracle_script(config: OracleConfig, script_path: Path) -> None:
	"""Render the standalone Yosys program used by the Oracle.

	Args:
		config: Validated inputs and Yosys options for the run.
		script_path: Destination path for the generated script.

	Raises:
		OSError: If the script cannot be created or written.
		ValueError: If a path cannot be safely represented in the script.
	"""

	with script_path.open("w", encoding="ascii") as stream:
		stream.write("# Generated by yosys-hier-equiv flatten-oracle.\n\n")
		_write_side(stream, config, config.gold_sources, "gold")
		_write_side(stream, config, config.gate_sources, "gate")
		stream.write("design -reset\n")
		stream.write("design -copy-from gold gold\n")
		stream.write("design -copy-from gate gate\n")
		stream.write("equiv_make -inames gold gate equiv\n")
		stream.write("hierarchy -top equiv\n")
		stream.write(f"equiv_simple -seq {config.seq}\n")
		stream.write("equiv_status -assert\n")


def run_flatten_oracle(config: OracleConfig) -> OracleResult:
	"""Run the full-flatten Oracle and retain its script and log.

	Args:
		config: Sources, top module, proof depth, and output configuration.

	Returns:
		The equivalence result and paths to the retained artifacts.

	Raises:
		OSError: If directories, files, or the Yosys process cannot be accessed.
		ValueError: If the configuration is invalid.
	"""

	_validate_config(config)
	work_dir = config.work_dir.resolve()
	work_dir.mkdir(parents=True, exist_ok=True)
	script_path = work_dir / "equiv.ys"
	log_path = work_dir / "equiv.log"
	render_flatten_oracle_script(config, script_path)

	with log_path.open("w", encoding="utf-8") as log_stream:
		completed = subprocess.run(
			[config.yosys, "-Q", "-s", str(script_path)],
			stdout=log_stream,
			stderr=subprocess.STDOUT,
			check=False,
		)

	return OracleResult(
		equivalent=completed.returncode == 0,
		returncode=completed.returncode,
		script_path=script_path,
		log_path=log_path,
	)
