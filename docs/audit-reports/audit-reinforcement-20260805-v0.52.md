# MAREF v0.52.0 风险·缺口·补强审计报告

> **审计日期**: 2026-08-05
> **审计基线**: dev 分支 HEAD `112e60d5`（tag v0.52.0 之后 2 commits）
> **审计方法**: research-verification v2.0（Phase 0 全景情报 → Phase 1 交叉验证 → Phase 2 盲点扫描 → Phase 3 优先级分级 → Phase 4 补强执行方案 → Phase 5 事实修正）
> **情报来源**: 3 个并行审计 Agent（治理安全 / 架构演化 / 测试发布链）+ 主 Agent 交叉验证 12 项关键声明
> **前置审计**: [gap-audit-20260805.md](./gap-audit-20260805.md)（G-01~G-11）· [meta-audit-report-v0.51-20260805.md](./meta-audit-report-v0.51-20260805.md)（M0-M3）

---

## 0. 执行摘要

**结论: ⚠️ 未通过 — 代码实现质量高（15723 tests 收集、gov 1055 + security 326 全绿、ruff 通过），但存在 3 项 P0 级架构真实性缺陷、1 项 CI 发布链完全失效、1 项安全机制名不符实。**

本次审计共确认 **18 项缺口**：🔴 Critical 3 / 🟠 High 6 / 🟡 Medium 5 / 🟢 Low 4。

与前置审计（G-01~G-11、M0-M3）相比：**版本链断裂（G-01）、mission 未回写（G-02）、审计链 M1-M2、M0 pulse 陈旧等均已修复**，但暴露了更深层的三类系统性问题：

| 类别 | 本质 | 代表缺口 |
|------|------|---------|
| **A. 自我演化真实性** | 演化闭环的"验证-收敛"环节是伪实现，可零验证交付演化结果 | R-1 虚假收敛、R-2 死配置安全机制 |
| **B. 安全特性接线** | 安全组件多数停留在"实现+测试通过"，未完成生产管线贯通与强制启用 | S-1 消毒链路零调用、S-2 分级自报可信、S-3 scope 防伪恒失效 |
| **C. 发布/声明治理** | CI 损坏、版本声明与实际脱节、构建链断裂 | Q-1 ci.yml 语法损坏、Q-2 Tauri 发布失败、Q-4 覆盖率声明失真 |

---

## 1. Phase 0/1 — 全景情报与交叉验证

### 1.1 已确认的正面资产（防止审计只见缺陷）

| 资产 | 证据 |
|------|------|
| 六极架构映射真实 | `recursive/` 2.7 万行/106 文件、`governance/` 9429 行/36 文件，天极→爻变全部有实质实现 |
| 34-state Gray Code FSM 完整 | 10 治理态 4-bit + 24 agent 态 5-bit，单比特迁移、HALT 吸收态 |
| 审计链 HMAC 实现质量高 | `audit.py` Ed25519 优先 / HMAC-SHA256 兜底 + 链式哈希 + verify_integrity 三态判定 |
| 联邦 metering 结算已含 outcome_quality | 权重守恒实现 + 22 处断言的专项测试 |
| TrustEngineV2 F821 已清除 | gap-audit G-04 记载的 F821 已修复，实例化+评估实测通过 |
| v0.51 数据治理交付扎实 | DataCatalog 指纹校验、LineageTracker BFS 扩散面、SchemaValidator drift 检测均真实可用 |
| 测试规模大且治理/安全域绿 | 15723 collected；gov 1055 / security 326 / sidecar wiring 1085 全 passed |
| 版本链已闭合 | 7 文件一致 0.52.0 + CHANGELOG + tag v0.52.0 + version-check.sh 8/8 OK |
| M0-M3 元可观测已修复 | meta-monitor 四层全绿、479 legacy 告警迁移闭合 |

### 1.2 交叉验证结论（12 项关键声明全部核实）

