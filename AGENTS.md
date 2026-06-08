# Agent Operating Manual: MAREF v0.30.0-GA

> **上位法**: 本文件受 [MAREF 治理框架](GOVERNANCE.md) 约束。冲突时以治理框架为准。
> **泄密预防**: 本仓库不得包含 T3/T2 级内容（路径/Key/IP/时间戳/依赖图）。
> **项目状态源**: `STATE.yaml`（本仓库根目录）— 外围 Code Agent 的唯一事实源，启动时先读取 version 字段判断是否过时。

## Project Overview
- **名称**: MAREF (Multi-Agent Recursive Evolution Framework)
- **版本**: v0.30.0-GA
- **定位**: Agent 治理操作系统 (Agent Governance OS)
- **技术栈**: Python 3.10+ / FastAPI / Electron / React 19+TypeScript / TLA+
- **架构**: 六层治理架构（天极→人极→地极→经卦→别卦→爻变）
- **代码风格**: PEP 8 + ruff + mypy strict mode
- **安全级别**: 最高（不可降级安全断言）
- **开源协议**: Apache-2.0

## Repository Structure
```
maref-experiments/
├── src/
│   ├── maref/          # Core governance framework
│   ├── maref_lite/     # CLI entry points
│   ├── sidecar/        # Observation sidecar + MCP bridge
│   ├── drift_guard/    # Distribution shift detection
│   └── formal/         # TLA+ formal specifications
├── gui/                # Electron + React GUI
├── tests/              # Test suites (540 files, 5991 tests)
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

# Desktop tests
pytest tests/desktop/ -v

# Type checking
mypy src/

# Linting
ruff check src/

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
| Factory Missions O/W/V | Eliminates self-verification blind spots |
| MCP + A2A dual protocol | Maximum ecosystem interoperability |
| Electron + React GUI | Cross-platform desktop agent workstation |
| Sidecar MCP bridge | Standardized Agent observation protocol |
| AuditLogger HMAC | Tamper-evident audit trail (ISO 27001 C.5.33) |

## Knowledge Vault
- **路径**: `vault/`
- **格式**: YAML with frontmatter
- **Signals**: 12 market/technology signals (S-20260511-001 ~ 012)
- **KDPs**: 9 key decision points (K-20260511-001 ~ 009)
- **Patterns**: 1 competitive positioning pattern

## Mission Workspace
- **路径**: `.missions/v0.25.0-security-enhancement/`
- **特性**: 22/22 completed, 330 tests passed
- **验证**: 7 validator rounds, 4 issues found and resolved
- **里程碑**: m0-m6 all completed

## Python Version
- **推荐**: Python 3.11 (`.venv3` → 重命名为 `.venv/`)
- **兼容**: Python 3.10+
- **当前**: Python 3.14 (Homebrew 系统 Python，仅限 `.venv` 使用)

## Quick Reference
- MAREF Lite CLI: `maref-lite --help`
- PERCV CLI: `maref percv --help`
- Sidecar health: `GET /api/health`
- MCP endpoint: `POST /api/mcp`
- MCP well-known: `GET /api/mcp/.well-known`

## 治理合规检查清单

每次提交前应确认：

- [ ] 无 T3/T2 级内容（路径/Key/IP/时间戳）
- [ ] `git remote -v` 为 `maref-org/maref`
- [ ] pre-push hook 已就位
- [ ] CI: pytest + mypy + ruff 通过