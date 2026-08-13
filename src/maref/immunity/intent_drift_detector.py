from __future__ import annotations

import ast
import time
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from maref.immunity.acceptance_extractor import AcceptanceCriterion, AcceptanceExtractor

if TYPE_CHECKING:
    from maref.immunity.immune_checker import ImmuneChecker, ImmuneHit
    from maref.immunity.negative_gene_bank import NegativeGeneBank
    from maref.recursive.safety_gate_v2 import SafetyGateV2


@dataclass
class FuzzTestResult:
    criterion_id: str
    description: str
    category: str
    passed: bool
    error: str | None = None


@dataclass
class IntentDriftResult:
    passed: bool
    intent_valid: bool
    test_results: list[FuzzTestResult]
    blocked: bool
    extracted_gene_ids: list[str] = field(default_factory=list)
    immune_hits: list[ImmuneHit] = field(default_factory=list)


class IntentDriftDetector:
    def __init__(self, gene_bank: NegativeGeneBank | None = None) -> None:
        self._extractor = AcceptanceExtractor()
        self._gene_bank = gene_bank
        self._safety_gate: SafetyGateV2 | None = None

    def attach_safety_gate(self, gate: SafetyGateV2) -> None:
        """附加 SafetyGateV2 - 哈希变化时调用其 block() 阻断。"""
        self._safety_gate = gate

    def verify_intent_hash(self, criteria: list[AcceptanceCriterion], expected_hash: str) -> bool:
        actual = self._extractor.compute_intent_hash(criteria)
        return actual.hash_value == expected_hash

    def evaluate_code(
        self,
        code: str,
        criteria: list[AcceptanceCriterion],
        expected_hash: str,
        immune_checker: ImmuneChecker | None = None,
        language: str = "python",
    ) -> IntentDriftResult:
        intent_valid = self.verify_intent_hash(criteria, expected_hash)
        if not intent_valid:
            if self._safety_gate is not None:
                self._safety_gate.block("intent_drift:hash_mismatch")
            return IntentDriftResult(
                passed=False, intent_valid=False, test_results=[], blocked=True
            )
        test_results = self._fuzz_test_code(code, criteria, language)
        immune_hits: list[ImmuneHit] = []
        if immune_checker is not None:
            immune_hits = immune_checker.scan(code, language=language)
        extracted: list[str] = []
        failures = [r for r in test_results if not r.passed]
        if failures and self._gene_bank is not None:
            for f in failures:
                gid = self._extract_negative_gene(f, code, language)
                if gid:
                    extracted.append(gid)
        passed = len(failures) == 0 and len(immune_hits) == 0
        return IntentDriftResult(
            passed=passed,
            intent_valid=True,
            test_results=test_results,
            blocked=False,
            extracted_gene_ids=extracted,
            immune_hits=immune_hits,
        )

    def _fuzz_test_code(
        self, code: str, criteria: list[AcceptanceCriterion], language: str = "python"
    ) -> list[FuzzTestResult]:
        if language != "python":
            return self._fuzz_non_python(code, criteria, language)
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return [
                FuzzTestResult(
                    criterion_id=c.criterion_id,
                    description=c.description,
                    category=c.category,
                    passed=False,
                    error=f"Syntax error: {e}",
                )
                for c in criteria
            ]
        func_names = {
            node.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        results: list[FuzzTestResult] = []
        for c in criteria:
            result = self._test_single_criterion(c, tree, func_names)
            results.append(result)
        return results

    def _fuzz_non_python(
        self, code: str, criteria: list[AcceptanceCriterion], language: str
    ) -> list[FuzzTestResult]:
        results: list[FuzzTestResult] = []
        for c in criteria:
            desc_words = set(c.description.lower().split())
            code_lower = code.lower()
            passed = any(w in code_lower for w in desc_words if len(w) > 2)
            results.append(
                FuzzTestResult(
                    criterion_id=c.criterion_id,
                    description=c.description,
                    category=c.category,
                    passed=passed,
                )
            )
        return results

    def _test_single_criterion(
        self, criterion: AcceptanceCriterion, tree: ast.AST, func_names: set[str]
    ) -> FuzzTestResult:
        desc = criterion.description
        if criterion.category == "happy_path":
            for word in self._extract_keywords(desc):
                if any(word in fn for fn in func_names):
                    return FuzzTestResult(
                        criterion_id=criterion.criterion_id,
                        description=desc,
                        category=criterion.category,
                        passed=True,
                    )
            return FuzzTestResult(
                criterion_id=criterion.criterion_id,
                description=desc,
                category=criterion.category,
                passed=False,
                error=f"No function matches: {desc}",
            )
        if criterion.category == "error":
            for node in ast.walk(tree):
                if isinstance(node, (ast.Try, ast.ExceptHandler)):
                    return FuzzTestResult(
                        criterion_id=criterion.criterion_id,
                        description=desc,
                        category=criterion.category,
                        passed=True,
                    )
            return FuzzTestResult(
                criterion_id=criterion.criterion_id,
                description=desc,
                category=criterion.category,
                passed=False,
                error="No try/except error handling found",
            )
        if criterion.category == "boundary":
            for node in ast.walk(tree):
                if isinstance(node, ast.If):
                    test_str = ast.dump(node.test)
                    for kw in ("None", "len", "==", "is None", "<", ">", "not"):
                        if kw in test_str:
                            return FuzzTestResult(
                                criterion_id=criterion.criterion_id,
                                description=desc,
                                category=criterion.category,
                                passed=True,
                            )
            return FuzzTestResult(
                criterion_id=criterion.criterion_id,
                description=desc,
                category=criterion.category,
                passed=False,
                error="No boundary condition check found",
            )
        return FuzzTestResult(
            criterion_id=criterion.criterion_id,
            description=desc,
            category=criterion.category,
            passed=True,
        )

    def _extract_keywords(self, description: str) -> list[str]:
        keywords: list[str] = []
        for pair in (
            ("登录", "login"),
            ("注册", "register"),
            ("搜索", "search"),
            ("上传", "upload"),
            ("成功", "success"),
            ("失败", "fail"),
            ("锁定", "lock"),
            ("拒绝", "reject"),
            ("空", "empty"),
        ):
            if pair[0] in description or pair[1] in description.lower():
                keywords.append(pair[1])
        return keywords or [description[:20].lower()]

    def _extract_negative_gene(
        self, failure: FuzzTestResult, code: str, language: str
    ) -> str | None:
        if self._gene_bank is None:
            return None
        from maref.immunity.negative_gene_bank import NegativeGene

        gene_id = f"NEG-DRIFT-{uuid.uuid4().hex[:8].upper()}"
        gene = NegativeGene(
            gene_id=gene_id,
            cwe_id="CWE-1104",
            risk_level="MEDIUM",
            severity=5,
            blocked=False,
            title=f"Intent drift: {failure.description[:60]}",
            description=f"Code failed acceptance criterion '{failure.description}' during fuzz testing. Category: {failure.category}. Error: {failure.error}",
            source="intent_drift_detector",
            first_seen=time.time(),
            occurrences=1,
            retention_days=365,
            hmac_signature="",
            patterns=[],
            variants=[],
        )
        try:
            self._gene_bank.store_gene(gene)
            return gene_id
        except Exception:
            return None
