from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from maref.identity.credential_manager import (
    CredentialManager,
    CredentialRecord,
    CredentialStatus,
    CredentialType,
)

logger = logging.getLogger(__name__)

@dataclass
class RotationPolicy:
    """密钥轮转策略"""

    rotation_interval: float  # 秒
    warning_before: float  # 提前告警时间（秒）
    auto_rotate: bool = False
    max_age: float | None = None  # 最大生存时间


class KeyRotator:
    """密钥轮转管理器"""

    DEFAULT_POLICIES: dict[CredentialType, RotationPolicy] = {
        CredentialType.API_KEY: RotationPolicy(
            rotation_interval=90 * 24 * 3600,  # 90 天
            warning_before=7 * 24 * 3600,  # 提前 7 天告警
            auto_rotate=False,
        ),
        CredentialType.SIGNING_KEY: RotationPolicy(
            rotation_interval=365 * 24 * 3600,  # 1 年
            warning_before=30 * 24 * 3600,  # 提前 30 天告警
            auto_rotate=False,
        ),
        CredentialType.HMAC_KEY: RotationPolicy(
            rotation_interval=180 * 24 * 3600,  # 180 天
            warning_before=14 * 24 * 3600,  # 提前 14 天告警
            auto_rotate=False,
        ),
        CredentialType.BROWSER_SESSION: RotationPolicy(
            rotation_interval=24 * 3600,  # 24 小时
            warning_before=2 * 3600,  # 提前 2 小时告警
            auto_rotate=False,
            max_age=7 * 24 * 3600,  # 最长 7 天
        ),
        CredentialType.OAUTH_TOKEN: RotationPolicy(
            rotation_interval=3600,  # 1 小时（refresh_token）
            warning_before=300,  # 提前 5 分钟告警
            auto_rotate=True,
        ),
    }

    def __init__(
        self,
        manager: CredentialManager,
        policies: dict[CredentialType, RotationPolicy] | None = None,
    ) -> None:
        self._manager = manager
        self._policies = policies or self.DEFAULT_POLICIES
        self._rotation_callbacks: list[Callable[[CredentialRecord], None]] = []

    def register_rotation_callback(
        self,
        callback: Callable[[CredentialRecord], None],
    ) -> None:
        """注册轮转回调（用于通知外部系统）"""
        self._rotation_callbacks.append(callback)

    def check_all(self) -> list[dict[str, Any]]:
        """检查所有凭据的轮转状态"""
        results: list[dict[str, Any]] = []

        for record in self._manager.list_credentials():
            policy = self._policies.get(record.credential_type)
            if not policy:
                continue

            status: dict[str, Any] = {
                "credential_id": record.credential_id,
                "name": record.name,
                "type": record.credential_type.value,
                "needs_rotation": False,
                "warning": False,
                "reason": "",
            }

            if record.status == CredentialStatus.REVOKED:
                status["reason"] = "revoked"
            elif record.is_expired():
                status["needs_rotation"] = True
                status["reason"] = "expired"
            elif record.needs_rotation():
                status["needs_rotation"] = True
                status["reason"] = "rotation_interval_reached"
            elif policy.max_age and (time.time() - record.created_at) > policy.max_age:
                status["needs_rotation"] = True
                status["reason"] = "max_age_exceeded"
            elif record.expires_at:
                time_until_expiry = record.expires_at - time.time()
                if time_until_expiry < policy.warning_before:
                    status["warning"] = True
                    status["reason"] = f"expires_in_{int(time_until_expiry / 3600)}_hours"

            results.append(status)

        return results

    def notify_expiring(self) -> list[CredentialRecord]:
        """通知即将过期的凭据"""
        expiring: list[CredentialRecord] = []

        for record in self._manager.list_credentials():
            policy = self._policies.get(record.credential_type)
            if not policy or not record.expires_at:
                continue

            time_until_expiry = record.expires_at - time.time()
            if 0 < time_until_expiry < policy.warning_before:
                expiring.append(record)
                for callback in self._rotation_callbacks:
                    try:
                        callback(record)
                    except Exception as e:
                        cb_name = getattr(callback, "__qualname__", repr(callback))
                        logger.warning(
                            "Rotation callback %s failed for credential %s: %s",
                            cb_name,
                            record.name,
                            e,
                        )

        return expiring
