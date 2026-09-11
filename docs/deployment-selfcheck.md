# MAREF 部署自检指南（G11-2）

> **上位依据**: [TRUST_DECLARATION.md](TRUST_DECLARATION.md) · [RB-012 成本护栏](runbook/rb-012-cost-guardrails.md) · [INC-2026-08-13-001](incidents/INC-2026-08-13-001-cost-burn-telemetry-blackout.md)
> **目的**: 全新部署 5 分钟内验证 MAREF 是否"健康、能遥测、能拦住问题"；任何静默失效点均在此暴露。

---

## 1. 快速部署

```bash
# 前置：Python 3.10+（推荐 3.11/3.12），本机已有 3.14 也可
git clone https://github.com/maref-org/maref && cd maref
pip install -e ".[dev]"

# 校验版本
maref --version

# 初始化 HMAC 密钥（必须！无密钥则审计 fail-closed，治理不可用）
if [ ! -f ~/.maraf_hmac_key ]; then
  openssl rand -hex 32 > ~/.maraf_hmac_key
  chmod 600 ~/.maraf_hmac_key
fi

# 生成成本护栏策略（写审计链）
maref cost-policy
```

---

## 2. 运行自检

```bash
maref selfcheck
```

### 七项检查含义

| # | 检查项 | 判定标准 | 失败时的修复指令 |
|---|--------|----------|------------------|
| 1 | HMAC key 存在 | env `MAREF_HMAC_SECRET_KEY` 或 `~/.maraf_hmac_key` 可读 | 见上"初始化 HMAC 密钥" |
| 2 | 审计链 24h 有真实事件 | 最新一条 JSON 的 event_type 非空 | 触发一次治理动作（`maref cost-policy --reason test`）后重试 |
| 3 | 遥测链路健康 | 本地遥测缓冲无滞留事件 | 检查 `~/.maref/telemetry/events.db`；云端不可达属正常（本地聚合兜底） |
| 4 | ObsBridge 已接线 | sidecar `/api/obs/status` 返回 wired 含 state_machine | 启动 sidecar（`maref serve --port 8000`），需 v0.54+ |
| 5 | 审计链未被测试污染 | 24h 内噪音（纯 state_transition）比例 < 阈值 | 检查是否有测试/压力脚本写入生产 `.governance/`（应走 /tmp 隔离） |
| 6 | proxy /usage 可达 | `127.0.0.1:8147/usage` 返回 | 已部署闭源 proxy 时检查其端口；未部署时此项 FAIL 属预期（见 §4） |
| 7 | 成本护栏阈值生效 | `~/.maref/proxy_config.json` 有 call/ctx 阈值；无配置时回退检查开源 CostGuard | `maref cost-policy` 生成策略 |

---

## 3. 看门狗（meta_monitor）部署

看门狗逻辑在开源 `src/maref/observability/meta_monitor.py`，调度可自建：

```bash
# 手动单次
python -m maref.observability.meta_monitor --single-run

# 常驻（每 5 分钟），建议用 launchd 或 cron
nohup python -m maref.observability.meta_monitor --daemon --interval 300 \
  > /tmp/meta-monitor.log 2>&1 &
```

**launchd 模板**（`deploy/com.maref.meta-monitor.plist`，按环境替换路径）：

```xml
<key>EnvironmentVariables</key>
<dict>
  <key>MAREF_AUDIT_PATH</key>
  <string>/path/to/maref/.governance</string>
  <key>MAREF_HMAC_SECRET_KEY</key>
  <string>（从 ~/.maraf_hmac_key 读取后填入或经 env）</string>
  <key>PYTHONPATH</key>
  <string>/path/to/maref/src</string>
</dict>
<key>ProgramArguments</key>
<array>
  <string>/path/to/maref/.venv/bin/python3</string>
  <string>-m</string>
  <string>maref.observability.meta_monitor</string>
  <string>--daemon</string>
  <string>--interval</string>
  <string>300</string>
</array>
<key>RunAtLoad</key><true/>
<key>KeepAlive</key><false/>
```

> **重要（G5）**：看门狗已禁止自我续命——它只检查真实审计事件。
> 若你看到 `meta_monitor_touch.jsonl` 仍被周期性写入，说明运行的是 v0.54 修复前代码，
> **必须重启进程**（`launchctl kickstart -k gui/$(id -u)/com.maref.meta-monitor`）。

---

## 4. proxy /usage 检查项说明

`maref selfcheck` 第 6 项检查 `127.0.0.1:8147/usage`：

- **已部署闭源 proxy**：应可达，返回日 token 用量。
- **未部署 proxy（纯开源部署）**：此项 FAIL 属预期，不代表系统不可用——
  成本护栏执行由 `maref.cost_guard.CostGuard` 提供（第 7 项回退验证其可加载）。
  接入方法见 [RB-012「开源部署」节](runbook/rb-012-cost-guardrails.md)。

---

## 5. 常见问题

| 现象 | 原因 | 处置 |
|------|------|------|
| selfcheck 第 2 项 FAIL | 审计链无真实事件（可能被测试污染或 key 缺失） | 运行 `maref cost-policy --reason smoke` 触发一次真实决策；检查 key |
| 遥测缓冲滞留事件 | 云端端点不可达 | 属正常（本地 SQLite 兜底）；如需云端增强，恢复 telemetry.maref.org |
| 看门狗报 audit stale | 审计链真实断裂（修复后不再被 touch 掩盖） | 检查 sidecar/state_machine 是否存活、key 是否缺失 |
| 成本异常无告警 | 未接入 CostGuard 的调用路径 | 自建代理接入 CostGuard（RB-012 §开源部署） |
| 第 6 项 proxy FAIL | 无闭源 proxy | 预期；用开源 CostGuard 覆盖执行端 |

---

## 6. 部署验收清单

```text
□ git clone 成功，maref --version 有输出
□ ~/.maraf_hmac_key 存在（600 权限）
□ maref cost-policy 成功且 ~/.maref/proxy_config.json 有阈值
□ maref selfcheck 第 1/2/5/7 项 PASS（3/4/6 按部署形态判定）
□ 看门狗运行中，无 meta_monitor_touch.jsonl 周期性写入
□ 触发一次 API 调用，~/.maref/audit/cost_events.ndjson 出现 HMAC 签名记录
```

---

> **维护记录**: v1.0（2026-08-14）随 INC-2026-08-13-001 追审补全（G11-2）。