"""G1 外部身份指纹测试 (v0.52.1 M2)。

覆盖:
- ExternalAccountRegistry 账号登记/未声明检测
- IdentityFingerprint 指纹提取与相似度
- SybilDetector 多重身份聚类
- CollusionDetector 自导自演/互相背书/跨代理共享
- IdentityProbe sentinel 事件
"""

from __future__ import annotations

import asyncio
import time

from maref.sentinel.event import AttackType, Severity
from maref.sentinel.identity import (
    CollusionDetector,
    CollusionKind,
    EndorsementEvent,
    EndorsementKind,
    ExternalAccount,
    ExternalAccountRegistry,
    IdentityFingerprint,
    IdentityProbe,
    PlatformType,
    SybilDetector,
)
from maref.sentinel.probes.base import ProbeConfig


def _account(
    handle: str,
    agent_did: str = "agent-01",
    declared: bool = False,
    platform: PlatformType = PlatformType.GITHUB,
    first_seen: float | None = None,
    ip_hash: str = "ip1",
    ua_hash: str = "ua1",
) -> ExternalAccount:
    return ExternalAccount(
        platform=platform,
        handle=handle,
        agent_did=agent_did,
        declared=declared,
        first_seen=first_seen or time.time(),
        ip_hash=ip_hash,
        ua_hash=ua_hash,
    )


class TestExternalAccountRegistry:
    def test_register_and_get(self):
        reg = ExternalAccountRegistry()
        acc = _account("dev-x", declared=True)
        reg.register(acc)
        got = reg.get(PlatformType.GITHUB, "dev-x")
        assert got is not None
        assert got.handle == "dev-x"

    def test_register_idempotent(self):
        reg = ExternalAccountRegistry()
        acc = _account("dev-x")
        reg.register(acc)
        count_after_first = reg.count()
        reg.register(_account("dev-x"))  # 同 handle → 更新不重复
        assert reg.count() == count_after_first

    def test_undeclared_accounts(self):
        reg = ExternalAccountRegistry()
        reg.register(_account("declared-a", declared=True))
        reg.register(_account("hidden-b", declared=False))
        undeclared = reg.undeclared_accounts()
        assert [u.handle for u in undeclared] == ["hidden-b"]

    def test_mark_declared(self):
        reg = ExternalAccountRegistry()
        reg.register(_account("dev-x", declared=False))
        assert reg.mark_declared(PlatformType.GITHUB, "dev-x") is True
        assert reg.get(PlatformType.GITHUB, "dev-x").declared is True

    def test_list_by_agent(self):
        reg = ExternalAccountRegistry()
        reg.register(_account("a1", agent_did="agent-01"))
        reg.register(_account("a2", agent_did="agent-02"))
        assert len(reg.list_by_agent("agent-01")) == 1
        assert len(reg.list_by_agent("agent-02")) == 1

    def test_missing_handle_none(self):
        reg = ExternalAccountRegistry()
        assert reg.get(PlatformType.GITHUB, "nope") is None


class TestIdentityFingerprint:
    def _profiles(self) -> tuple:
        fp = IdentityFingerprint()
        t = time.time()
        p1 = fp.extract_profile(
            texts=["提交了修复程序", "更新了依赖版本", "修复了测试用例"],
            timestamps=[t, t + 100, t + 200],
            ip_hash="ip1",
            ua_hash="ua1",
        )
        p2 = fp.extract_profile(
            texts=["修复程序已提交", "依赖版本已更新", "测试用例通过"],
            timestamps=[t + 50, t + 150, t + 250],
            ip_hash="ip1",
            ua_hash="ua1",
        )
        p3 = fp.extract_profile(
            texts=[
                "今天天气很好我们去公园散步顺便买杯咖啡",
                "周末准备去爬山看日出",
                "晚上看了部电影然后睡觉",
            ],
            timestamps=[t + 1000],
            ip_hash="ip99",
            ua_hash="ua99",
        )
        return fp, p1, p2, p3

    def test_similar_profiles_high_similarity(self):
        _, p1, p2, _ = self._profiles()
        sim = IdentityFingerprint().similarity(p1, p2)
        assert sim >= 0.7

    def test_different_profiles_low_similarity(self):
        _, p1, _, p3 = self._profiles()
        sim = IdentityFingerprint().similarity(p1, p3)
        assert sim < 0.6

    def test_identical_self_similarity(self):
        fp, p1, _, _ = self._profiles()
        assert fp.similarity(p1, p1) == 1.0

    def test_profile_to_dict(self):
        _, p1, _, _ = self._profiles()
        d = p1.to_dict()
        assert d["ngram_count"] > 0
        assert len(d["active_buckets"]) == 6

    def test_egress_mismatch_zero_not_neutral(self):
        # G1-I1: 双不匹配网络出口 → 0.0 (非中性 0.5)
        from maref.sentinel.identity import FingerprintProfile

        fp = IdentityFingerprint()
        a = FingerprintProfile(ip_hash="ipA", ua_hash="uaA")
        b = FingerprintProfile(ip_hash="ipB", ua_hash="uaB")
        assert fp._egress_similarity(a, b) == 0.0
        # 无数据仍中性
        assert fp._egress_similarity(
            FingerprintProfile(), FingerprintProfile()
        ) == 0.5


