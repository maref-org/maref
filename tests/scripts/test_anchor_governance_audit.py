"""审计链外部锚定脚本回归测试.

回归点: 发布前置检查必须 fail-closed。AuditAnchor 运行时 fail-open
（TSA 失败仍写锚点），脚本必须截断无令牌尾巴并在重验时拒绝放行，
否则一次 TSA 抖动会让该批次永久失去时间证明。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import anchor_governance_audit as audit  # noqa: E402
import rfc3161_stamp as stamp  # noqa: E402

from maref.governance.audit import AuditLogger  # noqa: E402
from maref.governance.audit_anchor import AnchorRecord  # noqa: E402


def _anchor_line(root: str, token: str) -> str:
    record = AnchorRecord(
        batch_start_id="a",
        batch_end_id="b",
        merkle_root=root,
        event_count=1,
        tsa_token=token,
        anchored_at=1.0,
    )
    return json.dumps(record.to_dict(), sort_keys=True)


def _fill_audit(tmp_path: Path, count: int = 3) -> Path:
    logger = AuditLogger(log_path=tmp_path / "audit.jsonl", hmac_key="test-key")
    for index in range(count):
        logger.log(
            event_type="governance_decision",
            actor="test-suite",
            action=f"decision-{index}",
            details=f"ALLOW: step {index}",
            metadata={"step": index},
        )
    return tmp_path / "audit.jsonl"


class TestTrim:
    def test_trims_from_first_untokened_anchor(self, tmp_path):
        path = tmp_path / "anchors.jsonl"
        path.write_text(
            "\n".join(
                [
                    _anchor_line("a" * 64, "token-1"),
                    _anchor_line("b" * 64, ""),
                    _anchor_line("c" * 64, "token-3"),
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        removed = audit._trim_incomplete_anchors(path)

        assert removed == 2
        remaining = [line for line in path.read_text(encoding="utf-8").splitlines() if line]
        assert len(remaining) == 1
        assert json.loads(remaining[0])["merkle_root"] == "a" * 64

    def test_complete_file_untouched(self, tmp_path):
        path = tmp_path / "anchors.jsonl"
        original = _anchor_line("a" * 64, "token") + "\n"
        path.write_text(original, encoding="utf-8")

        assert audit._trim_incomplete_anchors(path) == 0
        assert path.read_text(encoding="utf-8") == original

    def test_missing_file_is_noop(self, tmp_path):
        assert audit._trim_incomplete_anchors(tmp_path / "missing.jsonl") == 0


class TestVerifyTokens:
    def test_missing_token_reported(self, tmp_path):
        anchors = [
            AnchorRecord("a", "b", "1" * 64, 1, tsa_token="", anchored_at=1.0),
        ]

        problems = audit._verify_all_tokens(anchors, tmp_path, tmp_path / "ca.pem")

        assert any("no timestamp token" in problem for problem in problems)

    def test_missing_token_file_reported(self, tmp_path):
        anchors = [
            AnchorRecord("a", "b", "2" * 64, 1, tsa_token="dG9rZW4=", anchored_at=1.0),
        ]

        problems = audit._verify_all_tokens(anchors, tmp_path, tmp_path / "ca.pem")

        assert any("missing request/token file" in problem for problem in problems)


class TestFailClosed:
    def test_main_returns_nonzero_when_tsa_fails(self, tmp_path, monkeypatch):
        audit_path = _fill_audit(tmp_path, count=2)
        monkeypatch.setattr(stamp, "fetch_ca", lambda *a, **k: tmp_path / "ca.pem")

        def failing_stamp(*args, **kwargs):
            raise stamp.TimestampError("tsa offline")

        monkeypatch.setattr(audit, "_stamp_root", failing_stamp)

        code = audit.main(
            [
                "--audit",
                str(audit_path),
                "--out-dir",
                str(tmp_path / "out"),
                "--batch-size",
                "10",
            ]
        )

        assert code == 1
