"""Tests for EU AI Act record-keeping module (Art.12)."""

from __future__ import annotations

import json

from maref.compliance.eu_ai_act_v2.record_keeping import (
    AIActLogEntry,
    AIActLogger,
    RegulatoryLogExporter,
    RetentionPolicy,
)


class TestAIActLogEntry:
    def test_construct_with_all_fields(self) -> None:
        entry = AIActLogEntry(
            entry_id="abc123",
            system_id="sys-01",
            system_version="2.0.0",
            session_id="sess-001",
            event_timestamp_utc="2026-07-11T12:00:00Z",
            use_period_start="2026-07-11T00:00:00Z",
            use_period_end="2026-07-11T23:59:59Z",
            input_data_hash="abcdef",
            input_data_fields=["query", "response"],
            reference_database="db-main",
            reference_version="v3",
            decision_type="classification",
            decision_rationale="threshold met",
            confidence_score=0.95,
            human_oversight_person_id="user-42",
            human_oversight_action="reviewed",
            automated_only_exemption=None,
            risk_event=True,
            anomaly_flag=False,
            error_type=None,
            failsafe_triggered=False,
        )
        assert entry.entry_id == "abc123"
        assert entry.system_id == "sys-01"
        assert entry.system_version == "2.0.0"
        assert entry.session_id == "sess-001"
        assert entry.event_timestamp_utc == "2026-07-11T12:00:00Z"
        assert entry.use_period_start == "2026-07-11T00:00:00Z"
        assert entry.use_period_end == "2026-07-11T23:59:59Z"
        assert entry.input_data_hash == "abcdef"
        assert entry.input_data_fields == ["query", "response"]
        assert entry.reference_database == "db-main"
        assert entry.reference_version == "v3"
        assert entry.decision_type == "classification"
        assert entry.decision_rationale == "threshold met"
        assert entry.confidence_score == 0.95
        assert entry.human_oversight_person_id == "user-42"
        assert entry.human_oversight_action == "reviewed"
        assert entry.automated_only_exemption is None
        assert entry.risk_event is True
        assert entry.anomaly_flag is False
        assert entry.error_type is None
        assert entry.failsafe_triggered is False

    def test_default_values(self) -> None:
        entry = AIActLogEntry(
            entry_id="default",
            system_id="sys-01",
            system_version="1.0.0",
            session_id="sess-001",
            event_timestamp_utc="2026-01-01T00:00:00Z",
            use_period_start="2026-01-01T00:00:00Z",
            use_period_end="2026-01-01T01:00:00Z",
            input_data_hash="",
        )
        assert entry.input_data_fields == []
        assert entry.reference_database == ""
        assert entry.reference_version == ""
        assert entry.decision_type == ""
        assert entry.decision_rationale == ""
        assert entry.confidence_score is None
        assert entry.human_oversight_person_id is None
        assert entry.human_oversight_action is None
        assert entry.automated_only_exemption is None
        assert entry.risk_event is False
        assert entry.anomaly_flag is False
        assert entry.error_type is None
        assert entry.failsafe_triggered is False

    def test_risk_event_and_anomaly_independent(self) -> None:
        risk = AIActLogEntry(
            entry_id="r1", system_id="s1", system_version="1.0",
            session_id="se1", event_timestamp_utc="t", use_period_start="t",
            use_period_end="t", input_data_hash="h", risk_event=True,
        )
        anomaly = AIActLogEntry(
            entry_id="r2", system_id="s1", system_version="1.0",
            session_id="se1", event_timestamp_utc="t", use_period_start="t",
            use_period_end="t", input_data_hash="h", anomaly_flag=True,
        )
        both = AIActLogEntry(
            entry_id="r3", system_id="s1", system_version="1.0",
            session_id="se1", event_timestamp_utc="t", use_period_start="t",
            use_period_end="t", input_data_hash="h",
            risk_event=True, anomaly_flag=True,
        )
        assert risk.risk_event and not risk.anomaly_flag
        assert anomaly.anomaly_flag and not anomaly.risk_event
        assert both.risk_event and both.anomaly_flag

    def test_human_oversight_action_values(self) -> None:
        for action in ("reviewed", "overrode", "escalated", "none", None):
            entry = AIActLogEntry(
                entry_id="h1", system_id="s1", system_version="1.0",
                session_id="se1", event_timestamp_utc="t", use_period_start="t",
                use_period_end="t", input_data_hash="h",
                human_oversight_action=action,
            )
            assert entry.human_oversight_action == action

    def test_confidence_score_none_by_default(self) -> None:
        entry = AIActLogEntry(
            entry_id="c1", system_id="s1", system_version="1.0",
            session_id="se1", event_timestamp_utc="t", use_period_start="t",
            use_period_end="t", input_data_hash="h",
        )
        assert entry.confidence_score is None

    def test_confidence_score_various_values(self) -> None:
        for val in (0.0, 0.5, 1.0, 0.999):
            entry = AIActLogEntry(
                entry_id="cv1", system_id="s1", system_version="1.0",
                session_id="se1", event_timestamp_utc="t", use_period_start="t",
                use_period_end="t", input_data_hash="h",
                confidence_score=val,
            )
            assert entry.confidence_score == val


