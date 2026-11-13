# GB/Z 185.8 表2 `logType` 与 ACPs AMP 日志类型映射

> 背景：我方对《人工智能 智能体互联 第8部分：智能体审计（征求意见稿）》建议二指出，
> 表2 的 `logType` 枚举与上游 AMP v2.2.0 的 `ACPsLogType` 无映射关系。
> 本文给出可落地的映射方案，供实现方与起草组参考。

## 1. 两套枚举

| 来源 | 取值 |
|---|---|
| GB/Z 185.8 §9.1.2 表2 | `access`（访问）、`message`（消息）、`business`（业务） |
| GB/Z 185.8 §10 表8（存储） | 额外出现 `system`（系统），仅用于存储结构 |
| ACPs AMP v2.2.0 `ACPsLogType` | `heartbeat`、`access`、`metrics`、`audit`、`message`、`system` |

**缺口**：标准正文的传输枚举只有 3 类，AMP 有 6 类；其中 `audit`、`metrics`、`heartbeat`、`system`
四类在 §9.1.2 无对应值。

## 2. 建议映射

| AMP 类型 | 建议国标 `logType` | 依据 | 备注 |
|---|---|---|---|
| `access` | `access` | 同名同义 | 直接映射 |
| `message` | `message` | 同名同义 | 直接映射 |
| `audit` | `business` | 审计事件是业务事件的特例，且表7 的必选属性（actor/action/target/result）与 AMP audit 记录同构 | **需在表2 注中写明归并规则**，否则实现方只能自造值 |
| `metrics` | `business` | 指标上报属于业务自描述数据 | 建议同时允许下沉到 `attributes` |
| `system` | `system`（建议扩充） | §10 表8 已存在 `system` 语义，正文枚举缺列 | 若不扩充，系统日志只能填 `business`，与 §9.2 系统日志主体内容冲突 |
| `heartbeat` | `system` | 心跳是运行时存活记录，非业务事件 | 同 `system` 的扩充前提 |

## 3. 实现侧建议（最小改动）

1. 传输层写 `logType` 前先经映射函数归一化，不直接透传 AMP 原始值。
2. 原始 AMP 类型写入 `attributes.acps.logType`，保留可追溯性（表2 `attributes` 定义即"补充描述日志的上下文信息"）。
3. 若起草组采纳扩充 `system`，映射函数改为恒等映射，其余不变。

## 4. 与标准修订的对应关系

| 我方意见 | 若采纳的落地形态 |
|---|---|
| 建议二（映射说明） | 表2 `logType` 描述后加注："来自 ACPs AMP 的实现宜按以下规则映射：audit→business、metrics→business、heartbeat→system" |
| 建议一（correlationId 必选） | 同一审批链的 request/decision/execute 事件共用 `correlationId`，映射时不得丢失该字段 |

## 5. 参考实现

`src/maref/governance/authorization_level.py` 的 `audit_fields()` 提供与表7 对齐的
`authorization_level` / `authorization_credential_id` / `primary_subject` 字段，
可与本文映射表配合使用。
