from __future__ import annotations

import smtplib
from unittest.mock import MagicMock, patch

import httpx

from maref.executor.notifications import (
    CLINotificationChannel,
    EmailChannel,
    NotificationChannel,
    NotificationManager,
    WebhookChannel,
)


class TestEmailChannel:
    def test_email_channel_send_success(self) -> None:
        mock_smtp = MagicMock()
        mock_smtp.__enter__.return_value = mock_smtp
        with patch("smtplib.SMTP_SSL", return_value=mock_smtp) as mock_cls:
            channel = EmailChannel(
                smtp_host="smtp.example.com",
                smtp_port=465,
                username="user",
                password="pass",
                from_addr="from@example.com",
                to_addrs=["to@example.com"],
                use_tls=True,
            )
            result = channel.send("Test Title", "Test Message")
            assert result is True
            mock_cls.assert_called_once_with("smtp.example.com", 465)
            mock_smtp.login.assert_called_once_with("user", "pass")
            mock_smtp.sendmail.assert_called_once()

    def test_email_channel_send_without_tls(self) -> None:
        mock_smtp = MagicMock()
        mock_smtp.__enter__.return_value = mock_smtp
        with patch("smtplib.SMTP", return_value=mock_smtp) as mock_cls:
            channel = EmailChannel(
                smtp_host="smtp.example.com",
                smtp_port=587,
                username="user",
                password="pass",
                from_addr="from@example.com",
                to_addrs=["to@example.com"],
                use_tls=False,
            )
            result = channel.send("Test Title", "Test Message")
            assert result is True
            mock_cls.assert_called_once_with("smtp.example.com", 587)
            mock_smtp.login.assert_called_once_with("user", "pass")
            mock_smtp.sendmail.assert_called_once()

    def test_email_channel_send_failure(self) -> None:
        with patch("smtplib.SMTP_SSL", side_effect=smtplib.SMTPException("Connection failed")):
            channel = EmailChannel(
                smtp_host="smtp.example.com",
                smtp_port=465,
                username="user",
                password="pass",
                from_addr="from@example.com",
                to_addrs=["to@example.com"],
                use_tls=True,
            )
            result = channel.send("Test Title", "Test Message")
            assert result is False


class TestWebhookChannel:
    def test_webhook_channel_send_success(self) -> None:
        mock_response = MagicMock()
        mock_response.is_success = True
        with patch("httpx.post", return_value=mock_response) as mock_post:
            channel = WebhookChannel(
                url="https://hooks.example.com/notify",
                headers={"X-Api-Key": "secret"},
                timeout=5.0,
            )
            result = channel.send("Test Title", "Test Message", level="warning")
            assert result is True
            mock_post.assert_called_once_with(
                "https://hooks.example.com/notify",
                json={"title": "Test Title", "message": "Test Message", "level": "warning"},
                headers={"X-Api-Key": "secret"},
                timeout=5.0,
            )

    def test_webhook_channel_send_default_headers(self) -> None:
        mock_response = MagicMock()
        mock_response.is_success = True
        with patch("httpx.post", return_value=mock_response) as mock_post:
            channel = WebhookChannel(url="https://hooks.example.com/notify")
            result = channel.send("Title", "Message")
            assert result is True
            mock_post.assert_called_once_with(
                "https://hooks.example.com/notify",
                json={"title": "Title", "message": "Message", "level": "info"},
                headers={},
                timeout=10.0,
            )

    def test_webhook_channel_send_failure(self) -> None:
        with patch("httpx.post", side_effect=httpx.RequestError("Timeout")):
            channel = WebhookChannel(url="https://hooks.example.com/notify")
            result = channel.send("Test Title", "Test Message")
            assert result is False

    def test_webhook_channel_non_success_status(self) -> None:
        mock_response = MagicMock()
        mock_response.is_success = False
        with patch("httpx.post", return_value=mock_response):
            channel = WebhookChannel(url="https://hooks.example.com/notify")
            result = channel.send("Test Title", "Test Message")
            assert result is False


