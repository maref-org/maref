# Agent Operating Manual: MAREF v0.25.0 Security Mission (Pilot)

## Project Overview
- **技术栈**: Python 3.10+ / FastAPI / Redis (可选) / 标准库优先
- **架构**: 分层治理架构（观测→分析→评估→决策→执行→验证）
- **代码风格**: PEP 8 + ruff + mypy strict mode
- **安全级别**: 最高（不可降级安全断言）

## Boundaries
- **禁止**: 修改 `validation-contract.md`（仅 Orchestrator 可修改）
- **禁止**: 跨特征深度导入（每个特征目录独立）
- **禁止**: 在 Worker 中运行数据库迁移（仅 CI/CD 执行）
- **禁止**: 绕过 TrustBoundaryManager 进行跨域调用

## Coding Conventions
- 所有 API 路由使用 `/api/v1/` 前缀
- 错误处理统一使用异常类，状态码标准化
- 所有异步函数必须包裹 `try/except`
- 安全相关函数必须声明 `@security_critical` 装饰器
- 所有加密操作使用 `cryptography` 或 `hashlib` 库，禁止自行实现密码学原语

## Handoff Discipline
每个特征完成后必须:
1. 运行完整测试套件（`pytest tests/ -v --cov`）
2. 覆盖率 ≥ 该特征的 `test_coverage_threshold`
3. 提交 Git commit，消息格式: `feat(s3): zero-trust gateway enhancement`
4. 更新 `features.json` 中该特征状态为 `completed`
5. 在 `knowledge-library/` 留下实现笔记

## Knowledge Library
- **路径**: `.missions/v0.25.0-security-enhancement/knowledge/`
- **格式**: `<feature-id>-learnings.md`
- **内容**: 技术决策 rationale、已知限制、后续优化方向

## Security-Specific Rules
- 所有输入必须验证（`pydantic` + 自定义校验器）
- 所有输出必须编码（防止 XSS/注入）
- 凭证/密钥不得硬编码，必须使用环境变量
- 审计日志必须包含：timestamp, actor, action, resource, result, risk_score
