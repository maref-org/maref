from __future__ import annotations

import json
import os
import tempfile

import pytest

from maref.immunity.negative_gene_bank import NegativeGeneBank
from maref.immunity.seed_updater import (
    CWEImportError,
    export_genes_to_json,
    seed_from_cwe_json,
)

SAMPLE_CWE_GENES = [
    {
        "cwe_id": "CWE-79",
        "title": "Improper Neutralization of Input During Web Page Generation",
        "description": "Cross-site Scripting (XSS) - failure to sanitize user input in web output",
        "risk_level": "HIGH",
        "severity": 9,
        "blocked": True,
        "patterns": [
            {"type": "regex", "value": r"<script>.*?</script>", "score": 0.9},
            {"type": "regex", "value": r"innerHTML\s*=", "score": 0.8},
        ],
        "variants": [
            {"language": "javascript", "code": "element.innerHTML = userInput;"},
            {"language": "python", "code": "return f'<div>{name}</div>'"},
        ],
    },
    {
        "cwe_id": "CWE-89",
        "title": "Improper Neutralization of Special Elements in SQL",
        "description": "SQL Injection - failure to parameterize SQL queries",
        "risk_level": "CRITICAL",
        "severity": 10,
        "blocked": True,
        "patterns": [
            {"type": "regex", "value": r"SELECT.*FROM.*WHERE.*\+", "score": 1.0},
            {"type": "regex", "value": r"execute\(.*['\"]", "score": 1.0},
        ],
        "variants": [
            {
                "language": "python",
                "code": 'cursor.execute("SELECT * FROM users WHERE id = " + uid)',
            },
        ],
    },
    {
        "cwe_id": "CWE-22",
        "title": "Improper Limitation of a Pathname to a Restricted Directory",
        "description": "Path Traversal - failure to sanitize file path inputs",
        "risk_level": "HIGH",
        "severity": 8,
        "blocked": True,
        "patterns": [
            {"type": "regex", "value": r"open\(.*\.\.\./", "score": 0.9},
        ],
        "variants": [],
    },
]

SAMPLE_ENTRY_NO_CWE = {
    "title": "Missing CWE ID",
    "description": "This entry has no cwe_id and should be skipped",
    "risk_level": "HIGH",
    "severity": 5,
    "blocked": True,
    "patterns": [],
    "variants": [],
}


