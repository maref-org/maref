from __future__ import annotations

from maref.immunity.acceptance_extractor import (
    AcceptanceExtractor,
)


class TestAcceptanceExtractor:
    """M2.1: PRD -> Acceptance Criteria pipeline."""

    def test_extract_ac_login_returns_at_least_3(self):
        extractor = AcceptanceExtractor()
        criteria = extractor.extract_ac("实现用户登录功能")
        assert len(criteria) >= 3

    def test_extract_ac_login_includes_boundary(self):
        extractor = AcceptanceExtractor()
        criteria = extractor.extract_ac("实现用户登录功能")
        categories = {c.category for c in criteria}
        assert "boundary" in categories
        boundary = [c for c in criteria if c.category == "boundary"]
        assert len(boundary) >= 1

    def test_extract_ac_login_includes_happy_path(self):
        extractor = AcceptanceExtractor()
        criteria = extractor.extract_ac("实现用户登录功能")
        categories = {c.category for c in criteria}
        assert "happy_path" in categories

    def test_extract_ac_login_includes_error(self):
        extractor = AcceptanceExtractor()
        criteria = extractor.extract_ac("实现用户登录功能")
        categories = {c.category for c in criteria}
        assert "error" in categories

    def test_each_criterion_has_test_template(self):
        extractor = AcceptanceExtractor()
        criteria = extractor.extract_ac("实现用户登录功能")
        for c in criteria:
            assert c.test_template
            assert "def test_" in c.test_template
            has_assert = "assert" in c.test_template
            has_raises = "pytest.raises" in c.test_template
            assert has_assert or has_raises

    def test_each_criterion_has_unique_id(self):
        extractor = AcceptanceExtractor()
        criteria = extractor.extract_ac("实现用户登录功能")
        ids = [c.criterion_id for c in criteria]
        assert len(ids) == len(set(ids))

    def test_intent_hash_is_sha256(self):
        extractor = AcceptanceExtractor()
        criteria = extractor.extract_ac("实现用户登录功能")
        ih = extractor.compute_intent_hash(criteria)
        assert len(ih.hash_value) == 64
        int(ih.hash_value, 16)

    def test_intent_hash_is_deterministic(self):
        extractor = AcceptanceExtractor()
        c1 = extractor.extract_ac("实现用户登录功能")
        c2 = extractor.extract_ac("实现用户登录功能")
        ih1 = extractor.compute_intent_hash(c1)
        ih2 = extractor.compute_intent_hash(c2)
        assert ih1.hash_value == ih2.hash_value
        assert ih1.criteria_count == ih2.criteria_count

    def test_intent_hash_changes_with_different_description(self):
        extractor = AcceptanceExtractor()
        c1 = extractor.extract_ac("实现用户登录功能")
        c2 = extractor.extract_ac("实现用户注册功能")
        ih1 = extractor.compute_intent_hash(c1)
        ih2 = extractor.compute_intent_hash(c2)
        assert ih1.hash_value != ih2.hash_value

    def test_intent_hash_tracks_count(self):
        extractor = AcceptanceExtractor()
        criteria = extractor.extract_ac("实现用户登录功能")
        ih = extractor.compute_intent_hash(criteria)
        assert ih.criteria_count == len(criteria)

    def test_register_extraction(self):
        extractor = AcceptanceExtractor()
        criteria = extractor.extract_ac("实现用户注册功能")
        assert len(criteria) >= 3
        assert any(c.category == "boundary" for c in criteria)
        assert any(c.category == "happy_path" for c in criteria)
        assert any(c.category == "error" for c in criteria)

    def test_search_extraction(self):
        extractor = AcceptanceExtractor()
        criteria = extractor.extract_ac("实现搜索功能")
        assert len(criteria) >= 3
        assert any(c.category == "happy_path" for c in criteria)

    def test_upload_extraction(self):
        extractor = AcceptanceExtractor()
        criteria = extractor.extract_ac("文件上传功能")
        assert len(criteria) >= 3
        assert any(c.category == "boundary" for c in criteria)

    def test_generic_fallback_extraction(self):
        extractor = AcceptanceExtractor()
        criteria = extractor.extract_ac("实现数据分析功能")
        assert len(criteria) >= 3
        assert any(c.category == "happy_path" for c in criteria)

    def test_deduplication(self):
        extractor = AcceptanceExtractor()
        criteria = extractor.extract_ac("实现用户登录功能")
        descriptions = [c.description for c in criteria]
        assert len(descriptions) == len(set(descriptions))

    def test_english_login_keyword(self):
        extractor = AcceptanceExtractor()
        criteria = extractor.extract_ac("Implement user login")
        assert len(criteria) >= 3

    def test_signin_variant(self):
        extractor = AcceptanceExtractor()
        criteria = extractor.extract_ac("Add sign in to app")
        assert len(criteria) >= 3

    def test_register_variant_signup(self):
        extractor = AcceptanceExtractor()
        criteria = extractor.extract_ac("Implement signup")
        assert len(criteria) >= 3

    def test_search_variant_query(self):
        extractor = AcceptanceExtractor()
        criteria = extractor.extract_ac("Add query functionality")
        assert len(criteria) >= 3

    def test_upload_variant_import(self):
        extractor = AcceptanceExtractor()
        criteria = extractor.extract_ac("数据导入功能")
        assert len(criteria) >= 3
