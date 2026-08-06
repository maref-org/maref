"""M5 红蓝对抗攻击模拟器 — 5 类针对中国用户的恶意 Agent 行为模拟。

每个模拟器生成对应 Probe 期望的输入数据 (FlowRecord / environ dict / 命令字符串等),
不实际执行恶意代码,保证测试安全可重复。

攻击类型对应:
  ① pixel_tracking    — 邮件像素追踪 (NetworkEgressProbe)
  ② silent_timezone   — 静默时区读取 (TimezoneProbe + EnvProbe)
  ③ env_exfil         — 环境变量外泄 (EnvProbe + NetworkEgressProbe)
  ④ steganography     — 日期分隔符隐写 (NetworkEgressProbe)
  ⑤ privilege_abuse   — 权限滥用 (BashValidator + SeccompFilter)
"""

from scripts.redteam.attack_pixel_tracking import PixelTrackingAttack
from scripts.redteam.attack_silent_timezone import SilentTimezoneAttack
from scripts.redteam.attack_env_exfil import EnvExfilAttack
from scripts.redteam.attack_steganography import SteganographyAttack
from scripts.redteam.attack_privilege_abuse import PrivilegeAbuseAttack

__all__ = [
    "PixelTrackingAttack",
    "SilentTimezoneAttack",
    "EnvExfilAttack",
    "SteganographyAttack",
    "PrivilegeAbuseAttack",
]
