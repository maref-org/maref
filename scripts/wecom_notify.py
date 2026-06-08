#!/usr/bin/env python3
"""WeCom (企业微信) notification sender for MAREF study syncing.

Usage:
    # Send a text message to all members
    python scripts/wecom_notify.py --title "研究结论已同步" --message "..."

    # Send a markdown message (WeCom Bot mode only)
    python scripts/wecom_notify.py --webhook --title "..." --message "..."

Environment variables:
    WECOM_CORPID       — 企业微信 CorpID
    WECOM_AGENTID      — 企业微信 AgentId
    WECOM_SECRET       — 企业微信应用 Secret
    WECOM_WEBHOOK_URL  — 企业微信机器人 Webhook URL（备选）

    These can be set in .env (development) or ~/.maref.env (production),
    or stored in macOS Keychain via keyring_store.py.
"""

import json
import os
import sys
from argparse import ArgumentParser, RawDescriptionHelpFormatter

import requests


def get_access_token(corpid: str, secret: str) -> str:
    resp = requests.get(
        "https://qyapi.weixin.qq.com/cgi-bin/gettoken",
        params={"corpid": corpid, "corpsecret": secret},
        timeout=10,
    )
    data = resp.json()
    if data.get("errcode") != 0:
        raise RuntimeError(f"Failed to get access token: {data.get('errmsg', data)}")
    return data["access_token"]


def send_app_message(
    token: str,
    agent_id: str,
    title: str,
    message: str,
    to_user: str = "@all",
) -> dict:
    """Send application message (支持文本和 markdown 卡片)."""
    payload = {
        "touser": to_user,
        "msgtype": "textcard",
        "agentid": agent_id,
        "textcard": {
            "title": title,
            "description": message,
            "url": "https://github.com/maref-org/maref",
            "btntxt": "查看详情",
        },
    }
    resp = requests.post(
        f"https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={token}",
        json=payload,
        timeout=10,
    )
    data = resp.json()
    if data.get("errcode") != 0:
        raise RuntimeError(f"Failed to send message: {data.get('errmsg', data)}")
    return data


def send_webhook_message(webhook_url: str, title: str, message: str) -> dict:
    """Send markdown message via group robot webhook."""
    payload = {
        "msgtype": "markdown",
        "markdown": {
            "content": f"# {title}\n{message}",
        },
    }
    resp = requests.post(webhook_url, json=payload, timeout=10)
    data = resp.json()
    if data.get("errcode") != 0:
        raise RuntimeError(f"Failed to send webhook message: {data.get('errmsg', data)}")
    return data


def load_env() -> None:
    """Load .env or ~/.maref.env if present."""
    for env_file in [".env", os.path.expanduser("~/.maref.env")]:
        if os.path.isfile(env_file):
            with open(env_file) as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, _, value = line.partition("=")
                    os.environ.setdefault(key.strip(), value.strip())
            break


def main() -> None:
    load_env()

    parser = ArgumentParser(
        description="Send WeCom (企业微信) notification for MAREF sync",
        formatter_class=RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--title", required=True, help="Message title")
    parser.add_argument("--message", required=True, help="Message body (text or markdown)")
    parser.add_argument("--webhook", action="store_true", help="Use webhook robot mode instead of app message")
    parser.add_argument("--to", default="@all", help="Target user (app message mode, default: @all)")
    args = parser.parse_args()

    try:
        if args.webhook:
            webhook_url = os.environ.get("WECOM_WEBHOOK_URL")
            if not webhook_url:
                print("ERROR: WECOM_WEBHOOK_URL not set", file=sys.stderr)
                sys.exit(1)
            result = send_webhook_message(webhook_url, args.title, args.message)
        else:
            corpid = os.environ.get("WECOM_CORPID")
            secret = os.environ.get("WECOM_SECRET")
            agent_id = os.environ.get("WECOM_AGENTID")
            if not all([corpid, secret, agent_id]):
                print("ERROR: WECOM_CORPID, WECOM_SECRET, WECOM_AGENTID must be set", file=sys.stderr)
                sys.exit(1)
            token = get_access_token(corpid, secret)
            result = send_app_message(token, agent_id, args.title, args.message, to_user=args.to)

        print(f"OK: {json.dumps(result, ensure_ascii=False)}")

    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
