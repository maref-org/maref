from __future__ import annotations

from maref.recursive.hook_chain import HookChain
from maref.recursive.hook_registry import (
    HookRegistry,
    HookResult,
    HookVerdict,
)
from maref.recursive.hook_templates import (
    HookTemplate,
    HookTemplateLibrary,
    create_default_template_library,
    destructive_operation_guard,
    integrity_guard,
    secret_leak_guard,
    sensitive_path_guard,
)
from maref.recursive.hook_topics import MarefTopic


class TestHookRegistry:
    def test_register_and_get_chain(self) -> None:
        registry = HookRegistry()
        hid = registry.register(MarefTopic.ROLE_PRE_INVOKE, lambda d: HookResult(HookVerdict.PASS, "h1"))
        chain = registry.get_chain(MarefTopic.ROLE_PRE_INVOKE)
        assert len(chain) == 1
        assert chain[0].handler_id == hid

    def test_multiple_handlers_sorted_by_priority(self) -> None:
        registry = HookRegistry()
        hid_low = registry.register(MarefTopic.ROLE_PRE_INVOKE, lambda d: HookResult(HookVerdict.PASS, "low"), priority=0)
        hid_high = registry.register(MarefTopic.ROLE_PRE_INVOKE, lambda d: HookResult(HookVerdict.PASS, "high"), priority=100)
        chain = registry.get_chain(MarefTopic.ROLE_PRE_INVOKE)
        assert chain[0].handler_id == hid_high
        assert chain[1].handler_id == hid_low

    def test_unregister_existing(self) -> None:
        registry = HookRegistry()
        registry.register(MarefTopic.SESSION_START, lambda d: HookResult(HookVerdict.PASS), handler_id="h1")
        assert registry.unregister(MarefTopic.SESSION_START, "h1")
        chain = registry.get_chain(MarefTopic.SESSION_START)
        assert len(chain) == 0

    def test_unregister_nonexistent(self) -> None:
        registry = HookRegistry()
        assert not registry.unregister(MarefTopic.SESSION_START, "nonexistent")

    def test_clear(self) -> None:
        registry = HookRegistry()
        registry.register(MarefTopic.SESSION_START, lambda d: HookResult(HookVerdict.PASS, "h1"))
        registry.clear()
        assert len(registry.get_chain(MarefTopic.SESSION_START)) == 0

    def test_custom_handler_id(self) -> None:
        registry = HookRegistry()
        hid = registry.register(
            MarefTopic.ROLE_PRE_INVOKE,
            lambda d: HookResult(HookVerdict.PASS),
            handler_id="my-custom-id",
        )
        assert hid == "my-custom-id"


class TestHookChain:
    def test_execute_all_pass(self) -> None:
        registry = HookRegistry()
        registry.register(MarefTopic.ROLE_PRE_INVOKE, lambda d: HookResult(HookVerdict.PASS, "h1"))
        registry.register(MarefTopic.ROLE_PRE_INVOKE, lambda d: HookResult(HookVerdict.PASS, "h2"))
        chain = HookChain(registry)
        result = chain.execute(MarefTopic.ROLE_PRE_INVOKE, {})
        assert result.passed
        assert len(result.execution_stack.entries) == 2

    def test_execute_block_stops_chain(self) -> None:
        registry = HookRegistry()
        handler2_called = []

        def h1(d: dict) -> HookResult:
            return HookResult(HookVerdict.BLOCK, "blocker")

        def h2(d: dict) -> HookResult:
            handler2_called.append(True)
            return HookResult(HookVerdict.PASS, "h2")

        registry.register(MarefTopic.ROLE_PRE_INVOKE, h1, priority=100)
        registry.register(MarefTopic.ROLE_PRE_INVOKE, h2, priority=0)
        chain = HookChain(registry)
        result = chain.execute(MarefTopic.ROLE_PRE_INVOKE, {})
        assert not result.passed
        assert len(result.execution_stack.entries) == 1
        assert len(handler2_called) == 0

    def test_execute_fatal_stops_chain(self) -> None:
        registry = HookRegistry()
        handler2_called = []

        def h1(d: dict) -> HookResult:
            return HookResult(HookVerdict.FATAL, "fatal_handler")

        def h2(d: dict) -> HookResult:
            handler2_called.append(True)
            return HookResult(HookVerdict.PASS, "h2")

        registry.register(MarefTopic.ROLE_PRE_INVOKE, h1, priority=100)
        registry.register(MarefTopic.ROLE_PRE_INVOKE, h2, priority=0)
        chain = HookChain(registry)
        result = chain.execute(MarefTopic.ROLE_PRE_INVOKE, {})
        assert not result.passed
        assert result.verdict == HookVerdict.FATAL

    def test_execute_audit_passes_through(self) -> None:
        registry = HookRegistry()
        registry.register(MarefTopic.ROLE_PRE_INVOKE, lambda d: HookResult(HookVerdict.AUDIT, "auditor"))
        registry.register(MarefTopic.ROLE_PRE_INVOKE, lambda d: HookResult(HookVerdict.PASS, "h2"))
        chain = HookChain(registry)
        result = chain.execute(MarefTopic.ROLE_PRE_INVOKE, {})
        assert result.passed
        assert len(result.execution_stack.entries) == 2

    def test_execution_stack_contains_metadata(self) -> None:
        registry = HookRegistry()
        registry.register(MarefTopic.ROLE_PRE_INVOKE, lambda d: HookResult(HookVerdict.PASS, "h1"))
        chain = HookChain(registry)
        result = chain.execute(MarefTopic.ROLE_PRE_INVOKE, {})
        entry = result.execution_stack.entries[0]
        assert "handler_id" in entry
        assert "verdict" in entry
        assert "duration_ms" in entry

    def test_total_duration_set(self) -> None:
        registry = HookRegistry()
        registry.register(MarefTopic.ROLE_PRE_INVOKE, lambda d: HookResult(HookVerdict.PASS, "h1"))
        chain = HookChain(registry)
        result = chain.execute(MarefTopic.ROLE_PRE_INVOKE, {})
        assert result.total_duration_ms >= 0

    def test_all_passed_with_audit(self) -> None:
        registry = HookRegistry()
        registry.register(MarefTopic.ROLE_PRE_INVOKE, lambda d: HookResult(HookVerdict.AUDIT, "a"))
        chain = HookChain(registry)
        result = chain.execute(MarefTopic.ROLE_PRE_INVOKE, {})
        assert result.all_passed