| # | 声明 | 验证方法 | 结果 |
|---|------|---------|------|
| V-1 | ci.yml 语法损坏 | `python -c "yaml.safe_load(...)"` | ✅ 确认 line 45 column 221 ScannerError |
| V-2 | release.yml 引用不存在的 action | grep line 72 | ✅ 确认 `dtolnay/rust-action@stable` |
| V-3 | REL VERIFY 仅跑 git status | 读 `recursive_evolution_loop.py:885-895` | ✅ 确认 |
| V-4 | REL 指标 hasattr fallback 恒 1.0 | 读 `:858-883` | ✅ 确认 test_pass_rate 无属性即 1.0 |
| V-5 | 550 个 *.cover 误提交 | `find src -name "*,cover"` | ✅ 确认 550 |
| V-6 | sanitize_by_category 零生产调用 | grep src/ | ✅ 确认 0 调用者 |
| V-7 | SensitiveDataLineage 无生产接线 | grep src/ | ✅ 确认仅 lineage.py + 自身 |
| V-8 | DecisionExplainer 零接线 | grep src/maref/ | ✅ 确认仅 explainer.py 自身 |
| V-9 | issuer_public_keys 无注入点 | grep src/maref/ | ✅ 确认无任何构造调用传入 |
| V-10 | mypy 1 error 在 report_generator.py:200 | `mypy src/maref` | ✅ 确认 v0.33.0 遗留 |
| V-11 | evolution/engine.py CircuitBreaker 死代码 | grep 调用点 | ✅ 确认仅 2 处 get_stats 读取 |
| V-12 | G-01/G-02/G-11 已修复 | git grep + 文件读 | ✅ 确认版本 0.52.0 / mission completed / 报告入库 |

---

## 2. Phase 2 — 系统性盲点扫描

从通用维度（法律合规 A / 供应链 B / 情报 C / 质量治理 D / 隐性风险 E / 领域特定 F）扫描后，**确认缺失/弱化的维度**：

| 维度 | 缺失项 | 审计证据 |
|------|--------|---------|
| **A 法律合规** | 消毒还原机制无授权审计；审计链密钥从磁盘明文文件读取（`.maraf_hmac_key` 文件名拼写错误） | `sanitizer.py:152-167`、`audit.py:290-311` |
| **B 供应链** | 无 SBOM/依赖漏洞扫描入库；debug 脚本（`*_fixed*.py`）随仓库发布 | CI 无依赖扫描 job；`scripts/` 16+ 残留 |
| **C 情报/观测** | `SystemSnapshot` 不含 pass_rate/coverage 字段，演化观测数据源失真 | `self_observer.py:19-29` |
| **D 质量治理** | 覆盖率声明不可复现（27.39% vs 52.49% 口径漂移）；mypy_errors 声明 0 实测 1 | `STATE.yaml:67` vs 实测 |
| **E 隐性风险** | 伪收敛（演化"停得太早"）；死配置安全机制制造虚假安全感 | `recursive_evolution_loop.py`、`evolution/engine.py` |
| **F 领域特定** | TrustBoundary 分级输入自报可信 = 可降级绕过白名单；scope 签名防伪恒不执行；数据/价值治理纯内存无持久化 | `risk_classifier.py:99-100`、`trust_boundary.py:206` |

---

## 3. Phase 3 — 优先级分级（18 项缺口）

评分维度：**影响度**（0-100，暴露后损失/合规风险） × **紧急度**（0-100，当前是否需要）。

### 🔴 CRITICAL（影响≥85 且 紧急≥80）

| ID | 缺口 | 影响 | 紧急 | 证据 |
|----|------|------|------|------|
| **C-1** | **REL 自我演化虚假收敛**: VERIFY 仅跑 git status，指标恒 pass_rate=1.0，第 3 轮必判"收敛"并 commit——零验证即交付演化结果 | 95 | 90 | `recursive_evolution_loop.py:858-895,563-594` + `self_observer.py:19-29`；已实测复现 |
| **C-2** | **CI 主链 `ci.yml` 语法损坏**: 50 次运行 0 成功，lint/test/security/integrity/crypto 门禁自 v0.50.0 起从未在 CI 执行，`STATE.yaml G2_ci_green: true` 失实 | 92 | 90 | `.github/workflows/ci.yml:45`，yaml.safe_load 实测 ScannerError |
| **C-3** | **TrustBoundary 分级输入自报可信 + scope 防伪恒失效**: impact_scope/reversible 取自调用方 metadata 可降级绕过白名单；issuer_public_keys 无注入点 verify_signature 永不执行；默认部署无 scope → 身份绑定失效；task_preflight 接受调用方 dict 可伪造 scope | 90 | 85 | `risk_classifier.py:99-100`、`trust_boundary.py:191-252`、`task_preflight.py:421-429` |

