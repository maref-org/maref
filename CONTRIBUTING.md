# MAREF 贡献指南

> **贡献方式**：Pull Request 或 Fork + PR
> - **MAREF 采用 Pull Request 模式**：小团队快速迭代，避免分支爆炸

---

## 快速开始

### 1. 环境准备

```bash
# 克隆仓库
git clone https://github.com/maref-org/maref.git
cd maref

# 创建虚拟环境（推荐）
python3 -m venv .venv
source .venv/bin/activate

# 安装开发依赖
pip install -e ".[dev]"
```

### 2. 开发流程

```bash
# 拉取最新代码
git pull origin main

# 创建功能分支（从 main 分支）
# 命名规范: <type>/<slug>，type ∈ feat|fix|refactor|chore|docs|test
git checkout -b feat/your-feature-name

# 进行开发
# ... 你的修改 ...

# 运行测试
pytest tests/ -v

# 提交更改
git add .
git commit -m "feat: add your feature"

# 推送到远程分支
git push origin feat/your-feature-name
```

### 3. 提交 Pull Request

```bash
# 在 GitHub 上创建 Pull Request
gh pr create --title "Add your feature" --body "描述你的更改"
```

---

## 代码规范

### Python

- **PEP 8 遵循**：遵循 PEP 8 编码规范
- **类型注解**：使用 `from __future__ import annotations` + 类型注解
- **文档字符串**：使用三引号字符串 `"""` �不是单引号字符串 `'`
- **导入顺序**：标准库 → 第三方库 → 本地模块

### TypeScript

- **ESLint + TypeScript strict mode**
- **类型安全**：避免 `any`，使用具体类型

---

## 测试规范

### 单元测试

```python
# 运行所有测试
pytest tests/ -v

# 运行特定测试文件
pytest tests/test_specific_file.py -v

# 运行特定测试并生成覆盖率报告
pytest tests/ --cov=src/maref --cov-report=html
```

### 集成测试

```bash
# 运行所有测试并生成覆盖率报告
pytest tests/ -v --cov=src/maref --cov-report=html --cov-report=term

# 检查覆盖率是否达到目标（核心模块 ≥60%，整体 ≥40%）
```

---

## 提交前检查清单

### 代码质量

- [ ] 运行 `ruff check src/` - 0 错误
- [ ] 运行 `mypy src/maref/ --ignore-missing-imports` - 0 �误误

### 测试

- [ ] 运行 `pytest tests/ -v` - 所有测试通过
- [ ] 运行 `pytest tests/integration/percv/ -v` - PERCV 集成测试通过

### 文档

- [ ] 更新相关文档（如适用）

---

## 提交信息模板

```
feat: 简短描述

详细描述（可选）：
- 实现了什么功能
- 使用了什么技术
- 影响了哪些模块

关联 Issue（可选）：
- Fixes #123
- Closes #456

Breaking Changes（可选）：
- 列出所有破坏性变更

Co-authored-by（可选）：
- 列出共同贡献者
```

---

## 常见问题

### 贡献前

- 是否有未提交的更改？`git status`
- 是否有未推送的提交？`git log origin/main..HEAD`

### 开发中

- 如何处理冲突？`git pull --rebase origin main`
- 如何撤销本地更改？`git reset --hard HEAD~1`

---

## 联系方式

- **GitHub Discussions**: 用于技术讨论
- **GitHub Issues**: 用于 Bug 报告和功能请求
- **Email**: admin@maref.cc

---

## 资源

- [MAREF 官法](docs/CONSTITUTION.md)
- [MAREF 开源执行规范](docs/oss-execution-norm-v1.0.md)
- [AGENTS.md](AGENTS.md)
