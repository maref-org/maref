"""治理度量脚本回归测试.

覆盖 2026-10-20 review 发现的四类缺陷：
1. KPI verdict 词表错配（ok/allow）与 HITL 事件类型丢失
2. hooks 回退路径的 trust 公式与 no_telemetry 三态
3. confidence 聚合的低样本/退化探针剔除与先验回退
4. approval_tier 小样本守卫与时间戳解析
"""

from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import approval_tier  # noqa: E402
import backlog_sla  # noqa: E402
import coding_agent_status  # noqa: E402
import confidence_realtime  # noqa: E402
import probe_sampler  # noqa: E402
import probe_threshold_calibrate  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_hooks_cache():
    coding_agent_status._hooks_cache = None
    yield
    coding_agent_status._hooks_cache = None


def _blank_kpi() -> dict:
    return {
        "tool_calls_total": 0,
        "tool_calls_allowed": 0,
        "tool_calls_intercepted": 0,
        "tool_calls_denied": 0,
        "tool_calls_hitl": 0,
        "interception_rate": 0.0,
        "hitl_rate": 0.0,
        "avg_latency_ms": 0.0,
        "p95_latency_ms": 0.0,
        "total_tokens": 0,
        "total_cost_usd": 0.0,
        "trust_score": 50.0,
        "hitl_events": 0,
        "unique_correlations": 0,
        "kpi_source": "no_telemetry",
    }


# --------------------------------------------------------------------------
# coding_agent_status
# --------------------------------------------------------------------------


def test_hooks_kpi_does_not_double_count_allow_and_executed(monkeypatch):
    monkeypatch.setattr(
        coding_agent_status,
        "_hooks_24h_counts",
        lambda: {"a": {"ALLOW": 100, "EXECUTED": 100, "DENY": 0, "BLOCKED": 0}},
    )
    kpi = coding_agent_status._hooks_runtime_kpi("a", _blank_kpi())
    assert kpi["tool_calls_total"] == 100
    assert kpi["tool_calls_allowed"] == 100
    assert kpi["trust_score"] == 100.0
    assert kpi["kpi_source"] == "hooks_agent_24h"


def test_hooks_kpi_penalises_deny_and_hitl(monkeypatch):
    monkeypatch.setattr(
        coding_agent_status,
        "_hooks_24h_counts",
        lambda: {"a": {"ALLOW": 80, "DENY": 10, "HITL": 10}},
    )
    kpi = coding_agent_status._hooks_runtime_kpi("a", _blank_kpi())
    assert kpi["tool_calls_hitl"] == 10
    assert kpi["tool_calls_total"] == 100
    assert kpi["hitl_rate"] == 10.0
    # denied 10% → 拦截 0.5*10 + 拒绝 1.0*10 + HITL 0.3*10 = 18 分
    assert kpi["trust_score"] == 82.0


def test_hooks_kpi_without_data_stays_no_telemetry(monkeypatch):
    monkeypatch.setattr(coding_agent_status, "_hooks_24h_counts", lambda: {})
    kpi = coding_agent_status._hooks_runtime_kpi("a", _blank_kpi())
    assert kpi["kpi_source"] == "no_telemetry"
    assert kpi["tool_calls_total"] == 0


def test_local_obs_verdict_ok_counts_as_allowed():
    events = [
        {
            "event_type": "tool_call_end",
            "metadata": {"event_type": "tool_call_end", "verdict": "ok", "latency_ms": 12.0},
        },
    ]
    kpi = coding_agent_status._compute_runtime_kpi("a", "", None, events, [])
    assert kpi["tool_calls_allowed"] == 1
    assert kpi["tool_calls_total"] == 1
    assert kpi["kpi_source"] == "sidecar_obs"
    assert kpi["avg_latency_ms"] == 12.0


def test_local_hitl_event_is_counted_and_capped():
    events = [{"event_type": "hitl_triggered", "metadata": {"event_type": "hitl_triggered"}}]
    kpi = coding_agent_status._compute_runtime_kpi("a", "", None, events, [])
    assert kpi["tool_calls_hitl"] == 1
    assert kpi["hitl_rate"] == 100.0
    assert kpi["trust_score"] < 100.0


def test_mcp_decision_metadata_keeps_event_type():
    mcp = [
        {
            "event_type": "governance_decision",
            "metadata": {"event_type": "tool_call_end", "verdict": "deny"},
        },
    ]
    kpi = coding_agent_status._compute_runtime_kpi("a", "", None, [], mcp)
    assert kpi["tool_calls_denied"] == 1


