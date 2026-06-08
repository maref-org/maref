#!/usr/bin/env python3
"""
OPC 一窗通名称自主申报 — 智动化
=============================
三步自动导航 → 自动填充字号/行业/资本
您只需处理: 验证码 + 电子签名
=========================================================
用法: python3 /Volumes/1TB-M2/public/maref/scripts/opc_register_automation.py
"""

import sys, time
from playwright.sync_api import sync_playwright

FORM = {
    "xinghao": "硅基",
    "beixuan": ["硅基", "双生", "融硅", "衍易", "爻变"],
    "hangye": "智能科技",
    "ziben": "100",
    "chuzi_qixian": "2031-06-02",
    "gudong_bili": "100",
}


def L(msg):
    print(f"  [{time.strftime('%H:%M')}] {msg}")


def run():
    print("\n  ╔══════════════════════════════════════════╗")
    print("  ║   OPC 一窗通 · 智动化                   ║")
    print(f"  ║   公司: 深圳市{FORM['xinghao']}{FORM['hangye']}有限公司  ║")
    print("  ║                                          ║")
    print("  ║   三步自动导航 → 自动填充               ║")
    print("  ║   您只需处理: 验证码 + 签名             ║")
    print("  ╚══════════════════════════════════════════╝\n")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", headless=False)
        page = browser.new_page()
        page.set_default_timeout(30000)

        # ─── ① OPC 服务专区 ───────────────────────────
        URL_1 = "https://amr.sz.gov.cn/xxgk/qt/ztlm/opcfwzq/"
        L(f"① 打开 OPC 服务专区...")
        page.goto(URL_1, wait_until="networkidle", timeout=60000)
        time.sleep(2)
        L(f"   当前页面: {page.title()}")

        # ─── ② 点击「立即在线开办」→ 企业开办页 ─────
        URL_2 = "https://amr.sz.gov.cn/xxgk/qt/ztlm/qykb/"
        L(f"② 进入企业开办平台...")
        page.goto(URL_2, wait_until="networkidle", timeout=60000)
        time.sleep(2)
        L(f"   当前页面: {page.title()}")

        # ─── ③ 点击「办理入口」→ 广东政务服务网 ─────
        L(f"③ 查找「办理入口」...")
        btn = page.get_by_text("办理入口", exact=False).or_(
              page.locator("a:has-text('办理入口')")).or_(
              page.locator("button:has-text('办理入口')")).first
        if btn.count() > 0 and btn.is_visible():
            with page.expect_navigation(timeout=30000):
                btn.click()
            time.sleep(3)
            L(f"   当前页面: {page.url}")
        else:
            L(f"   未找到「办理入口」，请手动点击")
            input("   按 Enter 继续...")

        # ─── ④ 权责清单 → 选择内资有限责任公司 ───────
        L(f"④ 选择「内资有限责任公司设立登记」...")
        link = page.get_by_text("内资有限责任公司设立登记", exact=True).or_(
               page.locator("a:has-text('内资有限责任公司设立登记')")).or_(
               page.locator("div:has-text('内资有限责任公司设立登记')")).first
        if link.count() > 0 and link.is_visible():
            with page.expect_navigation(timeout=30000):
                link.click()
            time.sleep(2)
            L(f"   已选择内资有限责任公司")
        else:
            L(f"   未找到，请手动点击")
            input("   按 Enter 继续...")

        # ─── ⑤ 使用其他企业名称申请 ──────────────────
        L(f"⑤ 进入名称申报...")
        btn2 = page.get_by_text("使用其他企业名称申请", exact=False).or_(
               page.locator("a:has-text('使用其他企业名称申请')")).first
        if btn2.count() > 0 and btn2.is_visible():
            btn2.click()
            time.sleep(2)
        else:
            L(f"   未找到，请手动点击")
            input("   按 Enter 继续...")

        # ─── ⑥ 选「名称自主申报」→ 下一步 ───────────
        L(f"⑥ 勾选「名称自主申报」...")
        radio = page.locator("input[type='radio']").first
        if radio.count() > 0:
            radio.check()
            time.sleep(0.5)
        nxt = page.get_by_text("下一步").or_(
              page.locator("button:has-text('下一步')")).first
        if nxt.count() > 0:
            nxt.click()
            time.sleep(2)

        # ─── ⑦ 自动填充 ──────────────────────────────
        L(f"⑦ 自动填充表单...")
        time.sleep(1)

        # 字号
        for sel in ["input[id*='xinghao']", "input[name*='xinghao']",
                     "input[placeholder*='字号']"]:
            inp = page.locator(sel).first
            if inp.count() > 0 and inp.is_visible():
                inp.fill(FORM["xinghao"])
                L(f"   ✅ 字号: {FORM['xinghao']}")
                break

        input("   处理验证码 → 点击查重确认 → Enter")

        # 行业
        for sel in ["input[id*='hangye']", "input[name*='hangye']",
                     "input[placeholder*='行业']"]:
            inp = page.locator(sel).first
            if inp.count() > 0 and inp.is_visible():
                inp.fill(FORM["hangye"])
                L(f"   ✅ 行业: {FORM['hangye']}")
                break

        input("   确认行业 → 选择企业类型「有限责任公司(自然人独资)」→ Enter")

        # ─── ⑧ 投资人信息 ────────────────────────────
        print(f"\n  ┌──── 投资人信息 ────────────────────┐")
        print(f"  │  出资比例: {FORM['gudong_bili']}%                  │")
        print(f"  │  出资期限: {FORM['chuzi_qixian']}              │")
        print(f"  └─────────────────────────────────────┘")
        input("   填写投资人信息 → Enter")

        # ─── ⑨ 提交 ──────────────────────────────────
        print(f"\n  ✅ 名称: 深圳市{FORM['xinghao']}{FORM['hangye']}有限公司")
        print(f"  ✅ 类型: 有限责任公司（自然人独资）")
        input("   提交申请 → Enter")

        L("名称自主申报完成！")
        input("   按 Enter 关闭浏览器")
        browser.close()


if __name__ == "__main__":
    run()