### 🟠 HIGH（影响≥70 且 紧急≥65）

| ID | 缺口 | 影响 | 紧急 | 证据 |
|----|------|------|------|------|
| **H-1** | **C1→C2→C3 消毒/血缘链路零生产调用 + C4 推迟**: 数据泄露防护仅组件级，管线未贯通，sanitize_by_category/SensitiveDataLineage 无调用者 | 85 | 80 | `sanitizer.py:83`、`sensitive_lineage.py:69` 无生产调用；计划明确 C4 推迟 |
| **H-2** | **sanitizer 授权还原无鉴权**: restore_output 仅凭自传布尔 authorized=True 还原，无身份/密钥/审计/时效 | 80 | 75 | `sanitizer.py:152-167` |
| **H-3** | **Tauri GUI 发布链断裂**: release.yml 引用不存在的 dtolnay/rust-action，4 平台发布全部失败，v0.52.0 桌面 GUI 从未发布 | 75 | 80 | `.github/workflows/release.yml:72` |
| **H-4** | **evolution/engine.py 两层安全机制死代码**: CircuitBreaker 无触发调用、OscillationFixLoop 零调用，circuit_breaker_permanent_open 永不可达 | 75 | 70 | `engine.py:127-140,427-444` |
| **H-5** | **声明 vs 实测系统性失实**: STATE.yaml mypy_errors:0 实测 1（v0.33 遗留）；CHANGELOG "mypy 33→0" 不成立；G2_ci_green 失实 | 72 | 70 | `STATE.yaml:67,122` + mypy 实测 |
| **H-6** | **B2 价值记录未入审计链**: ValueTrackingEngine 有 HMAC 签名但无 UnifiedAuditStore/AuditLogger 写入，防抵赖链路不完整 | 70 | 65 | `value/tracking.py:68-98` |

### 🟡 MEDIUM（影响≥50 或 紧急≥50）

| ID | 缺口 | 影响 | 紧急 | 证据 |
|----|------|------|------|------|
| **M-1** | **覆盖率门禁不达标且口径漂移**: 全仓实测 27.39% vs fail_under=50；STATE.yaml 52.49% 依赖不可复现子集 | 65 | 55 | `pyproject.toml:238` + 实测 |
| **M-2** | **state_machine 审计链 fail-closed 缺陷 + chain_hash 语义不一致**: 未配密钥状态机不可用；两条链同名字段两种计算 | 60 | 55 | `state_machine.py:111-117,146-149` vs `audit.py:266-268` |
| **M-3** | **meta-audit-gate.yml 每 5 分钟失败**: starlette 依赖缺失，持续烧 Actions 配额并产生失败噪音 | 55 | 65 | `.github/workflows/meta-audit-gate.yml:30` |
| **M-4** | **lastfailed 570 条残留**: 已修复测试仍留失败缓存，"6 域清零"声明与缓存矛盾 | 50 | 55 | `.pytest_cache/v/cache/lastfailed` |
| **M-5** | **security_critical 装饰器名不符实**: 仅 DEBUG 日志+标记，无审计强制写入；AuditLogger/CircuitBreaker/state_machine 关键路径未标注 | 52 | 50 | `decorators.py:27-49` |

### 🟢 LOW（其他）