class TestSybilDetector:
    def _setup(self) -> tuple:
        reg = ExternalAccountRegistry()
        t = time.time()
        a1 = _account("dev-alfa", declared=True, first_seen=t - 2000)
        a2 = _account("dev-beta", declared=False, first_seen=t - 1000)
        a3 = _account("dev-gamma", declared=False, first_seen=t - 500)
        for a in (a1, a2, a3):
            reg.register(a)

        fp = IdentityFingerprint()
        profs = {}
        texts = ["提交了修复程序", "更新了依赖版本", "修复了测试用例"]
        for a in (a1, a2, a3):
            profs[a.account_id] = fp.extract_profile(
                texts=texts,
                timestamps=[t] * 5,
                ip_hash="ip1",
                ua_hash="ua1",
                profile_id=a.account_id,
            )
        return reg, profs

    def test_detect_sybil_cluster(self):
        reg, profs = self._setup()
        clusters = SybilDetector().detect(reg.all_accounts(), profs)
        assert len(clusters) >= 1
        cluster = clusters[0]
        assert len(cluster.account_ids) >= 2
        assert "fingerprint_similarity" in cluster.signals
        assert cluster.agent_did == "agent-01"

    def test_no_signal_when_disparate(self):
        reg = ExternalAccountRegistry()
        t = time.time()
        a1 = _account("normal-1", declared=True, first_seen=t)
        a2 = _account("normal-2", declared=True, first_seen=t)
        reg.register(a1)
        reg.register(a2)

        fp = IdentityFingerprint()
        p1 = fp.extract_profile(["今天天气很好我们去公园散步"], [t], "ipA", "uaA")
        p2 = fp.extract_profile(["量子物理实验报告分析数据"], [t + 999999], "ipB", "uaB")
        clusters = SybilDetector().detect(
            reg.all_accounts(), {a1.account_id: p1, a2.account_id: p2}
        )
        assert clusters == []

    def test_short_window_multi_account(self):
        reg, profs = self._setup()
        clusters = SybilDetector().detect(reg.all_accounts(), {})
        # 无指纹, 但短窗口多账号信号应触发
        sybil = [c for c in clusters if "short_window_multi" in c.signals]
        assert len(sybil) >= 1

    def test_short_window_excludes_early_accounts(self):
        # G1-I2: 短窗口聚类不得拖入窗口外的早期账号
        import time as _time

        reg = ExternalAccountRegistry()
        t = _time.time()
        reg.register(
            _account("early-real", declared=True, first_seen=t - 47 * 3600)
        )
        for i in range(3):
            reg.register(
                _account(f"fake-{i}", declared=False, first_seen=t - (3 - i) * 3600)
            )
        detector = SybilDetector(window_hours=24)
        groups = detector._cluster_by_window(reg.all_accounts())
        early_id = reg.get(PlatformType.GITHUB, "early-real").account_id
        assert not any(early_id in g for g in groups)

    def test_cluster_to_dict(self):
        reg, profs = self._setup()
        clusters = SybilDetector().detect(reg.all_accounts(), profs)
        d = clusters[0].to_dict()
        assert d["confidence"] > 0
        assert "signals" in d


class TestCollusionDetector:
    def test_self_endorsement_same_agent(self):
        detector = CollusionDetector()
        detector.record_endorsement(
            EndorsementEvent(
                endorser_account="acct-a",
                target_account="acct-b",
                action=EndorsementKind.REVIEW,
                agent_did="agent-01",
                target_agent_did="agent-01",
            )
        )
        report = detector.detect()
        assert report.has_signal
        kinds = {e.kind for e in report.events}
        assert CollusionKind.SELF_ENDORSEMENT in kinds

    def test_mutual_endorsement(self):
        detector = CollusionDetector()
        detector.record_endorsement(
            EndorsementEvent(endorser_account="a", target_account="b", action=EndorsementKind.THANK)
        )
        detector.record_endorsement(
            EndorsementEvent(endorser_account="b", target_account="a", action=EndorsementKind.THANK)
        )
        report = detector.detect()
        kinds = {e.kind for e in report.events}
        assert CollusionKind.MUTUAL_ENDORSEMENT in kinds

    def test_cross_agent_account_share(self):
        detector = CollusionDetector()
        # 同一外部句柄 (platform+handle) 被两个不同 agent 使用 → 共享
        acc1 = _account("shared-acct", agent_did="agent-01")
        acc2 = _account("shared-acct", agent_did="agent-02")  # 同 handle, 不同 agent
        report = detector.detect(accounts=[acc1, acc2])
        kinds = {e.kind for e in report.events}
        assert CollusionKind.CROSS_AGENT_SHARE in kinds

    def test_share_event(self):
        detector = CollusionDetector()
        detector.record_endorsement(
            EndorsementEvent(
                endorser_account="legacy-holder",
                action=EndorsementKind.SHARE,
                shared_resource="账号与token遗产",
            )
        )
        report = detector.detect()
        kinds = {e.kind for e in report.events}
        assert CollusionKind.CROSS_AGENT_SHARE in kinds

    def test_report_to_dict(self):
        detector = CollusionDetector()
        detector.record_endorsement(
            EndorsementEvent(
                endorser_account="a",
                target_account="b",
                action=EndorsementKind.REVIEW,
                agent_did="agent-01",
                target_agent_did="agent-01",
            )
        )
        report = detector.detect()
        d = report.to_dict()
        assert d["max_confidence"] > 0
        assert d["endorsement_count"] == 1

    def test_min_confidence_filters_events(self):
        # G1-I3: min_confidence 过滤低置信度事件
        detector = CollusionDetector(min_confidence=0.9)
        detector.record_endorsement(
            EndorsementEvent(endorser_account="a", target_account="b", action=EndorsementKind.THANK)
        )
        detector.record_endorsement(
            EndorsementEvent(endorser_account="b", target_account="a", action=EndorsementKind.THANK)
        )
        report = detector.detect()
        assert report.events == []  # mutual_endorsement 0.75 < 0.9 被过滤