class TestRetentionPolicy:
    def test_default_duration(self) -> None:
        policy = RetentionPolicy()
        assert policy.duration_days == 183

    def test_default_public_authority(self) -> None:
        policy = RetentionPolicy()
        assert not policy.apply_to_public_authority

    def test_custom_duration(self) -> None:
        policy = RetentionPolicy(duration_days=365)
        assert policy.duration_days == 365

    def test_custom_public_authority(self) -> None:
        policy = RetentionPolicy(apply_to_public_authority=True)
        assert policy.apply_to_public_authority

    def test_zero_duration(self) -> None:
        policy = RetentionPolicy(duration_days=0)
        assert policy.duration_days == 0


class TestAIActLoggerInstantiation:
    def test_instantiate_standalone(self) -> None:
        logger = AIActLogger(system_id="sys-01")
        assert isinstance(logger, AIActLogger)
        assert logger.system_id == "sys-01"
        assert logger.system_version == "1.0.0"

    def test_default_system_version(self) -> None:
        logger = AIActLogger(system_id="sys-01")
        assert logger.system_version == "1.0.0"

    def test_custom_system_version(self) -> None:
        logger = AIActLogger(system_id="sys-01", system_version="2.5.0")
        assert logger.system_version == "2.5.0"

    def test_default_retention_policy(self) -> None:
        logger = AIActLogger(system_id="sys-01")
        assert isinstance(logger.retention, RetentionPolicy)
        assert logger.retention.duration_days == 183

    def test_custom_retention_policy(self) -> None:
        policy = RetentionPolicy(duration_days=365)
        logger = AIActLogger(system_id="sys-01", retention=policy)
        assert logger.retention.duration_days == 365