| ID | 缺口 | 影响 | 紧急 |
|----|------|------|------|
| **L-1** | DEPRECATED 模块退役不彻底（4 个仍被生产/包级导出）+ 550 *.cover + 12 生成物 | 40 | 40 |
| **L-2** | 数据/价值治理纯内存无持久化 | 35 | 30 |
| **L-3** | 根目录 9 个 test_phase*.py + scripts/ 16+ *_fixed* 调试脚本入库 | 30 | 30 |
| **L-4** | 架构文档滞后（architecture.md 仍标 v0.36.0-rc）+ E3/E4 幻觉检测推迟 + settlement 无 result-based pricing | 30 | 25 |

---

## 4. Phase 4 — 补强执行方案

### 4.1 模块架构设计（缺口 → 模块映射）

| 缺口 | 受益模块 | 优先级 |
|------|---------|--------|
| C-1 虚假收敛 | `recursive/evolution_metrics.py`（新）— 真实测试指标采集；`self_observer.py` 补 pass_rate/coverage；`_run_quality_checks` 改真实 pytest | **P0** |
| C-2 ci.yml | `.github/workflows/ci.yml` 修复 + `STATE.yaml` 失实更正 + CI 复跑验证 | **P0** |
| C-3 分级自报可信 | `governance/risk_classifier.py` 加服务端权重；`trust_boundary.py` 强制 scope 注入；`issuer_public_keys` 默认加载公钥目录 | **P0** |
| H-1 消毒链路零调用 | `security/sanitizer.py` 增加统一入口 `SanitizationPipeline`；数据管线接线 | **P1** |
| H-2 还原无鉴权 | `security/sanitizer.py` restore 加身份签名+时效+审计 | **P1** |
| H-3 Tauri 发布 | `.github/workflows/release.yml:72` 改 `dtolnay/rust-toolchain` + 本地验证构建 | **P1** |
| H-4 死配置安全机制 | `evolution/engine.py` 接线 CircuitBreaker/OscillationFixLoop 真实调用 | **P1** |
| H-5 声明失实 | `STATE.yaml` + `CHANGELOG` 按实测修正；mypy report_generator.py:200 修复 | **P1** |
| H-6 价值记录入链 | `value/tracking.py` 增加 UnifiedAuditStore 写入 | **P1** |
| M-1 覆盖率口径 | 统一 coverage 配置（pyproject source 覆盖） + 复跑记录 | **P2** |
| M-2 审计链一致性 | `state_machine.py` 密钥 fail-open + chain_hash 统一算法 | **P2** |
| M-3 meta-audit 依赖 | workflow 安装 full deps 或拆 job | **P2** |
| M-4 lastfailed | 清理缓存 + 回归确认 | **P2** |
| M-5 装饰器 | `decorators.py` 补强制审计写入 | **P2** |

### 4.2 里程碑路线图

```
v0.53.0-M1（W1） 真实演化闭环 + CI 修复          C-1 + C-2 + H-5（mypy/声明修正）
  → 演化指标采集器上线、ci.yml 复绿、验证真实收敛判定

v0.53.0-M2（W2） TrustBoundary 真实加固          C-3 + H-1 + H-2
  → 分级服务端校验、scope 签名防伪、消毒管线贯通、还原鉴权

v0.53.0-M3（W3） 发布链与安全接线                H-3 + H-4 + H-6
  → Tauri 发布修复、演化引擎熔断接线、价值记录入审计链

v0.53.0-M4（W4） 质量收口                         M-1~M-5 + L-1~L-4
  → 覆盖率复跑、缓存清理、DEPRECATED 退役、文档更新、版本 bump 0.53.0
```

### 4.3 ROI 评估

| 投入 | 估算 |
|------|------|
| 新模块开发 | 1 个（`evolution_metrics.py`）+ 5 处重构 |
| 外部集成 | 0（纯仓库内修复） |
| 测试 | ~80 个新测试用例（演化指标采集/收敛判定/消毒管线/还原鉴权/scope 防伪） |
| 总工时 | 3-4 周 |
| 核心收益 | **让"自我演化可信"从口头声明变为真实可验证**；堵住 TrustBoundary 可降级绕过的安全后门；恢复 CI 门禁真实约束力 |

---

## 5. Phase 5 — 事实修正登记

