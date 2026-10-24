"""audit_health_check 时间戳解析与链路探针回归测试。"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import audit_health_check as health


def test_parse_timestamp_iso_z():
    parsed = health._parse_timestamp("2026-10-19T18:26:25Z")
    assert parsed == datetime(2026, 10, 19, 18, 26, 25, tzinfo=timezone.utc)


def test_parse_timestamp_iso_offset_and_naive():
    offset = health._parse_timestamp("2026-10-20T02:26:25+08:00")
    naive = health._parse_timestamp("2026-10-19T18:26:25")
    assert offset == datetime(2026, 10, 19, 18, 26, 25, tzinfo=timezone.utc)
    assert naive == datetime(2026, 10, 19, 18, 26, 25, tzinfo=timezone.utc)


def test_parse_timestamp_epoch_formats():
    expected = datetime(2026, 10, 19, 18, 26, 25, tzinfo=timezone.utc)
    assert health._parse_timestamp(expected.timestamp()) == expected
    assert health._parse_timestamp(str(expected.timestamp())) == expected
    assert health._parse_timestamp(int(expected.timestamp() * 1000)) == expected


def test_parse_timestamp_invalid_returns_none():
    assert health._parse_timestamp(None) is None
    assert health._parse_timestamp(True) is None
    assert health._parse_timestamp("not-a-timestamp") is None
    assert health._parse_timestamp(float("nan")) is None


def _write_chain(path: Path, entry: dict) -> Path:
    path.write_text(json.dumps(entry) + "\n", encoding="utf-8")
    return path


def test_probe_chain_accepts_iso_z(tmp_path):
    now = datetime.now(timezone.utc)
    path = _write_chain(
        tmp_path / "audit.jsonl",
        {
            "timestamp": now.isoformat().replace("+00:00", "Z"),
            "actor": "opencode",
            "action": "test",
            "metadata": {"source": "heartbeat"},
        },
    )

    probed = health._probe_chain(path)

    assert probed is not None
    assert probed["status"] == "FRESH"
    assert probed["traffic"] == "heartbeat_only"
    assert probed["last_entry_ts"] is not None


def test_probe_chain_invalid_timestamp_does_not_raise(tmp_path):
    path = _write_chain(
        tmp_path / "audit.jsonl",
        {"timestamp": "2026-10-19T18:26:25Z", "action": "broken"},
    )
    path.write_text(
        path.read_text(encoding="utf-8").replace("2026-10-19T18:26:25Z", "bad-ts"),
        encoding="utf-8",
    )

    probed = health._probe_chain(path)

    assert probed is not None
    assert probed["status"] == "STALE"
    assert probed["last_entry_ts"] is None


def test_classify_traffic_uses_iso_timestamps(tmp_path):
    now = datetime.now(timezone.utc)
    lines = [
        json.dumps(
            {
                "timestamp": (now - timedelta(minutes=i)).isoformat().replace("+00:00", "Z"),
                "action": "HEARTBEAT",
            }
        )
        for i in range(3)
    ]
    path = tmp_path / "audit.jsonl"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    assert health._classify_traffic(path, 0.0) == "heartbeat_only"