class TestCLINotificationChannel:
    def test_cli_channel_send_rich(self) -> None:
        mock_console = MagicMock()
        with (
            patch("rich.console.Console", return_value=mock_console),
            patch("rich.panel.Panel") as mock_panel_cls,
        ):
            channel = CLINotificationChannel(use_rich=True)
            result = channel.send("Test Title", "Test Message", level="error")
            assert result is True
            mock_console.print.assert_called_once()
            mock_panel_cls.assert_called_once_with(
                "Test Message", title="Test Title", subtitle="error"
            )

    def test_cli_channel_send_fallback(self) -> None:
        with (
            patch("builtins.print") as mock_print,
            patch("rich.console.Console", side_effect=ImportError("no rich")),
        ):
            channel = CLINotificationChannel(use_rich=True)
            result = channel.send("Fallback Title", "Fallback Message")
            assert result is True
            assert channel.use_rich is False
            mock_print.assert_any_call("[INFO] Fallback Title")
            mock_print.assert_any_call("Fallback Message")

    def test_cli_channel_send_fallback_when_use_rich_false(self) -> None:
        with patch("builtins.print") as mock_print:
            channel = CLINotificationChannel(use_rich=False)
            result = channel.send("Plain Title", "Plain Message", level="critical")
            assert result is True
            mock_print.assert_any_call("[CRITICAL] Plain Title")
            mock_print.assert_any_call("Plain Message")


class TestNotificationManager:
    def test_register_and_list_channels(self) -> None:
        manager = NotificationManager()
        ch1 = MagicMock(spec=NotificationChannel)
        ch2 = MagicMock(spec=NotificationChannel)
        manager.register_channel("email", ch1)
        manager.register_channel("webhook", ch2)
        channels = manager.list_channels()
        assert "email" in channels
        assert "webhook" in channels
        assert len(channels) == 2

    def test_notify_all_calls_all_channels(self) -> None:
        manager = NotificationManager()
        ch1 = MagicMock(spec=NotificationChannel)
        ch2 = MagicMock(spec=NotificationChannel)
        ch1.send.return_value = True
        ch2.send.return_value = True
        manager.register_channel("ch1", ch1)
        manager.register_channel("ch2", ch2)
        results = manager.notify_all("Title", "Message", level="info")
        ch1.send.assert_called_once_with("Title", "Message", "info")
        ch2.send.assert_called_once_with("Title", "Message", "info")
        assert results == {"ch1": True, "ch2": True}

    def test_notify_all_partial_failure(self) -> None:
        manager = NotificationManager()
        ch1 = MagicMock(spec=NotificationChannel)
        ch2 = MagicMock(spec=NotificationChannel)
        ch1.send.return_value = True
        ch2.send.return_value = False
        manager.register_channel("ch1", ch1)
        manager.register_channel("ch2", ch2)
        results = manager.notify_all("Title", "Message")
        ch1.send.assert_called_once()
        ch2.send.assert_called_once()
        assert results == {"ch1": True, "ch2": False}

    def test_notify_all_with_no_channels(self) -> None:
        manager = NotificationManager()
        results = manager.notify_all("Title", "Message")
        assert results == {}

    def test_unregister_channel(self) -> None:
        manager = NotificationManager()
        ch = MagicMock(spec=NotificationChannel)
        manager.register_channel("test", ch)
        assert "test" in manager.list_channels()
        manager.unregister_channel("test")
        assert "test" not in manager.list_channels()
        assert len(manager.list_channels()) == 0

    def test_unregister_nonexistent_channel(self) -> None:
        manager = NotificationManager()
        manager.unregister_channel("nonexistent")

    def test_get_channel(self) -> None:
        manager = NotificationManager()
        ch = MagicMock(spec=NotificationChannel)
        manager.register_channel("test", ch)
        retrieved = manager.get_channel("test")
        assert retrieved is ch

    def test_get_channel_nonexistent(self) -> None:
        manager = NotificationManager()
        result = manager.get_channel("nonexistent")
        assert result is None
