#!/usr/bin/env python3
"""
MAREF Version Sync Tool

Ensures all version references across the project are consistent.
Reads version from pyproject.toml and updates:
  - README.md badge
  - CHANGELOG.md header
  - Dockerfile LABEL
  - gui/package.json
  - otel_middleware.py tracer version
  - mcp_bridge.py version

Usage:
    python scripts/sync_version.py              # Sync to pyproject.toml version
    python scripts/sync_version.py --version 1.0.0  # Set specific version
    python scripts/sync_version.py --check      # Check if all versions match
"""

import argparse
import json
import re
import sys
from pathlib import Path

# Project root
ROOT = Path(__file__).resolve().parent.parent

# Version source files with their patterns
VERSION_FILES = {
    "pyproject.toml": {
        "path": ROOT / "pyproject.toml",
        "pattern": r'^version\s*=\s*"([^"]+)"',
        "replacement": 'version = "{version}"',
        "priority": "source",
    },
    "README.md": {
        "path": ROOT / "README.md",
        "pattern": r'version-([0-9]+\.[0-9]+\.[0-9]+(?:-[a-z]+)?)\-',
        "replacement": 'version-{version}-',
        "priority": "derived",
    },
    "CHANGELOG.md": {
        "path": ROOT / "CHANGELOG.md",
        "pattern": r'^## \[v?([^\]]+)\]',
        "replacement": None,
        "priority": "derived",
        "has_group": True,
    },
    "Dockerfile": {
        "path": ROOT / "Dockerfile",
        "pattern": r'^LABEL\s+org\.opencontainers\.image\.version="([^"]+)"',
        "replacement": 'LABEL org.opencontainers.image.version="{version}"',
        "priority": "derived",
    },
    "gui/package.json": {
        "path": ROOT / "gui" / "package.json",
        "pattern": r'"version":\s*"([^"]+)"',
        "replacement": '"version": "{version}"',
        "priority": "derived",
    },
    "otel_middleware.py": {
        "path": ROOT / "src" / "maref" / "observability" / "otel_middleware.py",
        "pattern": r'"(0\.\d+\.\d+(?:-[a-z]+)?)"',
        "replacement": '"{version}"',
        "priority": "derived",
    },
    "mcp_bridge.py": {
        "path": ROOT / "src" / "sidecar" / "mcp_bridge.py",
        "pattern": r'"version":\s*"([^"]+)"',
        "replacement": '"version": "{version}"',
        "priority": "derived",
    },
}


def get_pyproject_version() -> str:
    """Read version from pyproject.toml."""
    path = VERSION_FILES["pyproject.toml"]["path"]
    if not path.exists():
        print(f"ERROR: {path} not found")
        sys.exit(1)
    content = path.read_text()
    match = re.search(VERSION_FILES["pyproject.toml"]["pattern"], content, re.MULTILINE)
    if not match:
        print("ERROR: Could not find version in pyproject.toml")
        sys.exit(1)
    return match.group(1)


def check_versions() -> dict[str, str]:
    """Check all version references and return mismatches."""
    source_version = get_pyproject_version()
    results = {"pyproject.toml": source_version}
    mismatches = {}

    for name, config in VERSION_FILES.items():
        if config["priority"] == "source":
            continue
        path = config["path"]
        if not path.exists():
            results[name] = "FILE_NOT_FOUND"
            continue

        content = path.read_text()
        match = re.search(config["pattern"], content, re.MULTILINE)
        if match:
            try:
                version = match.group(1)
            except IndexError:
                version = match.group(0)
            results[name] = version
            if version != source_version:
                mismatches[name] = version
        else:
            results[name] = "NOT_FOUND"

    return results, source_version, mismatches


def sync_version(target_version: str | None = None) -> bool:
    """Sync all version references to match."""
    if target_version is None:
        target_version = get_pyproject_version()

    print(f"Syncing all versions to: {target_version}")

    for name, config in VERSION_FILES.items():
        if config["priority"] == "source":
            continue
        path = config["path"]
        if not path.exists():
            print(f"  SKIP {name}: file not found")
            continue

        content = path.read_text()
        pattern = config["pattern"]

        if name == "CHANGELOG.md":
            # Special handling for CHANGELOG - add new header if not exists
            if f"## [v{target_version}]" not in content and f"## [{target_version}]" not in content:
                new_header = f"## [v{target_version}] - 2026-05-17\n\n### Added\n- TODO\n\n### Changed\n- TODO\n\n### Fixed\n- TODO\n\n"
                # Insert after first line
                lines = content.split("\n", 1)
                content = lines[0] + "\n\n" + new_header + (lines[1] if len(lines) > 1 else "")
                path.write_text(content)
                print(f"  UPDATED {name}: added new version header")
            else:
                print(f"  OK {name}: version header exists")
            continue

        new_content, count = re.subn(
            pattern,
            config["replacement"].format(version=target_version) if config["replacement"] else "",
            content,
            count=0,
            flags=re.MULTILINE
        )

        if count > 0:
            path.write_text(new_content)
            print(f"  UPDATED {name}: {count} occurrence(s)")
        else:
            print(f"  OK {name}: version matches")

    return True


def main():
    parser = argparse.ArgumentParser(description="MAREF Version Sync Tool")
    parser.add_argument("--version", "-v", help="Set specific version")
    parser.add_argument("--check", "-c", action="store_true", help="Check version consistency")
    args = parser.parse_args()

    if args.check:
        results, source_version, mismatches = check_versions()
        print(f"Source version (pyproject.toml): {source_version}")
        print("\nVersion status:")
        for name, version in results.items():
            status = "MISMATCH" if name in mismatches else "OK"
            print(f"  {status:10s} {name}: {version}")

        if mismatches:
            print(f"\n✗ {len(mismatches)} version mismatch(es) found")
            print("Run: python scripts/sync_version.py --version {version}")
            sys.exit(1)
        else:
            print("\n✓ All versions are consistent")
            sys.exit(0)
    else:
        target = args.version
        sync_version(target)
        print("\n✓ Version sync complete")
        if args.check:
            check_versions()


if __name__ == "__main__":
    main()
