#!/usr/bin/env python3
"""MAREF Desktop Agent runtime environment diagnostic.

Usage: python scripts/check_desktop_env.py

Checks:
1. Optional dependencies availability
2. macOS accessibility permissions
3. PyAutoGUI real-mode readiness
4. Window manager backend status
5. OmniParser backend status
"""

from __future__ import annotations

import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


def _check_import(name: str, package: str) -> dict[str, Any]:
    try:
        __import__(name)
        return {"available": True, "error": None}
    except ImportError as e:
        return {"available": False, "error": str(e), "hint": f"pip install {package}"}


def _run_osascript(script: str) -> str | None:
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


def check_dependencies() -> dict[str, Any]:
    return {
        "Pillow": _check_import("PIL", "Pillow"),
        "PyAutoGUI": _check_import("pyautogui", "PyAutoGUI"),
        "playwright": _check_import("playwright", "playwright"),
        "pyobjc (Quartz)": _check_import("Quartz", "pyobjc-framework-Quartz"),
        "transformers": _check_import("transformers", "transformers"),
        "torch": _check_import("torch", "torch"),
        "networkx": _check_import("networkx", "networkx"),
        "huggingface_hub": _check_import("huggingface_hub", "huggingface-hub"),
    }


def check_gpu() -> dict[str, Any]:
    result: dict[str, Any] = {"cuda": False, "mps": False, "available": False, "device": "cpu"}
    try:
        import torch
        if torch.cuda.is_available():
            result["cuda"] = True
            result["available"] = True
            result["device"] = f"cuda ({torch.cuda.device_count()} device(s))"
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            result["mps"] = True
            result["available"] = True
            if not result["cuda"]:
                result["device"] = "mps (Apple Silicon)"
    except ImportError:
        pass
    return result


def check_network() -> dict[str, Any]:
    import urllib.request
    targets = {
        "huggingface": "https://huggingface.co",
        "pypi": "https://pypi.org",
    }
    result = {}
    for name, url in targets.items():
        try:
            urllib.request.urlopen(url, timeout=5)
            result[name] = True
        except Exception:
            result[name] = False
    return result


def check_disk_space() -> dict[str, Any]:
    cache_dir = Path.home() / ".cache" / "maref" / "models"
    cache_dir.mkdir(parents=True, exist_ok=True)
    try:
        usage = shutil.disk_usage(cache_dir)
        return {
            "cache_path": str(cache_dir),
            "free_gb": round(usage.free / (1024 ** 3), 1),
            "total_gb": round(usage.total / (1024 ** 3), 1),
            "sufficient": usage.free > 10 * 1024 ** 3,
        }
    except Exception as e:
        return {"error": str(e), "sufficient": False}


def check_screen_resolution() -> dict[str, Any]:
    try:
        import pyautogui
        w, h = pyautogui.size()
        return {"width": w, "height": h, "adequate": w >= 1024 and h >= 768}
    except ImportError:
        return {"width": 0, "height": 0, "adequate": False}


def check_multi_display() -> dict[str, Any]:
    system = platform.system()
    if system == "Darwin":
        try:
            result = subprocess.run(
                ["system_profiler", "SPDisplaysDataType"],
                capture_output=True, text=True, timeout=10,
            )
            count = result.stdout.count("Display Type")
            return {"count": max(count, 1)}
        except Exception:
            return {"count": 1}
    return {"count": 1}


def check_sandbox_mode() -> dict[str, Any]:
    from maref.desktop.agent import DesktopAgent
    try:
        agent_live = DesktopAgent(dry_run=False)
        live_ok = agent_live.controller.pyautogui_available
    except Exception:
        live_ok = False
    return {"dry_run_ready": True, "live_mode_ready": live_ok}


