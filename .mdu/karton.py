"""Mock KARTON orchestrator for RLM-GRAPH."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def run(cmd: list[str], cwd: Path | None = None) -> int:
    print(f"[KARTON] {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd)
    return result.returncode


def main() -> int:
    root = Path(__file__).resolve().parent
    venv = root / ".venv"
    python = venv / "Scripts" / "python.exe" if sys.platform == "win32" else venv / "bin" / "python"

    if not python.exists():
        print("[KARTON] Missing .venv, falling back to system python")
        python = Path(sys.executable)

    commands = [
        [str(python), "-m", "pip", "install", "--quiet", "flask", "duckdb", "pyyaml"],
        [str(python), "-m", "pytest", "tests/", "-q"],
    ]

    status = 0
    for cmd in commands:
        code = run(cmd, cwd=root)
        if code != 0:
            status = code
            break

    return status


if __name__ == "__main__":
    raise SystemExit(main())
