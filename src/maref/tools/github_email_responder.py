"""
GitHub 邮件自动响应机制

根据解析后的邮件内容，自动执行相应的仓库维护操作：
- 合并 PR（Dependabot 等）
- 回复 Issue
- 添加标签
- 关闭过期 Issue
- 重启失败 Workflow
- 失败原因分析
- 失败通知转发

安全规范：
- 所有自动操作记录审计日志
- 高风险操作需要人工审批
- 支持白名单机制（指定可自动操作的仓库）
"""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import urllib.request
import urllib.parse
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from .github_email_parser import ParsedAction, ParsedEmail, EmailPriority

logger = logging.getLogger(__name__)


class ActionType(Enum):
    """操作类型"""
    REVIEW_PR = "review_pr"
    MERGE_PR = "merge_pr"
    COMMENT_ON_PR = "comment_on_pr"
    COMMENT_ON_ISSUE = "comment_on_issue"
    CLOSE_ISSUE = "close_issue"
    LABEL_ISSUE = "label_issue"
    ASSIGN_ISSUE = "assign_issue"
    RESTART_WORKFLOW = "restart_workflow"
    MERGE_DEPENDABOT = "merge_dependabot"
    SECURITY_INVESTIGATE = "security_investigate"
    RELEASE_CHECK = "release_check"
    CUSTOM = "custom"


class ApprovalPolicy(Enum):
    """审批策略"""
    ALWAYS_REQUIRE = "always_require"     # 始终需要审批
    AUTO_WHEN_LOW = "auto_when_low"        # 低优先级自动执行
    AUTO_WHEN_WHITELISTED = "auto_whitelisted"  # 白名单仓库自动执行
    NEVER_AUTO = "never_auto"             # 永不自动执行


@dataclass
class ActionResult:
    """操作结果"""
    success: bool
    action_type: str
    description: str
    error: str | None = None
    output: str = ""
    timestamp: str = ""
    requires_followup: bool = False


@dataclass
class ResponderConfig:
    """响应器配置"""
    auto_merge_dependabot: bool = False
    auto_close_stale_days: int = 0
    auto_restart_failed_workflows: bool = False
    auto_label_security_issues: bool = True
    auto_analyze_failure: bool = True
    require_approval_for_public_repos: bool = True
    allowed_repos: list[str] = field(default_factory=list)  # 白名单
    blocked_actions: list[str] = field(default_factory=list)  # 禁止的操作
    comment_templates: dict[str, str] = field(default_factory=dict)
    
    # 通知转发配置
    notify_webhook_url: str = ""  # Webhook URL for forwarding failures
    notify_on_failure: bool = True  # Whether to forward failure notifications
    notify_channels: list[str] = field(default_factory=list)  # ["webhook", "email", "slack"]
    slack_webhook_url: str = ""
    email_smtp_server: str = ""
    email_smtp_port: int = 587
    email_sender: str = ""
    email_password: str = ""
    email_receivers: list[str] = field(default_factory=list)


