#!/usr/bin/env python3
"""CostGuard 开源接入示例（INC-2026-08-13-001 追审部署包）。

将 MAREF 开源成本护栏执行端（src/maref/cost_guard.py）接入任意
HTTP 代理 / 网关节点的最小模板。本文件自包含可运行，仅用于演示接线，
可直接复制进你的代理代码（如 unified_proxy 兼容层或新的网关实现）。

用法（测试）：
    python3 deploy/cost-guard-gateway-example.py --self-test

前置：
    pip install -e .[dev]  （或 export PYTHONPATH=src）
    maref cost-policy       （生成 ~/.maref/proxy_config.json 阈值）
    ~/.maraf_hmac_key       （审计 HMAC 密钥，否则 fail-closed 不写审计）
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

# 确保能 import 开源 CostGuard（dev 安装或 PYTHONPATH=src）
SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from maref.cost_guard import CostGuard  # noqa: E402


def intercept_request(guard: CostGuard, model: str, body: dict[str, object]) -> tuple[int | None, str | None]:
    """对一次 API 请求执行三层成本护栏。

    返回 (status_code, error_message)；None, None 表示放行。
    """
    # 1. CALL-GUARD：30 分钟滑动窗口次数上限（高价模型收紧）
    limit, blocked = guard.enforce_call(model)
    if blocked:
        guard.log_guard_block(model, "call_guard", f"limit={limit}/30min")
        return 429, f"模型 {model} 近 30 分钟调用已达上限（{limit} 次），请稍后再试"

    # 2. CTX-GUARD：请求上下文长度（防上下文膨胀烧钱）
    ctx_chars = guard.estimate_req_chars(body)
    if guard.enforce_ctx(ctx_chars):
        guard.log_guard_block(model, "ctx_guard", f"chars={ctx_chars}")
        return 429, f"请求上下文 {ctx_chars} 字符超过护栏上限，请 /clear 或缩短历史"

    # 3. BUDGET-GUARD：日 token 预算（含本次估算）
    est_tokens = max(1, ctx_chars // 3)
    if guard.enforce_budget(est_tokens):
        guard.log_guard_block(model, "budget_guard", f"est={est_tokens}")
        return 429, "今日 token 预算已超限，请等待次日重置或调高 daily_token_budget"

    return None, None


def on_success(guard: CostGuard, model: str, in_chars: int, out_chars: int, wall_ms: float) -> None:
    """调用成功后：累计 token + 写 cost_event 审计。"""
    est = max(1, in_chars // 3)
    guard.record_tokens(est)
    guard.log_cost_event(model, in_chars, out_chars, wall_ms, "none")


def self_test() -> None:
    """离线自测：不发起真实 API 调用，审计写入隔离临时目录。"""

    tmp = Path(tempfile.mkdtemp(prefix="cost-guard-demo-"))
    os.environ.setdefault("UP_CONFIG", str(Path.home() / ".maref" / "proxy_config.json"))
    os.environ.setdefault("UP_AUDIT_DIR", str(tmp / "audit"))
    guard = CostGuard()

    body: dict[str, object] = {"messages": [{"content": "hello " * 50}]}
    model = "glm-5.2"

    # 前 60 次放行（或按 proxy_config 阈值），超限后 429
    for i in range(61):
        code, msg = intercept_request(guard, model, body)
        if code is not None:
            print(f"第 {i+1} 次调用被拦：{code} {msg}")
            break
    on_success(guard, model, 250, 100, 12.3)

    # CTX 超限演示
    code, msg = intercept_request(guard, "deepseek-flash", {"messages": [{"content": "x" * 500000}]})
    assert code == 429 and "上下文" in (msg or ""), f"CTX 拦截未生效: {code} {msg}"
    print("CTX-GUARD 拦截演示 OK")
    print(f"审计文件: {os.environ.get('UP_AUDIT_DIR', str(Path.home() / '.maref' / 'audit'))}")
    print("self-test 完成——CostGuard 可正常加载并执行三层护栏")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CostGuard 接入示例")
    parser.add_argument("--self-test", action="store_true", help="离线自测")
    args = parser.parse_args()
    if args.self_test:
        self_test()
    else:
        print("运行 --self-test 验证接线；生产接入请将 intercept_request 挂到你的代理/网关。")
