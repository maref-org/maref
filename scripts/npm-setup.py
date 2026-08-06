#!/usr/bin/env python3
"""
MAREF npm 注册 + 发布助手

利用 Playwright 自动化:
  1. 打开 npmjs.com 注册/登录页
  2. 使用 GitHub OAuth 一键登录（共享浏览器已登录 GitHub）
  3. 用户完成邮箱验证（人工步骤）
  4. 自动执行 npm login + npm publish

用法:
  python3 scripts/npm-setup.py [--publish-only]

依赖:
  playwright (已安装)
  chromium (已安装)
"""

import subprocess
import sys
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SDK_DIR = REPO_ROOT / "sdk" / "typescript"


def check_playwright() -> bool:
    try:
        from playwright.sync_api import sync_playwright
        return True
    except ImportError:
        return False


def open_npm_registration():
    """打开 npm 注册页，让用户通过 GitHub 登录"""
    print("=" * 60)
    print("MAREF npm 注册助手")
    print("=" * 60)
    print()
    print("正在启动浏览器...")
    print()

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,  # 可见窗口，方便用户交互
            channel=None,    # 使用 Playwright 自带的 Chromium
        )
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
        )
        page = context.new_page()

        print("🌐 已打开 npm 注册页面")
        print()
        print("操作步骤:")
        print("  1. 点击「Sign up for free」或「Sign in with GitHub」")
        print("  2. 如果选 GitHub: 授权 npm 访问你的 GitHub 账号")
        print("  3. 如果选 Email: 输入邮箱 → 收验证邮件 → 点击确认链接")
        print("  4. 注册完成后回到此终端")
        print()
        input("按 Enter 继续打开 npmjs.com...")

        page.goto("https://www.npmjs.com/signup", wait_until="networkidle")
        print("✅ 页面已加载，请在浏览器中完成注册")
        print()

        # 等待用户完成注册（检测 URL 变为已登录状态）
        print("等待注册完成... 注册成功后请回到此终端按 Enter")
        input("按 Enter 继续（如果已注册）...")

        # 检查是否已登录
        page.goto("https://www.npmjs.com/settings/profile", wait_until="networkidle")
        current_url = page.url
        if "settings" in current_url:
            print("✅ npm 已登录！")
        else:
            print("⚠️ 似乎还未登录，请检查浏览器窗口")
            input("登录完成后按 Enter 继续...")

        browser.close()


def do_npm_login_and_publish():
    """在终端中执行 npm login 和 publish"""
    print()
    print("=" * 60)
    print("npm 登录 + 发布")
    print("=" * 60)
    print()
    print("现在需要在终端中登录 npm（使用浏览器中注册的账号）")
    print()

    # npm login
    result = subprocess.run(
        ["npm", "login", "--registry=https://registry.npmjs.org/"],
        cwd=str(SDK_DIR),
    )
    if result.returncode != 0:
        print("❌ npm login 失败")
        return False

    print("✅ npm login 成功！")
    print()

    # Build SDK
    print("构建 SDK...")
    result = subprocess.run(
        ["npm", "run", "build"],
        cwd=str(SDK_DIR),
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"❌ Build 失败:\n{result.stderr}")
        return False
    print("✅ Build 成功")
    print()

    # Publish
    print("发布 @maref/sdk@0.2.0 ...")
    result = subprocess.run(
        ["npm", "publish", "--registry=https://registry.npmjs.org/",
         "--access", "public"],
        cwd=str(SDK_DIR),
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"❌ 发布失败:\n{result.stderr}")
        return False

    print()
    print("🎉 @maref/sdk@0.2.0 已成功发布到 npm！")
    print(f"   查看: https://www.npmjs.com/package/@maref/sdk")
    return True


def main():
    publish_only = "--publish-only" in sys.argv

    if not check_playwright():
        print("❌ Playwright 未安装。运行: pip install playwright && playwright install chromium")
        sys.exit(1)

    if not publish_only:
        open_npm_registration()

    do_npm_login_and_publish()


if __name__ == "__main__":
    main()
