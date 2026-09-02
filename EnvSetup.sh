#!/usr/bin/env bash
# EnvSetup.sh — load the self-contained yosys-hier-equiv environment.
#
# Usage:
#   source EnvSetup.sh
#
# What it sets up:
#   1. A uv-managed Python virtualenv at .venv with this project installed
#      in editable mode. Created automatically via `uv sync` on first use.
#   2. The bundled OSS CAD Suite toolchain at .local/bin (contains yosys).
#   3. The YOSYS environment variable pointing at the bundled Yosys, which
#      the Makefile and the CLI use as their default.
#
# .venv/bin is placed before .local/bin so that the virtualenv python3
# always wins over any interpreter shipped inside OSS CAD Suite. The
# script is idempotent: sourcing it repeatedly does not duplicate PATH
# entries and does not rebuild the virtualenv.

_repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]:-$0}")" && pwd -P)" || _repo_root="$PWD"

if ! command -v uv >/dev/null 2>&1; then
	echo "EnvSetup.sh: 'uv' is required but was not found in PATH." >&2
	echo "Install it first: https://docs.astral.sh/uv/getting-started/installation/" >&2
	return 1 2>/dev/null || exit 1
fi

if [ ! -x "$_repo_root/.venv/bin/python" ]; then
	echo "EnvSetup.sh: creating Python virtualenv (.venv) via 'uv sync' ..."
	if ! (cd "$_repo_root" && uv sync); then
		echo "EnvSetup.sh: 'uv sync' failed; see the output above." >&2
		return 1 2>/dev/null || exit 1
	fi
fi

export VIRTUAL_ENV="$_repo_root/.venv"
case ":$PATH:" in
	*":$VIRTUAL_ENV/bin:"*) ;;
	*) export PATH="$VIRTUAL_ENV/bin:$PATH" ;;
esac

export OSS_CAD_SUITE_HOME="$_repo_root/.local"
export YOSYS="$OSS_CAD_SUITE_HOME/bin/yosys"
if [ ! -x "$YOSYS" ]; then
	echo "EnvSetup.sh: bundled Yosys not found at $YOSYS." >&2
	echo "Extract the OSS CAD Suite tarball into .local/ first, e.g.:" >&2
	echo "  mkdir -p .local && tar -xzf oss-cad-suite-linux-x64-*.tgz --strip-components=1 -C .local" >&2
	return 1 2>/dev/null || exit 1
fi
case ":$PATH:" in
	*":$OSS_CAD_SUITE_HOME/bin:"*) ;;
	*) export PATH="$OSS_CAD_SUITE_HOME/bin:$PATH" ;;
esac

unset _repo_root
hash -r 2>/dev/null || true

echo "yosys-hier-equiv environment ready:"
echo "  python: $(command -v python3) ($(python3 --version 2>&1))"
echo "  yosys:  $YOSYS ($("$YOSYS" -V 2>&1))"
