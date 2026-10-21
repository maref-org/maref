"""Three-model silver labeling for calibration episodes.

Three providers vote independently; only majority-agreed fields are stored.
Results are *silver*, never ground truth: they are tagged with the model set
and per-field agreement so a later human audit can measure drift.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from typing import Any

from .label import FIX_TYPES, ROOT_CAUSES, SEVERITIES, record_label

FIELDS = ("root_cause", "fix_type", "severity", "reusable")
ROOT_VALUES = set(ROOT_CAUSES.values())
FIX_VALUES = set(FIX_TYPES.values())
SEV_VALUES = set(SEVERITIES.values())


@dataclass(frozen=True)
class Model:
    name: str
    base_url: str
    model: str
    key_env: str
    extra: dict[str, Any] = dataclass_field(default_factory=dict)


MODELS = {
    "deepseek": Model(
        "deepseek", "https://api.deepseek.com/v1", "deepseek-chat", "DEEPSEEK_API_KEY"
    ),
    "qwen": Model(
        "qwen",
        "https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
        "qwen3.8-max",
        "BAILIAN_TOKEN_API_KEY",
        {"enable_thinking": False},
    ),
    "glm": Model(
        "glm",
        "https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
        "glm-5.2",
        "BAILIAN_TOKEN_API_KEY",
        {"thinking": {"type": "disabled"}},
    ),
}

RUBRIC = """你是软件失败事件标注器。根据错误证据，从固定枚举中选值，只输出一个 JSON 对象。

root_cause（失败根因）:
- environment: 权限、路径/命令不存在、服务未启动、网络/VPN、磁盘
- dependency: 缺包、版本冲突、import 失败
- logic: 测试失败、断言、业务逻辑错误
- type: 语法/类型错误
- prompt: 指令不清、用户纠正、agent 理解偏差
- tool: 工具自身故障、治理拦截、MCP 超时、编辑器匹配失败
- lint: linter 报告
- other / unknown: 其他或无法判断

fix_type（实际所需修复动作）: code | config | prompt | retry | none
severity: critical | high | medium | low（是否阻断任务、能否自动恢复）
reusable: true 表示该教训可迁移到其他任务

示例:
1. "[MAREF] BLOCKED (Write:AGENTS.md): require_hitl_for" -> {"root_cause":"tool","fix_type":"config","severity":"high","reusable":true}
2. "FAILED tests/x.py::test_y - AssertionError: 1 != 2" -> {"root_cause":"logic","fix_type":"code","severity":"high","reusable":true}
3. "ls: /data/x: No such file or directory" -> {"root_cause":"environment","fix_type":"config","severity":"medium","reusable":false}
4. "Error calling MCP: Request timed out after 3000ms" -> {"root_cause":"tool","fix_type":"retry","severity":"medium","reusable":false}
5. 用户说“还是报错，重新跑一次” -> {"root_cause":"prompt","fix_type":"prompt","severity":"medium","reusable":true}
6. "ruff: E501 line too long" -> {"root_cause":"lint","fix_type":"code","severity":"low","reusable":true}
"""


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return {}
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def parse_vote(text: str) -> dict[str, Any]:
    data = _extract_json(text)
    root = str(data.get("root_cause") or "").strip().lower()
    fix = str(data.get("fix_type") or "").strip().lower()
    sev = str(data.get("severity") or "").strip().lower()
    reusable = data.get("reusable")
    if isinstance(reusable, str):
        reusable = reusable.strip().lower() in {"true", "yes", "y", "1"}
    return {
        "root_cause": root if root in ROOT_VALUES else "",
        "fix_type": fix if fix in FIX_VALUES else "",
        "severity": sev if sev in SEV_VALUES else "",
        "reusable": reusable if isinstance(reusable, bool) else None,
    }


def _prompt(item: dict[str, Any]) -> str:
    snippet = str(item.get("snippet") or "")[:360]
    return (
        f"{RUBRIC}\n事件:\n"
        f"- runtime: {item.get('runtime', '')}\n"
        f"- error_class: {item.get('error_class', '')}\n"
        f"- tool: {item.get('tool', '')}\n"
        f"- outcome: {item.get('outcome', '')}\n"
        f"- snippet: {snippet}\n"
        '只输出: {"root_cause":"","fix_type":"","severity":"","reusable":true}'
    )


def _request(model: Model, messages: list[dict[str, str]], timeout: int, retries: int) -> str:
    key = os.environ.get(model.key_env, "")
    if not key:
        return ""
    body = json.dumps(
        {
            "model": model.model,
            "temperature": 0,
            "max_tokens": 800,
            "messages": messages,
            **model.extra,
        }
    ).encode()
    request = urllib.request.Request(
        f"{model.base_url}/chat/completions",
        data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = json.load(response)
            return str(payload["choices"][0]["message"].get("content") or "")
        except Exception:  # noqa: BLE001 - network errors are retried
            if attempt >= retries:
                return ""
            time.sleep(1.5 * (attempt + 1))
    return ""


def ask(model: Model, prompt: str, timeout: int = 120, retries: int = 2) -> dict[str, Any]:
    content = _request(model, [{"role": "user", "content": prompt}], timeout, retries)
    vote = parse_vote(content)
    if all(vote[field] not in (None, "") for field in FIELDS):
        return vote
    repair = (
        prompt + "\n\n上一次输出不合法或被截断。只输出一个 JSON 对象，四个字段都必须存在，"
        "root_cause 只能取 environment|dependency|logic|type|prompt|tool|lint|other|unknown，"
        "fix_type 只能取 code|config|prompt|retry|none。不要输出解释。"
    )
    return parse_vote(_request(model, [{"role": "user", "content": repair}], timeout, retries))


def consensus(votes: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Majority per field; ties yield None. Returns values + agreement stats."""
    result: dict[str, Any] = {}
    unanimous = 0
    for field in FIELDS:
        values = [vote.get(field) for vote in votes.values() if vote.get(field) not in (None, "")]
        counts: dict[Any, int] = {}
        for value in values:
            counts[value] = counts.get(value, 0) + 1
        best = max(counts.values()) if counts else 0
        winners = [value for value, count in counts.items() if count == best]
        result[field] = winners[0] if len(winners) == 1 and best >= 2 else None
        if len(winners) == 1 and best == len(votes):
            unanimous += 1
    result["unanimous_fields"] = unanimous
    result["agreement"] = round(unanimous / len(FIELDS), 3)
    result["votes"] = len(votes)
    return result