class TestAIActLoggerLogEvent:
    def test_log_event_creates_entry(self) -> None:
        logger = AIActLogger(system_id="sys-01")
        entry = logger.log_event(
            session_id="sess-001",
            use_period_start="2026-07-11T00:00:00Z",
            use_period_end="2026-07-11T23:59:59Z",
            input_data="test input",
        )
        assert isinstance(entry, AIActLogEntry)
        assert entry.entry_id != ""
        assert len(entry.entry_id) == 12

    def test_log_event_generates_hash(self) -> None:
        logger = AIActLogger(system_id="sys-01")
        entry = logger.log_event(
            session_id="sess-001",
            use_period_start="2026-07-11T00:00:00Z",
            use_period_end="2026-07-11T23:59:59Z",
            input_data="hello world",
        )
        import hashlib
        expected = hashlib.sha256(b"hello world").hexdigest()
        assert entry.input_data_hash == expected

    def test_log_event_hash_determinism(self) -> None:
        logger = AIActLogger(system_id="sys-01")
        e1 = logger.log_event(
            session_id="sess-001",
            use_period_start="t", use_period_end="t",
            input_data="same data",
        )
        e2 = logger.log_event(
            session_id="sess-002",
            use_period_start="t", use_period_end="t",
            input_data="same data",
        )
        assert e1.input_data_hash == e2.input_data_hash

    def test_log_event_sets_system_fields(self) -> None:
        logger = AIActLogger(system_id="sys-99", system_version="3.0.0")
        entry = logger.log_event(
            session_id="sess-X",
            use_period_start="2026-07-11T00:00:00Z",
            use_period_end="2026-07-11T23:59:59Z",
            input_data="data",
        )
        assert entry.system_id == "sys-99"
        assert entry.system_version == "3.0.0"
        assert entry.session_id == "sess-X"

    def test_log_event_sets_timestamps(self) -> None:
        logger = AIActLogger(system_id="sys-01")
        entry = logger.log_event(
            session_id="sess-001",
            use_period_start="2026-01-01T00:00:00Z",
            use_period_end="2026-01-01T23:59:59Z",
            input_data="data",
        )
        assert "T" in entry.event_timestamp_utc
        assert entry.event_timestamp_utc.endswith("Z") or "+" in entry.event_timestamp_utc
        assert entry.use_period_start == "2026-01-01T00:00:00Z"
        assert entry.use_period_end == "2026-01-01T23:59:59Z"

    def test_log_event_with_risk_anomaly_kwargs(self) -> None:
        logger = AIActLogger(system_id="sys-01")
        entry = logger.log_event(
            session_id="sess-001",
            use_period_start="t", use_period_end="t",
            input_data="data",
            risk_event=True,
            anomaly_flag=True,
            failsafe_triggered=True,
        )
        assert entry.risk_event is True
        assert entry.anomaly_flag is True
        assert entry.failsafe_triggered is True

    def test_log_event_with_confidence_and_oversight(self) -> None:
        logger = AIActLogger(system_id="sys-01")
        entry = logger.log_event(
            session_id="sess-001",
            use_period_start="t", use_period_end="t",
            input_data="data",
            confidence_score=0.87,
            human_oversight_person_id="auditor-01",
            human_oversight_action="overrode",
        )
        assert entry.confidence_score == 0.87
        assert entry.human_oversight_person_id == "auditor-01"
        assert entry.human_oversight_action == "overrode"

    def test_log_event_with_decision_fields(self) -> None:
        logger = AIActLogger(system_id="sys-01")
        entry = logger.log_event(
            session_id="sess-001",
            use_period_start="t", use_period_end="t",
            input_data="data",
            decision_type="rejection",
            decision_rationale="below threshold",
            reference_database="db-v1",
            reference_version="v2",
        )
        assert entry.decision_type == "rejection"
        assert entry.decision_rationale == "below threshold"
        assert entry.reference_database == "db-v1"
        assert entry.reference_version == "v2"

    def test_log_event_with_input_data_fields(self) -> None:
        logger = AIActLogger(system_id="sys-01")
        entry = logger.log_event(
            session_id="sess-001",
            use_period_start="t", use_period_end="t",
            input_data="data",
            input_data_fields=["field1", "field2"],
        )
        assert entry.input_data_fields == ["field1", "field2"]

    def test_log_event_with_error_type(self) -> None:
        logger = AIActLogger(system_id="sys-01")
        entry = logger.log_event(
            session_id="sess-001",
            use_period_start="t", use_period_end="t",
            input_data="data",
            error_type="timeout",
        )
        assert entry.error_type == "timeout"

    def test_log_event_empty_input(self) -> None:
        logger = AIActLogger(system_id="sys-01")
        entry = logger.log_event(
            session_id="sess-001",
            use_period_start="t", use_period_end="t",
            input_data="",
        )
        import hashlib
        assert entry.input_data_hash == hashlib.sha256(b"").hexdigest()

    def test_log_event_very_long_input(self) -> None:
        logger = AIActLogger(system_id="sys-01")
        long_data = "x" * 100000
        entry = logger.log_event(
            session_id="sess-001",
            use_period_start="t", use_period_end="t",
            input_data=long_data,
        )
        import hashlib
        assert entry.input_data_hash == hashlib.sha256(long_data.encode()).hexdigest()

    def test_log_event_auto_entry_id_different(self) -> None:
        logger = AIActLogger(system_id="sys-01")
        e1 = logger.log_event("s1", "t", "t", "a")
        e2 = logger.log_event("s2", "t", "t", "b")
        assert e1.entry_id != e2.entry_id

    def test_log_event_returns_stored_entry(self) -> None:
        logger = AIActLogger(system_id="sys-01")
        entry = logger.log_event("s1", "t", "t", "data")
        assert logger._entries[entry.entry_id] is entry

    def test_log_event_stores_internal_dict(self) -> None:
        logger = AIActLogger(system_id="sys-01")
        entry = logger.log_event("s1", "t", "t", "data")
        assert entry.entry_id in logger._entries

    def test_log_event_entry_id_length(self) -> None:
        logger = AIActLogger(system_id="sys-01")
        entry = logger.log_event("s1", "t", "t", "data")
        assert len(entry.entry_id) == 12