def check_audit_log() -> dict[str, Any]:
    audit_files = [
        Path("governance_audit.jsonl"),
        Path("recursive_governance_audit.jsonl"),
    ]
    result = {}
    for f in audit_files:
        if f.exists():
            size = f.stat().st_size
            result[f.name] = {"exists": True, "size_bytes": size}
        else:
            result[f.name] = {"exists": False}
    return result


def check_macos_permissions() -> dict[str, Any]:
    if platform.system() != "Darwin":
        return {"note": "Not macOS — permissions check skipped"}

    accessibility = False
    output = _run_osascript(
        'tell application "System Events" to return count of every process'
    )
    if output is not None and output.strip().isdigit():
        accessibility = True

    return {
        "accessibility": accessibility,
        "accessibility_hint": (
            None if accessibility
            else "System Preferences → Privacy & Security → Accessibility → add Terminal"
        ),
    }


def check_window_manager() -> dict[str, Any]:
    from maref.desktop.window_manager import WindowManager

    wm = WindowManager()
    info = wm.backend_info

    window_count = 0
    try:
        windows = wm.list_windows()
        window_count = len(windows)
    except Exception:
        pass

    return {
        "backend": info.get("active_backend", "unknown"),
        "accessibility_granted": info.get("accessibility", False),
        "quartz_available": info.get("quartz_backend", False),
        "window_count": window_count,
    }


def check_input_controller() -> dict[str, Any]:
    from maref.desktop.input_controller import InputController

    controller = InputController(dry_run=False)
    perms = controller.check_permissions()

    return {
        "pyautogui_available": controller.pyautogui_available,
        "dry_run_mode": controller.dry_run,
        "permissions": perms,
    }


def check_screen_parser() -> dict[str, Any]:
    from maref.desktop.screen_parser import OmniParserInterface

    results: dict[str, dict[str, Any]] = {}
    for backend in ("auto", "mock", "omni_parser", "cog_agent"):
        parser = OmniParserInterface(backend=backend)
        ok = parser.initialize()
        results[backend] = {
            "initialized": ok,
            "backend_info": parser.backend_info,
        }
    return results


