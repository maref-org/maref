from __future__ import annotations

import os
import time
import uuid
from typing import TYPE_CHECKING, Any

from maref.security.decorators import security_critical

if TYPE_CHECKING:
    from maref.immunity.negative_gene_bank import NegativeGeneBank
    from maref.recursive.experience_pool import ExperiencePool


class AutoGeneExtractionPipeline:
    def __init__(self, gene_bank: NegativeGeneBank, experience_pool: ExperiencePool) -> None:
        self._gene_bank = gene_bank
        self._experience_pool = experience_pool
        self._extraction_count = 0
        self._recent_extractions: list[dict[str, Any]] = []

    @property
    def extraction_count(self) -> int:
        return self._extraction_count

    @property
    def recent_extractions(self) -> list[dict[str, Any]]:
        return list(self._recent_extractions)

    @security_critical
    def extract_from_heal(self, snapshot: str, fix_code: str, reason: str = "") -> str | None:
        gene = self._build_gene(
            title="Self-healed code pattern fixed",
            description=f"Auto-heal corrected pattern. Reason: {reason or 'unknown'}",
            cwe_id="CWE-1104",
            risk_level="MEDIUM",
            severity=5,
            blocked=False,
            source="auto_heal",
            pattern_value=self._pattern_from_diff(snapshot, fix_code),
        )
        if gene is None:
            return None
        gene_id = self._gene_bank.store_gene(gene)
        self._record_extraction("heal", gene_id, reason)
        self._sync_to_experience(gene, f"auto_extract_heal:{reason}")
        return gene_id

    @security_critical
    def extract_from_rollback(self, code_snapshot: str, reason: str = "") -> str | None:
        gene = self._build_gene(
            title="Code pattern caused rollback",
            description=f"Auto-extracted from rollback. Reason: {reason or 'unknown'}",
            cwe_id="CWE-1104",
            risk_level="HIGH",
            severity=7,
            blocked=True,
            source="self_executor_rollback",
            pattern_value=self._pattern_from_code(code_snapshot),
        )
        if gene is None:
            return None
        gene_id = self._gene_bank.store_gene(gene)
        self._record_extraction("rollback", gene_id, reason)
        self._sync_to_experience(gene, f"auto_extract_rollback:{reason}")
        return gene_id

    @security_critical
    def extract_from_block(self, blocked_code: str, reason: str = "") -> str | None:
        gene = self._build_gene(
            title="Code pattern blocked by SafetyGate",
            description=f"Auto-extracted from gate block. Reason: {reason or 'unknown'}",
            cwe_id="CWE-1104",
            risk_level="HIGH",
            severity=8,
            blocked=True,
            source="safety_gate_v2",
            pattern_value=self._pattern_from_code(blocked_code),
        )
        if gene is None:
            return None
        gene_id = self._gene_bank.store_gene(gene)
        self._record_extraction("block", gene_id, reason)
        self._sync_to_experience(gene, f"auto_extract_block:{reason}")
        return gene_id

    @security_critical
    def sync_with_experience_pool(self) -> int:
        count = 0
        for extraction in self._recent_extractions:
            tag = f"auto_gene:{extraction['source']}"
            existing = self._experience_pool.query_by_tag(tag)
            if not existing:
                self._sync_to_experience_from_record(extraction)
                count += 1
        return count

    def _build_gene(
        self,
        title: str,
        description: str,
        cwe_id: str,
        risk_level: str,
        severity: int,
        blocked: bool,
        source: str,
        pattern_value: str,
    ) -> Any | None:
        if not pattern_value:
            return None
        from maref.immunity.negative_gene_bank import GenePattern, GeneVariant, NegativeGene

        gene_id = f"AUTO-{uuid.uuid4().hex[:8].upper()}"
        now = time.time()
        gene = NegativeGene(
            gene_id=gene_id,
            cwe_id=cwe_id,
            risk_level=risk_level,
            severity=severity,
            blocked=blocked,
            title=title,
            description=description,
            source=source,
            first_seen=now,
            occurrences=1,
            retention_days=730,
            patterns=[
                GenePattern(
                    pattern_id=f"PAT-{uuid.uuid4().hex[:8].upper()}",
                    gene_id=gene_id,
                    pattern_type="string_content",
                    pattern_value=pattern_value,
                )
            ],
            variants=[
                GeneVariant(
                    variant_id=f"VAR-{uuid.uuid4().hex[:8].upper()}",
                    gene_id=gene_id,
                    language="python",
                    variant_code=pattern_value,
                )
            ],
        )
        gene.update_hmac(self._get_hmac_key())
        return gene

    def _pattern_from_diff(self, old_code: str, new_code: str) -> str:
        diff_lines: list[str] = []
        old_lines = old_code.splitlines()
        new_lines = new_code.splitlines()
        max_len = max(len(old_lines), len(new_lines))
        for i in range(max_len):
            old_line = old_lines[i] if i < len(old_lines) else ""
            new_line = new_lines[i] if i < len(new_lines) else ""
            if old_line != new_line:
                diff_lines.append(new_line)
        result = "\n".join(diff_lines).strip()
        return result[:200] if result else ""

    def _pattern_from_code(self, code: str) -> str:
        return code.strip()[:200] if code.strip() else ""

    _HMAC_KEY_ENV = "MAREF_AUTO_GENE_HMAC_KEY"
    _FALLBACK_KEY = b"ma-ref-auto-gene-key"

    def _get_hmac_key(self) -> bytes:
        key = os.environ.get(self._HMAC_KEY_ENV)
        return key.encode() if key else self._FALLBACK_KEY

    def _record_extraction(self, source: str, gene_id: str, reason: str) -> None:
        self._extraction_count += 1
        self._recent_extractions.append(
            {"gene_id": gene_id, "source": source, "reason": reason, "timestamp": time.time()}
        )

    def _sync_to_experience(self, gene: Any, tag_hint: str) -> None:
        from maref.recursive.experience_pool import ExperienceEntry

        entry = ExperienceEntry(
            entry_id=f"ext_{uuid.uuid4().hex[:8]}",
            timestamp=time.time(),
            context=f"Auto-extracted negative gene: {gene.title} ({gene.source})",
            decision="EXTRACT",
            outcome="stored",
            lesson_learned=gene.description[:200],
            tags=[f"auto_gene:{gene.source}", f"cwe:{gene.cwe_id}"],
        )
        self._experience_pool.store(entry)

    def _sync_to_experience_from_record(self, extraction: dict[str, Any]) -> None:
        from maref.recursive.experience_pool import ExperienceEntry

        entry = ExperienceEntry(
            entry_id=f"sync_{uuid.uuid4().hex[:8]}",
            timestamp=time.time(),
            context=f"Synced extraction: {extraction['gene_id']} ({extraction['source']})",
            decision="SYNC",
            outcome="synced",
            lesson_learned=f"Auto-synced from {extraction['source']}: {extraction['reason']}",
            tags=[f"auto_gene:{extraction['source']}", "sync"],
        )
        self._experience_pool.store(entry)