class TestAIActLoggerCountEvents:
    def test_count_events_zero_initially(self) -> None:
        logger = AIActLogger(system_id="sys-01")
        assert logger.count_events() == 0

    def test_count_events_after_one(self) -> None:
        logger = AIActLogger(system_id="sys-01")
        logger.log_event("s1", "t", "t", "data")
        assert logger.count_events() == 1

    def test_count_events_after_multiple(self) -> None:
        logger = AIActLogger(system_id="sys-01")
        for i in range(5):
            logger.log_event(f"s{i}", "t", "t", f"data{i}")
        assert logger.count_events() == 5


class TestAIActLoggerQuery:
    def test_query_no_filters_returns_all(self) -> None:
        logger = AIActLogger(system_id="sys-01")
        logger.log_event("s1", "t", "t", "a")
        logger.log_event("s2", "t", "t", "b")
        results = logger.query()
        assert len(results) == 2

    def test_query_filter_by_system_id(self) -> None:
        logger = AIActLogger(system_id="sys-01")
        logger.log_event("s1", "t", "t", "a")
        logger.log_event("s2", "t", "t", "b")
        results = logger.query(system_id="sys-01")
        assert len(results) == 2

    def test_query_filter_by_system_id_no_match(self) -> None:
        logger = AIActLogger(system_id="sys-01")
        logger.log_event("s1", "t", "t", "a")
        results = logger.query(system_id="sys-other")
        assert results == []

    def test_query_filter_by_risk_event(self) -> None:
        logger = AIActLogger(system_id="sys-01")
        logger.log_event("s1", "t", "t", "a")
        logger.log_event("s2", "t", "t", "b", risk_event=True)
        results = logger.query(risk_event=True)
        assert len(results) == 1
        assert results[0].session_id == "s2"

    def test_query_filter_by_anomaly_flag(self) -> None:
        logger = AIActLogger(system_id="sys-01")
        logger.log_event("s1", "t", "t", "a")
        logger.log_event("s2", "t", "t", "b", anomaly_flag=True)
        logger.log_event("s3", "t", "t", "c", anomaly_flag=True)
        results = logger.query(anomaly_flag=True)
        assert len(results) == 2

    def test_query_filter_by_session_id(self) -> None:
        logger = AIActLogger(system_id="sys-01")
        logger.log_event("target-session", "t", "t", "a")
        logger.log_event("other-session", "t", "t", "b")
        results = logger.query(session_id="target-session")
        assert len(results) == 1
        assert results[0].session_id == "target-session"

    def test_query_filter_by_session_id_no_match(self) -> None:
        logger = AIActLogger(system_id="sys-01")
        logger.log_event("s1", "t", "t", "a")
        results = logger.query(session_id="nonexistent")
        assert results == []

    def test_query_combination_risk_and_anomaly(self) -> None:
        logger = AIActLogger(system_id="sys-01")
        logger.log_event("s1", "t", "t", "a", risk_event=True, anomaly_flag=True)
        logger.log_event("s2", "t", "t", "b", risk_event=True, anomaly_flag=False)
        logger.log_event("s3", "t", "t", "c", risk_event=False, anomaly_flag=True)
        logger.log_event("s4", "t", "t", "d")
        results = logger.query(risk_event=True, anomaly_flag=True)
        assert len(results) == 1
        assert results[0].session_id == "s1"

    def test_query_combination_risk_and_session(self) -> None:
        logger = AIActLogger(system_id="sys-01")
        logger.log_event("s-risk", "t", "t", "a", risk_event=True)
        logger.log_event("s-risk", "t", "t", "b", risk_event=False)
        logger.log_event("s-other", "t", "t", "c", risk_event=True)
        results = logger.query(session_id="s-risk", risk_event=True)
        assert len(results) == 1
        assert results[0].input_data_hash != ""

    def test_query_empty_logger(self) -> None:
        logger = AIActLogger(system_id="sys-01")
        results = logger.query()
        assert results == []

    def test_query_filters_risk_event_false(self) -> None:
        logger = AIActLogger(system_id="sys-01")
        logger.log_event("s1", "t", "t", "a", risk_event=False)
        logger.log_event("s2", "t", "t", "b", risk_event=True)
        results = logger.query(risk_event=False)
        assert len(results) == 1
        assert results[0].session_id == "s1"

    def test_query_filters_anomaly_flag_false(self) -> None:
        logger = AIActLogger(system_id="sys-01")
        logger.log_event("s1", "t", "t", "a", anomaly_flag=False)
        logger.log_event("s2", "t", "t", "b", anomaly_flag=True)
        results = logger.query(anomaly_flag=False)
        assert len(results) == 1
        assert results[0].session_id == "s1"

    def test_query_returns_copy_not_reference(self) -> None:
        logger = AIActLogger(system_id="sys-01")
        logger.log_event("s1", "t", "t", "a")
        results = logger.query()
        results.clear()
        assert logger.count_events() == 1


