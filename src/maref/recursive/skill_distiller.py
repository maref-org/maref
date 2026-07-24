from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from maref.recursive.agent_marketplace import AgentMarketplace
from maref.recursive.skill_converter import SkillConverter
from maref.recursive.skill_loader import SkillLoader
from maref.recursive.skill_registry_store import SkillRegistryStore, SkillRegistrationResult, register_distilled_skill
from maref.recursive.skill_scanner import ScannedSkill, SkillScanner, SkillScannerConfig
from maref.recursive.skill_scorer import QualityScore, SkillScorer

logger = logging.getLogger(__name__)


@dataclass
class SkillDistillationConfig:
    scanner_config: SkillScannerConfig = field(default_factory=SkillScannerConfig)
    quality_threshold: float = 0.7
    max_new_skills_per_cycle: int = 5
    agent_id: str = "maref_skill_distiller"


@dataclass
class SkillDistillationResult:
    scanned_count: int = 0
    scored_count: int = 0
    passed_threshold: int = 0
    already_processed: int = 0
    new_skills_registered: int = 0
    skills: list[dict[str, Any]] = field(default_factory=list)
    registrations: list[SkillRegistrationResult] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    duration_ms: float = 0.0


class SkillDistiller:
    """Orchestrates the full distillation pipeline:

    scan → score → filter → convert → dedup → register
    """

    def __init__(
        self,
        config: SkillDistillationConfig | None = None,
        scanner: SkillScanner | None = None,
        scorer: SkillScorer | None = None,
        converter: SkillConverter | None = None,
        registry_store: SkillRegistryStore | None = None,
        loader: SkillLoader | None = None,
        marketplace: AgentMarketplace | None = None,
    ) -> None:
        self._config = config or SkillDistillationConfig()
        self._scanner = scanner or SkillScanner(self._config.scanner_config)
        self._scorer = scorer or SkillScorer()
        self._converter = converter or SkillConverter()
        self._registry = registry_store or SkillRegistryStore()
        self._loader = loader or SkillLoader()
        self._marketplace = marketplace

    def run_pipeline(self) -> SkillDistillationResult:
        import time

        t0 = time.monotonic()
        result = SkillDistillationResult()

        # 1. Scan
        candidates = self._scanner.scan()
        result.scanned_count = len(candidates)
        logger.info("SkillDistiller: scanned %d SKILL.md files", result.scanned_count)

        for skill in candidates:
            # 2. Score
            qs = self._scorer.score(skill.raw_content, skill.frontmatter)
            result.scored_count += 1

            if not self._scorer.is_quality(qs, self._config.quality_threshold):
                logger.debug("SkillDistiller: %s scored %.3f — below threshold", skill.local_path.name, qs.overall)
                continue

            result.passed_threshold += 1
            logger.info(
                "SkillDistiller: %s scored %.3f — above threshold",
                skill.local_path.name, qs.overall,
            )

            # 3. Convert
            skill_dict = self._converter.convert(
                content=skill.raw_content,
                content_hash=skill.content_hash,
                repo_url=skill.repo_url,
                repo_path=str(skill.local_path),
                frontmatter=skill.frontmatter,
                quality=qs,
            )

            # 4. Dedup
            if self._registry.is_already_processed(skill.content_hash):
                result.already_processed += 1
                logger.debug("SkillDistiller: %s already processed — skipping", skill.local_path.name)
                continue

            # 5. Register
            try:
                reg = register_distilled_skill(
                    skill_dict=skill_dict,
                    loader=self._loader,
                    marketplace=self._marketplace,
                    agent_id=self._config.agent_id,
                )
                result.registrations.append(reg)
                if reg.success:
                    self._registry.mark_processed(skill.content_hash)
                    result.new_skills_registered += 1
                    result.skills.append(skill_dict)
                    logger.info(
                        "SkillDistiller: registered '%s' (listing=%s)",
                        reg.skill_name, reg.listing_id,
                    )
                else:
                    result.errors.append(f"{skill.local_path.name}: {reg.error}")
            except Exception as exc:
                result.errors.append(f"{skill.local_path.name}: {exc}")

            if result.new_skills_registered >= self._config.max_new_skills_per_cycle:
                logger.info("SkillDistiller: reached max %d new skills per cycle — stopping", self._config.max_new_skills_per_cycle)
                break

        result.duration_ms = int((time.monotonic() - t0) * 1000)
        logger.info(
            "SkillDistiller: scanned=%d passed=%d new=%d errors=%d in %.1fs",
            result.scanned_count,
            result.passed_threshold,
            result.new_skills_registered,
            len(result.errors),
            result.duration_ms / 1000,
        )
        return result

    @classmethod
    def from_config(cls, config: SkillDistillationConfig | None = None) -> SkillDistiller:
        """Convenience constructor with defaults."""
        return cls(config=config or SkillDistillationConfig())
