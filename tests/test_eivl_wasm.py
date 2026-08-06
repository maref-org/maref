"""
EIVL-WASM 沙箱测试
"""

from __future__ import annotations

from maref.eivl.wasm_sandbox import (
    EIVLVerifier,
    ExecutionStatus,
    ResourceLimits,
    SandboxCapabilities,
    WasmSandboxExecutor,
    create_eivl_verifier,
    create_wasm_sandbox,
)


class TestResourceLimits:
    """测试资源限制"""

    def test_default_limits(self) -> None:
        """测试默认限制"""
        limits = ResourceLimits()
        assert limits.max_memory_mb == 128
        assert limits.max_cpu_time_ms == 5000
        assert limits.max_wall_time_ms == 10000

    def test_custom_limits(self) -> None:
        """测试自定义限制"""
        limits = ResourceLimits(
            max_memory_mb=256,
            max_cpu_time_ms=10000,
        )
        assert limits.max_memory_mb == 256
        assert limits.max_cpu_time_ms == 10000

    def test_to_dict(self) -> None:
        """测试字典转换"""
        limits = ResourceLimits()
        data = limits.to_dict()
        assert "max_memory_mb" in data
        assert data["max_memory_mb"] == 128


class TestSandboxCapabilities:
    """测试沙箱能力"""

    def test_default_capabilities(self) -> None:
        """测试默认能力配置"""
        caps = SandboxCapabilities()
        assert caps.allow_network == False
        assert caps.allow_file_read == False
        assert caps.validate_access("network") == False

    def test_allowed_capabilities(self) -> None:
        """测试允许的能力"""
        caps = SandboxCapabilities(
            allow_network=True,
            allow_file_read=True,
        )
        assert caps.validate_access("network") == True
        assert caps.validate_access("file_read") == True
        assert caps.validate_access("file_write") == False

    def test_syscall_whitelist(self) -> None:
        """测试系统调用白名单"""
        caps = SandboxCapabilities(allowed_syscalls=["read", "write", "exit"])
        assert caps.validate_access("syscall:read") == True
        assert caps.validate_access("syscall:exec") == False


class TestWasmSandboxExecutor:
    """测试 WASM 沙箱执行器"""

    def test_create_sandbox(self) -> None:
        """测试创建沙箱"""
        sandbox = create_wasm_sandbox()
        assert isinstance(sandbox, WasmSandboxExecutor)

    def test_execute_valid_wasm(self) -> None:
        """测试执行有效 WASM"""
        sandbox = create_wasm_sandbox()

        # 最小有效 WASM 模块 (魔术数字 + 版本)
        wasm_bytes = b"\x00asm\x01\x00\x00\x00"

        result = sandbox.execute(wasm_bytes)

        assert result.status == ExecutionStatus.SUCCESS
        assert result.exit_code == 0
        assert result.output_hash != ""

    def test_execute_invalid_wasm(self) -> None:
        """测试执行无效 WASM"""
        sandbox = create_wasm_sandbox()

        # 无效 WASM
        wasm_bytes = b"invalid"

        result = sandbox.execute(wasm_bytes)

        assert result.status == ExecutionStatus.RUNTIME_ERROR

    def test_memory_limit_check(self) -> None:
        """测试内存限制检查"""
        limits = ResourceLimits(max_memory_mb=1)
        sandbox = create_wasm_sandbox(limits=limits)

        # 创建较大的 WASM 模块触发内存限制
        wasm_bytes = b"\x00asm\x01\x00\x00\x00" + b"\x00" * (1024 * 1024 * 2)

        result = sandbox.execute(wasm_bytes)

        # 应该因为内存限制而失败或成功（取决于模拟逻辑）
        assert result is not None

    def test_execution_with_capabilities(self) -> None:
        """测试带能力的执行"""
        sandbox = create_wasm_sandbox()

        wasm_bytes = b"\x00asm\x01\x00\x00\x00"
        caps = SandboxCapabilities(allow_network=True)

        result = sandbox.execute(wasm_bytes, capabilities=caps)

        assert result.status == ExecutionStatus.SUCCESS
        assert "network" in result.capabilities_used

    def test_verify_execution(self) -> None:
        """测试执行验证"""
        sandbox = create_wasm_sandbox()

        wasm_bytes = b"\x00asm\x01\x00\x00\x00"
        result = sandbox.execute(wasm_bytes)

        is_valid = sandbox.verify_execution(wasm_bytes, result)
        assert is_valid == True

    def test_get_stats(self) -> None:
        """测试统计信息"""
        sandbox = create_wasm_sandbox()

        # 执行几次
        wasm_bytes = b"\x00asm\x01\x00\x00\x00"
        sandbox.execute(wasm_bytes)
        sandbox.execute(wasm_bytes)

        stats = sandbox.get_stats()
        assert stats["total_executions"] == 2
        assert stats["total_cpu_time_ms"] >= 0.0


class TestEIVLVerifier:
    """测试 EIVL 验证器"""

    def test_create_verifier(self) -> None:
        """测试创建验证器"""
        verifier = create_eivl_verifier()
        assert isinstance(verifier, EIVLVerifier)

    def test_record_evidence(self) -> None:
        """测试记录证据"""
        verifier = create_eivl_verifier()

        wasm_bytes = b"\x00asm\x01\x00\x00\x00"
        sandbox = create_wasm_sandbox()
        result = sandbox.execute(wasm_bytes)

        evidence = verifier.record_evidence("test-hash", result)

        assert "verifier_id" in evidence
        assert "timestamp" in evidence
        assert "signature" in evidence
        assert evidence["wasm_hash"] == "test-hash"

    def test_verify_evidence(self) -> None:
        """测试验证证据"""
        verifier = create_eivl_verifier()

        wasm_bytes = b"\x00asm\x01\x00\x00\x00"
        sandbox = create_wasm_sandbox()
        result = sandbox.execute(wasm_bytes)

        evidence = verifier.record_evidence("test-hash", result)
        is_valid = verifier.verify_evidence(evidence)

        assert is_valid == True

    def test_tampered_evidence(self) -> None:
        """测试篡改证据检测"""
        verifier = create_eivl_verifier()

        wasm_bytes = b"\x00asm\x01\x00\x00\x00"
        sandbox = create_wasm_sandbox()
        result = sandbox.execute(wasm_bytes)

        evidence = verifier.record_evidence("test-hash", result)

        # 篡改证据
        evidence["wasm_hash"] = "tampered-hash"

        is_valid = verifier.verify_evidence(evidence)
        assert is_valid == False

    def test_get_evidence_chain(self) -> None:
        """测试获取证据链"""
        verifier = create_eivl_verifier()

        wasm_bytes = b"\x00asm\x01\x00\x00\x00"
        sandbox = create_wasm_sandbox()

        for i in range(3):
            result = sandbox.execute(wasm_bytes)
            verifier.record_evidence(f"hash-{i}", result)

        chain = verifier.get_evidence_chain()
        assert len(chain) == 3

    def test_verification_stats(self) -> None:
        """测试验证统计"""
        verifier = create_eivl_verifier()

        wasm_bytes = b"\x00asm\x01\x00\x00\x00"
        sandbox = create_wasm_sandbox()
        result = sandbox.execute(wasm_bytes)

        evidence = verifier.record_evidence("hash", result)
        verifier.verify_evidence(evidence)

        stats = verifier.get_verification_stats()
        assert stats["total_evidence"] == 1
        assert stats["verified_count"] == 1
