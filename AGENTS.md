# Agent Operating Manual: MAREF v0.36.0-rc

> **上位法**: 本文件受 [Athena 系统宪法 v1.5](https://github.com/maref-org/maref/blob/main/docs/CONSTITUTION.md) 约束。冲突时以宪法为准。
> **同步方向**: A → B 单向。本仓库是 Track B 发布源，由 Athena 内部部署经叙事转化后同步。
> **CLAUDE.md**: 本仓库的 Agent 指令文件。Agent 启动前必须阅读。

## Project Overview
- **名称**: MAREF (Multi-Agent Recursive Evolution Framework)
- **版本**: v0.36.0-rc
- **定位**: Agent 治理操作系统 (Agent Governance OS)
- **技术栈**: Python 3.10+ / FastAPI / Electron / React 19+TypeScript / TLA+
- **架构**: 概念语义层 天极→人极→地极→经卦→别卦→爻变（I Ching 治理语义）映射到代码实现层叠 元层→治理层→编排层→执行层→基础设施层（详见 docs/architecture.md）
- **代码风格**: PEP 8 + ruff + mypy strict mode
- **安全级别**: 最高（不可降级安全断言）
- **RSI Level**: L2 (Conditional Pass)
- **开源协议**: Apache-2.0

## Repository Structure
```
maref/
├── src/
│   ├── maref/          # Core governance framework
│   ├── maref_lite/     # CLI entry points
│   ├── sidecar/        # Observation sidecar + MCP bridge
│   ├── drift_guard/    # Distribution shift detection
│   └── formal/         # TLA+ formal specifications
├── gui/                # Electron + React GUI + Immunity Dashboard
├── tests/              # Test suites (14 SAEB benchmark tests, 220+ L2 release tests)
├── .missions/          # Factory Missions workspace
├── vault/              # Knowledge vault (signals, kdps, patterns)
├── scripts/            # Build and automation scripts
└── k8s/                # Kubernetes deployment configs
```

## Boundaries
- **禁止**: 修改 `.missions/v0.25.0-security-enhancement/validation-contract.md`（仅 Orchestrator 可修改）
- **禁止**: 跨特征深度导入（每个特征目录独立）
- **禁止**: 绕过 TrustBoundaryManager 进行跨域调用
- **禁止**: 在生产代码中硬编码密钥/凭证
- **端口范围**: 3000-3010（GUI 开发），8000（Sidecar），9000-9010（测试）

## Coding Conventions
- 所有 API 路由使用 `/api/v1/` 前缀
- 数据库操作必须通过标准接口，禁止裸 SQL
- 错误处理统一使用异常类，HTTP 状态码标准化
- 所有异步函数必须包裹 `try/except`
- 安全相关函数必须声明 `@security_critical` 装饰器
- 所有加密操作使用 `cryptography` 或 `hashlib` 库，禁止自行实现密码学原语
- Python: ruff + mypy strict mode
- TypeScript: ESLint + TypeScript strict mode

## Handoff Discipline
每个特征完成后必须:
1. 运行完整测试套件（`pytest tests/ -v --cov`）
2. 覆盖率 ≥ 该特征的 `test_coverage_threshold`
3. 提交 Git commit，消息格式: `feat(module): description`
4. 更新 `.missions/v0.25.0-security-enhancement/features.json`
5. 在 `knowledge-library/` 留下实现笔记

## Security-Specific Rules
- 所有输入必须验证（`pydantic` + 自定义校验器）
- 所有输出必须编码（防止 XSS/注入）
- 凭证/密钥必须使用 macOS Keychain 或环境变量
- 审计日志必须包含 HMAC-SHA256 签名
- 跨域调用必须通过 TrustBoundaryManager 授权
- Electron: hardenedRuntime=true, asar=true, entitlements only JIT+network+files

## Testing Commands
```bash
# Python unit tests
pytest tests/ -v --cov=src/maref --cov-report=term-missing

# Security-specific tests
pytest tests/security/ -v

# SAEB recursive benchmark
pytest tests/benchmark/test_saeb.py -v

# Desktop tests
pytest tests/desktop/ -v

# Type checking
mypy src/

# Linting
ruff check src/

# Version consistency check
bash scripts/version-check.sh

# Security scanning
trufflehog filesystem .

# GUI
cd gui && pnpm lint && pnpm build
```

## Build Commands
```bash
# Python package
pip install -e ".[dev]"

# Electron (GUI)
cd gui && pnpm install && pnpm electron:dev

# Build verification
bash scripts/verify_electron_build.sh

# Sidecar binary (PyInstaller)
bash packaging/build-sidecar.sh

# Sidecar binary verification
bash packaging/verify-sidecar.sh

# Docker
docker build -t maref:latest .

# Kubernetes
kubectl apply -f k8s/production/
```

## Key Design Decisions
| Decision | Rationale |
|----------|-----------|
| 64-state Gray Code FSM | Hamming distance=1 transitions guarantee stability |
| TLA+ formal verification | Prove correctness before implementation |
| SAEB recursive benchmark | Self-Adaptive Error Benchmark — agents detect+fix injected defects |
| Immune self-SAEB | Immunity system runs SAEB on itself to detect gene degradation |
| Factory Missions O/W/V | Eliminates self-verification blind spots |
| MCP + A2A dual protocol | Maximum ecosystem interoperability |
| Electron + React GUI | Cross-platform desktop agent workstation |
| Sidecar MCP bridge | Standardized Agent observation protocol |
| AuditLogger HMAC | Tamper-evident audit trail (ISO 27001 C.5.33) |

## Knowledge Vault
- **路径**: `vault/`
- **格式**: YAML with frontmatter
- **Signals**: 13 market/technology signals (S-20260511-001 ~ 013)
- **KDPs**: 10 key decision points (K-20260511-001 ~ 010)
- **Patterns**: 1 competitive positioning pattern

## Mission Workspace
- **路径**: `.missions/v0.25.0-security-enhancement/`
- **特性**: 35/35 completed (22 v0.25.0 + 13 L2), 9547+ tests collected (5968 passed in standard suite, 220+ L2 release tests)
- **验证**: 7 validator rounds, 4 issues found and resolved
- **里程碑**: m0-m7 all completed

## Quick Reference
- MAREF Lite CLI: `maref-lite --help`
- PERCV CLI: `maref percv --help`
- Sidecar health: `GET /api/health`
- MCP endpoint: `POST /api/mcp`
- MCP well-known: `GET /api/mcp/.well-known`
- Immunity cooldown: `GET /api/immunity/cooldown`
- Immunity cooldown summary: `GET /api/immunity/cooldown/summary`
- Gene audit trail: `GET /api/immunity/genes`
- Error codes: `maref.exceptions.MAREFError` (20 codes E0000–E4002)
- SAEB comparison: `from maref.evaluation.saeb import run_comparison`
- L2 acceptance report: `docs/rsi/l2-acceptance-report-20260702.md`

## Open Source Execution Norm
> **上位法**: 本文件受 [MAREF 开源执行规范 v1.0](docs/oss-execution-norm-v1.0.md) 约束。
> **宪法对齐**: Athena 系统宪法 v1.5 第十条（外部 Code Agent 治理）· 第十一条（跨仓库治理）
> **同步方向**: A → B 单向。本仓库是 Track B 发布源。

- 当前阶段: S0（详见 `docs/oss-todo.md`）
- 执行规范: `docs/oss-execution-norm-v1.0.md`
- 执行日志: `docs/execution-logs/`
- 执行 skill: `.claude/skills/governance-orchestrator/`
- 首次实战: 每步操作需记录日志，完成后封装 Skill
