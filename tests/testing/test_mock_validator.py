from __future__ import annotations

import json
from pathlib import Path

from maref.testing.mock_validator import MockValidator


class TestMockValidator:
    def test_mock_validator_detects_extra_keys(self, tmp_path: Path) -> None:
        schema_dir = tmp_path / "schemas"
        mock_dir = tmp_path / "mocks"
        schema_dir.mkdir()
        mock_dir.mkdir()

        schema = {"name": "Alice", "age": 30}
        mock = {"name": "Alice", "age": 30, "extra_key": "boom"}
        (schema_dir / "user_schema.json").write_text(json.dumps(schema))
        (mock_dir / "user_mock.json").write_text(json.dumps(mock))

        validator = MockValidator(schema_dir, mock_dir)
        errors = validator.validate_all()
        assert len(errors) == 1
        assert "extra_key" in errors[0]

    def test_mock_validator_detects_missing_keys(self, tmp_path: Path) -> None:
        schema_dir = tmp_path / "schemas"
        mock_dir = tmp_path / "mocks"
        schema_dir.mkdir()
        mock_dir.mkdir()

        schema = {"name": "Alice", "age": 30}
        mock = {"name": "Alice"}
        (schema_dir / "user_schema.json").write_text(json.dumps(schema))
        (mock_dir / "user_mock.json").write_text(json.dumps(mock))

        validator = MockValidator(schema_dir, mock_dir)
        errors = validator.validate_all()
        assert len(errors) == 1
        assert "age" in errors[0]

    def test_mock_validator_passes_when_matching(self, tmp_path: Path) -> None:
        schema_dir = tmp_path / "schemas"
        mock_dir = tmp_path / "mocks"
        schema_dir.mkdir()
        mock_dir.mkdir()

        schema = {"name": "Alice", "age": 30}
        mock = {"name": "Alice", "age": 30}
        (schema_dir / "user_schema.json").write_text(json.dumps(schema))
        (mock_dir / "user_mock.json").write_text(json.dumps(mock))

        validator = MockValidator(schema_dir, mock_dir)
        errors = validator.validate_all()
        assert errors == []
