# OSS 深水区登记表（Deepwater Registry）

> **维护**: 闭源王炸层路径登记，与 `scripts/oss-exclude-list.txt` 双向一致。
> **规则**: 本表登记的内容**绝不允许**出现在公开分支（main/oss-release）的 tree 或历史中。
> **同步**: 新增深水区实现 → 先在本表登记 → 同步追加到 oss-exclude-list.txt → 人工评审发布。
> **审计**: 2026-08-14 初版（对齐 26号战略 §13.2 + 修复计划 R2/R5）

---

## 一、王炸层路径登记（闭源，绝不开源）

| 领域 | 路径（glob） | 26号战略归属 | 状态 |
|------|-------------|-------------|------|
| 联邦 TLA+ 优化引擎 | `src/maref/federation/tla_engine/**` | §13.2 王炸层 | 未来守卫（未创建） |
| 跨 Agent 信任传播 | `src/maref/trustgnn/**` | §13.2 王炸层 | 未来守卫（未创建） |
| 成本博弈调度器 | `src/maref/cost_scheduler/**` | §13.2 王炸层 | 未来守卫（未创建） |
| 多模态攻击检测 | `src/maref/multimodal_guard/**` | §13.2 王炸层 | 未来守卫（未创建） |
| Attack-1M 数据湖 | `data/attack_1m/**` | §13.2 王炸层 | 未来守卫（未创建） |
| Agent PKI 私有信任根 | `src/maref/security/trust_root/**` | §13.2 王炸层（补登） | 未来守卫（未创建） |
| Agent PKI 实现 | `src/maref/security/agent_pki/**` | §13.2 王炸层（补登） | 未来守卫（未创建） |
| 供应链安全**深度实现**（图数据库漏洞传播+自动修复编排） | `src/maref/supply_chain/deep/**` | §13.2 王炸层 | 未来守卫（未创建） |
| 边缘分裂脑**自愈引擎**（CRDT+国密 HSM） | `src/maref/edge/self_heal/**` | §13.2 王炸层 | 未来守卫（未创建） |
| 免疫**基因库**/绕过模式图谱 | `src/maref/immunity/gene_vault/**` + `src/maref/attack_patterns/**` | §13.2 王炸层 | 未来守卫（未创建） |

### 1.1 命名约定（防混淆）

| 词 | 边界 | 说明 |
|----|------|------|
| `supply_chain` | 公开钩子（SBOM 生成/信任验证/漏洞扫描，已公开 Apache-2.0） | 深度实现在 `deep/` 子目录，王炸 |
| `immunity` | 公开框架（免疫检查/cooldown/self_saeb，已公开） | **基因库**在 `gene_vault/`，王炸；框架不含基因数据 |
| `redblue` | 公开框架（攻击向量/引擎，已公开） | 参数秘传，不在公开仓 |
| `recursive/distributed_crdt` | 公开框架（CRDT 同步） | **自愈引擎**在 edge/self_heal，王炸 |

> 注：`src/maref/federation/` 现存 23 files（bootstrap/gateway/trust/settlement 等）属**半开协议层**（Apache-2.0 公开），非王炸层；仅其子目录 `tla_engine/**` 为王炸层。

---

## 二、豁免说明（公开但需注意）

| 路径 | 原因 | 备注 |
|------|------|------|
| `src/maref/federation/**`（除 `tla_engine/**`） | A2A/联邦协议标准接口，开源钩子层 | oss-check 放行 |
| `src/maref/supply_chain/**`（除 `deep/**`） | SBOM/信任验证/漏洞扫描，开源钩子层 | 深度实现归属王炸层 |
| `src/maref/immunity/**`（除 `gene_vault/**`） | 免疫框架（参数秘传），半开源层 | 框架公开、基因库不动 |
| `src/maref/redblue/**` | 对抗引擎框架，半开源层 | 引擎公开、参数秘传 |

---

## 三、维护历史

| 日期 | 变更 | 登记人 |
|------|------|--------|
| 2026-08-14 | 初版建立；补登 Agent PKI 两条路径；与 oss-exclude-list/oss-check 对齐 | 外部 Agent（审计） |
| 2026-08-14 | **修复门禁执行力**：JSON-BLOCK 审查发现仅加清单不可靠（glob `**/x/**` 跨目录缺陷）；新增王炸路径同步写入 oss-check.sh `SENSITIVE_PREFIXES` 硬编码前缀 + 排除清单。实测 11 王炸路径全拦截、47 公开钩子文件 0 误伤 | 外部 Agent（审查修复） |

---

*本表为审计修复计划 R2/R5 产物。任何王炸层实现创建前必须完成登记+门禁双保险。*