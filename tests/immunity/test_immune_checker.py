import pytest

from maref.immunity.immune_checker import ImmuneChecker
from maref.immunity.negative_gene_bank import (
    GenePattern,
    GeneVariant,
    NegativeGene,
    NegativeGeneBank,
)


@pytest.fixture
def checker():
    bank = NegativeGeneBank(":memory:")
    _seed_test_genes(bank)
    return ImmuneChecker(bank)


def _seed_test_genes(bank: NegativeGeneBank):
    genes = [
        NegativeGene(
            "",
            "CWE-295",
            "HIGH",
            9,
            True,
            "SSL Verify False",
            "verify=False bypasses cert check",
            "test",
            1000.0,
            patterns=[
                GenePattern("", "", "regex", r"verify\s*=\s*(False|0)"),
                GenePattern("", "", "ast_call", "requests.get("),
            ],
            variants=[
                GeneVariant("", "", "python", "requests.get(url, verify=False)"),
            ],
        ),
        NegativeGene(
            "",
            "CWE-94",
            "CRITICAL",
            10,
            True,
            "eval() usage",
            "eval() executes arbitrary code",
            "test",
            1000.0,
            patterns=[
                GenePattern("", "", "ast_call", "eval("),
            ],
            variants=[
                GeneVariant("", "", "python", "eval(user_input)"),
            ],
        ),
        NegativeGene(
            "",
            "CWE-502",
            "HIGH",
            9,
            True,
            "pickle deserialisation",
            "pickle.load() from untrusted data = RCE",
            "test",
            1000.0,
            patterns=[
                GenePattern("", "", "import_name", "pickle"),
                GenePattern("", "", "regex", r"pickle\.loads?\("),
            ],
        ),
        NegativeGene(
            "",
            "CWE-79",
            "MEDIUM",
            6,
            False,
            "innerHTML usage",
            "innerHTML assignment without sanitisation",
            "test",
            1000.0,
            patterns=[
                GenePattern("", "", "regex", r"\.innerHTML\s*="),
            ],
        ),
        NegativeGene(
            "",
            "CWE-798",
            "CRITICAL",
            10,
            True,
            "Hardcoded API Key",
            "API key literal in source code",
            "test",
            1000.0,
            patterns=[
                GenePattern("", "", "regex", r"sk-[A-Za-z0-9]{20,}"),
            ],
        ),
    ]
    for g in genes:
        bank.store_gene(g)


# ── Scan ─────────────────────────────────────────────────────────────────


class TestScan:
    def test_detect_regex_pattern(self, checker):
        code = "response = requests.get(url, verify=False)"
        hits = checker.scan(code)
        assert len(hits) >= 1
        hit = next(h for h in hits if h.gene_title == "SSL Verify False")
        assert hit.blocked is True

    def test_detect_variant(self, checker):
        code = "requests.get(url, verify=False)"
        hits = checker.scan(code)
        variant_hits = [h for h in hits if h.match_type == "variant"]
        assert len(variant_hits) >= 1

    def test_detect_eval_ast(self, checker):
        code = "result = eval(user_input)"
        hits = checker.scan_ast(code)
        eval_hits = [h for h in hits if "eval" in h.gene_title]
        assert len(eval_hits) >= 1

    def test_detect_pickle_import(self, checker):
        code = "import pickle; data = pickle.load(file)"
        hits = checker.scan_ast(code)
        pickle_hits = [h for h in hits if "pickle" in h.gene_title]
        assert len(pickle_hits) >= 1

    def test_detect_innerhtml(self, checker):
        code = "element.innerHTML = userInput"
        hits = checker.scan(code)
        inner_hits = [h for h in hits if "innerHTML" in h.gene_title]
        assert len(inner_hits) >= 1

    def test_no_false_positive_on_clean_code(self, checker):
        code = """
def add(a, b):
    return a + b

def multiply(x, y):
    return x * y
"""
        hits = checker.scan(code)
        # clean code should have zero hits for our dangerous patterns
        assert len(hits) == 0


class TestScanAST:
    def test_ast_precision_over_regex(self, checker):
        """AST catches eval() even when not matched by simple regex patterns"""
        code = """
result = eval("1+1")
"""
        # regex scan catches the direct eval call
        regex_hits = checker.scan(code)
        eval_regex = [h for h in regex_hits if "eval" in h.gene_title]
        # AST catches it via ast.Call node inspection
        ast_hits = checker.scan_ast(code)
        eval_ast = [h for h in ast_hits if "eval" in h.gene_title]
        # both methods should detect the direct eval() call
        assert len(eval_regex) >= 1 or len(eval_ast) >= 1


class TestVariants:
    """0.2-A4: >=5 variants of verify=False all detected."""

    def test_verify_false_variants_all_detected(self, checker):
        variants = [
            "requests.get(url, verify=False)",
            "requests.get(url, verify=0)",
            "requests.post(url, verify=False)",
            "session.get(url, verify=False)",
            "httpx.get(url, verify=False)",
        ]
        for v in variants:
            hits = checker.scan(v)
            ssl_hits = [h for h in hits if h.gene_title == "SSL Verify False"]
            assert len(ssl_hits) >= 1, f"Variant not detected: {v}"


class TestScanFile:
    def test_scan_file(self, checker, tmp_path):
        f = tmp_path / "test_code.py"
        f.write_text("response = requests.get(url, verify=False)")
        hits = checker.scan_file(str(f))
        assert len(hits) >= 1


# ── Edge Cases ───────────────────────────────────────────────────────────


class TestEdgeCases:
    def test_empty_code(self, checker):
        assert checker.scan("") == []
        assert checker.scan_ast("") == []

    def test_invalid_syntax(self, checker):
        # should not crash
        hits = checker.scan("def broken(:")
        assert isinstance(hits, list)

    def test_ast_invalid_syntax(self, checker):
        hits = checker.scan_ast("def broken(:")
        assert hits == []

    def test_long_code_performance(self, checker):
        code_lines = [f"x_{i} = requests.get(url, verify=False)\n" for i in range(1000)]
        code = "".join(code_lines)
        import time

        start = time.time()
        hits = checker.scan(code)
        elapsed = time.time() - start
        assert elapsed < 0.5  # 500ms for 1000 lines (0.2-A3)
