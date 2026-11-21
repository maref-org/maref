# 切换访谈（市场验证）执行包

> 背景：2026-11-21 产物层诊断的结论是「能力已经足够，缺的是外部验证」。
> 真实用户验证仍为 0（0 访谈 / 0 标书 / 0 报价单）。本目录是把「聊过了」变成
> 可核验、可否证证据的最小执行包。

| 文件 | 作用 |
|---|---|
| [`SCRIPT.md`](./SCRIPT.md) | 30–40 分钟访谈脚本：五个必问、五条禁令、判定口径 |
| [`OUTREACH.md`](./OUTREACH.md) | 触达话术库：10 个可直接复制的模板、触达节奏、回复分类、禁忌清单 |
| [`CANDIDATES.md`](./CANDIDATES.md) | 15 席候选清单（5 席 × 3）、公开来源、排除项、替换规则 |
| [`TARGETS.md`](./TARGETS.md) | 五席目标结构（3 集成商 + 1 测评机构 + 1 受监管企业）、准入判据、漏斗与停止条件 |
| [`EVIDENCE.md`](./EVIDENCE.md) | 证据四级（L0–L3）、脱敏清单、命名规范、什么不能当证据 |
| [`ledger.yaml`](./ledger.yaml) | 结构化访谈账本（唯一事实源） |
| [`artifacts/`](./artifacts/) | 脱敏后的 L2/L3 证据副本 |

## 三条命令

```bash
python3 scripts/interview_ledger.py --check        # 结构校验 + PII fail-closed
python3 scripts/interview_ledger.py --eval --json  # 硬/强信号汇总，kill 判定
python3 scripts/interview_ledger.py --report       # 生成可引用的 markdown 表
```

退出码：`0` 正常 / `1` 账本不合法 / `2` 用法或文件错误 / `3` **需求假设被早期否证**。

## 这个包不做什么

- 不替你做需求结论。`--eval` 只报计数与阈值。
- 不证明「会有人买」。它只能证明「到目前为止没找到愿付钱的人」，或「已找到 N 个」。
- 不替代合同、发票、中标通知 —— 那些才是 L3。