def label_item(item: dict[str, Any], models: list[Model], call: Any = None) -> dict[str, Any]:
    ask_fn = call or ask
    prompt = _prompt(item)
    with ThreadPoolExecutor(max_workers=len(models)) as pool:
        votes = list(pool.map(lambda model: ask_fn(model, prompt), models))
    by_model = {model.name: vote for model, vote in zip(models, votes, strict=True)}
    result = consensus(by_model)
    result["model_votes"] = by_model
    return result


def _items_from_batch(path: str) -> list[dict[str, Any]]:
    items = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict) and "id" in item:
                items.append(item)
    return items


def run(
    conn: sqlite3.Connection,
    batch_path: str,
    model_names: list[str],
    workers: int = 6,
    write: bool = False,
    limit: int | None = None,
) -> dict[str, Any]:
    items = _items_from_batch(batch_path)
    if limit:
        items = items[:limit]
    models = [MODELS[name] for name in model_names if name in MODELS]
    pending = []
    for item in items:
        row = conn.execute("SELECT label_status FROM episode WHERE id=?", (item["id"],)).fetchone()
        if row is not None and row["label_status"] == "pending":
            pending.append(item)

    def annotate(item: dict[str, Any]) -> dict[str, Any]:
        result = label_item(item, models)
        result["id"] = item["id"]
        return result

    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(annotate, pending))

    accepted = 0
    review = 0
    for result in results:
        ok = result["votes"] == len(models) and all(result[field] is not None for field in FIELDS)
        episode_id = str(result["id"])
        if ok:
            accepted += 1
            if write:
                record_label(
                    conn,
                    episode_id,
                    root_cause=str(result["root_cause"]),
                    fix_type=str(result["fix_type"]),
                    severity=str(result["severity"]),
                    reusable=bool(result["reusable"]),
                    notes=f"[silver] agreement={result['agreement']}",
                    labeled_by="llm-consensus:" + ",".join(m.name for m in models),
                )
                conn.execute(
                    "UPDATE label SET llm_suggestion_json=?, agree_with_llm=? WHERE episode_id=?",
                    (
                        json.dumps(result["model_votes"], ensure_ascii=False),
                        int(result["agreement"] * 100),
                        episode_id,
                    ),
                )
        else:
            review += 1
            if write:
                conn.execute(
                    "UPDATE episode SET label_status='needs_review' WHERE id=?", (episode_id,)
                )
                conn.execute(
                    "INSERT OR REPLACE INTO label(episode_id, labeled_by, labeled_at,"
                    " llm_suggestion_json, agree_with_llm) VALUES(?,?,?,?,?)",
                    (
                        episode_id,
                        "llm-consensus:" + ",".join(m.name for m in models),
                        time.time(),
                        json.dumps(result["model_votes"], ensure_ascii=False),
                        int(result["agreement"] * 100),
                    ),
                )
    if write:
        conn.commit()
    stats = {
        "items": len(items),
        "accepted": accepted,
        "needs_review": review,
        "unanimous_rate": round(
            sum(1 for r in results if r["unanimous_fields"] == len(FIELDS)) / len(results), 3
        )
        if results
        else 0.0,
        "field_majority": {
            field: round(sum(1 for r in results if r[field] is not None) / len(results), 3)
            for field in FIELDS
        }
        if results
        else {},
        "field_unanimity": {
            field: round(
                sum(
                    1
                    for r in results
                    if len({v.get(field) for v in r["model_votes"].values()}) == 1
                )
                / len(results),
                3,
            )
            for field in FIELDS
        }
        if results
        else {},
    }
    return {"stats": stats, "results": results, "batch": batch_path}


def write_results(results: dict[str, Any], out: str) -> None:
    with open(out, "w", encoding="utf-8") as handle:
        for result in results["results"]:
            handle.write(json.dumps(result, ensure_ascii=False) + "\n")
