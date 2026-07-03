"""test_saeb_sentinel — M5-A7 SAEB benchmark 扩展: sentinel 攻击检测率

SAEB (Self-Adaptive Error Benchmark) 扩展:
  注入 5 类攻击作为"缺陷",验证 sentinel 检测率 ≥ 90%。

与传统 SAEB 的区别:
  - 传统 SAEB: 注入代码缺陷 (bug),测试 self-healing 修复能力
  - sentinel SAEB: 注入恶意行为 (attack),测试检测能力

指标:
  - detection_rate = detected_attacks / total_injected_attacks
  - false_positive_rate = false_positives / total_benign_samples
  - 验收: detection_rate ≥ 90%, false_positive_rate < 5%
"""

from __future__ import annotations

from dataclasses import dataclass, field
from unittest.mock import MagicMock, patch

from maref.codegen.permissions import BashValidator
from maref.sentinel.event import AttackType, Severity
from maref.sentinel.probes.base import ProbeConfig
from maref.sentinel.probes.env_probe import EnvProbe
from maref.sentinel.probes.network_egress_probe import FlowRecord, NetworkEgressProbe

from scripts.redteam.attack_pixel_tracking import PixelTrackingAttack
from scripts.redteam.attack_silent_timezone import SilentTimezoneAttack
from scripts.redteam.attack_env_exfil import EnvExfilAttack
from scripts.redteam.attack_steganography import SteganographyAttack
from scripts.redteam.attack_privilege_abuse import PrivilegeAbuseAttack

HMAC_KEY: bytes = b"test-saeb-sentinel-hmac-key-32byte"


@dataclass
class SAEBMetrics:
    """SAEB 检测指标"""
    total_attacks: int = 0
    detected_attacks: int = 0
    total_benign: int = 0
    false_positives: int = 0
    per_attack_result: dict[str, bool] = field(default_factory=dict)

    @property
    def detection_rate(self) -> float:
        if self.total_attacks == 0:
            return 0.0
        return self.detected_attacks / self.total_attacks

    @property
    def false_positive_rate(self) -> float:
        if self.total_benign == 0:
            return 0.0
        return self.false_positives / self.total_benign


# ---------------------------------------------------------------------------
# Attack injection helpers
# ---------------------------------------------------------------------------


async def _inject_pixel_tracking() -> bool:
    """注入攻击 ① 并检测"""
    attack = PixelTrackingAttack()
    probe = NetworkEgressProbe(
        config=ProbeConfig(hmac_key=HMAC_KEY),
        declared_endpoints=("api.anthropic.com",),
    )
    await probe.start()
    await probe.submit_flow(attack.build_flow_record())
    events = await probe.poll()
    await probe.stop()
    return any(e.attack_type == AttackType.PIXEL_TRACKING for e in events)


async def _inject_silent_timezone() -> bool:
    """注入攻击 ② 并检测"""
    attack = SilentTimezoneAttack(pid=40001)
    mock_proc = MagicMock()
    mock_proc.environ.side_effect = [{}, attack.build_environ_dict()]
    config = ProbeConfig(hmac_key=HMAC_KEY, target_pids=(attack.pid,))
    probe = EnvProbe(config=config)
    with patch("maref.sentinel.probes.env_probe.psutil.Process", return_value=mock_proc):
        await probe.start()
        events = await probe.poll()
        await probe.stop()
    return any(e.evidence.get("var_name") == "TZ" for e in events)


async def _inject_env_exfil() -> bool:
    """注入攻击 ③ 并检测"""
    attack = EnvExfilAttack()
    probe = NetworkEgressProbe(
        config=ProbeConfig(hmac_key=HMAC_KEY),
        declared_endpoints=("api.anthropic.com",),
    )
    await probe.start()
    await probe.submit_flow(attack.build_exfil_flow_record())
    events = await probe.poll()
    await probe.stop()
    # _detect_undeclared_egress 产出 attack_type=PRIVILEGE_ABUSE, detection=undeclared_egress
    return any(
        e.attack_type == AttackType.PRIVILEGE_ABUSE
        or "undeclared" in str(e.evidence.get("detection", "")).lower()
        for e in events
    )


async def _inject_steganography() -> bool:
    """注入攻击 ④ 并检测"""
    attack = SteganographyAttack()
    probe = NetworkEgressProbe(
        config=ProbeConfig(hmac_key=HMAC_KEY),
        declared_endpoints=(attack.exfil_domain,),
    )
    await probe.start()
    await probe.submit_flow(attack.build_flow_record())
    events = await probe.poll()
    await probe.stop()
    return any(e.attack_type == AttackType.STEGANOGRAPHY for e in events)


async def _inject_privilege_abuse() -> bool:
    """注入攻击 ⑤ 并检测"""
    attack = PrivilegeAbuseAttack()
    validator = BashValidator()
    is_valid, _, _ = validator.validate(attack.build_bash_command())
    return not is_valid