class TestAIActLoggerRetention:
    def test_get_retention_status_shows_duration(self) -> None:
        logger = AIActLogger(system_id="sys-01")
        status = logger.get_retention_status()
        assert status["retention_days"] == 183

    def test_get_retention_status_shows_public_authority(self) -> None:
        logger = AIActLogger(system_id="sys-01")
        status = logger.get_retention_status()
        assert "apply_to_public_authority" in status

    def test_get_retention_status_with_custom_policy(self) -> None:
        policy = RetentionPolicy(duration_days=90, apply_to_public_authority=True)
        logger = AIActLogger(system_id="sys-01", retention=policy)
        status = logger.get_retention_status()
        assert status["retention_days"] == 90
        assert status["apply_to_public_authority"] is True

    def test_get_retention_status_includes_events_count(self) -> None:
        logger = AIActLogger(system_id="sys-01")
        logger.log_event("s1", "t", "t", "a")
        logger.log_event("s2", "t", "t", "b")
        status = logger.get_retention_status()
        assert status["total_events"] == 2

    def test_get_retention_status_includes_system_id(self) -> None:
        logger = AIActLogger(system_id="sys-abc")
        status = logger.get_retention_status()
        assert status["system_id"] == "sys-abc"

    def test_get_retention_status_includes_system_version(self) -> None:
        logger = AIActLogger(system_id="sys-01", system_version="4.0.0")
        status = logger.get_retention_status()
        assert status["system_version"] == "4.0.0"