class GitHubEmailResponder:
    """
    GitHub 邮件自动响应器

    根据解析后的邮件内容，执行相应的仓库维护操作。
    """

    def __init__(
        self,
        config: ResponderConfig | None = None,
        github_token: str | None = None,
        dry_run: bool = False,
    ):
        self._config = config or ResponderConfig()
        self._github_token = github_token or os.getenv("GITHUB_TOKEN", "")
        self._dry_run = dry_run
        self._action_log: list[ActionResult] = []
        self._custom_handlers: dict[str, Callable] = {}

    def handle_email(self, parsed: ParsedEmail) -> list[ActionResult]:
        """
        处理解析后的邮件，执行相应操作

        Args:
            parsed: 解析后的邮件对象

        Returns:
            操作结果列表
        """
        results: list[ActionResult] = []

        for action in parsed.actions:
            result = self._execute_action(action)
            results.append(result)
            self._action_log.append(result)

            if result.success:
                logger.info(f"操作成功: {result.description}")
            else:
                logger.warning(f"操作失败: {result.description} - {result.error}")

        return results

    def _execute_action(self, action: ParsedAction) -> ActionResult:
        """执行单个操作"""
        # 检查是否需要审批
        if self._requires_approval(action):
            return ActionResult(
                success=False,
                action_type=action.action_type,
                description=f"需要人工审批: {action.description}",
                error="requires_approval",
                timestamp=datetime.now(timezone.utc).isoformat(),
                requires_followup=True,
            )

        # 检查是否在黑名单中
        if action.action_type in self._config.blocked_actions:
            return ActionResult(
                success=False,
                action_type=action.action_type,
                description=f"操作被禁止: {action.action_type}",
                error="action_blocked",
                timestamp=datetime.now(timezone.utc).isoformat(),
            )

        # Dry run 模式
        if self._dry_run:
            return ActionResult(
                success=True,
                action_type=action.action_type,
                description=f"[DRY RUN] {action.description}",
                output=f"将执行: {action.suggested_command}",
                timestamp=datetime.now(timezone.utc).isoformat(),
            )

        # 分发到具体处理器
        handler = self._custom_handlers.get(action.action_type)
        if handler:
            return handler(action)

        handler_map = {
            "review_pr": self._handle_review_pr,
            "pr_merged": self._handle_pr_merged,
            "auto_merge_dependabot": self._handle_merge_dependabot,
            "review_dependabot": self._handle_review_dependabot,
            "handle_issue": self._handle_issue,
            "read_comment": self._handle_comment,
            "investigate_workflow_failure": self._handle_workflow_failure,
            "handle_security_alert": self._handle_security_alert,
            "release_published": self._handle_release,
        }

        handler_func = handler_map.get(action.action_type)
        if handler_func:
            return handler_func(action)

        return ActionResult(
            success=False,
            action_type=action.action_type,
            description=f"未找到处理器: {action.action_type}",
            error="no_handler",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    def _requires_approval(self, action: ParsedAction) -> bool:
        """检查操作是否需要审批"""
        # 明确需要审批的操作
        if action.requires_approval:
            return True

        # 公开仓库的所有写操作需要审批
        if self._config.require_approval_for_public_repos:
            # 这里简化处理，实际应该检查仓库可见性
            pass

        # 白名单仓库可跳过审批
        repo_key = f"{action.repo_owner}/{action.repo}"
        if repo_key in self._config.allowed_repos:
            return False

        # 低优先级操作且配置允许自动执行
        if (self._config.auto_merge_dependabot
                and action.action_type in ("auto_merge_dependabot",)):
            return False

        return action.requires_approval

    def _run_gh_command(self, cmd: list[str]) -> tuple[bool, str]:
        """执行 GitHub CLI 命令"""
        if not self._github_token:
            return False, "GITHUB_TOKEN 未设置"

        env = os.environ.copy()
        env["GH_TOKEN"] = self._github_token

        try:
            result = subprocess.run(
                ["gh"] + cmd,
                capture_output=True,
                text=True,
                timeout=60,
                env=env,
            )
            success = result.returncode == 0
            output = result.stdout if success else result.stderr
            return success, output.strip()
        except subprocess.TimeoutExpired:
            return False, "命令执行超时"
        except Exception as e:
            return False, str(e)

    # ===== 具体操作处理器 =====

    def _handle_review_pr(self, action: ParsedAction) -> ActionResult:
        """处理 PR 审查请求"""
        if not action.pr_number:
            return ActionResult(
                success=False,
                action_type=action.action_type,
                description="缺少 PR 编号",
                error="missing_pr_number",
                timestamp=datetime.now(timezone.utc).isoformat(),
            )

        success, output = self._run_gh_command([
            "pr", "view", str(action.pr_number),
            "--repo", f"{action.repo_owner}/{action.repo}",
            "--json", "title,body,state,files,commits",
        ])

        if success:
            return ActionResult(
                success=True,
                action_type=action.action_type,
                description=f"已获取 PR #{action.pr_number} 信息",
                output=output,
                timestamp=datetime.now(timezone.utc).isoformat(),
                requires_followup=True,
            )

        return ActionResult(
            success=False,
            action_type=action.action_type,
            description=f"获取 PR #{action.pr_number} 信息失败",
            error=output,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    def _handle_pr_merged(self, action: ParsedAction) -> ActionResult:
        """处理 PR 合并通知"""
        return ActionResult(
            success=True,
            action_type=action.action_type,
            description=f"PR #{action.pr_number} 已合并，无需操作",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    def _handle_merge_dependabot(self, action: ParsedAction) -> ActionResult:
        """自动合并 Dependabot PR"""
        if not action.pr_number:
            return ActionResult(
                success=False,
                action_type=action.action_type,
                description="缺少 PR 编号",
                error="missing_pr_number",
                timestamp=datetime.now(timezone.utc).isoformat(),
            )

        success, output = self._run_gh_command([
            "pr", "merge", str(action.pr_number),
            "--squash", "--delete-branch",
            "--repo", f"{action.repo_owner}/{action.repo}",
        ])

        if success:
            return ActionResult(
                success=True,
                action_type=action.action_type,
                description=f"已自动合并 Dependabot PR #{action.pr_number}",
                output=output,
                timestamp=datetime.now(timezone.utc).isoformat(),
            )

        return ActionResult(
            success=False,
            action_type=action.action_type,
            description=f"合并 Dependabot PR #{action.pr_number} 失败",
            error=output,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    def _handle_review_dependabot(self, action: ParsedAction) -> ActionResult:
        """审查 Dependabot PR（获取信息，不自动合并）"""
        if not action.pr_number:
            return ActionResult(
                success=False,
                action_type=action.action_type,
                description="缺少 PR 编号",
                error="missing_pr_number",
                timestamp=datetime.now(timezone.utc).isoformat(),
            )

        success, output = self._run_gh_command([
            "pr", "view", str(action.pr_number),
            "--repo", f"{action.repo_owner}/{action.repo}",
            "--json", "title,body,state,mergeable,mergeStateStatus",
        ])

        if success:
            return ActionResult(
                success=True,
                action_type=action.action_type,
                description=f"已获取 Dependabot PR #{action.pr_number} 信息",
                output=output,
                timestamp=datetime.now(timezone.utc).isoformat(),
                requires_followup=True,
            )

        return ActionResult(
            success=False,
            action_type=action.action_type,
            description=f"获取 Dependabot PR 信息失败",
            error=output,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    def _handle_issue(self, action: ParsedAction) -> ActionResult:
        """处理分配的 Issue"""
        if not action.issue_number:
            return ActionResult(
                success=False,
                action_type=action.action_type,
                description="缺少 Issue 编号",
                error="missing_issue_number",
                timestamp=datetime.now(timezone.utc).isoformat(),
            )

        success, output = self._run_gh_command([
            "issue", "view", str(action.issue_number),
            "--repo", f"{action.repo_owner}/{action.repo}",
            "--json", "title,body,state,labels,assignees",
        ])

        if success:
            return ActionResult(
                success=True,
                action_type=action.action_type,
                description=f"已获取 Issue #{action.issue_number} 信息",
                output=output,
                timestamp=datetime.now(timezone.utc).isoformat(),
                requires_followup=True,
            )

        return ActionResult(
            success=False,
            action_type=action.action_type,
            description=f"获取 Issue 信息失败",
            error=output,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    def _handle_comment(self, action: ParsedAction) -> ActionResult:
        """处理新评论"""
        number = action.issue_number or action.pr_number
        if not number:
            return ActionResult(
                success=False,
                action_type=action.action_type,
                description="缺少 Issue/PR 编号",
                error="missing_number",
                timestamp=datetime.now(timezone.utc).isoformat(),
            )

        # 先判断是 PR 还是 Issue
        success, output = self._run_gh_command([
            "issue", "view", str(number),
            "--repo", f"{action.repo_owner}/{action.repo}",
            "--json", "title,body,comments",
        ])

        if success:
            return ActionResult(
                success=True,
                action_type=action.action_type,
                description=f"已读取 #{number} 的新评论",
                output=output,
                timestamp=datetime.now(timezone.utc).isoformat(),
                requires_followup=True,
            )

        return ActionResult(
            success=False,
            action_type=action.action_type,
            description=f"获取评论失败",
            error=output,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    def _handle_workflow_failure(self, action: ParsedAction) -> ActionResult:
        """处理 Workflow 失败（包含自动重启、失败分析、通知转发）"""
        repo = f"{action.repo_owner}/{action.repo}"
        
        # 获取最近的失败运行
        success, output = self._run_gh_command([
            "run", "list",
            "--repo", repo,
            "--status", "failure",
            "--limit", "1",
            "--json", "name,status,conclusion,createdAt,headBranch,databaseId",
        ])

        if not success:
            return ActionResult(
                success=False,
                action_type=action.action_type,
                description=f"获取 Workflow 失败信息失败",
                error=output,
                timestamp=datetime.now(timezone.utc).isoformat(),
            )

        # 解析 run ID
        run_id = None
        try:
            runs = json.loads(output) if output else []
            if runs:
                run_id = runs[0].get("databaseId")
        except (json.JSONDecodeError, IndexError, KeyError):
            pass

        # ===== 1. 自动重启 =====
        restart_result = None
        if self._config.auto_restart_failed_workflows and run_id:
            restart_success, restart_output = self._run_gh_command([
                "run", "rerun", str(run_id),
                "--repo", repo,
                "--failed",
            ])
            restart_result = {
                "success": restart_success,
                "output": restart_output,
            }

        # ===== 2. 失败原因分析 =====
        analysis_result = None
        if self._config.auto_analyze_failure:
            analysis_result = self._analyze_workflow_failure(repo, run_id)

        # ===== 3. 通知转发 =====
        notification_result = None
        if self._config.notify_on_failure:
            notification_result = self._forward_failure_notification(
                repo=repo,
                action=action,
                run_id=run_id,
                restart_result=restart_result,
                analysis_result=analysis_result,
            )

        # 构建综合结果
        description_parts = [f"Workflow 失败: {action.metadata.get('workflow_name', 'unknown')}"]
        if restart_result:
            if restart_result["success"]:
                description_parts.append("已自动重启")
            else:
                description_parts.append("重启失败")
        if analysis_result:
            description_parts.append(f"失败原因: {analysis_result.get('summary', '未知')}")
        if notification_result:
            description_parts.append(f"通知已转发到 {', '.join(notification_result.get('channels', []))}")

        return ActionResult(
            success=True,
            action_type=action.action_type,
            description="; ".join(description_parts),
            output=json.dumps({
                "run_id": run_id,
                "restart": restart_result,
                "analysis": analysis_result,
                "notification": notification_result,
            }, indent=2, ensure_ascii=False),
            timestamp=datetime.now(timezone.utc).isoformat(),
            requires_followup=True,
        )

    def _analyze_workflow_failure(
        self,
        repo: str,
        run_id: int | None = None,
    ) -> dict[str, Any]:
        """分析 Workflow 失败原因"""
        if not run_id:
            return {"summary": "无法获取 run ID，跳过分析"}

        # 获取失败 job 列表
        success, jobs_output = self._run_gh_command([
            "api",
            f"/repos/{repo}/actions/runs/{run_id}/jobs",
            "--method", "GET",
        ])

        if not success:
            return {"summary": "获取 job 列表失败", "error": jobs_output}

        failed_jobs = []
        try:
            jobs_data = json.loads(jobs_output)
            for job in jobs_data.get("jobs", []):
                if job.get("conclusion") == "failure":
                    job_info = {
                        "name": job.get("name", "unknown"),
                        "status": job.get("status"),
                        "conclusion": job.get("conclusion"),
                        "steps": [],
                    }
                    
                    # 获取失败步骤
                    for step in job.get("steps", []):
                        if step.get("conclusion") == "failure":
                            job_info["steps"].append({
                                "name": step.get("name", "unknown"),
                                "status": step.get("status"),
                                "conclusion": step.get("conclusion"),
                            })
                    
                    failed_jobs.append(job_info)
        except (json.JSONDecodeError, KeyError):
            pass

        # 提取失败原因摘要
        if failed_jobs:
            job_names = [j["name"] for j in failed_jobs]
            summary = f"{len(failed_jobs)} 个 job 失败: {', '.join(job_names)}"
            
            # 常见失败模式识别
            for job in failed_jobs:
                for step in job.get("steps", []):
                    step_name = step.get("name", "").lower()
                    if "test" in step_name:
                        summary += "; 测试失败"
                    elif "lint" in step_name or "quality" in step_name:
                        summary += "; 代码质量检查失败"
                    elif "coverage" in step_name:
                        summary += "; 覆盖率不达标"
                    elif "audit" in step_name:
                        summary += "; 安全审计失败"
        else:
            summary = "未知失败原因"

        return {
            "summary": summary,
            "failed_jobs": failed_jobs,
            "run_url": f"https://github.com/{repo}/actions/runs/{run_id}",
        }

    def _forward_failure_notification(
        self,
        repo: str,
        action: ParsedAction,
        run_id: int | None = None,
        restart_result: dict | None = None,
        analysis_result: dict | None = None,
    ) -> dict[str, Any]:
        """转发失败通知到多个渠道"""
        channels_used = []
        
        workflow_name = action.metadata.get("workflow_name", "unknown")
        summary_parts = [
            f"🔴 Workflow 失败: {workflow_name}",
            f"仓库: {repo}",
        ]
        if run_id:
            summary_parts.append(f"Run: https://github.com/{repo}/actions/runs/{run_id}")
        if analysis_result:
            summary_parts.append(f"原因: {analysis_result.get('summary', '未知')}")
        if restart_result:
            if restart_result.get("success"):
                summary_parts.append("状态: 已自动重启")
            else:
                summary_parts.append("状态: 重启失败，需人工介入")
        
        message = "\n".join(summary_parts)

        # 发送到 Webhook
        if self._config.notify_webhook_url:
            try:
                payload = json.dumps({
                    "content": message,
                    "repo": repo,
                    "workflow": workflow_name,
                    "run_id": run_id,
                }).encode()
                req = urllib.request.Request(
                    self._config.notify_webhook_url,
                    data=payload,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=10) as resp:
                    if resp.status in (200, 204):
                        channels_used.append("webhook")
            except Exception as e:
                logger.warning(f"Webhook 通知失败: {e}")

        # 发送到 Slack
        if self._config.slack_webhook_url:
            try:
                payload = json.dumps({
                    "text": message,
                }).encode()
                req = urllib.request.Request(
                    self._config.slack_webhook_url,
                    data=payload,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=10) as resp:
                    if resp.status in (200, 204):
                        channels_used.append("slack")
            except Exception as e:
                logger.warning(f"Slack 通知失败: {e}")

        # 发送邮件通知
        if self._config.email_smtp_server and self._config.email_receivers:
            try:
                import smtplib
                from email.mime.text import MIMEText
                
                msg = MIMEText(message, "plain", "utf-8")
                msg["Subject"] = f"[{repo}] Workflow 失败: {workflow_name}"
                msg["From"] = self._config.email_sender
                msg["To"] = ", ".join(self._config.email_receivers)
                
                if self._config.email_smtp_port == 465:
                    server = smtplib.SMTP_SSL(
                        self._config.email_smtp_server,
                        self._config.email_smtp_port,
                    )
                else:
                    server = smtplib.SMTP(
                        self._config.email_smtp_server,
                        self._config.email_smtp_port,
                    )
                    server.starttls()
                
                server.login(self._config.email_sender, self._config.email_password)
                server.sendmail(
                    self._config.email_sender,
                    self._config.email_receivers,
                    msg.as_string(),
                )
                server.quit()
                channels_used.append("email")
            except Exception as e:
                logger.warning(f"邮件通知失败: {e}")

        return {
            "success": len(channels_used) > 0,
            "channels": channels_used,
        }

    def _handle_security_alert(self, action: ParsedAction) -> ActionResult:
        """处理安全告警"""
        success, output = self._run_gh_command([
            "api",
            f"/repos/{action.repo_owner}/{action.repo}/code-scanning/alerts",
            "--method", "GET",
        ])

        if success:
            result = ActionResult(
                success=True,
                action_type=action.action_type,
                description=f"已获取安全告警列表",
                output=output,
                timestamp=datetime.now(timezone.utc).isoformat(),
                requires_followup=True,
            )

            # 自动添加标签
            if self._config.auto_label_security_issues:
                labels = ["security", "bug", "critical"]
                # 这里简化处理，实际需要知道具体的 issue/pr
                pass

            return result

        return ActionResult(
            success=False,
            action_type=action.action_type,
            description=f"获取安全告警失败",
            error=output,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    def _handle_release(self, action: ParsedAction) -> ActionResult:
        """处理新版本发布"""
        success, output = self._run_gh_command([
            "release", "list",
            "--repo", f"{action.repo_owner}/{action.repo}",
            "--limit", "3",
        ])

        if success:
            return ActionResult(
                success=True,
                action_type=action.action_type,
                description=f"已获取最新版本列表",
                output=output,
                timestamp=datetime.now(timezone.utc).isoformat(),
            )

        return ActionResult(
            success=False,
            action_type=action.action_type,
            description=f"获取版本列表失败",
            error=output,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    # ===== 配置和注册 =====

    def register_handler(
        self,
        action_type: str,
        handler: Callable[[ParsedAction], ActionResult],
    ) -> None:
        """注册自定义处理器"""
        self._custom_handlers[action_type] = handler

    def set_config(self, **kwargs: Any) -> None:
        """更新配置"""
        for key, value in kwargs.items():
            if hasattr(self._config, key):
                setattr(self._config, key, value)

    def get_action_log(self) -> list[dict[str, Any]]:
        """获取操作日志"""
        return [
            {
                "success": r.success,
                "action_type": r.action_type,
                "description": r.description,
                "error": r.error,
                "timestamp": r.timestamp,
                "requires_followup": r.requires_followup,
            }
            for r in self._action_log
        ]

    def save_action_log(self, path: str | Path) -> None:
        """保存操作日志到文件"""
        log_data = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "dry_run": self._dry_run,
            "actions": self.get_action_log(),
        }
        Path(path).write_text(json.dumps(log_data, indent=2, ensure_ascii=False))


def create_github_email_responder(
    github_token: str | None = None,
    dry_run: bool = False,
    auto_merge_dependabot: bool = False,
    auto_restart_failed_workflows: bool = False,
    auto_analyze_failure: bool = True,
    notify_on_failure: bool = True,
    allowed_repos: list[str] | None = None,
    notify_webhook_url: str | None = None,
    slack_webhook_url: str | None = None,
    email_smtp_server: str | None = None,
    email_sender: str | None = None,
    email_password: str | None = None,
    email_receivers: list[str] | None = None,
) -> GitHubEmailResponder:
    """创建 GitHub 邮件响应器"""
    config = ResponderConfig(
        auto_merge_dependabot=auto_merge_dependabot,
        auto_restart_failed_workflows=auto_restart_failed_workflows,
        auto_analyze_failure=auto_analyze_failure,
        notify_on_failure=notify_on_failure,
        allowed_repos=allowed_repos or [],
        notify_webhook_url=notify_webhook_url or os.getenv("NOTIFY_WEBHOOK_URL", ""),
        slack_webhook_url=slack_webhook_url or os.getenv("SLACK_WEBHOOK_URL", ""),
        email_smtp_server=email_smtp_server or os.getenv("NOTIFY_EMAIL_SMTP", ""),
        email_sender=email_sender or os.getenv("NOTIFY_EMAIL_SENDER", ""),
        email_password=email_password or os.getenv("NOTIFY_EMAIL_PASSWORD", ""),
        email_receivers=email_receivers or [
            r.strip()
            for r in os.getenv("NOTIFY_EMAIL_RECEIVERS", "").split(",")
            if r.strip()
        ],
    )

    return GitHubEmailResponder(
        config=config,
        github_token=github_token,
        dry_run=dry_run,
    )
