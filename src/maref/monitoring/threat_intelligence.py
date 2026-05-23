"""
威胁情报集成器

集成多源威胁情报（CVE、OSINT、商业源），提供实时威胁检测和IOC管理。
支持自动化匹配和风险评分。

数据源:
- CVE/NVD 数据库
- OSV 开源漏洞数据库
- GitHub Security Advisories
- OSINT 开源情报
"""

from __future__ import annotations

import hashlib
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any


class ThreatSeverity(Enum):
    """威胁严重程度"""
    CRITICAL = "critical"    # CVSS 9.0+
    HIGH = "high"            # CVSS 7.0-8.9
    MEDIUM = "medium"        # CVSS 4.0-6.9
    LOW = "low"              # CVSS 0.1-3.9
    NONE = "none"            # CVSS 0.0


class IOCType(Enum):
    """IOC (Indicators of Compromise) 类型"""
    IP_ADDRESS = "ip"
    DOMAIN = "domain"
    URL = "url"
    FILE_HASH = "file_hash"
    EMAIL = "email"
    REGISTRY_KEY = "registry_key"
    PROCESS_NAME = "process"
    CVE = "cve"
    CUSTOM = "custom"


class ThreatSource(Enum):
    """威胁情报源"""
    CVE_NVD = "cve_nvd"
    OSV = "osv"
    GITHUB_SECURITY = "github_security"
    OSINT_FEED = "osint_feed"
    PYUP = "pyup"
    SNYK = "snyk"
    CUSTOM_FEED = "custom_feed"
    INTERNAL = "internal"


@dataclass
class ThreatIndicator:
    """威胁指标"""

    indicator_id: str
    indicator_type: IOCType
    value: str
    source: ThreatSource
    severity: ThreatSeverity
    description: str
    confidence: float  # 0.0-1.0
    first_seen: datetime
    last_seen: datetime
    tags: list[str] = field(default_factory=list)
    related_cves: list[str] = field(default_factory=list)
    mitre_techniques: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "indicator_id": self.indicator_id,
            "type": self.indicator_type.value,
            "value": self.value,
            "source": self.source.value,
            "severity": self.severity.value,
            "confidence": round(self.confidence, 2),
            "first_seen": self.first_seen.isoformat(),
            "last_seen": self.last_seen.isoformat(),
            "tags": self.tags,
            "related_cves": self.related_cves,
            "mitre_techniques": self.mitre_techniques,
        }

    def compute_hash(self) -> str:
        data = f"{self.indicator_type.value}:{self.value}:{self.source.value}"
        return hashlib.sha256(data.encode()).hexdigest()


@dataclass
class VulnerabilityReport:
    """漏洞报告"""

    report_id: str
    cve_id: str | None
    title: str
    description: str
    severity: ThreatSeverity
    cvss_score: float | None
    affected_components: list[str]
    fixed_versions: list[str]
    published_at: datetime
    updated_at: datetime
    references: list[str] = field(default_factory=list)
    exploit_available: bool = False
    patch_available: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_id": self.report_id,
            "cve_id": self.cve_id,
            "title": self.title,
            "description": self.description,
            "severity": self.severity.value,
            "cvss_score": self.cvss_score,
            "affected_components": self.affected_components,
            "fixed_versions": self.fixed_versions,
            "published_at": self.published_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "references": self.references,
            "exploit_available": self.exploit_available,
            "patch_available": self.patch_available,
        }


@dataclass
class ThreatAlert:
    """威胁告警"""

    alert_id: str
    alert_type: str  # "vulnerability", "ioc_match", "anomaly"
    severity: ThreatSeverity
    title: str
    description: str
    detected_at: datetime
    affected_assets: list[str]
    recommended_actions: list[str]
    is_active: bool = True
    resolved_at: datetime | None = None
    assigned_to: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "alert_id": self.alert_id,
            "type": self.alert_type,
            "severity": self.severity.value,
            "title": self.title,
            "description": self.description,
            "detected_at": self.detected_at.isoformat(),
            "affected_assets": self.affected_assets,
            "recommended_actions": self.recommended_actions,
            "is_active": self.is_active,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "assigned_to": self.assigned_to,
        }


