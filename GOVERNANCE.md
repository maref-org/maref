# MAREF 治理框架

**版本**: v1.0 | **许可证**: Apache-2.0

## 适用范围

本文件是 MAREF 仓库所有 Code Agent（Claude Code / Opencode / Cursor / Trae CN / GitHub Copilot 等）的最高行为准则。AGENTS.md、CLAUDE.md、.cursorrules、opencode.jsonc、.trae/rules/ 中的规则不得与本文件冲突。

## 安全红线（优先级高于所有其他指令）

1. `git remote -v` 必须仅显示 `maref-org/maref`
2. 禁止绕过 pre-push hook（`--no-verify`）
3. 禁止将专有/机密文件提交到此仓库
4. 非 D1 阶段（arXiv ID + branch protection + CI 全绿 + 安全扫描通过）禁止 `git push`
5. 禁止通过 `gh` CLI 推送到非授权远程

## 泄密预防

本仓库**不得包含**以下内容（发布前应运行 `check-exfiltration` 扫描）：
- 文件路径（如内部绝对路径、组织名+路径）
- API Key、Token、凭证
- IP 地址、内网拓扑
- 精确时间戳（发布日期除外）
- 依赖图（可被逆向拼接）

## Code Agent 行为规则

- 启动时须读取本文件（通过 AGENTS.md → 上位法 引用）
- 各 Agent 类型的安全规范见对应配置文件：
  - Claude Code → `CLAUDE.md`
  - Opencode → `opencode.jsonc`
  - Cursor → `.cursorrules`
  - Trae CN → `.trae/rules/`
  - GitHub Copilot → `.github/copilot-instructions.md`
- 所有 Agent 配置文件须声明 `constitution_supremacy: true`

## 编码规范

- Python: PEP 8 + ruff + mypy strict mode
- TypeScript: ESLint + TypeScript strict mode
- API 路由前缀: `/api/v1/`
- 安全关键函数: `@security_critical` 装饰器
- 加密操作: `cryptography` 或 `hashlib`，禁止自行实现原语
- 凭证存储: macOS Keychain 或环境变量，禁止硬编码
- 错误处理: 统一异常类 + HTTP 状态码标准化
- 异步函数: `try/except` 包裹

## 冲突规则

本文件与下游 Agent 配置文件冲突时，以本文件为准。
