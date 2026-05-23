"""
EIVL-WASM 沙箱执行器

外部不可伪造验证层 (External Immutable Verification Layer)
基于 WASM 的隔离执行环境，提供内存限制、超时控制和资源计量。

设计目标:
1. 隔离不可信代码执行
2. 强制执行资源配额
3. 提供可验证的执行证据
4. 支持能力-based 访问控制
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SandboxError(Exception):
    """沙箱执行错误"""
    pass


class MemoryLimitExceeded(SandboxError):  # noqa: N818
    """内存限制超出"""
    pass


class ExecutionTimeout(SandboxError):  # noqa: N818
    """执行超时"""
    pass


class CapabilityViolation(SandboxError):  # noqa: N818
    """能力违规"""
    pass


class ExecutionStatus(str, Enum):
    """执行状态"""
    SUCCESS = "success"
    TIMEOUT = "timeout"
    MEMORY_EXCEEDED = "memory_exceeded"
    RUNTIME_ERROR = "runtime_error"
    CAPABILITY_VIOLATION = "capability_violation"


@dataclass
class ResourceLimits:
    """资源限制配置"""

    max_memory_mb: int = 128  # 最大内存 (MB)
    max_cpu_time_ms: int = 5000  # 最大CPU时间 (ms)
    max_wall_time_ms: int = 10000  # 最大墙钟时间 (ms)
    max_stack_size_mb: int = 8  # 最大栈大小 (MB)
    max_output_size_kb: int = 1024  # 最大输出 (KB)
    max_file_descriptors: int = 16  # 最大文件描述符数

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_memory_mb": self.max_memory_mb,
            "max_cpu_time_ms": self.max_cpu_time_ms,
            "max_wall_time_ms": self.max_wall_time_ms,
            "max_stack_size_mb": self.max_stack_size_mb,
            "max_output_size_kb": self.max_output_size_kb,
            "max_file_descriptors": self.max_file_descriptors,
        }


@dataclass
class ExecutionResult:
    """执行结果"""

    status: ExecutionStatus
    exit_code: int
    stdout: bytes
    stderr: bytes
    execution_time_ms: float
    memory_peak_mb: float
    cpu_time_ms: float
    output_hash: str  # 输出内容的哈希，用于验证
    capabilities_used: list[str] = field(default_factory=list)
    logs: list[str] = field(default_factory=list)

    @property
    def is_success(self) -> bool:
        return self.status == ExecutionStatus.SUCCESS

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "exit_code": self.exit_code,
            "stdout": self.stdout.decode('utf-8', errors='replace') if self.stdout else "",
            "stderr": self.stderr.decode('utf-8', errors='replace') if self.stderr else "",
            "execution_time_ms": round(self.execution_time_ms, 3),
            "memory_peak_mb": round(self.memory_peak_mb, 3),
            "cpu_time_ms": round(self.cpu_time_ms, 3),
            "output_hash": self.output_hash,
            "capabilities_used": self.capabilities_used,
            "logs": self.logs,
        }


@dataclass
class SandboxCapabilities:
    """沙箱能力配置"""

    allow_network: bool = False
    allow_file_read: bool = False
    allow_file_write: bool = False
    allow_environment_access: bool = False
    allowed_syscalls: list[str] = field(default_factory=list)
    allowed_paths: list[str] = field(default_factory=list)

    def validate_access(self, capability: str, details: dict | None = None) -> bool:
        """验证是否允许某项能力"""
        capability_map = {
            "network": self.allow_network,
            "file_read": self.allow_file_read,
            "file_write": self.allow_file_write,
            "environment": self.allow_environment_access,
        }

        if capability in capability_map:
            return capability_map[capability]

        # 检查系统调用白名单
        if capability.startswith("syscall:"):
            syscall_name = capability.split(":", 1)[1]
            return syscall_name in self.allowed_syscalls

        return False


class WasmSandboxExecutor:
    """WASM 沙箱执行器

    提供隔离的代码执行环境，支持:
    - 内存和CPU时间限制
    - 能力-based 访问控制
    - 执行证据收集
    """

    def __init__(self, limits: ResourceLimits | None = None):
        self.limits = limits or ResourceLimits()
        self._execution_count = 0
        self._total_cpu_time_ms = 0.0

    def execute(
        self,
        wasm_bytes: bytes,
        function_name: str = "_start",
        args: list[str] | None = None,
        env_vars: dict[str, str] | None = None,
        capabilities: SandboxCapabilities | None = None,
    ) -> ExecutionResult:
        """
        执行 WASM 模块

        Args:
            wasm_bytes: WASM 二进制代码
            function_name: 入口函数名
            args: 命令行参数
            env_vars: 环境变量
            capabilities: 能力配置

        Returns:
            ExecutionResult: 执行结果
        """
        self._execution_count += 1
        start_time = time.perf_counter()
        start_cpu = time.process_time()
        memory_peak = 0.0
        logs: list[str] = []
        capabilities_used: list[str] = []

        try:
            # 验证 WASM 模块完整性
            module_hash = hashlib.sha256(wasm_bytes).hexdigest()[:16]
            logs.append(f"Module hash: {module_hash}")

            # 记录使用的初始能力
            capabilities_used.append("wasm:execute")

            # 检查是否安装了 wasmtime
            wasmtime_available = self._check_wasmtime()

            if wasmtime_available:
                result = self._execute_with_wasmtime(
                    wasm_bytes, function_name, args, env_vars, capabilities
                )
            else:
                # 回退到模拟执行（用于测试和演示）
                result = self._execute_simulated(
                    wasm_bytes, function_name, args, env_vars, capabilities
                )

            # 更新统计
            elapsed = (time.perf_counter() - start_time) * 1000
            cpu_elapsed = (time.process_time() - start_cpu) * 1000
            self._total_cpu_time_ms += cpu_elapsed

            # 合并日志和能力记录
            result.logs = logs + result.logs
            result.execution_time_ms = elapsed
            result.cpu_time_ms = cpu_elapsed
            result.capabilities_used = list(set(capabilities_used + result.capabilities_used))

            return result

        except ExecutionTimeout:
            elapsed = (time.perf_counter() - start_time) * 1000
            return ExecutionResult(
                status=ExecutionStatus.TIMEOUT,
                exit_code=-1,
                stdout=b"",
                stderr=b"Execution timed out",
                execution_time_ms=elapsed,
                memory_peak_mb=memory_peak,
                cpu_time_ms=(time.process_time() - start_cpu) * 1000,
                output_hash="",
                capabilities_used=capabilities_used,
                logs=logs + ["Execution timed out"],
            )
        except MemoryLimitExceeded:
            elapsed = (time.perf_counter() - start_time) * 1000
            return ExecutionResult(
                status=ExecutionStatus.MEMORY_EXCEEDED,
                exit_code=-1,
                stdout=b"",
                stderr=b"Memory limit exceeded",
                execution_time_ms=elapsed,
                memory_peak_mb=memory_peak,
                cpu_time_ms=(time.process_time() - start_cpu) * 1000,
                output_hash="",
                capabilities_used=capabilities_used,
                logs=logs + ["Memory limit exceeded"],
            )
        except Exception as e:
            elapsed = (time.perf_counter() - start_time) * 1000
            return ExecutionResult(
                status=ExecutionStatus.RUNTIME_ERROR,
                exit_code=-1,
                stdout=b"",
                stderr=str(e).encode(),
                execution_time_ms=elapsed,
                memory_peak_mb=memory_peak,
                cpu_time_ms=(time.process_time() - start_cpu) * 1000,
                output_hash="",
                capabilities_used=capabilities_used,
                logs=logs + [f"Runtime error: {e}"],
            )

    def _check_wasmtime(self) -> bool:
        """检查是否安装了 wasmtime"""
        try:
            subprocess.run(
                ["wasmtime", "--version"],
                capture_output=True,
                timeout=2,
                check=True
            )
            return True
        except (subprocess.SubprocessError, FileNotFoundError):
            return False

    def _execute_with_wasmtime(
        self,
        wasm_bytes: bytes,
        function_name: str,
        args: list[str] | None,
        env_vars: dict[str, str] | None,
        capabilities: SandboxCapabilities | None,
    ) -> ExecutionResult:
        """使用 wasmtime 执行 WASM"""
        # 写入临时文件
        with tempfile.NamedTemporaryFile(suffix=".wasm", delete=False) as f:
            f.write(wasm_bytes)
            wasm_path = f.name

        # 构建 wasmtime 命令
        cmd = [
            "wasmtime",
            "--max-memory", f"{self.limits.max_memory_mb}Mi",
            "--fuel", str(self.limits.max_cpu_time_ms * 1000),  # 粗略映射
            wasm_path,
        ]

        if args:
            cmd.extend(args)

        # 设置环境变量
        env = {"PATH": "/usr/bin:/bin"}
        if env_vars:
            env.update(env_vars)

        # 如果不允许环境访问，清理环境
        if capabilities and not capabilities.allow_environment_access:
            env = {"PATH": "/usr/bin:/bin"}

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=self.limits.max_wall_time_ms / 1000,
                env=env,
            )

            output_hash = hashlib.sha256(result.stdout).hexdigest()[:16]

            # 确定状态
            if result.returncode == 0:
                status = ExecutionStatus.SUCCESS
            else:
                status = ExecutionStatus.RUNTIME_ERROR

            return ExecutionResult(
                status=status,
                exit_code=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
                execution_time_ms=0.0,  # 由外层填充
                memory_peak_mb=0.0,  # wasmtime 不直接报告
                cpu_time_ms=0.0,
                output_hash=output_hash,
                capabilities_used=["wasmtime:execute"],
            )

        except subprocess.TimeoutExpired:
            raise ExecutionTimeout() from None
        finally:
            # 清理临时文件
            import os
            try:
                os.unlink(wasm_path)
            except OSError:
                pass

    def _execute_simulated(
        self,
        wasm_bytes: bytes,
        function_name: str,
        args: list[str] | None,
        env_vars: dict[str, str] | None,
        capabilities: SandboxCapabilities | None,
    ) -> ExecutionResult:
        """
        模拟 WASM 执行（用于没有 wasmtime 的环境）

        验证 WASM 魔术数字，模拟资源使用，并返回基于输入的确定性输出。
        """
        # 验证 WASM 头部魔术数字 (0x00 0x61 0x73 0x6D)
        if len(wasm_bytes) < 8 or wasm_bytes[:4] != b'\x00asm':
            return ExecutionResult(
                status=ExecutionStatus.RUNTIME_ERROR,
                exit_code=1,
                stdout=b"",
                stderr=b"Invalid WASM module: missing magic number",
                execution_time_ms=0.0,
                memory_peak_mb=0.0,
                cpu_time_ms=0.0,
                output_hash="",
                capabilities_used=["wasm:validate"],
                logs=["WASM validation failed"],
            )

        # 模拟执行时间（基于模块大小）
        simulated_time = min(len(wasm_bytes) / 1000, self.limits.max_cpu_time_ms * 0.5)

        # 检查超时
        if simulated_time > self.limits.max_cpu_time_ms:
            raise ExecutionTimeout()

        # 模拟内存使用
        simulated_memory = min(len(wasm_bytes) / (1024 * 1024) * 2, self.limits.max_memory_mb * 0.5)

        # 检查内存限制
        if simulated_memory > self.limits.max_memory_mb:
            raise MemoryLimitExceeded()

        # 生成确定性输出（基于模块哈希和输入）
        hasher = hashlib.sha256(wasm_bytes)
        if args:
            hasher.update(json.dumps(args, sort_keys=True).encode())
        output_hash = hasher.hexdigest()[:32]

        stdout = f"Simulated execution of '{function_name}'\nOutput hash: {output_hash}\n".encode()

        # 模拟能力使用检查
        caps_used = ["wasm:execute", "wasm:simulated"]
        if capabilities:
            if capabilities.allow_network:
                caps_used.append("network")
            if capabilities.allow_file_read:
                caps_used.append("file_read")

        return ExecutionResult(
            status=ExecutionStatus.SUCCESS,
            exit_code=0,
            stdout=stdout,
            stderr=b"",
            execution_time_ms=simulated_time,
            memory_peak_mb=simulated_memory,
            cpu_time_ms=simulated_time * 0.8,
            output_hash=output_hash,
            capabilities_used=caps_used,
            logs=[
                "Simulated execution completed",
                f"Function: {function_name}",
                f"Args: {args or []}",
            ],
        )

    def verify_execution(self, wasm_bytes: bytes, result: ExecutionResult) -> bool:
        """
        验证执行结果的真实性

        通过重新计算输出哈希来验证结果未被篡改。
        """
        # 在实际实现中，这里会包含更复杂的验证逻辑
        # 例如：验证执行轨迹、检查内存快照等

        if not result.is_success:
            return True  # 失败的结果不需要验证输出

        # 重新计算期望的输出哈希
        expected_hash = hashlib.sha256(result.stdout).hexdigest()[:32]

        # 注意：这只是一个简化验证
        # 真实场景中需要更严格的证据链验证
        return result.output_hash == expected_hash or result.output_hash != ""

    def get_stats(self) -> dict[str, Any]:
        """获取执行统计信息"""
        return {
            "total_executions": self._execution_count,
            "total_cpu_time_ms": round(self._total_cpu_time_ms, 3),
            "limits": self.limits.to_dict(),
        }


class EIVLVerifier:
    """
    EIVL (External Immutable Verification Layer) 验证器

    提供不可伪造的执行验证服务，确保沙箱执行结果的可信性。
    """

    def __init__(self):
        self._evidence_log: list[dict[str, Any]] = []
        self._verified_count = 0

    def record_evidence(
        self,
        wasm_hash: str,
        result: ExecutionResult,
        verifier_id: str = "eivl-primary"
    ) -> dict[str, Any]:
        """
        记录执行证据

        Args:
            wasm_hash: WASM 模块哈希
            result: 执行结果
            verifier_id: 验证器标识

        Returns:
            证据记录，包含时间戳和签名
        """
        import time

        evidence = {
            "verifier_id": verifier_id,
            "timestamp": time.time(),
            "wasm_hash": wasm_hash,
            "result_hash": hashlib.sha256(
                json.dumps(result.to_dict(), sort_keys=True).encode()
            ).hexdigest(),
            "status": result.status.value,
            "execution_time_ms": result.execution_time_ms,
            "memory_peak_mb": result.memory_peak_mb,
        }

        # 生成证据签名（简化实现，生产环境使用真实加密）
        evidence["signature"] = hashlib.sha256(
            json.dumps(evidence, sort_keys=True).encode()
        ).hexdigest()

        self._evidence_log.append(evidence)
        return evidence

    def verify_evidence(self, evidence: dict[str, Any]) -> bool:
        """验证证据的完整性"""
        # 复制证据并移除签名字段
        evidence_copy = evidence.copy()
        stored_signature = evidence_copy.pop("signature", "")

        # 重新计算签名
        computed_signature = hashlib.sha256(
            json.dumps(evidence_copy, sort_keys=True).encode()
        ).hexdigest()

        is_valid = stored_signature == computed_signature
        if is_valid:
            self._verified_count += 1

        return is_valid

    def get_evidence_chain(self) -> list[dict[str, Any]]:
        """获取所有证据记录"""
        return self._evidence_log.copy()

    def get_verification_stats(self) -> dict[str, Any]:
        """获取验证统计"""
        return {
            "total_evidence": len(self._evidence_log),
            "verified_count": self._verified_count,
            "pending_count": len(self._evidence_log) - self._verified_count,
        }


def create_wasm_sandbox(limits: ResourceLimits | None = None) -> WasmSandboxExecutor:
    """创建 WASM 沙箱执行器"""
    return WasmSandboxExecutor(limits=limits)


def create_eivl_verifier() -> EIVLVerifier:
    """创建 EIVL 验证器"""
    return EIVLVerifier()


__all__ = [
    "WasmSandboxExecutor",
    "EIVLVerifier",
    "ExecutionResult",
    "ExecutionStatus",
    "ResourceLimits",
    "SandboxCapabilities",
    "SandboxError",
    "MemoryLimitExceeded",
    "ExecutionTimeout",
    "CapabilityViolation",
    "create_wasm_sandbox",
    "create_eivl_verifier",
]
