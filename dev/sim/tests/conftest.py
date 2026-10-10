"""Shared helpers for roommind_sim tests."""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

SIM_ROOT = Path(__file__).resolve().parents[1]


def run_isolated(code: str, timeout: float = 30.0) -> subprocess.CompletedProcess:
    """Run ``code`` in a fresh interpreter (the clock patches process-global state)."""
    return subprocess.run(
        [sys.executable, "-c", textwrap.dedent(code)],
        check=False,
        cwd=SIM_ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
