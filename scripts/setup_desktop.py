#!/usr/bin/env python3
"""MAREF Desktop Agent one-click setup script.

Usage:
    python scripts/setup_desktop.py
    python scripts/setup_desktop.py --model omni_parser  # specific backend
    python scripts/setup_desktop.py --dry-run             # check without downloading

Automates:
1. Desktop dependencies installation
2. OmniParser / CogAgent model download
3. Playwright Chromium browser
4. macOS permissions guidance
5. Environment configuration
6. Post-setup diagnostic
"""

from __future__ import annotations

import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import httpx

MODEL_CACHE_DIR = Path.home() / ".cache" / "maref" / "models"
PLAYWRIGHT_BROWSERS = Path.home() / ".cache" / "ms-playwright"
OMNI_PARSER_MODEL = "microsoft/OmniParser-v2.0"
COG_AGENT_MODEL = "THUDM/cogagent-vqa-hf"


def _run(cmd: list[str], description: str = "", timeout: int = 300) -> tuple[bool, str]:
    action = description if description else f"Running: {' '.join(cmd)}"
    print(f"  {action}...", end=" ", flush=True)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if result.returncode == 0:
            print("OK")
            return True, result.stdout
        print("FAILED")
        print(f"    stderr: {result.stderr.strip()[-200:]}")
        return False, result.stderr
    except subprocess.TimeoutExpired:
        print("TIMEOUT")
        return False, "timeout"
    except FileNotFoundError:
        print("NOT FOUND")
        return False, f"command not found: {cmd[0]}"


def _check_python() -> dict[str, Any]:
    version = sys.version_info
    adequate = version >= (3, 10)
    return {
        "version": f"{version.major}.{version.minor}.{version.micro}",
        "adequate": adequate,
    }


def _check_gpu() -> dict[str, Any]:
    result: dict[str, Any] = {"cuda": False, "mps": False, "device": "cpu"}

    try:
        import torch

        if torch.cuda.is_available():
            result["cuda"] = True
            result["device"] = f"cuda:{torch.cuda.device_count()} device(s)"

        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            result["mps"] = True
            if not result["cuda"]:
                result["device"] = "mps (Apple Silicon)"
    except ImportError:
        result["device"] = "cpu"

    return result


def _check_huggingface_reachable() -> bool:
    try:
        response = httpx.get("https://huggingface.co", timeout=5, follow_redirects=True)
        return response.is_success
    except Exception:
        return False


def _install_desktop_deps(upgrade: bool = False) -> bool:
    cmd = [sys.executable, "-m", "pip", "install"]
    if upgrade:
        cmd.append("--upgrade")

    extras = ["Pillow", "PyAutoGUI", "playwright"]
    if _check_huggingface_reachable():
        extras.extend(["transformers", "torch", "accelerate", "sentencepiece"])

    cmd.extend(extras)
    success, _ = _run(cmd, "Installing desktop dependencies")
    return success


def _install_playwright_browsers() -> bool:
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            p.chromium.launch()
        print("  Playwright Chromium already installed: OK")
        return True
    except ImportError:
        print("  playwright not installed, skipping browser")
        return False
    except Exception:
        result = _run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            "Installing Playwright Chromium",
        )
        return result[0]


def _download_huggingface_model(model_id: str, cache_dir: str | None = None) -> bool:
    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        print("  huggingface_hub not available, trying git-lfs...")
        return _download_via_git_lfs(model_id)

    try:
        target_dir = cache_dir or str(MODEL_CACHE_DIR / model_id.replace("/", "_"))
        snapshot_download(
            model_id,
            cache_dir=target_dir,
            resume_download=True,
            max_workers=4,
        )
        return True
    except Exception as e:
        print(f"  Download failed: {e}")
        return False


def _download_via_git_lfs(model_id: str) -> bool:
    if not shutil.which("git"):
        print("  git not found")
        return False
    if not shutil.which("git-lfs"):
        print("  git-lfs not found")
        return True

    repo_dir = MODEL_CACHE_DIR / model_id.replace("/", "_")
    repo_url = f"https://huggingface.co/{model_id}"

    if repo_dir.exists():
        success, _ = _run(["git", "-C", str(repo_dir), "pull"], "Updating model repo")
    else:
        repo_dir.mkdir(parents=True, exist_ok=True)
        success, _ = _run(
            ["git", "clone", "--depth=1", repo_url, str(repo_dir)],
            f"Cloning {model_id}",
            timeout=600,
        )
    return success


def _configure_environment() -> None:
    env_file = Path(".env")
    example = Path(".env.example")

    if env_file.exists():
        print("  .env already exists, skipping")
        return

    if example.exists():
        shutil.copy(example, env_file)
        print("  Created .env from .env.example")
    else:
        env_file.write_text("# MAREF environment configuration\n")
        print("  Created default .env")