class TestRegulatoryLogExporterJSON:
    def test_export_json_valid_syntax(self) -> None:
        logger = AIActLogger(system_id="sys-01")
        entry = logger.log_event("s1", "t", "t", "data")
        exporter = RegulatoryLogExporter()
        output = exporter.export_json([entry])
        parsed = json.loads(output)
        assert isinstance(parsed, list)
        assert len(parsed) == 1

    def test_export_json_contains_entry_id(self) -> None:
        logger = AIActLogger(system_id="sys-01")
        entry = logger.log_event("s1", "t", "t", "data")
        exporter = RegulatoryLogExporter()
        output = json.loads(exporter.export_json([entry]))
        assert output[0]["entry_id"] == entry.entry_id

    def test_export_json_contains_key_fields(self) -> None:
        logger = AIActLogger(system_id="sys-01")
        entry = logger.log_event("sess-X", "t", "t", "data",
                                 risk_event=True, confidence_score=0.5)
        exporter = RegulatoryLogExporter()
        output = json.loads(exporter.export_json([entry]))[0]
        assert output["system_id"] == "sys-01"
        assert output["session_id"] == "sess-X"
        assert output["risk_event"] is True
        assert output["confidence_score"] == 0.5

    def test_export_json_multiple_entries(self) -> None:
        logger = AIActLogger(system_id="sys-01")
        e1 = logger.log_event("s1", "t", "t", "a")
        e2 = logger.log_event("s2", "t", "t", "b")
        exporter = RegulatoryLogExporter()
        output = json.loads(exporter.export_json([e1, e2]))
        assert len(output) == 2

    def test_export_json_empty_list(self) -> None:
        exporter = RegulatoryLogExporter()
        output = exporter.export_json([])
        assert json.loads(output) == []

    def test_export_json_indentation(self) -> None:
        logger = AIActLogger(system_id="sys-01")
        entry = logger.log_event("s1", "t", "t", "data")
        exporter = RegulatoryLogExporter()
        output = exporter.export_json([entry])
        lines = output.strip().split("\n")
        assert len(lines) > 1

    def test_export_json_contains_hash(self) -> None:
        logger = AIActLogger(system_id="sys-01")
        entry = logger.log_event("s1", "t", "t", "sensitive-data")
        exporter = RegulatoryLogExporter()
        output = json.loads(exporter.export_json([entry]))[0]
        assert "input_data_hash" in output
        assert "input_data" not in output

    def test_export_json_contains_timestamp(self) -> None:
        logger = AIActLogger(system_id="sys-01")
        entry = logger.log_event("s1", "t", "t", "data")
        exporter = RegulatoryLogExporter()
        output = json.loads(exporter.export_json([entry]))[0]
        assert output["event_timestamp_utc"] != ""

    def test_export_json_with_none_values(self) -> None:
        logger = AIActLogger(system_id="sys-01")
        entry = logger.log_event("s1", "t", "t", "data")
        exporter = RegulatoryLogExporter()
        output = json.loads(exporter.export_json([entry]))[0]
        assert output["human_oversight_person_id"] is None


class TestRegulatoryLogExporterMarkdown:
    def test_export_markdown_contains_table_headers(self) -> None:
        logger = AIActLogger(system_id="sys-01")
        entry = logger.log_event("s1", "t", "t", "data")
        exporter = RegulatoryLogExporter()
        output = exporter.export_markdown([entry])
        assert "system_id" in output
        assert "session_id" in output
        assert "event_timestamp_utc" in output

    def test_export_markdown_contains_entry_data(self) -> None:
        logger = AIActLogger(system_id="sys-42")
        entry = logger.log_event("sess-X", "t", "t", "data")
        exporter = RegulatoryLogExporter()
        output = exporter.export_markdown([entry])
        assert "sys-42" in output
        assert "sess-X" in output

    def test_export_markdown_empty_list(self) -> None:
        exporter = RegulatoryLogExporter()
        output = exporter.export_markdown([])
        assert "No log entries" in output or output.strip() == ""

    def test_export_markdown_multiple_entries(self) -> None:
        logger = AIActLogger(system_id="sys-01")
        e1 = logger.log_event("s1", "t", "t", "a")
        e2 = logger.log_event("s2", "t", "t", "b")
        exporter = RegulatoryLogExporter()
        output = exporter.export_markdown([e1, e2])
        assert output.count("|") >= 6

    def test_export_markdown_risk_marker(self) -> None:
        logger = AIActLogger(system_id="sys-01")
        entry = logger.log_event("s1", "t", "t", "data", risk_event=True)
        exporter = RegulatoryLogExporter()
        output = exporter.export_markdown([entry])
        assert "RISK" in output or "risk" in output.lower()

    def test_export_markdown_anomaly_marker(self) -> None:
        logger = AIActLogger(system_id="sys-01")
        entry = logger.log_event("s1", "t", "t", "data", anomaly_flag=True)
        exporter = RegulatoryLogExporter()
        output = exporter.export_markdown([entry])
        assert "ANOMALY" in output or "anomaly" in output.lower()

    def test_export_markdown_format_starts_with_table(self) -> None:
        logger = AIActLogger(system_id="sys-01")
        entry = logger.log_event("s1", "t", "t", "data")
        exporter = RegulatoryLogExporter()
        output = exporter.export_markdown([entry]).strip()
        assert output.startswith("|")