| 严重级别 | 位置 | 原文声明 | 实际 | 处理 |
|---------|------|---------|------|------|
| 🔴 严重 | `STATE.yaml:122` | `G2_ci_green: true` | ci.yml 语法损坏 50 次运行 0 成功 | P0 修复后重写 |
| 🟠 重要 | `STATE.yaml:67` | `mypy_errors: 0` | 实测 1 error（report_generator.py:200） | P1 修复 |
| 🟠 重要 | CHANGELOG v0.52.0 | "mypy 33 errors → 0" | 实际 1 error 残留 | P1 修复后更正 |
| 🟡 一般 | `STATE.yaml:57` | `coverage_overall: 52.49%` | 全仓实测 27.39%，口径不可复现 | P2 统一口径 |
| 🟢 参考 | `docs/architecture.md` | 版本标 v0.36.0-rc | 实际 v0.52.0 | P2 更新 |

---

**审计员**: opencode（MAREF 风险·缺口·补强审计）
**审计结论**: ⚠️ 未通过 — 存在 3 项 P0（虚假收敛、CI 失效、TrustBoundary 绕过）+ 1 项发布链断裂，按本报告 4.2 里程碑修复后建议复审

---

## 6. 修复进度登记（M1 + M2 已完成）

### 2026-08-06 M2 — C-3 TrustBoundary + H-1/H-2 消毒链路 ✅

| ID | 修复 | 验证 |
|----|------|------|
| C-3a 分级自报可信 | `risk_classifier.py` 新增 `classify_action_server`：动作字符串推导不可降级下限，metadata/trusted 仅可升级；`trust_boundary.py` 切换为服务端权威分级 | test_m2_governance_hardening.py C-3a 4 项 TDD；trust_boundary 回归全绿 |
| C-3b scope 防伪恒失效 | `trust_boundary.py` scope 校验 fail-closed：issuer 非空但无签名/公钥未配置/签名无效一律拒绝（原"公钥表外跳过验签"fail-open 边界废除） | W9 测试改断言 fail-closed；scope_subject_binding 回归全绿 |
| H-1 消毒链路零调用 | `DataSovereigntyManager.sanitize_data` 生产锚点（C1→C2→C3 贯通+审计）；`DataSovereigntyMiddleware` 放行时按涉事数据类消毒 `data_transfer.payload`；`MCPSecurityMiddleware` 链传播 `sanitized_payload` | test_m2 新增 manager+middleware+chain 3 项 TDD；test_data_sovereignty_middleware 回归全绿 |
| H-2 还原无鉴权 | `Sanitizer(audit_logger)` 注入审计；`restore_output` 授权还原必须提供 `authorized_by`（fail-closed）+ 记录 `pii_restore` 事件 | test_m2 H-2 4 项 TDD；test_sanitizer/category 2 处补 authorized_by |
| M2 门禁 | 全量 ruff 通过；`mypy src/maref` Success 713 files 0 errors；governance+security+compliance+middleware 2298 passed；version-check.sh 8/8 OK | 新增 tests/security/test_m2_governance_hardening.py（15 项）；integration 域 8 失败为基线既有（stash 对比验证） |

### 2026-08-05 M1 — C-1 + C-2 + H-5(mypy) ✅

| ID | 修复 | 验证 |
|----|------|------|
| C-1 虚假收敛 | `SystemSnapshot` 增加真实指标字段；`_collect_current_metrics` 改真实运行；`_run_quality_checks` 改真实 pytest | 新增 test_evolution_metrics.py 7 项 TDD；REL 相关 4 套件 134+7 passed |
| C-2 ci.yml | `ci.yml:45` block scalar 修复；release-to-social.yml 缩进修复 | 24 个 workflow YAML 全部解析通过 |
| H-5 mypy | `report_generator.py:151` 显式类型标注 | `mypy src/maref` Success, 713 files 0 errors |
| 声明修正 | STATE.yaml `G2_ci_green`/`gate_passed` 改为 false | version-check.sh 8/8 OK |

**待办**: M3（H-3 Tauri + H-4/H-6）、M4（质量收口）
**注意**: C-2 CI 复跑需 push 后在 GitHub Actions 确认，本机仅验证 YAML 语法与门禁。
