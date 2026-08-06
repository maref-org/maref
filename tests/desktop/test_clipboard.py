from __future__ import annotations

from maref.desktop.clipboard import (
    ClipboardContentType,
    ClipboardController,
    ClipboardEntry,
    ClipboardSafetyFilter,
)


class TestClipboardEntry:
    def test_is_sensitive_detects_password(self) -> None:
        entry = ClipboardEntry(content="my password is secret")
        assert entry.is_sensitive

    def test_is_sensitive_detects_token(self) -> None:
        entry = ClipboardEntry(content="Bearer sk-abc123")
        assert entry.is_sensitive

    def test_is_sensitive_benign_text(self) -> None:
        entry = ClipboardEntry(content="Hello, world!")
        assert not entry.is_sensitive

    def test_autosets_byte_size(self) -> None:
        entry = ClipboardEntry(content="hello")
        assert entry.byte_size == 5

    def test_to_dict_excludes_content(self) -> None:
        entry = ClipboardEntry(content="secret", source_app="test")
        d = entry.to_dict()
        assert "content" not in d
        assert d["is_sensitive"] is True


class TestClipboardSafetyFilter:
    def test_check_read_always_allowed(self) -> None:
        filt = ClipboardSafetyFilter()
        entry = ClipboardEntry(content="anything")
        assert filt.check_read(entry)

    def test_check_write_small_content(self) -> None:
        filt = ClipboardSafetyFilter()
        entry = ClipboardEntry(content="safe text")
        allowed, reason = filt.check_write(entry)
        assert allowed
        assert reason == ""

    def test_check_write_exceeds_max_size(self) -> None:
        filt = ClipboardSafetyFilter(max_content_size=10)
        entry = ClipboardEntry(content="x" * 100)
        allowed, reason = filt.check_write(entry)
        assert not allowed
        assert "exceeds max" in reason

    def test_check_write_sensitive_scrubbed(self) -> None:
        filt = ClipboardSafetyFilter(scrub_sensitive=True)
        entry = ClipboardEntry(content="my password is 1234")
        allowed, reason = filt.check_write(entry)
        assert not allowed
        assert "sensitive" in reason.lower()

    def test_check_write_sensitive_not_scrubbed(self) -> None:
        filt = ClipboardSafetyFilter(scrub_sensitive=False)
        entry = ClipboardEntry(content="my password is 1234")
        allowed, reason = filt.check_write(entry)
        assert allowed

    def test_detect_sensitive_finds_patterns(self) -> None:
        filt = ClipboardSafetyFilter()
        found = filt.detect_sensitive("Bearer sk-abc123 token here")
        assert len(found) >= 2
        assert "Bearer " in found or "sk-" in found

    def test_detect_sensitive_none_found(self) -> None:
        filt = ClipboardSafetyFilter()
        found = filt.detect_sensitive("plain text")
        assert found == []

    def test_access_log_tracks_reads(self) -> None:
        filt = ClipboardSafetyFilter()
        entry = ClipboardEntry(content="test data")
        filt.check_read(entry)
        assert len(filt.access_log) == 1
        assert filt.access_log[0]["action"] == "read"

    def test_access_log_tracks_writes(self) -> None:
        filt = ClipboardSafetyFilter()
        entry = ClipboardEntry(content="test data")
        filt.check_write(entry)
        assert len(filt.access_log) == 1
        assert filt.access_log[0]["action"] == "write"


class TestClipboardController:
    def test_dry_run_by_default(self) -> None:
        ctrl = ClipboardController()
        assert ctrl.dry_run

    def test_read_in_dry_mode(self) -> None:
        ctrl = ClipboardController(dry_run=True)
        entry = ctrl.read()
        assert entry.content == "[dry_run clipboard content]"
        assert entry.content_type == ClipboardContentType.TEXT

    def test_write_in_dry_mode_returns_true(self) -> None:
        ctrl = ClipboardController(dry_run=True)
        result = ctrl.write("test content")
        assert result

    def test_write_sensitive_in_dry_mode_blocked(self) -> None:
        ctrl = ClipboardController(dry_run=True)
        result = ctrl.write("password=1234")
        assert not result

    def test_clear_in_dry_mode(self) -> None:
        ctrl = ClipboardController(dry_run=True)
        assert ctrl.clear()

    def test_get_access_log(self) -> None:
        ctrl = ClipboardController(dry_run=True)
        ctrl.read()
        ctrl.write("safe text")
        log = ctrl.get_access_log()
        assert len(log) == 2

    def test_dry_run_setter(self) -> None:
        ctrl = ClipboardController(dry_run=True)
        ctrl.dry_run = False
        assert not ctrl.dry_run

    def test_read_without_dry_run_no_pyperclip(self) -> None:
        ctrl = ClipboardController(dry_run=False)
        ctrl._pyperclip_available = False
        entry = ctrl.read()
        assert entry.content == ""
        assert entry.content_type == ClipboardContentType.UNKNOWN

    def test_write_sensitive_scrubbed(self) -> None:
        ctrl = ClipboardController(dry_run=False, safety_filter=None)
        result = ctrl.write("my password is 1234")
        assert not result


class TestClipboardEntryAdvanced:
    def test_post_init_preserves_existing_byte_size(self) -> None:
        entry = ClipboardEntry(content="hello", byte_size=999)
        assert entry.byte_size == 999

    def test_post_init_empty_content(self) -> None:
        entry = ClipboardEntry(content="")
        assert entry.byte_size == 0


class TestClipboardSafetyFilterAdvanced:
    def test_detect_sensitive_bearer(self) -> None:
        filt = ClipboardSafetyFilter()
        found = filt.detect_sensitive("Authorization: Bearer xyz123")
        assert len(found) >= 1
        assert "Bearer " in found or "authorization:" in found

    def test_detect_sensitive_api_key(self) -> None:
        filt = ClipboardSafetyFilter()
        found = filt.detect_sensitive("api-key=abc123")
        assert "api-key" in found

    def test_check_write_exceeds_max_no_scrub(self) -> None:
        filt = ClipboardSafetyFilter(scrub_sensitive=True)
        entry = ClipboardEntry(content="safe but big" * 100000, byte_size=2_000_000)
        allowed, reason = filt.check_write(entry)
        assert not allowed
        assert "exceeds max" in reason

    def test_check_read_logs_access(self) -> None:
        filt = ClipboardSafetyFilter()
        entry = ClipboardEntry(content="test")
        filt.check_read(entry)
        log = filt.access_log
        assert log[0]["action"] == "read"
        assert log[0]["content_type"] == "text"
