from __future__ import annotations

from maref.immunity.intent_drift_detector import (
    IntentDriftDetector,
)

HAPPY_CODE = """
def login(username, password):
    if username is None or password is None:
        return {"error": "empty"}
    if len(password) < 8:
        return {"error": "too short"}
    try:
        result = authenticate(username, password)
        return result
    except AuthenticationError:
        return {"error": "auth_failed"}
"""

BAD_CODE = """
def login(username, password):
    return {"status": "success"}
"""


class TestIntentDriftDetector:
    """M2.2: Intent drift detection + fuzz test gate."""

    def test_intent_hash_mismatch_blocks(self):
        detector = IntentDriftDetector()
        criteria = detector._extractor.extract_ac("实现用户登录功能")
        result = detector.evaluate_code(
            code=HAPPY_CODE,
            criteria=criteria,
            expected_hash="deadbeef" * 8,
        )
        assert result.blocked is True
        assert result.intent_valid is False
        assert result.passed is False

    def test_intent_hash_valid_not_blocked(self):
        detector = IntentDriftDetector()
        criteria = detector._extractor.extract_ac("实现用户登录功能")
        ih = detector._extractor.compute_intent_hash(criteria)
        result = detector.evaluate_code(
            code=HAPPY_CODE,
            criteria=criteria,
            expected_hash=ih.hash_value,
        )
        assert result.blocked is False
        assert result.intent_valid is True

    def test_good_code_passes_fuzz(self):
        detector = IntentDriftDetector()
        criteria = detector._extractor.extract_ac("实现用户登录功能")
        ih = detector._extractor.compute_intent_hash(criteria)
        result = detector.evaluate_code(
            code=HAPPY_CODE,
            criteria=criteria,
            expected_hash=ih.hash_value,
        )
        assert result.intent_valid is True

    def test_bad_code_fails_fuzz(self):
        detector = IntentDriftDetector()
        criteria = detector._extractor.extract_ac("实现用户登录功能")
        ih = detector._extractor.compute_intent_hash(criteria)
        result = detector.evaluate_code(
            code=BAD_CODE,
            criteria=criteria,
            expected_hash=ih.hash_value,
        )
        assert result.passed is False
        assert len(result.test_results) > 0

    def test_verify_intent_hash_matches(self):
        detector = IntentDriftDetector()
        criteria = detector._extractor.extract_ac("实现用户登录功能")
        ih = detector._extractor.compute_intent_hash(criteria)
        assert detector.verify_intent_hash(criteria, ih.hash_value) is True

    def test_verify_intent_hash_mismatch(self):
        detector = IntentDriftDetector()
        criteria = detector._extractor.extract_ac("实现用户登录功能")
        assert detector.verify_intent_hash(criteria, "x" * 64) is False

    def test_fuzz_test_results_contain_all_criteria(self):
        detector = IntentDriftDetector()
        criteria = detector._extractor.extract_ac("实现用户登录功能")
        ih = detector._extractor.compute_intent_hash(criteria)
        result = detector.evaluate_code(
            code=HAPPY_CODE,
            criteria=criteria,
            expected_hash=ih.hash_value,
        )
        assert len(result.test_results) == len(criteria)

    def test_syntax_error_returns_all_failures(self):
        detector = IntentDriftDetector()
        criteria = [detector._extractor.extract_ac("实现用户登录功能")[0]]
        ih = detector._extractor.compute_intent_hash(criteria)
        result = detector.evaluate_code(
            code="def broken( ",
            criteria=criteria,
            expected_hash=ih.hash_value,
        )
        assert result.passed is False
        assert all(not r.passed for r in result.test_results)

    def test_non_python_fallback(self):
        detector = IntentDriftDetector()
        criteria = detector._extractor.extract_ac("实现搜索功能")
        ih = detector._extractor.compute_intent_hash(criteria)
        result = detector.evaluate_code(
            code="function search() { return []; }",
            criteria=criteria,
            expected_hash=ih.hash_value,
            language="javascript",
        )
        assert result.intent_valid is True

    def test_empty_criteria_not_crash(self):
        detector = IntentDriftDetector()
        result = detector.evaluate_code(
            code="",
            criteria=[],
            expected_hash="",
        )
        assert result.passed is False

    def test_evaluate_with_immune_checker(self):
        from maref.immunity.immune_checker import ImmuneChecker
        from maref.immunity.negative_gene_bank import NegativeGeneBank

        bank = NegativeGeneBank(":memory:")
        checker = ImmuneChecker(bank)
        detector = IntentDriftDetector(gene_bank=bank)
        criteria = detector._extractor.extract_ac("实现用户登录功能")
        ih = detector._extractor.compute_intent_hash(criteria)
        result = detector.evaluate_code(
            code=HAPPY_CODE,
            criteria=criteria,
            expected_hash=ih.hash_value,
            immune_checker=checker,
        )
        assert result.intent_valid is True
        assert isinstance(result.immune_hits, list)

    def test_auto_extract_negative_gene_on_failure(self):
        from maref.immunity.negative_gene_bank import NegativeGeneBank

        bank = NegativeGeneBank(":memory:")
        detector = IntentDriftDetector(gene_bank=bank)
        criteria = detector._extractor.extract_ac("实现用户登录功能")
        ih = detector._extractor.compute_intent_hash(criteria)
        result = detector.evaluate_code(
            code=BAD_CODE,
            criteria=criteria,
            expected_hash=ih.hash_value,
        )
        assert result.passed is False
        assert len(result.extracted_gene_ids) > 0
        stored = bank.get_gene(result.extracted_gene_ids[0])
        assert stored is not None
        assert stored.source == "intent_drift_detector"