class TestIntegration:
    def test_log_query_export_flow(self) -> None:
        logger = AIActLogger(system_id="sys-integration", system_version="1.0.0")
        logger.log_event(
            session_id="sess-flow",
            use_period_start="2026-07-11T00:00:00Z",
            use_period_end="2026-07-11T23:59:59Z",
            input_data="patient data",
            risk_event=False,
            confidence_score=0.99,
        )
        assert logger.count_events() == 1
        results = logger.query(session_id="sess-flow")
        assert len(results) == 1
        exporter = RegulatoryLogExporter()
        json_out = exporter.export_json(results)
        parsed = json.loads(json_out)
        assert parsed[0]["system_id"] == "sys-integration"
        assert parsed[0]["confidence_score"] == 0.99
        md_out = exporter.export_markdown(results)
        assert "sys-integration" in md_out

    def test_multiple_loggers_independent(self) -> None:
        logger_a = AIActLogger(system_id="sys-a")
        logger_b = AIActLogger(system_id="sys-b")
        logger_a.log_event("s1", "t", "t", "data")
        logger_b.log_event("s1", "t", "t", "data")
        assert logger_a.count_events() == 1
        assert logger_b.count_events() == 1

    def test_query_with_no_matches_returns_empty_list(self) -> None:
        logger = AIActLogger(system_id="sys-01")
        logger.log_event("s1", "t", "t", "a")
        results = logger.query(system_id="nonexistent", risk_event=True)
        assert results == []

    def test_log_event_all_optional_kwargs(self) -> None:
        logger = AIActLogger(system_id="sys-all-opt")
        entry = logger.log_event(
            session_id="sess-all",
            use_period_start="2026-01-01T00:00:00Z",
            use_period_end="2026-01-01T23:59:59Z",
            input_data="full data",
            input_data_fields=["a", "b"],
            reference_database="db",
            reference_version="v1",
            decision_type="approve",
            decision_rationale="all good",
            confidence_score=1.0,
            human_oversight_person_id="human-01",
            human_oversight_action="reviewed",
            automated_only_exemption="standard",
            risk_event=True,
            anomaly_flag=False,
            error_type=None,
            failsafe_triggered=False,
        )
        assert entry.system_id == "sys-all-opt"
        assert len(entry.entry_id) == 12
        import hashlib
        assert entry.input_data_hash == hashlib.sha256(b"full data").hexdigest()
        assert entry.input_data_fields == ["a", "b"]
        assert entry.decision_type == "approve"
        assert entry.human_oversight_action == "reviewed"
        assert entry.risk_event is True
        assert entry.anomaly_flag is False
        assert entry.failsafe_triggered is False
        assert entry.error_type is None

    def test_export_json_none_fields_serialized(self) -> None:
        logger = AIActLogger(system_id="sys-01")
        entry = logger.log_event("s1", "t", "t", "data")
        exporter = RegulatoryLogExporter()
        output = exporter.export_json([entry])
        parsed = json.loads(output)[0]
        assert parsed["confidence_score"] is None
        assert parsed["error_type"] is None
        assert parsed["automated_only_exemption"] is None

    def test_retention_policy_in_logger_init(self) -> None:
        policy = RetentionPolicy(duration_days=730)
        logger = AIActLogger(system_id="sys-long", retention=policy)
        status = logger.get_retention_status()
        assert status["retention_days"] == 730
        assert status["total_events"] == 0
