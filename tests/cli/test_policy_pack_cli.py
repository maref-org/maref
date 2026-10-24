from typer.testing import CliRunner

from maref_lite.cli import app

runner = CliRunner()


def test_validate_valid_pack(tmp_path):
    path = tmp_path / "eu.yaml"
    path.write_text(
        """
pack_format: 1
pack_id: eu-ai-act
name: EU AI Act
version: "1.0.0"
jurisdiction: eu
rules:
  - rule_id: eu-payment-deny
    action: "payment.*"
    decision: deny
    regulation_ref: "EU AI Act Art. 6"
""",
        encoding="utf-8",
    )
    result = runner.invoke(app, ["policy-pack", "validate", str(path)])
    assert result.exit_code == 0
    assert "eu-ai-act" in result.stdout


def test_validate_invalid_pack(tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text("pack_id: bad\n", encoding="utf-8")
    result = runner.invoke(app, ["policy-pack", "validate", str(path)])
    assert result.exit_code != 0
