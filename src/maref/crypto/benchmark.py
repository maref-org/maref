"""国密算法性能基准测试.

提供 SM2/SM3/SM4 各算法的吞吐量指标，用于：
- 开源白皮书性能章节数据支撑
- 与 AES-256/RSA-2048/SHA-256 的对比基准
- 容量规划参考
"""
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING
import structlog
from rich.console import Console
from .sm2 import SM2KeyPair, sm2_decrypt, sm2_encrypt, sm2_sign, sm2_verify
from .sm3 import sm3_hash, sm3_hmac
from .sm4 import sm4_decrypt_cbc, sm4_encrypt_cbc
from .sm4_gcm import sm4_decrypt_gcm, sm4_encrypt_gcm
logger = structlog.get_logger(__name__)
console = Console()
if TYPE_CHECKING:
    from collections.abc import Callable

@dataclass(frozen=True)
class BenchmarkResult:
    """性能基准测试结果."""
    algorithm: str
    operation: str
    iterations: int
    total_seconds: float
    ops_per_second: float
    throughput_mbps: float | None = None

def _benchmark(name: str, op: str, fn: Callable[[], object], iterations: int, data_bytes: int=0) -> BenchmarkResult:
    """运行基准测试."""
    for _ in range(min(10, iterations)):
        fn()
    start = time.perf_counter()
    for _ in range(iterations):
        fn()
    elapsed = time.perf_counter() - start
    ops_per_sec = iterations / elapsed if elapsed > 0 else float('inf')
    throughput = data_bytes * iterations / elapsed / 1048576 if elapsed > 0 and data_bytes > 0 else None
    return BenchmarkResult(algorithm=name, operation=op, iterations=iterations, total_seconds=elapsed, ops_per_second=ops_per_sec, throughput_mbps=throughput)

def run_all_benchmarks(sm2_keypair: SM2KeyPair | None=None, data_size_bytes: int=1024, iterations: int=100) -> list[BenchmarkResult]:
    """运行全部国密算法基准测试.

    Args:
        sm2_keypair: 预生成的 SM2 密钥对（避免测试时间包含生成时间）
        data_size_bytes: 测试数据块大小
        iterations: 每种操作迭代次数

    Returns:
        基准测试结果列表
    """
    if sm2_keypair is None:
        sm2_keypair = SM2KeyPair.generate()
    keypair = sm2_keypair
    data = b'x' * data_size_bytes
    sm4_key = b'3l5butlj26hvv313'
    sm4_iv = b'\x00' * 16
    sm4_nonce = b'\x00' * 12
    results: list[BenchmarkResult] = []
    results.append(_benchmark('SM3', 'hash', lambda : sm3_hash(data), iterations, data_size_bytes))
    results.append(_benchmark('SM3-HMAC', 'hmac', lambda : sm3_hmac(sm4_key, data), iterations, data_size_bytes))

    def _sm4_cbc_roundtrip() -> bytes:
        ct = sm4_encrypt_cbc(sm4_key, sm4_iv, data)
        return sm4_decrypt_cbc(sm4_key, sm4_iv, ct)
    results.append(_benchmark('SM4-CBC', 'encrypt+decrypt', _sm4_cbc_roundtrip, iterations, data_size_bytes))

    def _sm4_gcm_roundtrip() -> bytes:
        enc = sm4_encrypt_gcm(sm4_key, sm4_nonce, data)
        return sm4_decrypt_gcm(sm4_key, sm4_nonce, enc.ciphertext, enc.tag)
    results.append(_benchmark('SM4-GCM', 'encrypt+decrypt', _sm4_gcm_roundtrip, iterations, data_size_bytes))
    sm2_plaintext = b'x' * 32
    results.append(_benchmark('SM2', 'encrypt', lambda : sm2_encrypt(keypair.public_key, sm2_plaintext), iterations))
    sm2_ciphertext = sm2_encrypt(keypair.public_key, sm2_plaintext)
    results.append(_benchmark('SM2', 'decrypt', lambda : sm2_decrypt(keypair.private_key, sm2_ciphertext), iterations))
    results.append(_benchmark('SM2', 'sign', lambda : sm2_sign(keypair.private_key, data, public_key=keypair.public_key, use_sm3=True), iterations, data_size_bytes))
    sig = sm2_sign(keypair.private_key, data, public_key=keypair.public_key, use_sm3=True)
    results.append(_benchmark('SM2', 'verify', lambda : sm2_verify(keypair.public_key, data, sig, use_sm3=True), iterations, data_size_bytes))
    results.append(_benchmark('SM2', 'keypair_generate', lambda : SM2KeyPair.generate(), max(10, iterations // 10)))
    return results

def format_results(results: list[BenchmarkResult]) -> str:
    """格式化基准测试结果表格."""
    lines = ['=' * 80, f"{'Algorithm':<15} {'Operation':<20} {'Ops/sec':>12} {'Throughput':>15} {'Total(s)':>10}", '-' * 80]
    for r in results:
        tp = f'{r.throughput_mbps:.2f} MB/s' if r.throughput_mbps is not None else 'N/A'
        lines.append(f'{r.algorithm:<15} {r.operation:<20} {r.ops_per_second:>12.1f} {tp:>15} {r.total_seconds:>10.3f}')
    lines.append('=' * 80)
    return '\n'.join(lines)
if __name__ == '__main__':
    console.print('MAREF 国密性能基准测试')
    logger.info('生成 SM2 密钥对...')
    kp = SM2KeyPair.generate()
    logger.info('公钥: %s...', kp.public_key[:20])
    console.print()
    results = run_all_benchmarks(kp, data_size_bytes=1024, iterations=100)
    console.print(format_results(results))