class ThreatIntelligenceEngine:
    """
    威胁情报引擎

    管理和处理多源威胁情报数据，提供实时IOC匹配和威胁分析。
    """

    def __init__(self):
        self._indicators: dict[str, ThreatIndicator] = {}
        self._vulnerabilities: dict[str, VulnerabilityReport] = {}
        self._alerts: dict[str, ThreatAlert] = []
        self._ioc_index: dict[IOCType, dict[str, str]] = defaultdict(dict)  # type -> value -> indicator_id
        self._alert_history: list[ThreatAlert] = []
        self._threat_cache: dict[str, Any] = {}
        self._last_update: dict[ThreatSource, datetime] = {}

        self._initialize_builtin_indicators()

    def _initialize_builtin_indicators(self) -> None:
        """初始化内置威胁指标"""
        now = datetime.now()

        builtin = [
            ThreatIndicator(
                indicator_id="ioc-builtin-001",
                indicator_type=IOCType.CVE,
                value="CVE-2024-3094",
                source=ThreatSource.OSV,
                severity=ThreatSeverity.CRITICAL,
                description="XZ Utils backdoor - malicious code in liblzma",
                confidence=1.0,
                first_seen=now - timedelta(days=60),
                last_seen=now,
                tags=["supply_chain", "backdoor", "xz"],
                related_cves=["CVE-2024-3094"],
                mitre_techniques=["T1195.001", "T1574.001"],
            ),
            ThreatIndicator(
                indicator_id="ioc-builtin-002",
                indicator_type=IOCType.CVE,
                value="CVE-2024-4577",
                source=ThreatSource.CVE_NVD,
                severity=ThreatSeverity.CRITICAL,
                description="PHP CGI argument injection vulnerability",
                confidence=1.0,
                first_seen=now - timedelta(days=45),
                last_seen=now,
                tags=["rce", "php", "cgi"],
                related_cves=["CVE-2024-4577"],
                mitre_techniques=["T1190"],
            ),
        ]

        for indicator in builtin:
            self.add_indicator(indicator)

    def add_indicator(self, indicator: ThreatIndicator) -> str:
        """添加威胁指标"""
        self._indicators[indicator.indicator_id] = indicator

        indicator.compute_hash()
        self._ioc_index[indicator.indicator_type][indicator.value] = indicator.indicator_id

        self._last_update[indicator.source] = datetime.now()

        return indicator.indicator_id

    def add_vulnerability(self, vuln: VulnerabilityReport) -> str:
        """添加漏洞报告"""
        self._vulnerabilities[vuln.report_id] = vuln

        # 也为CVE创建指标
        if vuln.cve_id:
            indicator = ThreatIndicator(
                indicator_id=f"ioc-{vuln.cve_id}",
                indicator_type=IOCType.CVE,
                value=vuln.cve_id,
                source=ThreatSource.CVE_NVD,
                severity=vuln.severity,
                description=vuln.title,
                confidence=0.9,
                first_seen=vuln.published_at,
                last_seen=vuln.updated_at,
                related_cves=[vuln.cve_id],
            )
            self.add_indicator(indicator)

        return vuln.report_id

    def search_ioc(self, ioc_type: IOCType, value: str) -> ThreatIndicator | None:
        """搜索IOC"""
        indicator_id = self._ioc_index.get(ioc_type, {}).get(value)
        if indicator_id:
            return self._indicators.get(indicator_id)
        return None

    def match_against_indicators(self, target_value: str) -> list[ThreatIndicator]:
        """
        将目标值与所有指标匹配

        Args:
            target_value: 要匹配的值（IP、哈希、域名等）

        Returns:
            匹配到的威胁指标列表
        """
        matches: list[ThreatIndicator] = []

        for _ioc_type, value_index in self._ioc_index.items():
            if target_value in value_index:
                indicator_id = value_index[target_value]
                indicator = self._indicators.get(indicator_id)
                if indicator:
                    matches.append(indicator)

        # 按严重程度排序
        severity_order = {
            ThreatSeverity.CRITICAL: 0,
            ThreatSeverity.HIGH: 1,
            ThreatSeverity.MEDIUM: 2,
            ThreatSeverity.LOW: 3,
        }
        matches.sort(key=lambda x: severity_order.get(x.severity, 4))

        return matches

    def scan_components(self, components: list[dict[str, str]]) -> dict[str, Any]:
        """
        扫描组件以检测已知漏洞

        Args:
            components: 组件列表 [{"name": "...", "version": "..."}, ...]

        Returns:
            扫描结果字典
        """
        vulnerabilities_found: list[dict[str, Any]] = []

        for component in components:
            name = component.get("name", "")
            version = component.get("version", "")

            # 在已知漏洞中搜索匹配
            for vuln in self._vulnerabilities.values():
                for affected in vuln.affected_components:
                    if name.lower() in affected.lower():
                        vulnerabilities_found.append({
                            "component": name,
                            "version": version,
                            "vulnerability": vuln.to_dict(),
                        })

        risk_level = ThreatSeverity.NONE
        if vulnerabilities_found:
            severities = [v["vulnerability"]["severity"] for v in vulnerabilities_found]
            if any(s == ThreatSeverity.CRITICAL.value for s in severities):
                risk_level = ThreatSeverity.CRITICAL
            elif any(s == ThreatSeverity.HIGH.value for s in severities):
                risk_level = ThreatSeverity.HIGH
            elif any(s == ThreatSeverity.MEDIUM.value for s in severities):
                risk_level = ThreatSeverity.MEDIUM
            else:
                risk_level = ThreatSeverity.LOW

        return {
            "scanned_at": datetime.now().isoformat(),
            "components_scanned": len(components),
            "vulnerabilities_found": len(vulnerabilities_found),
            "risk_level": risk_level.value,
            "findings": vulnerabilities_found,
        }

    def create_alert(
        self,
        alert_type: str,
        severity: ThreatSeverity,
        title: str,
        description: str,
        affected_assets: list[str],
        recommended_actions: list[str],
    ) -> ThreatAlert:
        """创建威胁告警"""
        alert = ThreatAlert(
            alert_id=f"alert-{int(time.time())}-{len(self._alert_history)}",
            alert_type=alert_type,
            severity=severity,
            title=title,
            description=description,
            detected_at=datetime.now(),
            affected_assets=affected_assets,
            recommended_actions=recommended_actions,
        )

        self._alerts.append(alert)
        self._alert_history.append(alert)
        return alert

    def resolve_alert(self, alert_id: str) -> bool:
        """解决告警"""
        for alert in self._alerts:
            if alert.alert_id == alert_id and alert.is_active:
                alert.is_active = False
                alert.resolved_at = datetime.now()
                return True
        return False

    def get_active_alerts(self, min_severity: ThreatSeverity | None = None) -> list[ThreatAlert]:
        """获取活跃告警"""
        active = [a for a in self._alerts if a.is_active]

        if min_severity:
            severity_levels = {
                ThreatSeverity.CRITICAL: 4,
                ThreatSeverity.HIGH: 3,
                ThreatSeverity.MEDIUM: 2,
                ThreatSeverity.LOW: 1,
                ThreatSeverity.NONE: 0,
            }
            min_level = severity_levels[min_severity]
            active = [a for a in active if severity_levels.get(a.severity, 0) >= min_level]

        return sorted(active, key=lambda a: a.detected_at, reverse=True)

    def get_threat_summary(self) -> dict[str, Any]:
        """获取威胁态势摘要"""
        active_alerts = self.get_active_alerts()

        severity_counts = {
            "critical": 0, "high": 0, "medium": 0, "low": 0
        }
        for alert in active_alerts:
            severity_counts[alert.severity.value] += 1

        return {
            "generated_at": datetime.now().isoformat(),
            "total_indicators": len(self._indicators),
            "total_vulnerabilities": len(self._vulnerabilities),
            "active_alerts": len(active_alerts),
            "severity_breakdown": severity_counts,
            "threat_sources": {
                source.value: True for source in self._last_update
            },
            "last_update": {
                source.value: dt.isoformat()
                for source, dt in self._last_update.items()
            },
        }

    def export_indicators(self, source: ThreatSource | None = None) -> list[dict[str, Any]]:
        """导出威胁指标"""
        indicators = self._indicators.values()
        if source:
            indicators = [i for i in indicators if i.source == source]
        return [i.to_dict() for i in indicators]

    def assess_threat_for_asset(self, asset_id: str, asset_info: dict[str, Any]) -> dict[str, Any]:
        """
        评估特定资产的威胁风险

        Args:
            asset_id: 资产ID
            asset_info: 资产信息

        Returns:
            风险评估结果
        """
        # 查找匹配的IOC
        matched_iocs: list[dict[str, Any]] = []

        # 检查资产的各种属性
        for key, value in asset_info.items():
            if isinstance(value, str):
                matches = self.match_against_indicators(value)
                for m in matches:
                    matched_iocs.append({
                        "matched_field": key,
                        "indicator": m.to_dict(),
                    })

        # 计算风险评分
        risk_score = 0.0
        if matched_iocs:
            severity_scores = {
                "critical": 10.0,
                "high": 7.5,
                "medium": 5.0,
                "low": 2.5,
            }
            for match in matched_iocs:
                sev = match["indicator"]["severity"]
                risk_score = max(risk_score, severity_scores.get(sev, 0.0))

        risk_level = "low"
        if risk_score >= 9:
            risk_level = "critical"
        elif risk_score >= 7:
            risk_level = "high"
        elif risk_score >= 4:
            risk_level = "medium"

        return {
            "asset_id": asset_id,
            "assessment_time": datetime.now().isoformat(),
            "risk_score": round(risk_score, 1),
            "risk_level": risk_level,
            "matched_iocs": len(matched_iocs),
            "ioc_details": matched_iocs,
            "recommendation": "Review matched indicators and apply mitigations" if matched_iocs else "No threats detected",
        }


def create_threat_intelligence() -> ThreatIntelligenceEngine:
    """创建威胁情报引擎"""
    return ThreatIntelligenceEngine()


__all__ = [
    "ThreatIntelligenceEngine",
    "ThreatIndicator",
    "VulnerabilityReport",
    "ThreatAlert",
    "ThreatSeverity",
    "IOCType",
    "ThreatSource",
    "create_threat_intelligence",
]
