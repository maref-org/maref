# MAREF 开发指南

## 环境搭建

### 1. 克隆仓库

```bash
git clone <repository-url>
cd maref
```

### 2. 创建虚拟环境

```bash
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate  # Windows
```

### 3. 安装依赖

```bash
# 基础开发环境
pip install -e ".[dev]"

# 包含 ML 组件
pip install -e ".[dev,ml]"

# 包含 Sidecar 代理
pip install -e ".[dev,sidecar]"

# 全部安装
pip install -e ".[all]"
```

### 4. 安装 pre-commit hooks

```bash
pre-commit install
```

## 代码规范

### 代码风格

- 使用 **Ruff** 进行代码格式化和 lint
- 行长度限制：100 字符
- 使用双引号
- Google 风格文档字符串

### 类型检查

- 所有公共 API 必须添加类型注解
- 使用 **MyPy** 进行静态类型检查
- `disallow_untyped_defs = true`

### 运行检查

```bash
# 代码格式化检查
ruff format --check src tests

# 代码风格检查
ruff check src tests

# 类型检查
mypy src

# 自动修复问题
ruff check --fix src tests
ruff format src tests
```

## 测试

### 测试结构

```
tests/
├── unit/           # 单元测试
├── integration/    # 集成测试
└── chaos/          # 混沌工程测试
```

### 运行测试

```bash
# 运行所有测试
pytest

# 仅运行单元测试
pytest -m unit

# 运行集成测试
pytest -m integration

# 运行混沌测试
pytest -m chaos

# 生成覆盖率报告
pytest --cov=src --cov-report=html
```

### 测试标记

- `unit`: 单元测试（快速、无外部依赖）
- `integration`: 集成测试（需要外部服务）
- `chaos`: 混沌工程测试（破坏性测试）
- `slow`: 慢速测试（>5秒）

## Git 工作流

### 分支策略

- `main`: 稳定分支，仅通过 PR 合并
- `develop`: 开发分支，功能集成
- `feature/*`: 功能分支
- `fix/*`: 修复分支

### 提交规范

使用 Conventional Commits:

```
<type>(<scope>): <subject>

<body>

<footer>
```

类型:
- `feat`: 新功能
- `fix`: 修复
- `docs`: 文档
- `style`: 格式调整
- `refactor`: 重构
- `test`: 测试
- `chore`: 构建/工具

示例:
```
feat(maref-lite): add 10-state gray code state machine

Implement the Hetu 10-state governance overlay with
formal transition guarantees.

Closes #123
```

## 项目结构

```
.
├── src/
│   ├── maref_lite/     # MAREF-Lite 核心（10态治理）
│   ├── sidecar/        # MCP/A2A Sidecar 代理
│   ├── drift_guard/    # LoRA 漂移检测
│   └── formal/         # TLA+ 形式化规范
├── tests/              # 测试代码
├── docs/               # 文档
├── scripts/            # 脚本工具
├── data/               # 数据目录
└── results/            # 结果输出
```

## 发布流程

1. 更新 `pyproject.toml` 中的版本号
2. 更新 `CHANGELOG.md`
3. 创建 Git tag: `git tag v0.x.x`
4. 推送 tag: `git push origin v0.x.x`
5. CI 自动构建并发布到 PyPI

## 常见问题

### Q: 如何添加新的依赖？

A: 编辑 `pyproject.toml` 中的 `[project.dependencies]` 或 `[project.optional-dependencies]`，然后运行 `pip install -e ".[dev]"`。

### Q: 如何运行特定测试文件？

A: `pytest tests/unit/test_specific.py -v`

### Q: 如何调试测试？

A: `pytest tests/unit/test_specific.py --pdb`
