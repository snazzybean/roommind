"""Screenshots of a live instance with Playwright (headless Chromium).

Logs in with the instance's long-lived token, aligns the browser clock with the
simulation clock and collects browser console errors plus HA ``system_log`` errors.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from .instance import Instance
from .paths import sim_home

VIEWPORTS = {"desktop": (1440, 900), "mobile": (390, 844), "tablet": (820, 1180)}
CLOCK_ALIGN_THRESHOLD_S = 60.0


def browsers_path() -> Path:
    return sim_home() / "browsers"


def ensure_browser() -> None:
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(browsers_path()))
    try:
        import playwright  # noqa: F401
    except ImportError:
        subprocess.run(["uv", "pip", "install", "--python", sys.executable, "playwright"], check=True)
    if not any(browsers_path().glob("chromium_headless_shell-*")):
        subprocess.run([sys.executable, "-m", "playwright", "install", "--only-shell", "chromium"], check=True)


def screenshot(
    inst: Instance,
    path: str = "/roommind",
    viewport: str = "desktop",
    dark: bool = False,
    lang: str = "de",
    wait_s: float = 4.0,
    full_page: bool = False,
    out: Path | None = None,
    sim_now: float | None = None,
    actions: list[str] | None = None,
) -> dict[str, Any]:
    ensure_browser()
    from playwright.sync_api import sync_playwright

    port = inst.meta()["port"]
    base = f"http://127.0.0.1:{port}"
    token = inst.token_path.read_text().strip()
    width, height = VIEWPORTS[viewport]
    shots = inst.dir / "shots"
    shots.mkdir(exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "-", path.lower()).strip("-") or "root"
    out = out or shots / f"{time.strftime('%H%M%S')}-{slug}-{viewport}{'-dark' if dark else ''}.png"
    console: list[dict[str, str]] = []
    tokens = {
        "access_token": token,
        "token_type": "Bearer",
        "expires_in": 315360000,
        "hassUrl": base,
        "clientId": f"{base}/",
        "expires": int(time.time() * 1000) + 315360000 * 1000,
        "refresh_token": "",
    }
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx = browser.new_context(
            viewport={"width": width, "height": height},
            device_scale_factor=2 if viewport == "mobile" else 1,
            is_mobile=viewport == "mobile",
            has_touch=viewport != "desktop",
            locale=lang,
            color_scheme="dark" if dark else "light",
        )
        ctx.add_init_script(f"window.localStorage.setItem('hassTokens', {json.dumps(json.dumps(tokens))});")
        page = ctx.new_page()
        if sim_now is not None and abs(sim_now - time.time()) > CLOCK_ALIGN_THRESHOLD_S:
            page.clock.install(time=sim_now)
            page.clock.resume()
        page.on(
            "console",
            lambda m: console.append({"type": m.type, "text": m.text}) if m.type in ("error", "warning") else None,
        )
        page.on(
            "pageerror", lambda e: console.append({"type": "pageerror", "text": f"{e.message} {(e.stack or '')[:400]}"})
        )
        page.goto(base + path, wait_until="networkidle")
        page.wait_for_timeout(wait_s * 1000)
        for action in actions or []:
            _run_ui_action(page, action)
        page.screenshot(path=str(out), full_page=full_page)
        browser.close()
    return {"file": str(out), "console": console}


def _run_ui_action(page: Any, action: str) -> None:
    """``click:<text>`` / ``wait:<ms>`` / ``scroll:<px>`` for simple flows before the shot."""
    kind, _, arg = action.partition(":")
    if kind == "click":
        page.get_by_text(arg, exact=False).first.click()
        page.wait_for_timeout(1200)
    elif kind == "wait":
        page.wait_for_timeout(float(arg))
    elif kind == "scroll":
        page.mouse.wheel(0, float(arg))
        page.wait_for_timeout(600)
    else:
        raise ValueError(f"unknown ui action {action!r} (click:, wait:, scroll:)")