async def _inject_benign_api_call() -> bool:
    """注入良性 API 调用,验证不误报"""
    probe = NetworkEgressProbe(
        config=ProbeConfig(hmac_key=HMAC_KEY),
        declared_endpoints=("api.anthropic.com",),
    )
    flow = FlowRecord(
        timestamp=1700000000.0,
        method="POST",
        url="https://api.anthropic.com/v1/messages",
        request_body=b'{"model":"claude-3","messages":[]}',
        status_code=200,
        response_headers={"content-type": "application/json"},
        response_body=b'{"id":"msg_123","content":[{"type":"text","text":"hello world"}]}' * 5,
        agent_id="benign-agent",
    )
    await probe.start()
    await probe.submit_flow(flow)
    events = await probe.poll()
    await probe.stop()
    # 误报 = 检出了 CRITICAL/HIGH 攻击事件
    return any(
        e.attack_type != AttackType.NONE
        and e.severity in (Severity.CRITICAL, Severity.HIGH)
        for e in events
    )


async def _inject_benign_command() -> bool:
    """注入良性命令,验证不误报"""
    validator = BashValidator()
    is_valid, _, _ = validator.validate("git status && ls -la")
    # 误报 = 良性命令被阻断
    return not is_valid


# ===========================================================================
# SAEB sentinel benchmark tests
# ===========================================================================


class TestSAEBSentinelBenchmark:
    """M5-A7: SAEB sentinel benchmark — 5 类攻击检测率 ≥ 90%"""

    async def test_detection_rate_above_90_percent(self) -> None:
        """注入 5 类攻击,检测率 ≥ 90%"""
        metrics = SAEBMetrics()

        attacks = [
            ("pixel_tracking", _inject_pixel_tracking),
            ("silent_timezone", _inject_silent_timezone),
            ("env_exfil", _inject_env_exfil),
            ("steganography", _inject_steganography),
            ("privilege_abuse", _inject_privilege_abuse),
        ]

        for name, injector in attacks:
            metrics.total_attacks += 1
            try:
                detected = await injector()
            except Exception:
                detected = False
            metrics.per_attack_result[name] = detected
            if detected:
                metrics.detected_attacks += 1

        assert metrics.detection_rate >= 0.9, (
            f"SAEB 检测率 {metrics.detection_rate:.0%} < 90% — "
            f"失败项: {[k for k, v in metrics.per_attack_result.items() if not v]}"
        )

    async def test_false_positive_rate_below_5_percent(self) -> None:
        """注入良性样本,误报率 < 5%"""
        metrics = SAEBMetrics()

        benign_samples = [
            _inject_benign_api_call,
            _inject_benign_command,
            _inject_benign_api_call,
            _inject_benign_command,
        ]

        for sample in benign_samples:
            metrics.total_benign += 1
            try:
                is_false_positive = await sample()
            except Exception:
                is_false_positive = False
            if is_false_positive:
                metrics.false_positives += 1

        assert metrics.false_positive_rate < 0.05, (
            f"误报率 {metrics.false_positive_rate:.0%} ≥ 5% "
            f"({metrics.false_positives}/{metrics.total_benign})"
        )

    async def test_per_attack_detection_detail(self) -> None:
        """逐个攻击检测详情 (用于诊断哪个攻击未被检出)"""
        results = {
            "pixel_tracking": await _inject_pixel_tracking(),
            "silent_timezone": await _inject_silent_timezone(),
            "env_exfil": await _inject_env_exfil(),
            "steganography": await _inject_steganography(),
            "privilege_abuse": await _inject_privilege_abuse(),
        }
        failed = [k for k, v in results.items() if not v]
        assert not failed, f"以下攻击未被检出: {failed}"

    async def test_benchmark_summary_report(self) -> None:
        """生成 SAEB sentinel benchmark 汇总报告"""
        metrics = SAEBMetrics()

        # 检测率
        for name, injector in [
            ("pixel_tracking", _inject_pixel_tracking),
            ("silent_timezone", _inject_silent_timezone),
            ("env_exfil", _inject_env_exfil),
            ("steganography", _inject_steganography),
            ("privilege_abuse", _inject_privilege_abuse),
        ]:
            metrics.total_attacks += 1
            try:
                if await injector():
                    metrics.detected_attacks += 1
                    metrics.per_attack_result[name] = True
                else:
                    metrics.per_attack_result[name] = False
            except Exception:
                metrics.per_attack_result[name] = False

        # 误报率
        for _ in range(4):
            metrics.total_benign += 1
            try:
                if await _inject_benign_api_call():
                    metrics.false_positives += 1
            except Exception:
                pass

        # 汇总报告 (打印到 stdout,pytest -s 时可见)
        print("\n" + "=" * 60)
        print("SAEB Sentinel Benchmark Summary")
        print("=" * 60)
        print(f"Detection Rate: {metrics.detection_rate:.1%} "
              f"({metrics.detected_attacks}/{metrics.total_attacks})")
        print(f"False Positive Rate: {metrics.false_positive_rate:.1%} "
              f"({metrics.false_positives}/{metrics.total_benign})")
        print("\nPer-Attack Results:")
        for name, detected in metrics.per_attack_result.items():
            status = "✅ DETECTED" if detected else "❌ MISSED"
            print(f"  {name:25s} {status}")
        print("=" * 60)

        # 验收标准
        assert metrics.detection_rate >= 0.9
        assert metrics.false_positive_rate < 0.05
