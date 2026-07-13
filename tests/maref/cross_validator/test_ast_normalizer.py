from __future__ import annotations

from maref.cross_validator.ast_normalizer import (
    ASTNormalizer,
    SemanticEquivalenceChecker,
    SemanticFingerprint,
)


class TestSemanticFingerprint:
    def test_defaults(self) -> None:
        fp = SemanticFingerprint(
            hash="abc123",
            ast_structure="Module",
            token_sequence=["a", "b"],
        )
        assert fp.hash == "abc123"
        assert fp.ast_structure == "Module"
        assert fp.token_sequence == ["a", "b"]
        assert fp.metadata == {}

    def test_to_dict(self) -> None:
        fp = SemanticFingerprint(
            hash="abc", ast_structure="Expr", token_sequence=["x"],
            metadata={"version": 1},
        )
        d = fp.to_dict()
        assert d["hash"] == "abc"
        assert d["metadata"]["version"] == 1


class TestASTNormalizer:
    def test_init(self) -> None:
        normalizer = ASTNormalizer()
        assert normalizer is not None

    def test_normalize_simple_expr(self) -> None:
        normalizer = ASTNormalizer()
        result = normalizer.normalize("x = 1")
        assert result is not None

    def test_normalize_function(self) -> None:
        normalizer = ASTNormalizer()
        result = normalizer.normalize("def foo(a, b): return a + b")
        assert result is not None

    def test_normalize_empty(self) -> None:
        normalizer = ASTNormalizer()
        result = normalizer.normalize("")
        assert result is not None

    def test_generate_fingerprint(self) -> None:
        normalizer = ASTNormalizer()
        fp = normalizer.generate_fingerprint("x = 1 + 2")
        assert isinstance(fp, SemanticFingerprint)
        assert fp.hash

    def test_generate_fingerprint_empty(self) -> None:
        normalizer = ASTNormalizer()
        fp = normalizer.generate_fingerprint("")
        assert isinstance(fp, SemanticFingerprint)

    def test_equivalence_detection(self) -> None:
        normalizer = ASTNormalizer()
        fp1 = normalizer.generate_fingerprint("x = x + 1")
        fp2 = normalizer.generate_fingerprint("a = a + 1")
        # variable names differ but structure same — likely same fingerprint
        assert fp1.hash == fp2.hash


class TestSemanticEquivalenceChecker:
    def test_equivalent_code(self) -> None:
        checker = SemanticEquivalenceChecker()
        result = checker.check_equivalence("x = 1", "y = 1")
        assert result["equivalent"] is True

    def test_different_code(self) -> None:
        checker = SemanticEquivalenceChecker()
        result = checker.check_equivalence("x = 1", "print('hello')")
        assert result["equivalent"] is False

    def test_similarity_score(self) -> None:
        checker = SemanticEquivalenceChecker()
        result = checker.check_equivalence("a + b", "a + b")
        assert 0.0 <= result["similarity"] <= 1.0
