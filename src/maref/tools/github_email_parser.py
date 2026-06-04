"""
GitHub 邮件解析器

解析 GitHub 通知邮件，提取结构化信息：
- PR 审查请求
- Issue 通知
- 依赖更新
- Workflow 失败
- 安全告警
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EmailPriority(Enum):
    """邮件优先级"""
    CRITICAL = "critical"    # 安全告警、Workflow 失败
    HIGH = "high"           # PR 审查请求
    MEDIUM = "medium"       # Issue 分配、评论
    LOW = "low"             # 依赖更新、Release 发布
    INFO = "info"           # PR 合并、关闭等通知


@dataclass
class ParsedAction:
    """解析后的可执行操作"""
    action_type: str
    description: str
    priority: EmailPriority
    repo: str
    repo_owner: str
    pr_number: int | None = None
    issue_number: int | None = None
    suggested_command: str = ""
    requires_approval: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ParsedEmail:
    """解析结果"""
    raw_subject: str
    raw_body_preview: str
    notification_type: str
    priority: EmailPriority
    repo: str
    repo_owner: str
    actor: str
    commit_sha: str = ""
    commit_url: str = ""
    actions: list[ParsedAction] = field(default_factory=list)
    summary: str = ""


class GitHubEmailParser:
    """
    GitHub 邮件解析器

    将原始邮件解析为结构化的通知对象，
    并生成建议的操作列表。
    """

    def __init__(
        self,
        auto_merge_dependabot: bool = False,
        auto_close_stale_issues: bool = False,
        notify_on_workflow_failure: bool = True,
    ):
        self._auto_merge_dependabot = auto_merge_dependabot
        self._auto_close_stale_issues = auto_close_stale_issues
        self._notify_on_workflow_failure = notify_on_workflow_failure

    def parse(
        self,
        subject: str,
        body_preview: str = "",
        from_addr: str = "",
        action_url: str = "",
    ) -> ParsedEmail | None:
        """
        解析 GitHub 通知邮件

        Args:
            subject: 邮件主题
            body_preview: 正文预览
            from_addr: 发件人地址
            action_url: 操作 URL

        Returns:
            ParsedEmail 对象，如果不是 GitHub 通知则返回 None
        """
        # 验证是 GitHub 通知
        if "notifications@github.com" not in from_addr.lower():
            return None

        # 分类通知类型
        notification_type = self._classify(subject)

        # 提取仓库信息
        repo, repo_owner = self._extract_repo(subject)

        # 提取操作者
        actor = self._extract_actor(subject)

        # 提取 commit SHA 和 URL
        commit_sha, commit_url = self._extract_commit_info(subject, body_preview, action_url)

        # 生成操作建议
        actions = self._generate_actions(
            subject, body_preview, notification_type, repo, repo_owner, actor
        )

        # 确定优先级
        priority = self._determine_priority(notification_type, actions)

        # 生成摘要
        summary = self._generate_summary(
            subject, notification_type, repo, repo_owner, actor, actions
        )

        return ParsedEmail(
            raw_subject=subject,
            raw_body_preview=body_preview,
            notification_type=notification_type,
            priority=priority,
            repo=repo,
            repo_owner=repo_owner,
            actor=actor,
            commit_sha=commit_sha,
            commit_url=commit_url,
            actions=actions,
            summary=summary,
        )

    def _classify(self, subject: str) -> str:
        """分类通知类型"""
        s = subject.lower()

        if "pull request" in s:
            if "review requested" in s:
                return "pr_review_request"
            elif "merged" in s:
                return "pr_merged"
            elif "closed" in s:
                return "pr_closed"
            elif "reopened" in s:
                return "pr_reopened"
            elif "ready for review" in s:
                return "pr_ready_for_review"
            else:
                return "pr_notification"

        if "dependabot" in s:
            if "bumps" in s or "update" in s:
                return "dependabot_pr"
            return "dependabot_alert"

        if "issue" in s:
            if "assigned" in s:
                return "issue_assigned"
            elif "comment" in s:
                return "issue_comment"
            elif "closed" in s:
                return "issue_closed"
            elif "reopened" in s:
                return "issue_reopened"
            elif "labeled" in s:
                return "issue_labeled"
            else:
                return "issue_notification"

        # Workflow 失败（多种格式）
        # 格式 1: "workflow failed: ..."
        # 格式 2: "workflow run failed: ..."
        # 格式 3: "pr run failed: ..." (Release Gate 等 PR 触发的 workflow)
        # 格式 4: "... run failed"
        if ("workflow" in s or "pr run" in s) and ("fail" in s or "failed" in s):
            return "workflow_failure"

        if "security" in s or "vulnerability" in s:
            return "security_alert"

        if "release" in s and "published" in s:
            return "release_published"

        if "discussion" in s:
            return "discussion_notification"

        return "unknown"

    def _extract_repo(self, subject: str) -> tuple[str, str]:
        """提取仓库信息"""
        # 格式: [owner/repo] subject
        match = re.search(r"\[([^/]+)/([^\]]+)\]", subject)
        if match:
            return match.group(2), match.group(1)
        return "", ""

    def _extract_actor(self, subject: str) -> str:
        """提取操作者"""
        # username requested your review...
        match = re.search(r"^(\w+)\s+(requested|commented|merged|closed|opened)", subject)
        if match:
            return match.group(1)

        # ...by username
        match = re.search(r"by\s+(@?\w+)", subject)
        if match:
            return match.group(1).lstrip("@")

        return ""

    def _extract_commit_info(
        self,
        subject: str,
        body_preview: str,
        action_url: str,
    ) -> tuple[str, str]:
        """提取 commit SHA 和 URL"""
        _ = body_preview  # 预留参数
        sha = ""
        url = ""

        # 格式: (58228e4) 或 58228e4
        match = re.search(r"\(([0-9a-f]{7,40})\)", subject)
        if match:
            sha = match.group(1)
        else:
            match = re.search(r"\b([0-9a-f]{7,40})\b", subject)
            if match:
                sha = match.group(1)

        # 如果 action_url 包含 github.com，从中提取完整 URL
        if "github.com" in action_url:
            url = action_url
        elif sha:
            # 从主题提取仓库信息后构建 URL
            repo, repo_owner = self._extract_repo(subject)
            if repo and repo_owner:
                url = f"https://github.com/{repo_owner}/{repo}/commit/{sha}"

        return sha, url

    def _generate_actions(
        self,
        subject: str,
        body_preview: str,
        notification_type: str,
        repo: str,
        repo_owner: str,
        actor: str,
    ) -> list[ParsedAction]:
        """生成操作建议"""
        actions: list[ParsedAction] = []
        pr_num = self._extract_number(subject, "pr")
        issue_num = self._extract_number(subject, "issue")

        if notification_type == "pr_review_request":
            actions.append(ParsedAction(
                action_type="review_pr",
                description=f"审查 PR #{pr_num} 由 {actor} 创建",
                priority=EmailPriority.HIGH,
                repo=repo,
                repo_owner=repo_owner,
                pr_number=pr_num,
                suggested_command=f"gh pr view {pr_num} --repo {repo_owner}/{repo}",
                requires_approval=False,
                metadata={"actor": actor},
            ))

        elif notification_type == "pr_merged":
            actions.append(ParsedAction(
                action_type="pr_merged",
                description=f"PR #{pr_num} 已合并",
                priority=EmailPriority.INFO,
                repo=repo,
                repo_owner=repo_owner,
                pr_number=pr_num,
                suggested_command=f"gh pr view {pr_num} --repo {repo_owner}/{repo}",
                requires_approval=False,
                metadata={"actor": actor},
            ))

        elif notification_type == "dependabot_pr":
            # 提取依赖信息
            dep_info = self._extract_dependabot_info(subject, body_preview)

            if self._auto_merge_dependabot:
                actions.append(ParsedAction(
                    action_type="auto_merge_dependabot",
                    description=f"自动合并 Dependabot PR #{pr_num}: {dep_info.get('package', 'unknown')}",
                    priority=EmailPriority.LOW,
                    repo=repo,
                    repo_owner=repo_owner,
                    pr_number=pr_num,
                    suggested_command=(
                        f"gh pr merge {pr_num} --squash --delete-branch "
                        f"--repo {repo_owner}/{repo}"
                    ),
                    requires_approval=False,
                    metadata={**dep_info, "auto_merge": True},
                ))
            else:
                actions.append(ParsedAction(
                    action_type="review_dependabot",
                    description=f"审查 Dependabot PR #{pr_num}: {dep_info.get('package', 'unknown')}",
                    priority=EmailPriority.LOW,
                    repo=repo,
                    repo_owner=repo_owner,
                    pr_number=pr_num,
                    suggested_command=f"gh pr view {pr_num} --repo {repo_owner}/{repo}",
                    requires_approval=True,
                    metadata={**dep_info, "auto_merge": False},
                ))

        elif notification_type == "issue_assigned":
            actions.append(ParsedAction(
                action_type="handle_issue",
                description=f"Issue #{issue_num} 已分配给你",
                priority=EmailPriority.MEDIUM,
                repo=repo,
                repo_owner=repo_owner,
                issue_number=issue_num,
                suggested_command=f"gh issue view {issue_num} --repo {repo_owner}/{repo}",
                requires_approval=False,
                metadata={"actor": actor},
            ))

        elif notification_type == "issue_comment":
            actions.append(ParsedAction(
                action_type="read_comment",
                description=f"Issue/PR #{issue_num or pr_num} 有新评论",
                priority=EmailPriority.MEDIUM,
                repo=repo,
                repo_owner=repo_owner,
                issue_number=issue_num,
                pr_number=pr_num,
                suggested_command=(
                    f"gh issue view {issue_num or pr_num} --repo {repo_owner}/{repo}"
                ),
                requires_approval=False,
                metadata={"actor": actor},
            ))

        elif notification_type == "workflow_failure":
            wf_name = self._extract_workflow_name(subject, body_preview)
            actions.append(ParsedAction(
                action_type="investigate_workflow_failure",
                description=f"Workflow '{wf_name}' 执行失败",
                priority=EmailPriority.CRITICAL,
                repo=repo,
                repo_owner=repo_owner,
                suggested_command=(
                    f"gh run list --repo {repo_owner}/{repo} --status=failure --limit=1"
                ),
                requires_approval=False,
                metadata={"workflow_name": wf_name, "actor": actor},
            ))

        elif notification_type == "security_alert":
            actions.append(ParsedAction(
                action_type="handle_security_alert",
                description="发现安全告警，需要立即处理",
                priority=EmailPriority.CRITICAL,
                repo=repo,
                repo_owner=repo_owner,
                suggested_command=f"gh api /repos/{repo_owner}/{repo}/code-scanning/alerts",
                requires_approval=False,
                metadata={"actor": actor},
            ))

        elif notification_type == "release_published":
            actions.append(ParsedAction(
                action_type="release_published",
                description="新版本已发布",
                priority=EmailPriority.LOW,
                repo=repo,
                repo_owner=repo_owner,
                suggested_command=f"gh release list --repo {repo_owner}/{repo}",
                requires_approval=False,
                metadata={"actor": actor},
            ))

        return actions

    def _extract_number(self, subject: str, number_type: str) -> int | None:
        """提取 PR/Issue 编号"""
        _ = number_type  # 预留参数，未来可用于区分 PR 和 Issue 编号格式
        match = re.search(r"#(\d+)", subject)
        if match:
            return int(match.group(1))
        return None

    def _extract_dependabot_info(
        self,
        subject: str,
        body_preview: str,
    ) -> dict[str, str]:
        """提取 Dependabot 依赖信息"""
        info: dict[str, str] = {}

        # 格式: Bumps [package] from X.Y.Z to A.B.C
        match = re.search(r"Bumps\s+\[([^\]]+)\]\s+from\s+(\S+)\s+to\s+(\S+)", subject)
        if match:
            info["package"] = match.group(1)
            info["old_version"] = match.group(2)
            info["new_version"] = match.group(3)
            return info

        # 从正文提取
        match = re.search(r"Bumps\s+\[([^\]]+)\]\s+from\s+(\S+)\s+to\s+(\S+)", body_preview)
        if match:
            info["package"] = match.group(1)
            info["old_version"] = match.group(2)
            info["new_version"] = match.group(3)

        return info

    def _extract_workflow_name(self, subject: str, body_preview: str) -> str:
        """提取 Workflow 名称"""
        # 格式: Workflow failed: CI (job)
        match = re.search(r"Workflow\s+(?:run\s+)?(?:failed|failure)[:\s]+([^\(]+)", subject, re.I)
        if match:
            return match.group(1).strip()

        # 从正文提取
        match = re.search(r"Workflow\s+name[:\s]+([^\n]+)", body_preview, re.I)
        if match:
            return match.group(1).strip()

        return "unknown"

    def _determine_priority(
        self,
        notification_type: str,
        actions: list[ParsedAction],
    ) -> EmailPriority:
        """确定邮件优先级"""
        priority_map = {
            "security_alert": EmailPriority.CRITICAL,
            "workflow_failure": EmailPriority.CRITICAL,
            "pr_review_request": EmailPriority.HIGH,
            "issue_assigned": EmailPriority.MEDIUM,
            "issue_comment": EmailPriority.MEDIUM,
            "dependabot_pr": EmailPriority.LOW,
            "dependabot_alert": EmailPriority.LOW,
            "release_published": EmailPriority.LOW,
            "pr_merged": EmailPriority.INFO,
            "pr_closed": EmailPriority.INFO,
            "issue_closed": EmailPriority.INFO,
        }

        priority = priority_map.get(notification_type, EmailPriority.INFO)

        # 如果有高优先级操作，提升邮件优先级
        for action in actions:
            if action.priority in (EmailPriority.CRITICAL, EmailPriority.HIGH):
                priority = min(priority, action.priority, key=lambda p: list(EmailPriority).index(p))
                break

        return priority

    def _generate_summary(
        self,
        subject: str,
        notification_type: str,
        repo: str,
        repo_owner: str,
        actor: str,
        actions: list[ParsedAction],
    ) -> str:
        """生成邮件摘要"""
        type_labels = {
            "pr_review_request": "需要审查 PR",
            "pr_merged": "PR 已合并",
            "pr_closed": "PR 已关闭",
            "dependabot_pr": "Dependabot 依赖更新",
            "issue_assigned": "Issue 已分配",
            "issue_comment": "新评论",
            "workflow_failure": "Workflow 失败",
            "security_alert": "安全告警",
            "release_published": "新版本发布",
        }

        label = type_labels.get(notification_type, "GitHub 通知")
        repo_str = f"{repo_owner}/{repo}" if repo else "unknown"

        action_count = len(actions)
        auto_actions = sum(1 for a in actions if not a.requires_approval)

        summary = (
            f"[{label}] {repo_str} | {actor}\n"
            f"  {subject}\n"
            f"  {action_count} 个操作建议"
        )

        if auto_actions > 0:
            summary += f" ({auto_actions} 个可自动执行)"

        return summary
