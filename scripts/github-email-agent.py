#!/usr/bin/env python3
"""
GitHub 邮件监听 Agent 入口脚本

用法:
    # 启动持续监听
    python scripts/github-email-agent.py

    # 单次轮询
    python scripts/github-email-agent.py --once

    # Dry run 模式
    python scripts/github-email-agent.py --dry-run

    # 指定邮箱提供商
    python scripts/github-email-agent.py --provider qq

    # 查看统计
    python scripts/github-email-agent.py --stats
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from src.maref.tools.github_email_listener import (
    GitHubEmailListener,
    GitHubEmail,
    create_github_email_listener,
)
from src.maref.tools.github_email_parser import (
    GitHubEmailParser,
    ParsedEmail,
)
from src.maref.tools.github_email_responder import (
    GitHubEmailResponder,
    create_github_email_responder,
)

logger = logging.getLogger("github-email-agent")


def setup_logging(verbose: bool = False) -> None:
    """配置日志"""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def parse_args() -> argparse.Namespace:
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description="GitHub 邮件监听 Agent")
    parser.add_argument(
        "--once", action="store_true",
        help="单次轮询后退出",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Dry run 模式，记录操作但不执行",
    )
    parser.add_argument(
        "--provider", type=str, default=None,
        help="邮箱提供商 (hotmail, qq, gmail)",
    )
    parser.add_argument(
        "--interval", type=int, default=None,
        help="轮询间隔（秒）",
    )
    parser.add_argument(
        "--stats", action="store_true",
        help="显示统计信息后退出",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="详细日志",
    )
    parser.add_argument(
        "--log-file", type=str, default=None,
        help="日志文件路径",
    )
    return parser.parse_args()


def print_banner() -> None:
    """打印启动横幅"""
    banner = """
╔══════════════════════════════════════════════╗
║       GitHub 邮件监听 Agent v1.0.0           ║
║                                              ║
║  监听 → 解析 → 自动响应                      ║
╚══════════════════════════════════════════════╝
"""
    print(banner)


def on_signal(signum: int, frame) -> None:
    """信号处理"""
    logger.info(f"收到信号 {signum}，正在关闭...")
    sys.exit(0)


def main() -> None:
    args = parse_args()
    setup_logging(args.verbose)

    # 日志文件
    if args.log_file:
        fh = logging.FileHandler(args.log_file)
        fh.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        ))
        logging.getLogger().addHandler(fh)

    # 信号处理
    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGTERM, on_signal)

    # 打印横幅
    if not args.stats:
        print_banner()

    provider = args.provider or os.getenv("GITHUB_EMAIL_PROVIDER", "hotmail")
    interval = args.interval or int(os.getenv("GITHUB_EMAIL_POLL_INTERVAL", "60"))
    dry_run = args.dry_run or os.getenv("GITHUB_EMAIL_DRY_RUN", "false").lower() == "true"
    auto_merge_dependabot = os.getenv(
        "GITHUB_EMAIL_AUTO_MERGE_DEPENDABOT", "false"
    ).lower() == "true"
    auto_restart_workflows = os.getenv(
        "GITHUB_EMAIL_AUTO_RESTART_WORKFLOWS", "false"
    ).lower() == "true"
    auto_analyze_failure = os.getenv(
        "GITHUB_EMAIL_AUTO_ANALYZE_FAILURE", "true"
    ).lower() == "true"
    notify_on_failure = os.getenv(
        "GITHUB_EMAIL_NOTIFY_ON_FAILURE", "true"
    ).lower() == "true"

    # 创建监听器
    listener = create_github_email_listener(
        provider=provider,
        poll_interval=interval,
    )

    # 创建解析器
    parser = GitHubEmailParser(
        auto_merge_dependabot=auto_merge_dependabot,
    )

    # 创建响应器
    responder = create_github_email_responder(
        github_token=os.getenv("GITHUB_TOKEN"),
        dry_run=dry_run,
        auto_merge_dependabot=auto_merge_dependabot,
        auto_restart_failed_workflows=auto_restart_workflows,
        auto_analyze_failure=auto_analyze_failure,
        notify_on_failure=notify_on_failure,
        notify_webhook_url=os.getenv("NOTIFY_WEBHOOK_URL"),
        slack_webhook_url=os.getenv("SLACK_WEBHOOK_URL"),
        email_smtp_server=os.getenv("NOTIFY_EMAIL_SMTP"),
        email_sender=os.getenv("NOTIFY_EMAIL_SENDER"),
        email_password=os.getenv("NOTIFY_EMAIL_PASSWORD"),
        email_receivers=[
            r.strip()
            for r in os.getenv("NOTIFY_EMAIL_RECEIVERS", "").split(",")
            if r.strip()
        ],
    )

    # 注册处理回调
    def handle_email_callback(gh_email: GitHubEmail) -> None:
        """邮件处理回调"""
        parsed = parser.parse(
            subject=gh_email.subject,
            body_preview=gh_email.body_preview,
            from_addr=gh_email.from_addr,
            action_url=gh_email.action_url,
        )

        if parsed is None:
            logger.debug(f"跳过非 GitHub 邮件: {gh_email.subject}")
            return

        logger.info(f"解析结果: {parsed.summary}")

        # 执行响应
        results = responder.handle_email(parsed)

        for result in results:
            status = "✓" if result.success else "✗"
            logger.info(f"  {status} {result.description}")
            if result.error and result.error != "requires_approval":
                logger.warning(f"    错误: {result.error}")
            if result.requires_followup:
                logger.info(f"    需要后续操作")

    listener.register_handler(
        # 导入所有通知类型
        __import__(
            "src.maref.tools.github_email_listener",
            fromlist=["GitHubNotificationType"],
        ).GitHubNotificationType.PR_REVIEW_REQUEST,
        handle_email_callback,
    )

    # 注册其他通知类型
    from src.maref.tools.github_email_listener import GitHubNotificationType

    for notif_type in GitHubNotificationType:
        if notif_type != GitHubNotificationType.PR_REVIEW_REQUEST:
            listener.register_handler(notif_type, handle_email_callback)

    # 执行
    if args.stats:
        stats = listener.get_stats()
        print(json.dumps(stats, indent=2, ensure_ascii=False))
        return

    if args.once:
        logger.info("执行单次轮询...")
        emails = listener.poll_once()
        logger.info(f"处理了 {len(emails)} 封邮件")

        # 保存操作日志
        log_path = Path("logs/email-agent-actions.json")
        log_path.parent.mkdir(parents=True, exist_ok=True)
        responder.save_action_log(log_path)
        logger.info(f"操作日志已保存: {log_path}")
        return

    logger.info(f"启动持续监听 (interval={interval}s, dry_run={dry_run})")
    try:
        listener.start()
    except KeyboardInterrupt:
        logger.info("用户中断")
    finally:
        listener.stop()

        # 保存最终统计
        stats = listener.get_stats()
        stats_path = Path("logs/email-agent-stats.json")
        stats_path.parent.mkdir(parents=True, exist_ok=True)
        stats_path.write_text(json.dumps(stats, indent=2, ensure_ascii=False))
        logger.info(f"最终统计已保存: {stats_path}")


if __name__ == "__main__":
    main()
