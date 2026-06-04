"""
GitHub 邮件监听 Agent

通过 IMAP 监听 GitHub 通知邮件，解析并触发相应的仓库维护操作。

支持监听：
- frankiehot@hotmail.com (Hotmail/Outlook IMAP)
- athenabot@qq.com (QQ 邮箱 IMAP)
- 87909004@qq.com (QQ 邮箱 IMAP)

安全规范：
- 使用 App Password/授权码，非登录密码
- 密码通过环境变量或 Keychain 存储
- 所有操作记录审计日志
"""
from __future__ import annotations

import email
import imaplib
import logging
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.header import decode_header
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger(__name__)


class GitHubNotificationType(Enum):
    """GitHub 通知类型"""
    PR_REVIEW_REQUEST = "pr_review_request"
    PR_MERGED = "pr_merged"
    PR_CLOSED = "pr_closed"
    ISSUE_ASSIGNED = "issue_assigned"
    ISSUE_COMMENT = "issue_comment"
    ISSUE_CLOSED = "issue_closed"
    DEPENDABOT_ALERT = "dependabot_alert"
    DEPENDABOT_PR = "dependabot_pr"
    WORKFLOW_FAILURE = "workflow_failure"
    SECURITY_ALERT = "security_alert"
    DISCUSSION_COMMENT = "discussion_comment"
    RELEASE_PUBLISHED = "release_published"
    UNKNOWN = "unknown"


@dataclass
class GitHubEmail:
    """解析后的 GitHub 通知邮件"""
    message_id: str
    from_addr: str
    to_addr: str
    subject: str
    date: datetime
    notification_type: GitHubNotificationType
    repo: str = ""
    repo_owner: str = ""
    pr_number: int | None = None
    issue_number: int | None = None
    actor: str = ""
    action_url: str = ""
    body_preview: str = ""
    raw_headers: dict[str, str] = field(default_factory=dict)
    processed: bool = False


@dataclass
class IMAPConfig:
    """IMAP 连接配置"""
    host: str
    port: int
    username: str
    password: str  # 使用 App Password/授权码
    use_ssl: bool = True
    folder: str = "INBOX"
    search_folder: str = "INBOX"


class EmailProvider(Enum):
    """支持的邮箱提供商"""
    HOTMAIL = "hotmail"      # Outlook/Hotmail
    QQ = "qq"                # QQ 邮箱
    GMAIL = "gmail"          # Gmail
    CUSTOM = "custom"        # 自定义 IMAP


IMAP_CONFIGS = {
    EmailProvider.HOTMAIL: IMAPConfig(
        host="outlook.office365.com",
        port=993,
        username="",
        password="",
        use_ssl=True,
        folder="INBOX",
    ),
    EmailProvider.QQ: IMAPConfig(
        host="imap.qq.com",
        port=993,
        username="",
        password="",
        use_ssl=True,
        folder="INBOX",
    ),
    EmailProvider.GMAIL: IMAPConfig(
        host="imap.gmail.com",
        port=993,
        username="",
        password="",
        use_ssl=True,
        folder="INBOX",
    ),
}


