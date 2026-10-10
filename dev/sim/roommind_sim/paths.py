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


def roommind_src(repo: Path = REPO_ROOT, override: str | None = None) -> Path:
    """RoomMind code to load: this checkout, another path, or a git ref (exported once)."""
    override = override or os.environ.get("ROOMMIND_SIM_SRC")
    if not override:
        return repo / "custom_components" / "roommind"
    path = Path(override).expanduser()
    for candidate in (path / "custom_components" / "roommind", path):
        if (candidate / "manifest.json").is_file():
            return candidate.resolve()
    return _export_ref(repo, override)


def _export_ref(repo: Path, ref: str) -> Path:
    import subprocess

    sha = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--verify", f"{ref}^{{commit}}"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    if not sha:
        raise ValueError(f"--roommind-src {ref!r} is neither a RoomMind checkout nor a git ref")
    target = sim_home() / "src" / sha[:12]
    dest = target / "custom_components" / "roommind"
    if not (dest / "manifest.json").is_file():
        target.mkdir(parents=True, exist_ok=True)
        archive = subprocess.run(
            ["git", "-C", str(repo), "archive", sha, "custom_components/roommind"], capture_output=True, check=True
        ).stdout
        subprocess.run(["tar", "-x", "-C", str(target)], input=archive, check=True)
    return dest


def source_info(src: Path) -> dict[str, str]:
    """Describe the RoomMind code under test (path + git state when available)."""
    import subprocess

    info = {"path": str(src)}
    root = src.parents[1]
    describe = subprocess.run(
        ["git", "-C", str(root), "describe", "--tags", "--always", "--dirty"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    if describe and (root / ".git").exists():
        info["git"] = describe
    elif src.is_relative_to(sim_home() / "src"):
        info["git"] = src.parents[1].name
    return info


def simhome_src(sim_root: Path = SIM_ROOT) -> Path:
    return sim_root / "ha_component" / "simhome"
