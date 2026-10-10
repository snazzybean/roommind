"""Instances: directories, ports, processes (systemd-run or nohup), listing."""

from __future__ import annotations

import fcntl
import json
import os
import shutil
import signal
import socket
import subprocess
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .paths import SIM_ROOT, sim_home

LIVE_PORTS = range(8130, 8150)
BATCH_PORTS = range(8150, 8200)
MAIN_PORT = 8130
UNIT_PREFIX = "roommind-sim-"


@dataclass
class Instance:
    name: str
    dir: Path

    @classmethod
    def live(cls, name: str) -> Instance:
        return cls(name, sim_home() / "instances" / name)

    @classmethod
    def run(cls, scenario_name: str) -> Instance:
        stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime())
        base = sim_home() / "runs" / f"{stamp}-{scenario_name}"
        path = base
        n = 1
        while path.exists():
            n += 1
            path = base.with_name(f"{base.name}-{n}")
        return cls(path.name, path)

    @property
    def config_dir(self) -> Path:
        return self.dir / "config"

    @property
    def state_dir(self) -> Path:
        return self.dir / "state"

    @property
    def timeline_dir(self) -> Path:
        return self.dir / "timeline"

    @property
    def logs_dir(self) -> Path:
        return self.dir / "logs"

    @property
    def meta_path(self) -> Path:
        return self.dir / "meta.json"

    @property
    def scenario_path(self) -> Path:
        return self.dir / "scenario.json"

    @property
    def token_path(self) -> Path:
        return self.dir / "token"

    def create_dirs(self) -> None:
        for path in (self.config_dir, self.state_dir, self.timeline_dir, self.logs_dir):
            path.mkdir(parents=True, exist_ok=True)

    def meta(self) -> dict[str, Any]:
        if not self.meta_path.is_file():
            return {}
        return json.loads(self.meta_path.read_text())

    def write_meta(self, **changes: Any) -> dict[str, Any]:
        meta = self.meta() | changes
        self.dir.mkdir(parents=True, exist_ok=True)
        tmp = self.meta_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(meta, indent=2, sort_keys=True))
        tmp.replace(self.meta_path)
        return meta

    @property
    def unit(self) -> str:
        return f"{UNIT_PREFIX}{self.name}"

    def url(self, host: str | None = None) -> str:
        return f"http://{host or lan_ip() or '127.0.0.1'}:{self.meta().get('port')}"

    def is_running(self) -> bool:
        meta = self.meta()
        if meta.get("launcher") == "systemd":
            return _systemd_active(self.unit)
        pid = meta.get("pid")
        return bool(pid) and _pid_alive(int(pid))

    def remove(self) -> None:
        shutil.rmtree(self.dir, ignore_errors=True)
        release_port(self.name)


# --- ports ------------------------------------------------------------------------


@contextmanager
def _ports_lock():
    path = sim_home() / "ports.json"
    lock = path.with_suffix(".lock")
    with lock.open("a") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        data = json.loads(path.read_text()) if path.is_file() else {}
        yield data
        path.write_text(json.dumps(data, indent=2, sort_keys=True))


def _port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("0.0.0.0", port))
        except OSError:
            return False
    return True


def allocate_port(name: str, batch: bool = False) -> int:
    """Stable port per live instance (``main`` = 8130); batch runs lease one until released."""
    with _ports_lock() as data:
        for key, entry in list(data.items()):
            pid = entry.get("pid") if isinstance(entry, dict) else None
            if pid and not _pid_alive(int(pid)):
                del data[key]  # lease of a crashed run
        if not batch and name in data:
            entry = data[name]
            return int(entry["port"] if isinstance(entry, dict) else entry)
        taken = {int(e["port"] if isinstance(e, dict) else e) for e in data.values()}
        if not batch and name == "main":
            candidates = [MAIN_PORT]
        else:
            pool = BATCH_PORTS if batch else LIVE_PORTS
            candidates = [p for p in pool if p not in taken and p != MAIN_PORT]
        for port in candidates:
            if _port_free(port):
                data[name] = {"port": port, "pid": os.getpid() if batch else None}
                return port
    raise RuntimeError(f"no free port for {name} in {'batch' if batch else 'live'} range")


def release_port(name: str) -> None:
    with _ports_lock() as data:
        data.pop(name, None)


# --- processes -----------------------------------------------------------------------


def boot_command(inst: Instance, python: Path, extra: list[str]) -> list[str]:
    return [str(python), "-m", "roommind_sim.boot", "--instance-dir", str(inst.dir), *extra]


def boot_env() -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SIM_ROOT)
    env["PYTHONHASHSEED"] = "0"
    env["ROOMMIND_SIM_HOME"] = str(sim_home())
    return env


def start_live(inst: Instance, python: Path, extra: list[str], ttl_s: int) -> str:
    """Start detached. Returns the launcher used."""
    cmd = boot_command(inst, python, extra)
    env = boot_env()
    if shutil.which("systemd-run") and _systemd_available():
        subprocess.run(["systemctl", "reset-failed", inst.unit], capture_output=True, check=False)
        setenv = [f"--setenv={k}={env[k]}" for k in ("PYTHONPATH", "PYTHONHASHSEED", "ROOMMIND_SIM_HOME")]
        subprocess.run(
            [
                "systemd-run",
                f"--unit={inst.unit}",
                "--collect",
                "--quiet",
                f"--property=RuntimeMaxSec={ttl_s}",
                "--property=MemoryMax=1500M",
                "--property=Nice=5",
                f"--working-directory={SIM_ROOT}",
                *setenv,
                *cmd,
            ],
            check=True,
        )
        inst.write_meta(launcher="systemd", pid=None, ttl_s=ttl_s, started=time.time())
        return "systemd"
    log = (inst.logs_dir / "boot.log").open("ab")
    proc = subprocess.Popen(cmd, env=env, cwd=SIM_ROOT, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    inst.write_meta(launcher="nohup", pid=proc.pid, ttl_s=ttl_s, started=time.time())
    return "nohup"


def stop(inst: Instance, timeout: float = 60.0) -> bool:
    meta = inst.meta()
    if meta.get("launcher") == "systemd":
        if not _systemd_active(inst.unit):
            return False
        subprocess.run(["systemctl", "stop", inst.unit], check=False)
        return True
    pid = meta.get("pid")
    if not pid or not _pid_alive(int(pid)):
        return False
    os.killpg(int(pid), signal.SIGTERM)
    deadline = time.time() + timeout
    while time.time() < deadline and _pid_alive(int(pid)):
        time.sleep(0.2)
    if _pid_alive(int(pid)):
        os.killpg(int(pid), signal.SIGKILL)
    return True


def list_instances() -> list[Instance]:
    root = sim_home() / "instances"
    if not root.is_dir():
        return []
    return [Instance(p.name, p) for p in sorted(root.iterdir()) if (p / "meta.json").is_file()]


def lan_ip() -> str | None:
    """Primary LAN address, for printing URLs reachable from phones."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("192.0.2.1", 9))  # TEST-NET, nothing is sent
            return sock.getsockname()[0]
    except OSError:
        return None


def lan_cidr() -> str | None:
    ip = lan_ip()
    if not ip or ip.startswith("127."):
        return None
    return ".".join(ip.split(".")[:3]) + ".0/24"


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _systemd_available() -> bool:
    return Path("/run/systemd/system").is_dir()


def _systemd_active(unit: str) -> bool:
    res = subprocess.run(["systemctl", "is-active", "--quiet", unit], check=False)
    return res.returncode == 0