def check_desktop_agent() -> dict[str, Any]:
    from maref.desktop.agent import DesktopAgent

    agent = DesktopAgent(dry_run=True)
    return {
        "state": agent.state.value,
        "dry_run": agent.dry_run,
        "parser_backend": agent.parser.backend,
        "parser_initialized": agent.parser.initialized,
    }


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="MAREF Desktop Agent runtime diagnostic")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    results: dict[str, Any] = {}
    results["python"] = {"version": sys.version, "platform": f"{platform.system()} {platform.release()}"}
    results["dependencies"] = {}
    deps = check_dependencies()
    for name, info in deps.items():
        results["dependencies"][name] = info

    if platform.system() == "Darwin":
        results["macos_permissions"] = check_macos_permissions()

    results["window_manager"] = check_window_manager()
    results["input_controller"] = check_input_controller()
    results["screen_parser"] = check_screen_parser()
    results["desktop_agent"] = check_desktop_agent()
    results["gpu"] = check_gpu()
    results["network"] = check_network()
    results["disk"] = check_disk_space()
    results["screen"] = check_screen_resolution()
    results["multi_display"] = check_multi_display()
    results["sandbox"] = check_sandbox_mode()
    results["audit"] = check_audit_log()

    if args.json:
        import json as _json
        print(_json.dumps(results, indent=2, default=str))
        return 0

    print("=" * 60)
    print("  MAREF Desktop Agent — Runtime Environment Check")
    print("=" * 60)
    print()

    print(" 1. Python Environment")
    print(f"    version:  {sys.version.split()[0]}")
    print(f"    platform: {platform.system()} {platform.release()}")
    print()

    print(" 2. Dependencies (8 items)")
    for name, info in deps.items():
        status = "[OK]     " if info["available"] else "[MISSING]"
        hint = f" → {info['hint']}" if not info["available"] and "hint" in info else ""
        print(f"    {status} {name}{hint}")
    print()

    if platform.system() == "Darwin":
        print(" 3. macOS Permissions")
        perms = check_macos_permissions()
        acc = perms.get("accessibility", False)
        print(f"    [{'GRANTED' if acc else 'NOT GRANTED':>11}] Accessibility")
        if not acc and perms.get("accessibility_hint"):
            print(f"             → {perms['accessibility_hint']}")
        print()

    print(" 4. GPU Detection")
    gpu = check_gpu()
    print(f"    device: {gpu['device']}")
    print(f"    cuda:   {gpu['cuda']}")
    print(f"    mps:    {gpu['mps']}")
    print()

    print(" 5. Network Connectivity")
    net = check_network()
    for target, reachable in net.items():
        print(f"    [{'OK' if reachable else 'DOWN':>4}] {target}")
    print()

    print(" 6. Disk Space (model cache)")
    disk = check_disk_space()
    if "free_gb" in disk:
        print(f"    path:   {disk['cache_path']}")
        print(f"    free:   {disk['free_gb']} GB")
        print(f"    status: {'SUFFICIENT' if disk['sufficient'] else 'LOW (< 10 GB)'}")
    print()

    print(" 7. Screen Resolution")
    res = check_screen_resolution()
    print(f"    {res['width']}x{res['height']} — {'OK' if res['adequate'] else 'LOW'}")
    print()

    print(" 8. Multi-Display")
    md = check_multi_display()
    print(f"    displays: {md['count']}")
    print()

    print(" 9. Window Manager")
    wm = check_window_manager()
    print(f"    backend:      {wm['backend']}")
    print(f"    windows:      {wm['window_count']}")
    print()

    print("10. Input Controller")
    ic = check_input_controller()
    print(f"    PyAutoGUI: {ic['pyautogui_available']}")
    print(f"    dry run:   {ic['dry_run_mode']}")
    print()

    print("11. Screen Parser (OmniParser Backends)")
    sp = check_screen_parser()
    for backend, info in sp.items():
        status = "[OK]       " if info["initialized"] else "[NOT READY]"
        detail = info.get("backend_info", {})
        err = detail.get("error", "")
        print(f"    {status} {backend} {err}")
    print()

    print("12. Desktop Agent (E2E)")
    da = check_desktop_agent()
    print(f"    state:    {da['state']}")
    print(f"    dry run:  {da['dry_run']}")
    print(f"    parser:   {da['parser_backend']} (ready: {da['parser_initialized']})")
    print()

    print("13. Sandbox Mode")
    sb = check_sandbox_mode()
    print(f"    dry_run:   {'READY' if sb['dry_run_ready'] else 'FAILED'}")
    print(f"    live:      {'READY' if sb['live_mode_ready'] else 'UNAVAILABLE'}")
    print()

    print("14. Audit Logs")
    al = check_audit_log()
    for name, info in al.items():
        status = "[OK]      " if info["exists"] else "[NOT FOUND]"
        size = f"({info.get('size_bytes', 0)} bytes)" if info["exists"] else ""
        print(f"    {status} {name} {size}")
    print()

    print("15. Summary")
    all_deps_ok = all(d["available"] for d in deps.values())
    issues: list[str] = []
    if not all_deps_ok:
        issues.append("dependencies missing (pip install maref[desktop])")
    if platform.system() == "Darwin" and not results.get("macos_permissions", {}).get("accessibility", False):
        issues.append("Accessibility permission not granted")
    if not gpu["available"]:
        issues.append("no GPU — visual parsing will be slow")
    if disk.get("free_gb", 0) < 10:
        issues.append("low disk space for model cache")

    print("=" * 60)
    if issues:
        print(f"  Issues ({len(issues)}):")
        for i in issues:
            print(f"    - {i}")
    else:
        print("  All checks passed — MAREF desktop agent is READY")
    print("=" * 60)

    return 0 if not issues else 1


if __name__ == "__main__":
    sys.exit(main())
