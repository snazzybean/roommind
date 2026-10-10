"""Locations: simulation home (runtime data, outside the repo) and the source checkout."""

from __future__ import annotations

import os
from pathlib import Path

SIM_ROOT = Path(__file__).resolve().parents[1]  # dev/sim of the checkout this code runs from
REPO_ROOT = SIM_ROOT.parents[1]
DEFAULT_HA_VERSION = "2026.10.0"


def sim_home() -> Path:
    """Runtime data root; never inside the repository."""
    home = Path(os.environ.get("ROOMMIND_SIM_HOME", Path.home() / ".roommind-sim")).expanduser()
    home.mkdir(parents=True, exist_ok=True)
    return home


def venv_dir(version: str = DEFAULT_HA_VERSION) -> Path:
    return sim_home() / "venvs" / f"ha-{version}"


def venv_python(version: str = DEFAULT_HA_VERSION) -> Path:
    return venv_dir(version) / "bin" / "python"


def roommind_src(repo: Path = REPO_ROOT) -> Path:
    return repo / "custom_components" / "roommind"


def simhome_src(sim_root: Path = SIM_ROOT) -> Path:
    return sim_root / "ha_component" / "simhome"