class GitHubEmailListener:
    """
    GitHub 邮件监听 Agent

    通过 IMAP 连接邮箱，定期轮询 GitHub 通知邮件，
    解析邮件内容并触发相应的回调函数。
    """

    def __init__(
        self,
        provider: EmailProvider = EmailProvider.HOTMAIL,
        poll_interval: int = 60,
        max_emails_per_poll: int = 50,
        seen_uids: set[str] | None = None,
    ):
        self._provider = provider
        self._poll_interval = poll_interval
        self._max_emails_per_poll = max_emails_per_poll
        self._seen_uids: set[str] = seen_uids or set()
        self._handlers: dict[GitHubNotificationType, list[Callable]] = {}
        self._running = False
        self._last_error: str | None = None
        self._stats = {
            "total_polled": 0,
            "total_processed": 0,
            "total_errors": 0,
            "last_poll_time": None,
        }

    def configure(self, username: str, password: str) -> None:
        """配置 IMAP 连接信息"""
        config = IMAP_CONFIGS[self._provider]
        config.username = username
        config.password = password
        self._config = config

    def load_from_env(self) -> bool:
        """从环境变量加载配置"""
        provider = os.getenv("GITHUB_EMAIL_PROVIDER", "hotmail").lower()
        username = os.getenv("GITHUB_EMAIL_USERNAME", "")
        password = os.getenv("GITHUB_EMAIL_PASSWORD", "")

        if not username or not password:
            logger.warning("GITHUB_EMAIL_USERNAME 或 GITHUB_EMAIL_PASSWORD 未设置")
            return False

        try:
            self._provider = EmailProvider(provider)
        except ValueError:
            self._provider = EmailProvider.CUSTOM

        self.configure(username, password)

        # 可选配置
        if poll_interval := os.getenv("GITHUB_EMAIL_POLL_INTERVAL"):
            self._poll_interval = int(poll_interval)

        return True

    def register_handler(
        self,
        notification_type: GitHubNotificationType,
        handler: Callable[[GitHubEmail], None],
    ) -> None:
        """注册邮件处理回调"""
        if notification_type not in self._handlers:
            self._handlers[notification_type] = []
        self._handlers[notification_type].append(handler)

    def _connect_imap(self) -> imaplib.IMAP4_SSL | imaplib.IMAP4:
        """建立 IMAP 连接"""
        config = self._config

        if config.use_ssl:
            conn = imaplib.IMAP4_SSL(config.host, config.port)
        else:
            conn = imaplib.IMAP4(config.host, config.port)

        conn.login(config.username, config.password)
        logger.info(f"IMAP 连接成功: {config.host}:{config.port}")
        return conn

    def _decode_header(self, header_value: str) -> str:
        """解码邮件头"""
        if not header_value:
            return ""

        parts = []
        for part, charset in decode_header(header_value):
            if isinstance(part, bytes):
                parts.append(part.decode(charset or "utf-8", errors="replace"))
            else:
                parts.append(part)
        return "".join(parts)

    def _parse_github_notification(self, msg: email.message.Message) -> GitHubEmail | None:
        """
        解析 GitHub 通知邮件

        GitHub 通知邮件特征：
        - From: notifications@github.com
        - Subject: 包含特定格式的通知标题
        - List-Unsubscribe 头包含 GitHub URL
        - X-GitHub-Recipient-Reason 头包含通知原因
        """
        from_addr = self._decode_header(msg.get("From", ""))

        # 只处理 GitHub 通知邮件
        if "notifications@github.com" not in from_addr.lower():
            return None

        subject = self._decode_header(msg.get("Subject", ""))
        date_str = msg.get("Date", "")
        message_id = msg.get("Message-ID", "")

        # 解析日期
        try:
            date = email.utils.parsedate_to_datetime(date_str)
        except Exception:
            date = datetime.now(timezone.utc)

        # 解析通知类型
        notification_type = self._classify_notification(subject, msg)

        # 提取仓库信息
        repo, repo_owner = self._extract_repo_info(subject, msg)

        # 提取 PR/Issue 编号
        pr_number = self._extract_pr_number(subject, msg)
        issue_number = self._extract_issue_number(subject, msg)

        # 提取操作者
        actor = self._extract_actor(subject)

        # 提取 URL
        action_url = self._extract_action_url(msg)

        # 提取正文预览
        body_preview = self._extract_body_preview(msg)

        return GitHubEmail(
            message_id=message_id or "",
            from_addr=from_addr,
            to_addr=self._decode_header(msg.get("To", "")),
            subject=subject,
            date=date,
            notification_type=notification_type,
            repo=repo,
            repo_owner=repo_owner,
            pr_number=pr_number,
            issue_number=issue_number,
            actor=actor,
            action_url=action_url,
            body_preview=body_preview,
        )

    def _classify_notification(
        self,
        subject: str,
        msg: email.message.Message,
    ) -> GitHubNotificationType:
        """分类通知类型"""
        subject_lower = subject.lower()

        # PR 相关
        if "pull request" in subject_lower:
            if "review requested" in subject_lower:
                return GitHubNotificationType.PR_REVIEW_REQUEST
            elif "merged" in subject_lower:
                return GitHubNotificationType.PR_MERGED
            elif "closed" in subject_lower:
                return GitHubNotificationType.PR_CLOSED
            else:
                return GitHubNotificationType.PR_REVIEW_REQUEST

        # Dependabot
        if "dependabot" in subject_lower:
            if "bumps" in subject_lower or "update" in subject_lower:
                return GitHubNotificationType.DEPENDABOT_PR
            return GitHubNotificationType.DEPENDABOT_ALERT

        # Issue 相关
        if "issue" in subject_lower:
            if "assigned" in subject_lower:
                return GitHubNotificationType.ISSUE_ASSIGNED
            elif "comment" in subject_lower:
                return GitHubNotificationType.ISSUE_COMMENT
            elif "closed" in subject_lower:
                return GitHubNotificationType.ISSUE_CLOSED

        # Workflow
        if "workflow" in subject_lower and "fail" in subject_lower:
            return GitHubNotificationType.WORKFLOW_FAILURE

        # Security
        if "security" in subject_lower or "vulnerability" in subject_lower:
            return GitHubNotificationType.SECURITY_ALERT

        # Release
        if "release" in subject_lower and "published" in subject_lower:
            return GitHubNotificationType.RELEASE_PUBLISHED

        return GitHubNotificationType.UNKNOWN

    def _extract_repo_info(
        self,
        subject: str,
        msg: email.message.Message,
    ) -> tuple[str, str]:
        """提取仓库信息"""
        # GitHub 邮件格式: [repo_owner/repo] subject
        match = re.search(r"\[([^/]+)/([^\]]+)\]", subject)
        if match:
            return match.group(2), match.group(1)

        # 从 List-Unsubscribe 头提取
        list_unsubscribe = msg.get("List-Unsubscribe", "")
        match = re.search(r"github\.com/([^/]+)/([^/]+)", list_unsubscribe)
        if match:
            return match.group(2), match.group(1)

        return "", ""

    def _extract_pr_number(
        self,
        subject: str,
        msg: email.message.Message,
    ) -> int | None:
        """提取 PR 编号"""
        # 格式: #123
        match = re.search(r"#(\d+)", subject)
        if match:
            return int(match.group(1))
        return None

    def _extract_issue_number(
        self,
        subject: str,
        msg: email.message.Message,
    ) -> int | None:
        """提取 Issue 编号"""
        # Issue 也有 #123 格式，需要通过通知类型区分
        return self._extract_pr_number(subject, msg)

    def _extract_actor(self, subject: str) -> str:
        """提取操作者用户名"""
        # 格式: username requested... 或 username commented...
        match = re.search(r"by\s+(@?\w+)", subject)
        if match:
            return match.group(1).lstrip("@")

        # 格式: username requested your review
        match = re.search(r"^(\w+)\s+(requested|commented|merged|closed)", subject)
        if match:
            return match.group(1)

        return ""

    def _extract_action_url(self, msg: email.message.Message) -> str:
        """提取操作 URL"""
        # 从 List-Unsubscribe 或正文提取
        for header in ["List-Unsubscribe", "List-Post"]:
            value = msg.get(header, "")
            match = re.search(r"(https://github\.com/[^\s>]+)", value)
            if match:
                return match.group(1)

        # 从正文提取
        return ""

    def _extract_body_preview(self, msg: email.message.Message) -> str:
        """提取正文预览（前 500 字符）"""
        body = ""

        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                if content_type == "text/plain":
                    charset = part.get_content_charset() or "utf-8"
                    try:
                        body = part.get_payload(decode=True).decode(charset, errors="replace")
                        break
                    except Exception:
                        continue
        else:
            charset = msg.get_content_charset() or "utf-8"
            try:
                body = msg.get_payload(decode=True).decode(charset, errors="replace")
            except Exception:
                body = str(msg.get_payload())

        return body[:500].strip()

    def _process_email(self, gh_email: GitHubEmail) -> None:
        """处理单封邮件，触发注册的回调"""
        handlers = self._handlers.get(gh_email.notification_type, [])
        handlers.extend(self._handlers.get(GitHubNotificationType.UNKNOWN, []))

        for handler in handlers:
            try:
                handler(gh_email)
            except Exception as e:
                logger.error(f"处理邮件回调失败: {e}")
                self._stats["total_errors"] += 1

        gh_email.processed = True
        self._stats["total_processed"] += 1
        logger.info(
            f"已处理邮件: {gh_email.notification_type.value} "
            f"[{gh_email.repo_owner}/{gh_email.repo}] "
            f"PR#{gh_email.pr_number or 'N/A'} "
            f"Issue#{gh_email.issue_number or 'N/A'}"
        )

    def poll_once(self) -> list[GitHubEmail]:
        """执行一次邮件轮询"""
        if not hasattr(self, "_config"):
            if not self.load_from_env():
                logger.error("IMAP 配置未设置")
                return []

        processed_emails: list[GitHubEmail] = []

        try:
            conn = self._connect_imap()
            conn.select(self._config.folder, readonly=False)

            # 搜索未读邮件
            status, messages = conn.search(None, "UNSEEN")
            if status != "OK":
                logger.warning("搜索邮件失败")
                return []

            email_ids = messages[0].split()
            if not email_ids:
                logger.info("没有新邮件")
                return []

            # 限制处理数量
            to_process = email_ids[: self._max_emails_per_poll]

            for eid in to_process:
                status, msg_data = conn.fetch(eid, "(RFC822)")
                if status != "OK":
                    continue

                raw_email = msg_data[0][1]
                msg = email.message_from_bytes(raw_email)

                gh_email = self._parse_github_notification(msg)
                if gh_email is None:
                    continue

                # 检查是否已处理
                uid_str = eid.decode()
                if uid_str in self._seen_uids:
                    continue

                self._seen_uids.add(uid_str)
                self._process_email(gh_email)
                processed_emails.append(gh_email)

            conn.close()
            conn.logout()

        except imaplib.IMAP4.error as e:
            self._last_error = f"IMAP 错误: {e}"
            logger.error(self._last_error)
            self._stats["total_errors"] += 1
        except Exception as e:
            self._last_error = f"轮询错误: {e}"
            logger.error(self._last_error)
            self._stats["total_errors"] += 1

        self._stats["total_polled"] += len(processed_emails)
        self._stats["last_poll_time"] = datetime.now(timezone.utc).isoformat()

        return processed_emails

    def start(self) -> None:
        """启动持续监听"""
        self._running = True
        logger.info(
            f"启动 GitHub 邮件监听: "
            f"provider={self._provider.value}, "
            f"interval={self._poll_interval}s"
        )

        while self._running:
            try:
                self.poll_once()
            except Exception as e:
                logger.error(f"监听循环异常: {e}")
                self._stats["total_errors"] += 1

            time.sleep(self._poll_interval)

    def stop(self) -> None:
        """停止监听"""
        self._running = False
        logger.info("GitHub 邮件监听已停止")

    def get_stats(self) -> dict[str, Any]:
        """获取监听统计"""
        return {
            **self._stats,
            "provider": self._provider.value,
            "poll_interval": self._poll_interval,
            "seen_uids_count": len(self._seen_uids),
            "running": self._running,
            "last_error": self._last_error,
        }


def create_github_email_listener(
    provider: str = "hotmail",
    poll_interval: int = 60,
) -> GitHubEmailListener:
    """创建 GitHub 邮件监听器"""
    try:
        email_provider = EmailProvider(provider)
    except ValueError:
        email_provider = EmailProvider.HOTMAIL

    listener = GitHubEmailListener(
        provider=email_provider,
        poll_interval=poll_interval,
    )
    listener.load_from_env()
    return listener