class TestSeedFromCWESjon:
    """6.2-A1: Bulk import from CWE JSON files."""

    @pytest.fixture
    def json_file(self) -> str:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"genes": SAMPLE_CWE_GENES}, f)
            path = f.name
        yield path
        os.unlink(path)

    @pytest.fixture
    def json_file_list(self) -> str:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(SAMPLE_CWE_GENES, f)
            path = f.name
        yield path
        os.unlink(path)

    @pytest.fixture
    def json_file_cwe_entries(self) -> str:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"cwe_entries": SAMPLE_CWE_GENES}, f)
            path = f.name
        yield path
        os.unlink(path)

    def test_import_from_genes_key(self, json_file):
        bank = NegativeGeneBank(":memory:")
        result = seed_from_cwe_json(bank, json_file)
        assert result["imported"] == 3
        assert result["updated"] == 0
        assert result["skipped"] == 0
        assert result["total_genes"] >= 3

    def test_import_from_list(self, json_file_list):
        bank = NegativeGeneBank(":memory:")
        result = seed_from_cwe_json(bank, json_file_list)
        assert result["imported"] == 3

    def test_import_from_cwe_entries_key(self, json_file_cwe_entries):
        bank = NegativeGeneBank(":memory:")
        result = seed_from_cwe_json(bank, json_file_cwe_entries)
        assert result["imported"] == 3

    def test_import_skips_entries_without_cwe_id(self):
        bank = NegativeGeneBank(":memory:")
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"genes": SAMPLE_CWE_GENES + [SAMPLE_ENTRY_NO_CWE]}, f)
            path = f.name
        try:
            result = seed_from_cwe_json(bank, path)
            assert result["imported"] == 3
            assert result["skipped"] == 1
        finally:
            os.unlink(path)

    def test_imported_genes_persist_in_bank(self, json_file):
        bank = NegativeGeneBank(":memory:")
        seed_from_cwe_json(bank, json_file)
        cwe79 = bank.query_by_cwe("CWE-79")
        assert len(cwe79) == 1
        assert cwe79[0].title == "Improper Neutralization of Input During Web Page Generation"
        assert cwe79[0].risk_level == "HIGH"
        assert cwe79[0].severity == 9
        assert cwe79[0].blocked is True

    def test_imported_genes_have_patterns_and_variants(self, json_file):
        bank = NegativeGeneBank(":memory:")
        seed_from_cwe_json(bank, json_file)
        cwe79 = bank.query_by_cwe("CWE-79")[0]
        assert len(cwe79.patterns) == 2
        assert cwe79.patterns[0].pattern_type == "regex"
        assert len(cwe79.variants) == 2

        cwe89 = bank.query_by_cwe("CWE-89")[0]
        assert len(cwe89.patterns) == 2
        assert len(cwe89.variants) == 1

        cwe22 = bank.query_by_cwe("CWE-22")[0]
        assert len(cwe22.patterns) == 1
        assert len(cwe22.variants) == 0

    def test_import_records_source_in_gene_sources(self, json_file):
        bank = NegativeGeneBank(":memory:")
        result = seed_from_cwe_json(
            bank, json_file, source_name="maraf_cwe", source_url="https://example.com/cwe.json"
        )
        history = bank.get_import_history()
        assert len(history) == 1
        assert history[0]["source_name"] == "maraf_cwe"
        assert history[0]["source_url"] == "https://example.com/cwe.json"
        assert history[0]["gene_count"] >= 3
        assert result["source_id"] == history[0]["source_id"]

    def test_import_merge_updates_existing_genes(self, json_file):
        bank = NegativeGeneBank(":memory:")
        result1 = seed_from_cwe_json(bank, json_file)
        assert result1["imported"] == 3

        result2 = seed_from_cwe_json(bank, json_file, merge=True, source_name="custom")
        assert result2["imported"] == 0
        assert result2["skipped"] == 0
        assert result2["updated"] >= 3

    def test_import_duplicate_without_merge_skips(self, json_file):
        bank = NegativeGeneBank(":memory:")
        result1 = seed_from_cwe_json(bank, json_file)
        assert result1["imported"] == 3
        result2 = seed_from_cwe_json(bank, json_file, merge=False)
        assert result2["imported"] == 0
        assert result2["skipped"] == 3

    def test_unsupported_source_raises_error(self, json_file):
        bank = NegativeGeneBank(":memory:")
        with pytest.raises(CWEImportError, match="Unknown source"):
            seed_from_cwe_json(bank, json_file, source_name="unknown_source")

    def test_invalid_json_structure_raises_error(self):
        bank = NegativeGeneBank(":memory:")
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"invalid": "structure"}, f)
            path = f.name
        try:
            with pytest.raises(CWEImportError, match="Unknown JSON structure"):
                seed_from_cwe_json(bank, path)
        finally:
            os.unlink(path)


class TestImportHistory:
    """6.2-A2: Retain history of gene imports (versioning)."""

    def test_multiple_imports_recorded_in_order(self):
        bank = NegativeGeneBank(":memory:")
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"genes": [SAMPLE_CWE_GENES[0]]}, f)
            p1 = f.name
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"genes": [SAMPLE_CWE_GENES[1]]}, f)
            p2 = f.name
        try:
            seed_from_cwe_json(bank, p1, source_name="veracode", source_url="v1")
            seed_from_cwe_json(bank, p2, source_name="owasp", source_url="v2")
            history = bank.get_import_history()
            assert len(history) == 2
            assert history[0]["source_name"] == "owasp"
            assert history[1]["source_name"] == "veracode"
        finally:
            os.unlink(p1)
            os.unlink(p2)

    def test_hmac_integrity_preserved_after_import(self):
        bank = NegativeGeneBank(":memory:")
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"genes": SAMPLE_CWE_GENES}, f)
            path = f.name
        try:
            seed_from_cwe_json(bank, path)
            ok, tampered = bank.verify_integrity()
            assert ok, f"Tampered genes: {tampered}"
        finally:
            os.unlink(path)


class TestExportGenesToJSON:
    """Round-trip: export then re-import."""

    def test_export_and_reimport_roundtrip(self):
        bank = NegativeGeneBank(":memory:")
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"genes": SAMPLE_CWE_GENES}, f)
            source_path = f.name
        export_path = tempfile.mktemp(suffix=".json")
        try:
            seed_from_cwe_json(bank, source_path)
            count = export_genes_to_json(bank, export_path)
            assert count == 3

            bank2 = NegativeGeneBank(":memory:")
            result = seed_from_cwe_json(bank2, export_path, source_name="custom")
            assert result["imported"] == 3
        finally:
            os.unlink(source_path)
            os.unlink(export_path)

    def test_export_with_cwe_filter(self):
        bank = NegativeGeneBank(":memory:")
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"genes": SAMPLE_CWE_GENES}, f)
            path = f.name
        export_path = tempfile.mktemp(suffix=".json")
        try:
            seed_from_cwe_json(bank, path)
            count = export_genes_to_json(bank, export_path, cwe_filter="CWE-79")
            assert count == 1
        finally:
            os.unlink(path)
            os.unlink(export_path)
