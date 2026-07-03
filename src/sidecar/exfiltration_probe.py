from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from maref.sentinel.daemon import SentinelDaemon

logger = logging.getLogger(__name__)


class DataExfiltrationProbe:
    """数据外泄检测探针 — 与 sentinel 观测神经集成。

    M4 改造：从恒返回 False 的 stub 升级为通过 SentinelDaemon
    的网络出口观测数据判定外泄。

    向后兼容：无 sentinel 时退化为旧行为（返回 False）。
    """

    def __init__(self, sentinel_daemon: SentinelDaemon | None = None) -> None:
        self._sentinel = sentinel_daemon

    def check(self, data: bytes) -> bool:
        """旧签名 — 向后兼容。"""
        return self.check_exfiltration(data, pid=None)

    def check_exfiltration(self, data: bytes, pid: int | None = None) -> bool:
        """新签名：结合 sentinel 网络出口观测判定数据外泄。

        Args:
            data: 可疑数据载荷
            pid: 目标进程 PID（None 时使用默认观测）

        Returns:
            True = 检测到外泄行为
        """
        if self._sentinel is None:
            return False  # 降级：无 sentinel 时保持旧行为

        try:
            return self._sentinel.detect_exfiltration(data, pid)
        except Exception:
            logger.warning("Sentinel detect_exfiltration failed", exc_info=True)
            return False

    @property
    def available(self) -> bool:
        """探针是否可用（sentinel 已连接）。"""
        return self._sentinel is not None
