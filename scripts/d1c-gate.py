#!/usr/bin/env python3
"""
D1c Gate — 自动合规检查 + 推送

流程:
  1. 检查当前分支是否在 public/maref
  2. 运行完整的合规检查：
     a. 无内部路径 (grep /Volumes/1TB-M2)
     b. 无 API 密钥 (grep sk-*, nvapi-*)
     c. 无 Athena 专有文件
     d. 所有 remote 指向 maref-org
  3. 生成合规报告
  4. 推送到 maref-org/maref
  5. 记录推送日志

模式:
  --check-only: 仅检查，不推送
  --push: 检查通过后自动推送
  --auto: 作为 CI 后置步骤运行（非交互式）
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

PUBLIC_MAREF = Path("/Volumes/1TB-M2/public/maref")

FORBIDDEN_PATTERNS: list[tuple[str, str, str]] = [
    ("internal_path", r"/Volumes/1TB-M2", "HIGH"),
    ("username_path", r"/Users/(frankie|maref)", "HIGH"),
    ("private_org", r"frankiehot-tech", "HIGH"),
    ("api_key", r"sk-[a-zA-Z0-9]{32,}", "CRITICAL"),
    ("api_key_nvidia", r"nvapi-[a-zA-Z0-9_-]{30,}", "CRITICAL"),
    ("api_key_ark", r"ark-[a-zA-Z0-9-]{20,}", "CRITICAL"),
]

FORBIDDEN_FILES: list[str] = [
    "SOUL.md",
    "IDENTITY.md",
    "HEARTBEAT.md",
    "TOOLS.md",
    "USER.md",
]

REQUIRED_REMOTE = "maref-org/maref"


def run_git(args: list[str], cwd: Path = PUBLIC_MAREF) -> tuple[int, str, str]:
    try:
        result = subprocess.run(
            ["git", "-C", str(cwd)] + args,
            capture_output=True, text=True, timeout=30,
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except Exception as e:
        return -1, "", str(e)


def check_remote() -> list[str]:
    """Verify remote points to maref-org/maref."""
    errors = []
    rc, out, _ = run_git(["remote", "-v"])
    for line in out.split("\n"):
        if "(push)" in line and REQUIRED_REMOTE not in line:
            errors.append(f"Push remote 不是 {REQUIRED_REMOTE}: {line}")
    return errors


def check_staged_files() -> list[dict]:
    """Check staged files for forbidden patterns."""
    violations = []
    rc, out, _ = run_git(["diff", "--cached", "--name-only", "--diff-filter=ACMR"])
    if rc != 0:
        return [{"file": "git", "message": "git diff 失败"}]

    for filepath in out.split("\n"):
        if not filepath.strip():
            continue

        # Check filename
        if Path(filepath).name in FORBIDDEN_FILES:
            violations.append({
                "file": filepath,
                "line": 0,
                "rule": "forbidden_file",
                "severity": "CRITICAL",
                "message": f"禁止的文件: {Path(filepath).name}",
            })
            continue

        # Check content
        rc, content, _ = run_git(["show", ":" + filepath])
        if rc != 0:
            continue

        for pattern_name, pattern_regex, severity in FORBIDDEN_PATTERNS:
            for i, line in enumerate(content.split("\n"), 1):
                if re.search(pattern_regex, line):
                    violations.append({
                        "file": filepath,
                        "line": i,
                        "rule": pattern_name,
                        "severity": severity,
                        "content": line.strip()[:100],
                    })

    return violations


def check_oss_moat() -> list[str]:
    """运行 oss-check.sh 校验公开 tree 的闭源/敏感路径（护城河门禁，fail-closed）。

    D1c 是公开仓的"官方推送路径"，必须自带护城河检查——不能只依赖 pre-push
    （pre-push 可被 --no-verify 或异环境绕过）。脚本缺失/异常一律按未通过处理。
    """
    script = PUBLIC_MAREF / "scripts" / "oss-check.sh"
    if not script.exists():
        return [f"oss-check.sh 缺失（fail-closed 阻断）: {script}"]
    try:
        result = subprocess.run(
            ["bash", str(script), "HEAD"],
            cwd=str(PUBLIC_MAREF), capture_output=True, text=True, timeout=180,
        )
    except Exception as e:
        return [f"oss-check 执行异常（fail-closed）: {e}"]
    if result.returncode != 0:
        hits = [
            ln.strip()
            for ln in (result.stdout + "\n" + result.stderr).splitlines()
            if "✗" in ln or "命中" in ln
        ]
        return ["oss-check 未通过（护城河门禁）"] + (hits or [result.stdout.strip()[:200]])
    return []


def main() -> int:
    # ── 环境检查 ──
    try:
        import sys as _sys
        _sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
        from maref.infra.check_env import require_env
        require_env()
    except ImportError:
        pass

    parser = argparse.ArgumentParser(description="D1c Gate — 合规检查 + 推送")
    parser.add_argument("--check-only", action="store_true", help="仅检查，不推送")
    parser.add_argument("--push", action="store_true", help="检查通过后自动推送")
    parser.add_argument("--auto", action="store_true", help="非交互模式")
    args = parser.parse_args()

    print("🔍 D1c Gate — 合规检查")
    print("═" * 40)

    # Step 1: Check remote
    print("\n📡 检查远程仓库...")
    remote_errors = check_remote()
    if remote_errors:
        for e in remote_errors:
            print(f"  ❌ {e}")
    else:
        print("  ✅ Remote 正确指向 maref-org/maref")

    # Step 2: Check staged files
    print("\n📄 检查暂存文件...")
    violations = check_staged_files()
    if violations:
        critical = [v for v in violations if v["severity"] == "CRITICAL"]
        high = [v for v in violations if v["severity"] == "HIGH"]

        for v in violations:
            icon = "🔴" if v["severity"] == "CRITICAL" else "🟡"
            print(f"  {icon} {v['file']}:{v.get('line', '?')} — {v['message']}")

        if critical:
            print(f"\n❌ {len(critical)} 项严重违规，推送已阻止")
            return 1
    else:
        print("  ✅ 无违规")

    # Step 2.5: Check OSS moat (护城河门禁 — 闭源路径不得进入公开 tree)
    print("\n🛡️ 检查开源护城河 (oss-check)...")
    moat = check_oss_moat()
    if moat:
        for m in moat:
            print(f"  🔴 {m}")
        print("\n❌ 护城河门禁未通过，推送已阻止")
        return 1
    else:
        print("  ✅ 无闭源路径命中")

    # Step 3: Summary
    print("\n" + "═" * 40)
    print("✅ 合规检查通过")

    if args.push:
        print("\n📤 推送到 maref-org/maref...")
        rc, out, err = run_git(["push", "origin", "main"])
        if rc == 0:
            print("  ✅ 推送成功")
        else:
            print(f"  ❌ 推送失败: {err}")
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
