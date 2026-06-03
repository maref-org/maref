from __future__ import annotations

import smtplib
from abc import ABC, abstractmethod
from email.mime.text import MIMEText

import httpx


class NotificationChannel(ABC):
    @abstractmethod
    def send(self, title: str, message: str, level: str = "info") -> bool: ...


class EmailChannel(NotificationChannel):
    def __init__(
        self,
        smtp_host: str,
        smtp_port: int,
        username: str,
        password: str,
        from_addr: str,
        to_addrs: list[str],
        use_tls: bool = True,
    ) -> None:
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.username = username
        self.password = password
        self.from_addr = from_addr
        self.to_addrs = to_addrs
        self.use_tls = use_tls

    def send(self, title: str, message: str, level: str = "info") -> bool:
        msg = MIMEText(message, _charset="utf-8")
        msg["Subject"] = title
        msg["From"] = self.from_addr
        msg["To"] = ", ".join(self.to_addrs)

        try:
            if self.use_tls:
                with smtplib.SMTP_SSL(self.smtp_host, self.smtp_port) as server:
                    server.login(self.username, self.password)
                    server.sendmail(self.from_addr, self.to_addrs, msg.as_string())
            else:
                with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                    server.login(self.username, self.password)
                    server.sendmail(self.from_addr, self.to_addrs, msg.as_string())
            return True
        except Exception:
            return False


class WebhookChannel(NotificationChannel):
    def __init__(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        timeout: float = 10.0,
    ) -> None:
        self.url = url
        self.headers = headers or {}
        self.timeout = timeout

    def send(self, title: str, message: str, level: str = "info") -> bool:
        try:
            response = httpx.post(
                self.url,
                json={"title": title, "message": message, "level": level},
                headers=self.headers,
                timeout=self.timeout,
            )
            return response.is_success
        except Exception:
            return False


class CLINotificationChannel(NotificationChannel):
    def __init__(self, use_rich: bool = True) -> None:
        self.use_rich = use_rich

    def send(self, title: str, message: str, level: str = "info") -> bool:
        if self.use_rich:
            try:
                from rich.console import Console
                from rich.panel import Panel

                console = Console()
                panel = Panel(message, title=title, subtitle=level)
                console.print(panel)
                return True
            except ImportError:
                self.use_rich = False

        level_tag = level.upper()
        print(f"[{level_tag}] {title}")
        print(message)
        return True


class NotificationManager:
    def __init__(self) -> None:
        self._channels: dict[str, NotificationChannel] = {}

    def register_channel(self, name: str, channel: NotificationChannel) -> None:
        self._channels[name] = channel

    def unregister_channel(self, name: str) -> None:
        self._channels.pop(name, None)

    def notify_all(self, title: str, message: str, level: str = "info") -> dict[str, bool]:
        results: dict[str, bool] = {}
        for name, channel in self._channels.items():
            results[name] = channel.send(title, message, level)
        return results

    def get_channel(self, name: str) -> NotificationChannel | None:
        return self._channels.get(name)

    def list_channels(self) -> list[str]:
        return list(self._channels.keys())