class TestIdentityProbe:
    async def _poll(self, probe: IdentityProbe) -> list:
        return await probe.poll()

    def test_probe_emits_spoofing_events(self):
        reg = ExternalAccountRegistry()
        reg.register(_account("undeclared-1", declared=False))
        reg.register(_account("declared-1", declared=True))
        probe = IdentityProbe(config=ProbeConfig(hmac_key=b"k"), registry=reg)

        async def run() -> list:
            return await self._poll(probe)

        events = asyncio.run(run())
        spoofing = [e for e in events if e.attack_type == AttackType.IDENTITY_SPOOFING]
        assert len(spoofing) == 1
        assert spoofing[0].severity == Severity.HIGH
        assert spoofing[0].source == "identity"
        assert spoofing[0].hash  # HMAC 签名

    def test_probe_emits_sybil_events(self):
        reg = ExternalAccountRegistry()
        t = time.time()
        accs = [
            _account("s1", declared=False, first_seen=t - 100),
            _account("s2", declared=False, first_seen=t - 80),
            _account("s3", declared=False, first_seen=t - 60),
        ]
        for a in accs:
            reg.register(a)
        fp = IdentityFingerprint()
        profs = {}
        for a in accs:
            profs[a.account_id] = fp.extract_profile(
                ["提交修复程序", "更新依赖", "修复测试"],
                [t] * 3,
                "ip1",
                "ua1",
                profile_id=a.account_id,
            )
        sybil = SybilDetector()
        probe = IdentityProbe(
            config=ProbeConfig(hmac_key=b"k"),
            registry=reg,
            sybil_detector=sybil,
        )
        for a in accs:
            probe.submit_account(a, profs[a.account_id])

        events = asyncio.run(self._poll(probe))
        sybil_events = [e for e in events if e.attack_type == AttackType.SYBIL_ATTACK]
        assert len(sybil_events) >= 1

    def test_probe_dedup(self):
        reg = ExternalAccountRegistry()
        reg.register(_account("und-1", declared=False))
        probe = IdentityProbe(config=ProbeConfig(hmac_key=b"k"), registry=reg)
        first = asyncio.run(self._poll(probe))
        second = asyncio.run(self._poll(probe))
        assert len(first) == 1
        assert second == []  # 去重

    def test_submit_account_profile_lands_on_effective_record(self):
        # G1-I4: 幂等命中时 profile 归到 registry 生效记录 (非孤儿 key)
        import time as _time

        reg = ExternalAccountRegistry()
        fp = IdentityFingerprint()
        probe = IdentityProbe(
            config=ProbeConfig(hmac_key=b"k"), registry=reg, sybil_detector=SybilDetector()
        )
        a1 = _account("shared", agent_did="agent-01", first_seen=_time.time() - 100)
        a2 = _account("shared", agent_did="agent-02", first_seen=_time.time() - 50)
        p1 = fp.extract_profile(["提交修复"], [_time.time()], "ip1", "ua1", profile_id="p1")
        p2 = fp.extract_profile(["提交修复"], [_time.time()], "ip1", "ua1", profile_id="p2")
        probe.submit_account(a1, p1)
        probe.submit_account(a2, p2)
        effective = reg.get(PlatformType.GITHUB, "shared").account_id
        assert effective in probe.submitted_profiles()
        # 无孤儿 profile key
        assert all(k == effective for k in probe.submitted_profiles())

    def test_probe_emits_collusion_critical(self):
        reg = ExternalAccountRegistry()
        collusion = CollusionDetector()
        collusion.record_endorsement(
            EndorsementEvent(
                endorser_account="a",
                target_account="b",
                action=EndorsementKind.REVIEW,
                agent_did="agent-01",
                target_agent_did="agent-01",
            )
        )
        probe = IdentityProbe(
            config=ProbeConfig(hmac_key=b"k"),
            registry=reg,
            collusion_detector=collusion,
        )
        events = asyncio.run(self._poll(probe))
        crit = [e for e in events if e.severity == Severity.CRITICAL]
        assert len(crit) >= 1
