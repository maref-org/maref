"""
maref.sentinel.probes — 观测 Probe 套件

每个 Probe 负责一类行为的检测,产出一组 ObservationEvent。
所有 Probe 必须继承 Probe 抽象基类,实现 start/stop/poll 三个协程接口。

M1 已实现:
- ProcessProbe — 进程行为检测 (ptrace/SYS_ptrace 等调试器附加) — 攻击 ⑤
- EnvProbe — 环境变量读取检测 (ANTHROPIC_BASE_URL) — 攻击 ③
- FileProbe — 文件访问检测 (敏感路径如 ~/.ssh / /etc/passwd) — 通用
- TimezoneProbe — 时区静默读取检测 (/etc/localtime, TZ env) — 攻击 ②
- NetworkEgressProbe — 出站流量检测 (mitmproxy + 像素/隐写/未声明外联) — 攻击 ①④
- PromptBaselineProbe — prompt 隐蔽指令检测 (零宽字符/同形字) — 攻击 ④
"""

from __future__ import annotations

from maref.sentinel.probes.base import Probe, ProbeConfig
from maref.sentinel.probes.env_probe import EnvProbe
from maref.sentinel.probes.file_probe import FileProbe
from maref.sentinel.probes.network_egress_probe import FlowRecord, NetworkEgressProbe
from maref.sentinel.probes.process_probe import ProcessProbe
from maref.sentinel.probes.prompt_baseline_probe import (
    PromptBaselineProbe,
    PromptSubmission,
)
from maref.sentinel.probes.timezone_probe import TimezoneProbe

__all__: list[str] = [
    "Probe",
    "ProbeConfig",
    "ProcessProbe",
    "EnvProbe",
    "FileProbe",
    "TimezoneProbe",
    "NetworkEgressProbe",
    "FlowRecord",
    "PromptBaselineProbe",
    "PromptSubmission",
]