class TestHookTemplates:
    def test_destructive_guard_blocks_rm_rf(self) -> None:
        result = destructive_operation_guard("rm -rf /")
        assert result.verdict == HookVerdict.BLOCK

    def test_destructive_guard_blocks_drop_table(self) -> None:
        result = destructive_operation_guard("DROP TABLE users")
        assert result.verdict == HookVerdict.BLOCK

    def test_destructive_guard_blocks_sudo(self) -> None:
        result = destructive_operation_guard("sudo rm file")
        assert result.verdict == HookVerdict.BLOCK

    def test_destructive_guard_blocks_git_push_force(self) -> None:
        result = destructive_operation_guard("git push --force origin main")
        assert result.verdict == HookVerdict.BLOCK

    def test_destructive_guard_passes_safe(self) -> None:
        result = destructive_operation_guard("echo hello")
        assert result.verdict == HookVerdict.PASS

    def test_secret_leak_blocks_sk_key(self) -> None:
        result = secret_leak_guard("sk-abcdefghijklmnopqrstuvwxyz123456")
        assert result.verdict == HookVerdict.BLOCK

    def test_secret_leak_blocks_aws_key(self) -> None:
        result = secret_leak_guard("AKIAIOSFODNN7EXAMPLE")
        assert result.verdict == HookVerdict.BLOCK

    def test_secret_leak_blocks_bearer_token(self) -> None:
        result = secret_leak_guard("Bearer abcdefghijklmnopqrstuvwxyz")
        assert result.verdict == HookVerdict.BLOCK

    def test_secret_leak_passes_safe(self) -> None:
        result = secret_leak_guard("normal text output")
        assert result.verdict == HookVerdict.PASS

    def test_integrity_guard_fails_on_mismatch(self) -> None:
        result = integrity_guard({
            "expected_checksums": {"a.py": "abc"},
            "actual_checksums": {"a.py": "def"},
        })
        assert result.verdict == HookVerdict.FATAL

    def test_integrity_guard_fails_on_missing(self) -> None:
        result = integrity_guard({
            "expected_checksums": {"a.py": "abc"},
            "actual_checksums": {},
        })
        assert result.verdict == HookVerdict.FATAL

    def test_integrity_guard_passes_on_match(self) -> None:
        result = integrity_guard({
            "expected_checksums": {"a.py": "abc"},
            "actual_checksums": {"a.py": "abc"},
        })
        assert result.verdict == HookVerdict.PASS

    def test_sensitive_path_guard_blocks_git(self) -> None:
        result = sensitive_path_guard({"path": ".git/config"})
        assert result.verdict == HookVerdict.BLOCK

    def test_sensitive_path_guard_blocks_env(self) -> None:
        result = sensitive_path_guard({"path": "/app/.env"})
        assert result.verdict == HookVerdict.BLOCK

    def test_sensitive_path_guard_passes_safe(self) -> None:
        result = sensitive_path_guard({"path": "src/main.py"})
        assert result.verdict == HookVerdict.PASS


class TestHookTemplateLibrary:
    def test_default_library_has_four_templates(self) -> None:
        lib = create_default_template_library()
        templates = lib.list_templates()
        assert len(templates) == 4

    def test_get_template_by_name(self) -> None:
        lib = create_default_template_library()
        t = lib.get("destructive_operation_guard")
        assert t is not None
        assert t.priority == 100

    def test_get_nonexistent(self) -> None:
        lib = create_default_template_library()
        assert lib.get("nonexistent") is None

    def test_install_all_to_registry(self) -> None:
        lib = create_default_template_library()
        registry = HookRegistry()
        ids = lib.install_all(registry, "maref.layer3.role.pre_invoke")
        assert len(ids) == 2
        chain = registry.get_chain("maref.layer3.role.pre_invoke")
        assert len(chain) == 2

    def test_custom_template_registration(self) -> None:
        lib = HookTemplateLibrary()
        lib.register(HookTemplate(
            topic="maref.session.start",
            name="custom_startup",
            handler_func=lambda d: HookResult(HookVerdict.PASS),
            description="Custom startup hook",
            priority=50,
        ))
        assert len(lib.list_templates()) == 1

    def test_install_all_session_start(self) -> None:
        lib = create_default_template_library()
        registry = HookRegistry()
        ids = lib.install_all(registry, "maref.session.start")
        assert len(ids) == 1