# --------------------------------------------------------------------------
# confidence_realtime
# --------------------------------------------------------------------------


def _probe_db(tmp_path: Path, rows: list[tuple]) -> Path:
    db = tmp_path / "probe.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE probe_readings (id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "probe_name TEXT NOT NULL, severity TEXT NOT NULL, value REAL NOT NULL, "
        "threshold REAL NOT NULL, timestamp REAL NOT NULL, "
        "context_json TEXT NOT NULL DEFAULT '{}')"
    )
    conn.executemany(
        "INSERT INTO probe_readings (probe_name, severity, value, threshold, timestamp, context_json) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    conn.close()
    return db


def _row(probe: str, value: float, day_offset: int, ctx: dict, severity: str = "warning"):
    ts = datetime.now(timezone.utc).timestamp() - day_offset * 86400
    return (probe, severity, value, 0.0, ts, json.dumps({"source": "probe_sampler_v3", **ctx}))


def _write_thresholds(tmp_path: Path) -> Path:
    path = tmp_path / "probe_thresholds.json"
    path.write_text(
        json.dumps({
            "probes": {
                "oscillation": {"normal_max": 10.0, "critical_min": 20.0},
                "entropy": {"normal_max": 3.0, "critical_min": 5.0},
                "governance_health": {"normal_min": 80.0, "critical_min": 50.0},
                "agent_trust": {"normal_min": 70.0, "critical_min": 40.0},
            }
        })
    )
    return path


def test_confidence_excludes_low_sample_days(tmp_path, monkeypatch):
    db = _probe_db(tmp_path, [
        _row("oscillation", 0.0, 1, {"window_used": 3}),   # 低样本 → 剔除
        _row("oscillation", 0.0, 2, {"window_used": 100}),
        _row("oscillation", 0.0, 3, {"window_used": 100}),
    ])
    monkeypatch.setattr(confidence_realtime, "DB_PATH", str(db))
    monkeypatch.setattr(confidence_realtime, "THRESHOLD_PATH", str(_write_thresholds(tmp_path)))
    _score, stats, _calibrated = confidence_realtime.calculate_confidence()
    assert stats["excluded_low_sample"] == 1
    assert stats["total"] == 2


def test_confidence_excludes_constant_probe(tmp_path, monkeypatch):
    rows = [_row("entropy", 57.9, day, {"window_used": 500}) for day in range(1, 7)]
    db = _probe_db(tmp_path, rows)
    monkeypatch.setattr(confidence_realtime, "DB_PATH", str(db))
    monkeypatch.setattr(confidence_realtime, "THRESHOLD_PATH", str(_write_thresholds(tmp_path)))
    score, stats, _calibrated = confidence_realtime.calculate_confidence()
    assert stats["degenerate_probes"] == ["entropy"]
    assert stats["excluded_degenerate"] == 6
    # 唯一的探针被剔除 ⇒ 回退先验，而不是伪装成健康
    assert stats["fallback"] == "prior_no_samples"
    assert score == pytest.approx(68.0)


def test_confidence_flags_threshold_scale_mismatch(tmp_path, monkeypatch):
    rows = []
    for day in range(1, 8):
        rows.append(_row("entropy", 57.9 if day % 2 else 60.0, day, {"window_used": 500}))
        rows.append(_row("oscillation", 1.0, day, {"window_used": 500}))
    db = _probe_db(tmp_path, rows)
    monkeypatch.setattr(confidence_realtime, "DB_PATH", str(db))
    monkeypatch.setattr(confidence_realtime, "THRESHOLD_PATH", str(_write_thresholds(tmp_path)))
    _score, stats, _calibrated = confidence_realtime.calculate_confidence()
    assert "entropy" in stats["suspicious_probes"]
    assert "oscillation" not in stats["suspicious_probes"]


def test_confidence_handles_non_numeric_window_used(tmp_path, monkeypatch):
    db = _probe_db(tmp_path, [
        _row("oscillation", 0.0, 1, {"window_used": "n/a"}),
        _row("oscillation", 0.0, 2, {"window_used": 50}),
    ])
    monkeypatch.setattr(confidence_realtime, "DB_PATH", str(db))
    monkeypatch.setattr(confidence_realtime, "THRESHOLD_PATH", str(_write_thresholds(tmp_path)))
    _score, stats, _calibrated = confidence_realtime.calculate_confidence()
    assert stats["total"] == 2


# --------------------------------------------------------------------------
# approval_tier
# --------------------------------------------------------------------------


def test_timestamp_parses_naive_iso_as_utc(monkeypatch):
    parsed = approval_tier._timestamp_of({"timestamp": "2026-10-20T00:00:00"})
    expected = datetime(2026, 10, 20, tzinfo=timezone.utc).timestamp()
    assert parsed == pytest.approx(expected)


@pytest.mark.parametrize("metadata", ["not-a-dict", None, 42])
def test_entry_helpers_survive_bad_metadata(metadata):
    entry = {"metadata": metadata}
    assert approval_tier._verdict_of(entry) == "unknown"
    assert approval_tier._risk_of(entry) == "unknown"


def test_approval_tier_marks_insufficient_sample(tmp_path, monkeypatch):
    audit = tmp_path / "audit.jsonl"
    recursive = tmp_path / "recursive.jsonl"
    audit.write_text("")
    now = datetime.now(timezone.utc).timestamp()
    recursive.write_text("\n".join(
        json.dumps({"event_type": "governance_decision", "timestamp": now, "verdict": "allow"})
        for _ in range(3)
    ))
    report_file = tmp_path / "approval_tier_report.json"
    monkeypatch.setattr(approval_tier, "AUDIT_LOG", str(audit))
    monkeypatch.setattr(approval_tier, "RECURSIVE_LOG", str(recursive))
    monkeypatch.setattr(approval_tier, "report_path", lambda _name: report_file)
    approval_tier.analyze_tiers()
    report = json.loads(report_file.read_text())
    assert report["t2_1_acceptance"]["sample_adequate"] is False
    assert report["t2_1_acceptance"]["verdict"] == "INSUFFICIENT_DATA"


# --------------------------------------------------------------------------
# backlog_sla
# --------------------------------------------------------------------------


def test_backlog_timestamp_accepts_float_and_iso():
    now = datetime.now(timezone.utc).timestamp()
    assert backlog_sla._parse_timestamp(now) is not None
    assert backlog_sla._parse_timestamp("2026-10-20T00:00:00Z") is not None
    assert backlog_sla._parse_timestamp(None) is None


# --------------------------------------------------------------------------
# probe_threshold_calibrate
# --------------------------------------------------------------------------


def test_calibration_source_filter_excludes_legacy_rows(tmp_path, monkeypatch):
    now = datetime.now(timezone.utc).timestamp()
    db = _probe_db(tmp_path, [
        ("oscillation", "warning", 444.0, 0.0, now, json.dumps({})),
        ("oscillation", "warning", 1.0, 0.0, now - 10, json.dumps({"source": "probe_sampler_v3"})),
        ("oscillation", "warning", 2.0, 0.0, now - 9, json.dumps({"source": "probe_sampler_v3"})),
    ])
    monkeypatch.setattr(probe_threshold_calibrate, "DB_PATH", str(db))
    result = probe_threshold_calibrate.analyze_probe("oscillation", source="probe_sampler_v3")
    assert result["total_readings"] == 2
    assert max(result["value_range"]) < 10


def test_calibration_records_filters_in_config_and_artifact(tmp_path, monkeypatch):
    now = datetime.now(timezone.utc).timestamp()
    rows = [
        ("oscillation", "normal", float(i % 5), 0.0, now - i * 60, json.dumps({"source": "probe_sampler_v3"}))
        for i in range(30)
    ] + [
        ("entropy", "warning", 100.0 + i, 0.0, now - i * 60, json.dumps({"source": "probe_sampler_v3"}))
        for i in range(30)
    ]
    db = _probe_db(tmp_path, rows)
    config_path = tmp_path / "probe_thresholds.json"
    artifact_path = tmp_path / "calibration_artifact.json"
    monkeypatch.setattr(probe_threshold_calibrate, "DB_PATH", str(db))
    monkeypatch.setattr(probe_threshold_calibrate, "CONFIG_PATH", str(config_path))
    monkeypatch.setattr(probe_threshold_calibrate, "ARTIFACT_PATH", str(artifact_path))

    probe_threshold_calibrate.main(["--window-days", "7", "--source", "probe_sampler_v3"])

    config = json.loads(config_path.read_text())
    artifact = json.loads(artifact_path.read_text())
    assert config["filters"] == {"window_days": 7, "source": "probe_sampler_v3"}
    assert artifact["filters"] == config["filters"]
    assert artifact["per_probe"]["oscillation"]["total_readings"] > 0


def test_calibration_verify_detects_manual_edit(tmp_path, monkeypatch):
    config_path = tmp_path / "probe_thresholds.json"
    artifact_path = tmp_path / "calibration_artifact.json"
    config = {"probes": {"oscillation": {"normal_max": 10.0, "critical_min": 20.0}}}
    config_path.write_text(json.dumps(config))
    artifact_path.write_text(json.dumps({
        "config": {"probes": {"oscillation": {"normal_max": 444.0, "critical_min": 569.0}}},
        "config_sha256": "deadbeef",
        "db": {},
    }))
    monkeypatch.setattr(probe_threshold_calibrate, "CONFIG_PATH", str(config_path))
    monkeypatch.setattr(probe_threshold_calibrate, "ARTIFACT_PATH", str(artifact_path))
    assert probe_threshold_calibrate.verify() == 1


def test_calibration_verify_accepts_matching_artifact(tmp_path, monkeypatch):
    config_path = tmp_path / "probe_thresholds.json"
    artifact_path = tmp_path / "calibration_artifact.json"
    config = {"probes": {"oscillation": {"normal_max": 10.0, "critical_min": 20.0}}}
    config_path.write_text(json.dumps(config))
    artifact_path.write_text(json.dumps({"config": config, "config_sha256": "", "db": {}}))
    monkeypatch.setattr(probe_threshold_calibrate, "CONFIG_PATH", str(config_path))
    monkeypatch.setattr(probe_threshold_calibrate, "ARTIFACT_PATH", str(artifact_path))
    assert probe_threshold_calibrate.verify() == 0


def test_probe_sampler_window_filters_stale_events(tmp_path):
    import time

    log = tmp_path / "audit.jsonl"
    now = time.time()
    rows = [
        {"event_type": "tool_call_blocked", "timestamp": now - 60, "agent_id": "a"},
        {"event_type": "tool_call_blocked", "timestamp": now - 9 * 86400, "agent_id": "a"},
        {"event_type": "tool_call_blocked", "timestamp": "2020-01-01T00:00:00Z", "agent_id": "a"},
    ]
    log.write_text("\n".join(json.dumps(r) for r in rows) + "\n")

    all_rows = probe_sampler._load_entries(str(log))
    recent = probe_sampler._load_entries(str(log), since_ts=now - 86400)

    assert len(all_rows) == 3
    assert len(recent) == 1
    assert probe_sampler._to_ts("2020-01-01T00:00:00Z") > 1_500_000_000
    assert probe_sampler._to_ts("not-a-time") == 0.0


def test_calibration_refuses_degenerate_percentiles(tmp_path, monkeypatch):
    now = datetime.now(timezone.utc).timestamp()
    rows = [
        ("oscillation", "normal", 0.0, 0.0, now - i * 60, json.dumps({"source": "probe_sampler_v3"}))
        for i in range(30)
    ] + [
        ("entropy", "critical", 57.9, 0.0, now - i * 60, json.dumps({"source": "probe_sampler_v3"}))
        for i in range(30)
    ]
    db = _probe_db(tmp_path, rows)
    config_path = tmp_path / "probe_thresholds.json"
    artifact_path = tmp_path / "calibration_artifact.json"
    original = {"probes": {"oscillation": {"normal_max": 10.1, "critical_min": 11.11}}}
    config_path.write_text(json.dumps(original))
    monkeypatch.setattr(probe_threshold_calibrate, "DB_PATH", str(db))
    monkeypatch.setattr(probe_threshold_calibrate, "CONFIG_PATH", str(config_path))
    monkeypatch.setattr(probe_threshold_calibrate, "ARTIFACT_PATH", str(artifact_path))

    assert probe_threshold_calibrate.main(["--window-days", "30", "--source", "probe_sampler_v3"]) == 0
    assert json.loads(config_path.read_text()) == original
    assert not artifact_path.exists()


def test_calibration_accept_seed_writes_verifiable_artifact(tmp_path, monkeypatch):
    config_path = tmp_path / "probe_thresholds.json"
    artifact_path = tmp_path / "calibration_artifact.json"
    config = {"probes": {"oscillation": {"normal_max": 10.1, "critical_min": 11.11}}}
    config_path.write_text(json.dumps(config))
    monkeypatch.setattr(probe_threshold_calibrate, "DB_PATH", str(tmp_path / "x.db"))
    monkeypatch.setattr(probe_threshold_calibrate, "CONFIG_PATH", str(config_path))
    monkeypatch.setattr(probe_threshold_calibrate, "ARTIFACT_PATH", str(artifact_path))

    assert probe_threshold_calibrate.main(["--accept-seed", "--reason", "退化"]) == 0
    artifact = json.loads(artifact_path.read_text())
    assert artifact["provenance"] == "seed_uncalibrated"
    assert artifact["reason"] == "退化"
    assert probe_threshold_calibrate.verify() == 0