def _print_permissions_guidance() -> None:
    system = platform.system()
    print()
    print("=" * 56)
    print("  PERMISSIONS REQUIRED")
    print("=" * 56)

    if system == "Darwin":
        print("  macOS — grant these permissions:")
        print("    1. System Preferences → Privacy & Security → Accessibility")
        print("       → Add Terminal.app (and iTerm2 if using)")
        print("    2. System Preferences → Privacy & Security → Screen Recording")
        print("       → Add Terminal.app")
        print()
        print("  Check permissions: python scripts/check_desktop_env.py")
    elif system == "Linux":
        print("  Linux — ensure X11/Wayland permissions:")
        print("    1. xhost +SI:localuser:$(whoami)")
        print("    2. uinput group: sudo usermod -a -G uinput $USER")
        print()
    elif system == "Windows":
        print("  Windows — grant UIAccess:")
        print("    1. Run terminal as Administrator")
        print("    2. Enable UI Automation in Windows Settings")
        print()


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="MAREF Desktop Agent one-click setup")
    parser.add_argument(
        "--model",
        choices=["omni_parser", "cog_agent", "both", "none"],
        default="omni_parser",
        help="Model backend to download (default: omni_parser)",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Check environment only, don't download"
    )
    parser.add_argument("--no-model", action="store_true", help="Skip model download")
    parser.add_argument("--upgrade", action="store_true", help="Upgrade existing dependencies")
    args = parser.parse_args()

    print("=" * 56)
    print("  MAREF Desktop Agent — One-Click Setup")
    print("=" * 56)
    print()

    steps_total = 5 + (0 if args.no_model or args.dry_run else 2)
    steps_ok = 0

    # Step 1: Python check
    print(f"[1/{steps_total}] Python environment")
    py_info = _check_python()
    print(f"  Python {py_info['version']} — {'OK' if py_info['adequate'] else 'NEED 3.10+'}")
    if py_info["adequate"]:
        steps_ok += 1
    else:
        print("  ERROR: Python 3.10+ required")
        return 1

    if args.dry_run:
        print()
        gpu = _check_gpu()
        print(f"  GPU: {gpu['device']}")
        hf = _check_huggingface_reachable()
        print(f"  HuggingFace: {'reachable' if hf else 'unreachable'}")
        print(f"  Model cache: {MODEL_CACHE_DIR} (exists: {MODEL_CACHE_DIR.exists()})")
        print(f"  Playwright:  {PLAYWRIGHT_BROWSERS} (exists: {PLAYWRIGHT_BROWSERS.exists()})")
        _print_permissions_guidance()
        return 0

    # Step 2: Install dependencies
    print(f"\n[2/{steps_total}] Dependencies")
    if _install_desktop_deps(upgrade=args.upgrade):
        steps_ok += 1

    # Step 3: Playwright Chromium
    print(f"\n[3/{steps_total}] Browser engine")
    if _install_playwright_browsers():
        steps_ok += 1

    # Step 4: GPU detection
    print(f"\n[4/{steps_total}] GPU detection")
    gpu_info = _check_gpu()
    print(f"  Device: {gpu_info['device']}")
    steps_ok += 1

    # Step 5: Configure environment
    print(f"\n[5/{steps_total}] Environment configuration")
    _configure_environment()
    steps_ok += 1

    # Step 6-7: Model download
    if args.no_model:
        print("\n[Skipped] Model download (--no-model)")
        steps_total -= 2
    else:
        models_to_download = []
        if args.model in ("omni_parser", "both"):
            models_to_download.append(("OmniParser", OMNI_PARSER_MODEL))
        if args.model in ("cog_agent", "both"):
            models_to_download.append(("CogAgent", COG_AGENT_MODEL))

        for idx, (name, model_id) in enumerate(models_to_download, start=6):
            step_label = f"[{idx}/{steps_total}] {name} model"
            print(f"\n{step_label}")
            print(f"  Model:  {model_id}")
            print(f"  Cache:  {MODEL_CACHE_DIR}")
            hf_reachable = _check_huggingface_reachable()
            if not hf_reachable:
                print("  HuggingFace unreachable — model download skipped")
                print("  You can download manually later with:")
                print(
                    f"    python -c \"from huggingface_hub import snapshot_download; snapshot_download('{model_id}')\""
                )
                steps_total -= 1
                continue

            print("  Downloading...")
            if _download_huggingface_model(model_id):
                steps_ok += 1
                print(f"  {name} model: OK")
            else:
                print(f"  {name} model download failed — run setup again later")

    # Summary
    print()
    print("=" * 56)
    print(f"  Setup complete: {steps_ok}/{steps_total} steps successful")
    print("=" * 56)

    _print_permissions_guidance()

    print("  Post-setup:")
    print("    1. Check environment:  python scripts/check_desktop_env.py")
    print("    2. Run demo (dry-run):  maref desktop demo")
    print('    3. Run live task:       maref desktop run --live --task "open Finder"')
    print()

    return 0 if steps_ok >= steps_total - 1 else 1


if __name__ == "__main__":
    sys.exit(main())
