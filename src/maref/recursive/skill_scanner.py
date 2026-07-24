from __future__ import annotations

import hashlib
import logging
import random
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


@dataclass
class SkillScannerConfig:
    source_repos: list[str] = field(default_factory=lambda: [
        "https://github.com/anthropics/skills",
        "https://github.com/JackyST0/awesome-agent-skills",
    ])
    clone_base_dir: str | Path = ".maref/skill_cache"
    max_scan_per_cycle: int = 5
    clone_timeout_seconds: int = 120
    cache_ttl_days: int = 7


@dataclass
class ScannedSkill:
    local_path: Path
    repo_url: str
    repo_commit: str
    raw_content: str
    frontmatter: dict[str, Any]
    file_size_bytes: int
    content_hash: str


class SkillScanner:
    def __init__(self, config: SkillScannerConfig | None = None) -> None:
        self._config = config or SkillScannerConfig()
        self._clone_base = Path(self._config.clone_base_dir)

    def scan(self) -> list[ScannedSkill]:
        """Clone/pull repos, glob SKILL.md, return a batch (rate-limited)."""
        self._clone_base.mkdir(parents=True, exist_ok=True)
        candidates: list[ScannedSkill] = []
        errors: list[str] = []

        for repo_url in self._config.source_repos:
            try:
                clone_dir = self._ensure_clone(repo_url)
                commit = self._get_head_commit(clone_dir)
                for sk_path in sorted(clone_dir.rglob("SKILL.md")):
                    try:
                        raw = sk_path.read_text(encoding="utf-8", errors="replace")
                    except Exception:
                        continue
                    fm = self._parse_frontmatter(raw)
                    ch = self._compute_content_hash(raw)
                    candidates.append(ScannedSkill(
                        local_path=sk_path,
                        repo_url=repo_url,
                        repo_commit=commit,
                        raw_content=raw,
                        frontmatter=fm,
                        file_size_bytes=len(raw.encode("utf-8")),
                        content_hash=ch,
                    ))
            except Exception as exc:
                errors.append(f"{repo_url}: {exc}")
                logger.warning("SkillScanner: failed to scan %s: %s", repo_url, exc)

        if errors:
            logger.warning("SkillScanner: %d error(s): %s", len(errors), errors[:2])

        # Shuffle for diverse coverage, then rate-limit
        random.shuffle(candidates)
        return candidates[: self._config.max_scan_per_cycle]

    def _ensure_clone(self, repo_url: str) -> Path:
        repo_name = repo_url.rstrip("/").split("/")[-1]
        clone_dir = (self._clone_base / repo_name).resolve()

        if clone_dir.exists():
            age_seconds = time.time() - clone_dir.stat().st_mtime
            if age_seconds > self._config.cache_ttl_days * 86400:
                self._git(["fetch", "--depth=1"], clone_dir)
                self._git(["reset", "--hard", "origin/HEAD"], clone_dir)
            return clone_dir

        self._clone_base.mkdir(parents=True, exist_ok=True)
        self._git(["clone", "--depth=1", repo_url, str(clone_dir)], self._clone_base.resolve())
        return clone_dir

    def _get_head_commit(self, repo_dir: Path) -> str:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=str(repo_dir),
                capture_output=True,
                text=True,
                timeout=30,
            )
            return result.stdout.strip() if result.returncode == 0 else "unknown"
        except Exception:
            return "unknown"

    def _git(self, args: list[str], cwd: Path) -> None:
        subprocess.run(
            ["git"] + args,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=self._config.clone_timeout_seconds,
            check=True,
        )

    @staticmethod
    def _parse_frontmatter(content: str) -> dict[str, Any]:
        stripped = content.strip()
        if stripped.startswith("---"):
            parts = stripped.split("---", 2)
            if len(parts) >= 3:
                try:
                    return yaml.safe_load(parts[1]) or {}
                except yaml.YAMLError:
                    return {}
        return {}

    @staticmethod
    def _compute_content_hash(content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()
