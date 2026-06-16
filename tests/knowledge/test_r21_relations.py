from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from src.maref.knowledge.relations import (
    ExtractedRelation,
    LLMExtractor,
    RelationType,
    RuleBasedExtractor,
    _shared_keyword_count,
    _tokenize,
)


class TestTokenize:
    def test_simple_english(self):
        tokens = _tokenize("hello world test")
        assert "hello" in tokens
        assert "world" in tokens
        assert "test" in tokens

    def test_chinese_characters(self):
        tokens = _tokenize("系统诊断发现问题")
        assert "系" in tokens or "统" in tokens
        assert len(tokens) > 0

    def test_mixed_chinese_english(self):
        tokens = _tokenize("MAREF 系统发现 error")
        assert len(tokens) >= 3

    def test_empty_string(self):
        tokens = _tokenize("")
        assert tokens == []

    def test_punctuation_only(self):
        tokens = _tokenize("，。！？")
        assert tokens == []

    def test_single_char_english_filtered_out(self):
        tokens = _tokenize("a b c")
        assert len(tokens) == 0

    def test_numbers_included(self):
        tokens = _tokenize("error 404 found")
        assert "404" in tokens


class TestSharedKeywordCount:
    def test_identical_strings(self):
        count = _shared_keyword_count("hello world", "hello world")
        assert count >= 1

    def test_no_shared_keywords(self):
        count = _shared_keyword_count("abc def", "xyz uvw")
        assert count == 0

    def test_partial_overlap(self):
        count = _shared_keyword_count("hello world test", "hello world example")
        assert count >= 2


class TestRelationType:
    def test_all_relation_types(self):
        assert RelationType.SUPPORTS.value == "supports"
        assert RelationType.CONTRADICTS.value == "contradicts"
        assert RelationType.CAUSES.value == "causes"
        assert RelationType.SUGGESTS.value == "suggests"
        assert RelationType.OBSERVES.value == "observes"
        assert RelationType.PRECEDES.value == "precedes"
        assert RelationType.TESTS.value == "tests"
        assert RelationType.DERIVES.value == "derives"


class TestExtractedRelation:
    def test_dataclass_creation(self):
        rel = ExtractedRelation(
            subject_text="系统故障",
            relation=RelationType.CAUSES,
            object_text="服务中断",
            confidence=0.85,
            method="rule",
        )
        assert rel.subject_text == "系统故障"
        assert rel.relation == RelationType.CAUSES
        assert rel.object_text == "服务中断"
        assert rel.confidence == 0.85
        assert rel.method == "rule"


class TestRuleBasedExtractor:
    @pytest.fixture
    def extractor(self):
        return RuleBasedExtractor()

    def test_extract_causal_relation(self, extractor):
        relations = extractor.extract(
            "内存泄漏导致服务崩溃",
            ["内存泄漏", "服务崩溃", "系统重启"],
        )
        assert len(relations) > 0

    def test_extract_support_relation(self, extractor):
        relations = extractor.extract(
            "测试结果验证了修复方案",
            ["测试结果", "修复方案", "系统"],
        )
        assert len(relations) > 0

    def test_extract_contradiction_relation(self, extractor):
        relations = extractor.extract(
            "当前配置与安全策略冲突",
            ["当前配置", "安全策略", "系统"],
        )
        assert len(relations) > 0

    def test_extract_no_shared_keywords(self, extractor):
        relations = extractor.extract(
            "系统触发了错误处理",
            ["unrelated_node_xyz"],
        )
        assert len(relations) == 0

    def test_extract_returns_max_10(self, extractor):
        text_parts = []
        for i in range(20):
            text_parts.append(f"错误触发节点{i}")
        text = "导致 ".join(text_parts)

        candidates = [f"节点{i}" for i in range(20)]

        relations = extractor.extract(text, candidates)
        assert len(relations) <= 10

    def test_extract_confidence_range(self, extractor):
        relations = extractor.extract(
            "内存泄漏导致服务崩溃系统异常",
            ["内存泄漏", "服务崩溃", "系统异常"],
        )
        for rel in relations:
            assert 0.5 <= rel.confidence <= 0.9

    def test_extract_method_is_rule(self, extractor):
        relations = extractor.extract(
            "内存泄漏导致服务崩溃",
            ["内存泄漏", "服务崩溃"],
        )
        for rel in relations:
            assert rel.method == "rule"


class TestLLMExtractor:
    @pytest.fixture
    def mock_client(self):
        client = MagicMock()
        client.chat = AsyncMock()
        return client

    def test_init_without_client(self):
        extractor = LLMExtractor()
        assert extractor._client is None

    def test_extract_without_client_returns_empty(self):
        extractor = LLMExtractor()
        result = extractor.extract("text", ["candidate"])
        import asyncio

        relations = asyncio.run(result)
        assert relations == []

    def test_extract_with_client(self, mock_client):
        mock_response = json.dumps(
            [{"subject": "内存泄漏", "relation": "causes", "object": "服务崩溃"}]
        )
        mock_client.chat.return_value = mock_response

        extractor = LLMExtractor(client=mock_client)
        import asyncio

        relations = asyncio.run(extractor.extract("内存泄漏", ["服务崩溃"]))
        assert len(relations) == 1
        assert relations[0].relation == RelationType.CAUSES
        assert relations[0].method == "llm"
        assert relations[0].confidence == 0.75

    def test_extract_client_exception_returns_empty(self, mock_client):
        mock_client.chat.side_effect = RuntimeError("API error")

        extractor = LLMExtractor(client=mock_client)
        import asyncio

        relations = asyncio.run(extractor.extract("text", ["candidate"]))
        assert relations == []

    def test_parse_response_valid_json(self):
        response = json.dumps([{"subject": "A", "relation": "supports", "object": "B"}])
        result = LLMExtractor._parse_response(response)
        assert len(result) == 1
        assert result[0]["subject"] == "A"

    def test_parse_response_json_with_code_block(self):
        response = '```\n[{"subject": "X", "relation": "observes", "object": "Y"}]\n```'
        result = LLMExtractor._parse_response(response)
        assert len(result) == 1
        assert result[0]["subject"] == "X"

    def test_parse_response_invalid_json_returns_empty(self):
        result = LLMExtractor._parse_response("not json at all")
        assert result == []

    def test_parse_response_json_with_bracket_recovery(self):
        response = 'some text [{"subject": "Z", "relation": "suggests", "object": "W"}]'
        result = LLMExtractor._parse_response(response)
        assert len(result) == 1
        assert result[0]["subject"] == "Z"

    def test_parse_response_non_list_returns_empty(self):
        response = json.dumps({"key": "value"})
        result = LLMExtractor._parse_response(response)
        assert result == []

    def test_extract_candidates_truncation(self, mock_client):
        mock_response = json.dumps([{"subject": "A", "relation": "supports", "object": "B1"}])
        mock_client.chat.return_value = mock_response

        extractor = LLMExtractor(client=mock_client)
        many_candidates = [f"candidate_{i}" for i in range(50)]
        import asyncio

        relations = asyncio.run(extractor.extract("test text", many_candidates))
        assert len(relations) >= 1
