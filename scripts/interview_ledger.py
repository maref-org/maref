#!/usr/bin/env python3
"""访谈账本：把"聊过了"变成可核验、可被否证的市场证据。

为什么需要它：2026-11-21 的产物层诊断结论是"能力已够、缺的是外部验证"。
外部验证的第一道是**切换访谈**——不问"你会用吗"，只问"过去 12 个月你为这个
问题花了多少钱/加了多少班"。本脚本负责三件事：

1. ``--check``  结构校验（fail-closed）：缺 consent / 日期 / persona / 信号，
                或出现姓名、手机号、邮箱、微信等 PII 字段，一律拒绝。
2. ``--eval``   汇总硬信号，并在达到门槛时判定"需求假设被早期否证"（exit 3），
                脚本只报计数与阈值，不替人下"需求成立"的结论。
3. ``--report`` 生成 markdown 表，供对外材料引用（只含角色与机构类型，不含个人）。

判定口径（与诊断报告 §6.4 / §9.2 一致）：

- 硬信号 hard：``would_buy.signal == paid``（已付费/已中标）；
- 强信号 strong：``quote_requested`` / ``trial``（要过报价或进过试用）；
- 真实切换 switched：过去 12 个月为此**花过钱**或**加过班**（>0）；
- kill：访谈数 ≥ ``--kill-min`` 且 hard=strong=0 且 switched=0。

诚实边界：本脚本不会输出"需求已验证"。它只能证明"到目前为止没找到愿意付钱的人"，
或"已经找到 N 个愿意付钱的人"。后者仍需合同/发票/中标通知才能升级为 E1 证据。
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover - 环境守卫
    print("ERROR: 需要 pyyaml（pip install pyyaml）", file=sys.stderr)
    raise SystemExit(2) from None

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LEDGER = ROOT / "docs" / "research" / "interviews" / "ledger.yaml"

PERSONAS = {"integrator", "assessor", "regulated_enterprise", "platform", "other"}
SIGNALS = {"none", "interest", "trial", "quote_requested", "paid"}
HARD = {"paid"}
STRONG = {"quote_requested", "trial"}

# 只允许记录"角色"，不允许记录"人"。出现这些键即视为 PII 泄露风险。
FORBIDDEN_KEYS = {
    "name",
    "contact_name",
    "phone",
    "mobile",
    "telephone",
    "email",
    "mail",
    "wechat",
    "wx",
    "weixin",
}
ALLOWED_ROOT_KEYS = {
    "schema",
    "interviews",
}
# `switched` 不在必填项里：它由 spend_cny / hours_wasted 推导，不接受手填。
REQUIRED_ENTRY_KEYS = {"id", "date", "persona", "consent", "would_buy"}

_EXIT_OK = 0
_EXIT_INVALID = 1
_EXIT_USAGE = 2
_EXIT_KILL = 3


@dataclass
class Finding:
    level: str  # ERROR | WARNING
    where: str
    detail: str


def _as_int(value: Any) -> int:
    if value is None or value == "":
        return 0
    if isinstance(value, bool):
        raise ValueError("布尔值不能当作金额/小时")
    return int(value)


def _check_artifacts(entry: dict[str, Any], findings: list[Finding]) -> None:
    artifacts = entry.get("artifacts") or []
    if not isinstance(artifacts, list):
        findings.append(Finding("ERROR", str(entry.get("id")), "artifacts 必须是列表"))
        return
    for item in artifacts:
        path = ROOT / str(item)
        if not path.exists():
            findings.append(Finding("ERROR", str(entry.get("id")), f"证据文件不存在: {item}"))


def validate_entry(entry: dict[str, Any], index: int) -> list[Finding]:
    where = str(entry.get("id") or f"#{index}")
    findings: list[Finding] = []

    missing = REQUIRED_ENTRY_KEYS - set(entry)
    if missing:
        findings.append(Finding("ERROR", where, f"缺少字段: {sorted(missing)}"))

    leaked = FORBIDDEN_KEYS & set(entry)
    if leaked:
        findings.append(Finding("ERROR", where, f"禁止记录个人信息字段: {sorted(leaked)}"))

    persona = entry.get("persona")
    if persona is not None and persona not in PERSONAS:
        findings.append(Finding("ERROR", where, f"persona 非法: {persona!r}"))

    consent = entry.get("consent")
    if consent is not True:
        findings.append(Finding("ERROR", where, "consent 必须显式为 true（可记录、可引用）"))

    raw_date = entry.get("date")
    try:
        date.fromisoformat(str(raw_date))
    except (TypeError, ValueError):
        findings.append(Finding("ERROR", where, f"date 无法解析: {raw_date!r}"))

    would_buy = entry.get("would_buy")
    if not isinstance(would_buy, dict):
        findings.append(Finding("ERROR", where, "would_buy 必须是对象"))
    else:
        signal = would_buy.get("signal")
        if signal not in SIGNALS:
            findings.append(Finding("ERROR", where, f"would_buy.signal 非法: {signal!r}"))
        if signal in HARD | STRONG:
            try:
                if _as_int(would_buy.get("amount_cny")) <= 0:
                    findings.append(
                        Finding("ERROR", where, "有报价/付费信号但 amount_cny 缺失或 <= 0")
                    )
            except (TypeError, ValueError):
                findings.append(Finding("ERROR", where, "would_buy.amount_cny 不是整数"))

    for key in ("spend_cny", "hours_wasted"):
        try:
            _as_int(entry.get(key))
        except (TypeError, ValueError):
            findings.append(Finding("ERROR", where, f"{key} 不是整数"))

    _check_artifacts(entry, findings)
    return findings


def validate_ledger(data: dict[str, Any]) -> list[Finding]:
    if not isinstance(data, dict) or not isinstance(data.get("interviews"), list):
        return [Finding("ERROR", "root", "ledger 顶层必须是 {interviews: [...]}")]

    unknown_root = set(data) - ALLOWED_ROOT_KEYS
    findings = (
        [Finding("WARNING", "root", f"未知顶层键: {sorted(unknown_root)}")] if unknown_root else []
    )

    seen: set[str] = set()
    for index, entry in enumerate(data["interviews"]):
        if not isinstance(entry, dict):
            findings.append(Finding("ERROR", f"#{index}", "条目必须是对象"))
            continue
        findings.extend(validate_entry(entry, index))
        entry_id = str(entry.get("id") or "")
        if entry_id:
            if entry_id in seen:
                findings.append(Finding("ERROR", entry_id, "id 重复"))
            seen.add(entry_id)

    return findings


def evaluate(data: dict[str, Any], kill_min: int) -> dict[str, Any]:
    entries = [e for e in data.get("interviews", []) if isinstance(e, dict)]
    signals: dict[str, int] = {}
    hard = strong = switched = 0
    spend_total = 0
    hours_total = 0

    for entry in entries:
        signal = str((entry.get("would_buy") or {}).get("signal") or "none")
        signals[signal] = signals.get(signal, 0) + 1
        try:
            spend = _as_int(entry.get("spend_cny"))
            hours = _as_int(entry.get("hours_wasted"))
        except (TypeError, ValueError):
            spend = hours = 0
        spend_total += spend
        hours_total += hours
        if signal in HARD:
            hard += 1
        if signal in STRONG:
            strong += 1
        if spend > 0 or hours > 0:
            switched += 1

    total = len(entries)
    kill = total >= kill_min and hard == 0 and strong == 0 and switched == 0

    if total == 0:
        verdict = "证据不足：还没有任何访谈记录"
    elif total < kill_min:
        verdict = f"证据不足：{total}/{kill_min} 场，未到判定门槛"
    elif kill:
        verdict = f"需求假设被早期否证：{total} 场里 0 个硬/强信号、0 人为此花过钱或加过班"
    elif hard:
        verdict = f"已出现 {hard} 个硬信号（已付费/已中标），但仍需合同或发票才能升级为 E1"
    else:
        verdict = f"出现 {strong} 个强信号（报价/试用），尚未付费"

    return {
        "interviews": total,
        "signals": signals,
        "hard": hard,
        "strong": strong,
        "switched": switched,
        "spend_cny": spend_total,
        "hours_wasted": hours_total,
        "kill": kill,
        "kill_min": kill_min,
        "verdict": verdict,
    }


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"找不到账本: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError("ledger 顶层必须是对象")
    return data


def _print_findings(findings: list[Finding]) -> int:
    errors = [f for f in findings if f.level == "ERROR"]
    for finding in findings:
        stream = sys.stderr if finding.level == "ERROR" else sys.stdout
        print(f"[{finding.level}] {finding.where}: {finding.detail}", file=stream)
    return len(errors)


def _report(data: dict[str, Any], summary: dict[str, Any]) -> str:
    lines = [
        "# 访谈账本摘要",
        "",
        f"- 访谈数：**{summary['interviews']}**（判定门槛 {summary['kill_min']}）",
        f"- 硬信号（已付费/中标）：**{summary['hard']}**",
        f"- 强信号（报价/试用）：**{summary['strong']}**",
        f"- 真实切换（花过钱/加过班）：**{summary['switched']}**",
        f"- 合计花费：¥{summary['spend_cny']:,}；合计加班：{summary['hours_wasted']} 小时",
        "",
        "| id | 日期 | 角色 | 信号 | 花费(¥) | 加班(h) | 判决 |",
        "|---|---|---|---|---|---|---|",
    ]
    for entry in data.get("interviews", []):
        wb = entry.get("would_buy") or {}
        lines.append(
            f"| {entry.get('id', '')} | {entry.get('date', '')} | {entry.get('persona', '')} "
            f"| {wb.get('signal', 'none')} | {entry.get('spend_cny', 0)} "
            f"| {entry.get('hours_wasted', 0)} | {wb.get('amount_cny', '') or '-'} |"
        )
    lines += ["", f"> {summary['verdict']}"]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="MAREF 访谈账本")
    parser.add_argument("--file", "-f", default=str(DEFAULT_LEDGER), help="账本路径")
    parser.add_argument("--check", action="store_true", help="只做结构校验（fail-closed）")
    parser.add_argument("--eval", action="store_true", help="汇总信号并判定 kill")
    parser.add_argument("--report", action="store_true", help="输出 markdown 摘要")
    parser.add_argument("--json", action="store_true", help="机器可读输出")
    parser.add_argument("--kill-min", type=int, default=5, help="判定门槛（默认 5 场先导）")
    args = parser.parse_args(argv)

    if not args.check and not args.eval and not args.report:
        args.check = args.eval = True

    try:
        data = _load(Path(args.file))
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return _EXIT_USAGE

    findings = validate_ledger(data)
    errors = _print_findings(findings)

    if args.check:
        # --json 时保持 stdout 纯 JSON，人类摘要走 stderr。
        stream = sys.stderr if args.json else sys.stdout
        print(f"{len(findings) - errors} warning, {errors} error", file=stream)
        if errors:
            return _EXIT_INVALID

    if errors:
        # 结构不合法时不评估：宁可拒绝，也不要把脏数据算成"没需求"。
        print("ERROR: 账本结构不合法，拒绝对其评估", file=sys.stderr)
        return _EXIT_INVALID

    if not args.eval and not args.report:
        return _EXIT_OK

    summary = evaluate(data, args.kill_min)
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    if args.report:
        print(_report(data, summary), end="")
    if args.eval and not args.json:
        print(
            f"访谈 {summary['interviews']}｜hard {summary['hard']}｜strong {summary['strong']}"
            f"｜switched {summary['switched']}｜{summary['verdict']}"
        )

    return _EXIT_KILL if summary["kill"] else _EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
