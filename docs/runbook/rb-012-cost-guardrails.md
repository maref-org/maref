# RB-012: API 成本异常 / 烧钱（INC-2026-08-13-001）

## 告警信息

- **告警名**: `M4 Cost Critical` / `M4 Telemetry Liveness`
- **严重级别**: P0（成本失控）
- **触发条件**:
  - M4 检测到高价模型（glm-5.2/glm-4.7）30 分钟调用 > 60 次
  - 日 token 累计超 `UP_DAILY_TOKEN_BUDGET`（默认 500 万）
  - 请求上下文 > `UP_CTX_LIMIT_CHARS`（默认 20 万字符）被 CTX-GUARD 拦截
  - 近 24h 无任何 cost_event（遥测断裂信号）

## 影响范围

- API 账单爆炸（¥4/¥16 每百万 token 的 glm-5.2 尤其危险）
- 若未拦截：连续运行数小时即产生数百元成本
- 连带：上下文膨胀导致工具调用反复失败 → 死循环加剧烧钱

## 诊断步骤

1. 查看 proxy 用量聚合视图
   ```bash
   maref usage
   # 或直接查 /usage 端点
   curl -s http://127.0.0.1:8147/usage | python3 -m json.tool
   ```

2. 查看护栏拦截记录（审计链）
   ```bash
   tail -50 ~/.maref/audit/guard_blocks.ndjson
   tail -20 ~/.maref/audit/cost_events.ndjson
   ```

3. 查看 M4 检查详情
   ```bash
   python3 -m maref.observability.meta_monitor --single-run | python3 -m json.tool
   ```

4. 确认哪些模型在烧钱
   - `/usage` 的 `by_model` 字段：看 glm-5.2/glm-4.7 调用量与字符数

## 处置方案

| 场景 | 操作 |
|------|------|
| 高价模型调用激增 | 立即将主模型切换为低价模型（`/model` 切换 deepseek-v4-flash / glm-4-flash） |
| 上下文膨胀 | `/clear` 或新开会话，缩短历史；避免一次性读取大量文件 |
| 死循环（工具反复失败） | 检查 proxy stderr 的 `tool_use SKIP empty` 日志，中断任务重试 |
| 已超日预算被 429 | 等待次日预算重置，或调高 `UP_DAILY_TOKEN_BUDGET` 后重启 proxy |
| 阈值需调整 | `maref cost-policy --call-hard-limit N` 生成新策略（写审计链，proxy 热加载） |
| 疑似无护栏流量 | 检查 proxy 是否加载了 `~/.maref/proxy_config.json`，无则 `maref cost-policy` 生成 |

## 紧急止损（30 秒内）

```bash
# 1. 立即切换模型（若在 Claude Code 中）
#    /model 选择 deepseek-v4-flash

# 2. 收紧护栏（临时）
export UP_CALL_LIMIT=10    # 高价模型 30 分钟限 10 次
export UP_DAILY_TOKEN_BUDGET=1000000
# 重启 proxy

# 3. 停止烧钱会话
#    中断当前 ccg/cc 会话，/clear 或退出重开
```

## 验证

```bash
# 护栏生效：调用被 429 拦截
maref usage   # guarded 计数增长

# 审计链有 guard_block 记录
grep budget_guard ~/.maref/audit/guard_blocks.ndjson | tail

# M4 恢复 healthy
python3 -m maref.observability.meta_monitor --single-run | grep -A5 '"m4"'
```

## 预防

1. 部署后立即 `maref selfcheck` 验证七项能力
2. 保持 `~/.maref/proxy_config.json` 由治理生成（`maref cost-policy`）
3. 定期看 `maref usage` 的 `by_model` 分布，关注高价模型占比
4. 升级到 v0.54：M4 成本检查已接入 meta_monitor，异常 5 分钟内告警
