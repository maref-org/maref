#!/usr/bin/env python3
"""TLA+ 配置审计：每个 .cfg 都必须对应一个真实存在的规格，且它引用的每个
不变量/性质/常量都能在该规格（含仓库内 EXTENDS 链）里被定义。

背景（2026-11-22）：仓库有 10 个 .cfg，但 formal-verify.yml 只跑 4 个。抽查发现
另有两处死配置：
  - src/formal/MarefAgent24MC.cfg 把关键字写成 `INVARIANCES`（非法），
    TLC 报配置错误 —— 该规格从落地起从未被检查；
  - src/formal/MAREF_CrossDimModel.cfg 引用的 4 个不变量在任何 .tla 里都不存在
    （对应规格从未写出），是纯孤儿配置。
两者都不会让 CI 变红，因为 CI 从不碰它们。本脚本把"孤儿/坏配置"变成可执行检查。

用法:
  python3 scripts/formal_cfg_audit.py            # 人类可读 + 退出码
  python3 scripts/formal_cfg_audit.py --json     # 机器可读
  python3 scripts/formal_cfg_audit.py --root DIR # 指向其它检出（测试用）
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

IDENT_SECTIONS = ("INVARIANT", "INVARIANTS", "PROPERTY", "PROPERTIES", "SPECIFICATION")
DECL_SECTIONS = ("CONSTANT", "CONSTANTS")
# 其余已知关键字：出现即结束上一段，其值不做标识符解析
OTHER_SECTIONS = (
    "CHECK_DEADLOCK",
    "CONSTRAINT",
    "CONSTRAINTS",
    "ACTION_CONSTRAINT",
    "ACTION_CONSTRAINTS",
    "SYMMETRY",
    "VIEW",
    "ALIAS",
    "INIT",
    "NEXT",
    "POSTCONDITION",
    "DEADLOCK",
    "TERMINAL",
)

_NAME_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*(?:\([^)]*\))?\s*==", re.MULTILINE)
_CONST_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*(?:,|$)")
_EXTENDS_RE = re.compile(r"^EXTENDS\s+(.+)$", re.MULTILINE)


def _strip_cfg_comments(text: str) -> str:
    text = re.sub(r"\(\*.*?\*\)", "", text, flags=re.DOTALL)
    return re.sub(r"^\\\*.*$", "", text, flags=re.MULTILINE)


def parse_cfg(path: Path) -> tuple[set[str], set[str]]:
    """返回 (需要解析的标识符, 声明的常量名)。"""
    wanted: set[str] = set()
    constants: set[str] = set()
    section = ""
    for raw in _strip_cfg_comments(path.read_text(encoding="utf-8", errors="replace")).splitlines():
        line = raw.strip()
        if not line:
            continue
        head = line.split()[0].upper()
        if head in OTHER_SECTIONS:
            section = ""
            continue
        if head in IDENT_SECTIONS or head in DECL_SECTIONS:
            section = "ident" if head in IDENT_SECTIONS else "const"
            rest = line[len(line.split()[0]) :].strip()
            if not rest:
                continue
            line = rest
            head = line.split()[0].upper()
        if section == "ident" and head not in IDENT_SECTIONS:
            for tok in line.replace(",", " ").split():
                if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", tok):
                    wanted.add(tok)
        elif section == "const":
            m = _CONST_RE.match(line)
            if m:
                constants.add(m.group(1))
    return wanted, constants


def module_names(path: Path) -> set[str]:
    """模块里定义的名字（`X ==` / `X(a) ==`）+ CONSTANTS 声明。"""
    text = path.read_text(encoding="utf-8", errors="replace")
    names = set(_NAME_RE.findall(text))
    for block in re.findall(r"^CONSTANTS?\s*(.+?)(?=^\S|\Z)", text, re.MULTILINE | re.DOTALL):
        for m in re.finditer(r"^([A-Za-z_][A-Za-z0-9_]*)", block, re.MULTILINE):
            names.add(m.group(1))
    return names


def resolve(path: Path, seen: set[Path]) -> set[str]:
    if path in seen or not path.is_file():
        return set()
    seen.add(path)
    names = module_names(path)
    for ext in _EXTENDS_RE.findall(path.read_text(encoding="utf-8", errors="replace")):
        for mod in (p.strip() for p in ext.split(",")):
            names |= resolve(path.parent / f"{mod}.tla", seen)
    return names


def tracked_cfgs(root: Path) -> list[Path]:
    try:
        out = subprocess.run(
            ["git", "ls-files", "-z", "--", "*.cfg"], cwd=root, capture_output=True, check=True
        ).stdout
        return [root / p for p in out.decode("utf-8", "replace").split("\0") if p]
    except (OSError, subprocess.CalledProcessError):
        return sorted(root.rglob("*.cfg"))


def workflow_refs(root: Path) -> str:
    wf = root / ".github" / "workflows"
    if not wf.is_dir():
        return ""
    return "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in wf.glob("*.yml"))


def audit(root: Path) -> list[dict[str, object]]:
    wf_text = workflow_refs(root)
    results: list[dict[str, object]] = []
    for cfg in tracked_cfgs(root):
        wanted, constants = parse_cfg(cfg)
        rel = str(cfg.relative_to(root))
        siblings = sorted(cfg.parent.glob("*.tla"))
        best: Path | None = None
        best_missing: set[str] = set(wanted | constants)
        for spec in siblings:
            defined = resolve(spec, set())
            missing = (wanted | constants) - defined
            if not missing:
                best, best_missing = spec, set()
                break
            if len(missing) < len(best_missing):
                best, best_missing = spec, missing
        status = "ok"
        detail = ""
        if best is None:
            status = "orphan"
            detail = "同目录没有能解析其标识符的 .tla"
        elif best_missing:
            status = "broken"
            detail = f"{best.name} 未定义: {', '.join(sorted(str(m) for m in best_missing))}"
        results.append(
            {
                "cfg": rel,
                "spec": best.name if best else None,
                "status": status,
                "detail": detail,
                "in_ci": rel in wf_text,
            }
        )
    return results


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    root = Path(args.root).resolve()
    results = audit(root)
    failures = [r for r in results if r["status"] != "ok"]
    if args.json:
        print(
            json.dumps(
                {"results": results, "failures": len(failures)}, indent=2, ensure_ascii=False
            )
        )
    else:
        for r in results:
            mark = {"ok": "✅", "broken": "❌", "orphan": "🟠"}[str(r["status"])]
            ci = "CI" if r["in_ci"] else "  "
            print(f"{mark} {ci}  {r['cfg']}  → {r['spec'] or '(无)'}  {r['detail']}")
        not_in_ci = [r["cfg"] for r in results if not r["in_ci"]]
        print(
            f"\n共 {len(results)} 个 .cfg：坏/孤儿 {len(failures)} 个；未被 CI 引用 {len(not_in_ci)} 个"
        )
        if not_in_ci:
            print("未进 CI（不算失败，但要知道）: " + ", ".join(str(c) for c in not_in_ci))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
