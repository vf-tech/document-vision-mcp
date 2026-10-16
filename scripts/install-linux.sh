#!/usr/bin/env bash
# Pure Linux/WSL installation. Does not modify Codex configuration.
set -euo pipefail

project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
linux_python="${1:-/usr/bin/python3}"

if [[ ! -x "$linux_python" ]]; then
    printf 'Linux Python not found: %s\nInstall python3 and python3-venv, or pass an absolute Linux Python path.\n' "$linux_python" >&2
    exit 1
fi

check_linux='import sys; assert sys.platform == "linux", "Linux Python required (not Windows python.exe)"; assert sys.version_info >= (3,10), "Python >=3.10 required"'
"$linux_python" -c "$check_linux"

if [[ -e "$project_dir/.venv" ]]; then
    if [[ ! -x "$project_dir/.venv/bin/python" ]]; then
        printf 'Existing .venv is not a Linux venv. Move it aside and run this installer again.\n' >&2
        exit 1
    fi
else
    "$linux_python" -m venv "$project_dir/.venv"
fi

venv_python="$project_dir/.venv/bin/python"
"$venv_python" -c "$check_linux; assert sys.prefix != sys.base_prefix, 'Expected a virtual environment'"
"$venv_python" -m pip install "$project_dir"
"$venv_python" -c 'from document_vision_mcp.server import create_server; import sys; print("Ready:", sys.executable)'
printf '\nRegister from Linux/WSL Codex (replace /absolute/path/to/pdfs):\n'
printf 'codex mcp add document-vision -- %q -m document_vision_mcp.server --root /absolute/path/to/pdfs\n' "$venv_python"
