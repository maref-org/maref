# MAREF-ORG CI/CD 工作流配置方案

> **目标**: 将 OpenClaw 的 CI 基础设施适配到 maref-org/maref 独立开源仓库
> **代码库**: `/Volumes/1TB-M2/public/maref` → GitHub: `maref-org/maref`
> **文档库**: `/Volumes/1TB-M2/Athena知识库/.../MAREF递归演进框架/`（独立，不进入代码库）
> **生成日期**: 2026-05-25

---

## 一、路径边界声明（重要）

```
┌─────────────────────────────────────────────────────────────────┐
│  代码库 (Code Repository)                                        │
│  本地: /Volumes/1TB-M2/public/maref                             │
│  GitHub: https://github.com/maref-org/maref                     │
│                                                                  │
│  包含: src/, tests/, docs/ (技术文档), .github/workflows/       │
│  不包含: 申报材料/, 待执行/, PERCV研究报告/, 策略文档/           │
└─────────────────────────────────────────────────────────────────┘
                              ↕ 隔离边界
┌─────────────────────────────────────────────────────────────────┐
│  文档库 (Document Repository)                                    │
│  本地: /Volumes/1TB-M2/Athena知识库/.../MAREF递归演进框架/       │
│                                                                  │
│  包含: 策略文档, PERCV研究报告, 申报材料, 待执行, 归档/          │
│  不包含: 源代码, 测试代码, CI配置                                │
└─────────────────────────────────────────────────────────────────┘
```

**红线规则**: 任何策略文档、申报材料、PERCV 研究报告**不得**进入 `/Volumes/1TB-M2/public/maref` 代码库。

---

## 二、工作流文件清单

将以下文件创建到 `/Volumes/1TB-M2/public/maref/.github/workflows/`：

### 2.1 核心 CI 工作流

| 文件名 | 来源 | 适配说明 |
|--------|------|---------|
| `ci.yml` | OpenClaw `ci.yml` | 精简为 MAREF 核心模块测试 |
| `security-scan.yml` | OpenClaw `trufflehog-secrets-scan.yml` + `semgrep-scan.yml` | 合并为统一安全扫描 |
| `formal-verify.yml` | OpenClaw `formal-verify.yml` | 直接复用 TLA+ 验证 |
| `release-gate.yml` | OpenClaw `release-gate.yml` | 精简为开源发布检查 |

### 2.2 辅助工作流

| 文件名 | 功能 | 触发条件 |
|--------|------|---------|
| `chaos-test.yml` | 混沌工程测试 | 手动触发 + 每周定时 |
| `coverage-gate.yml` | 覆盖率门槛检查 | PR 时触发 |
| `documentation-quality.yml` | 文档质量检查 | PR 修改 docs/ 时触发 |

### 2.3 禁用/不迁移的工作流

| 文件名 | 原因 |
|--------|------|
| `subtree-split.yml` | OpenClaw 特有，MAREF 是独立仓库 |
| `check-mcp-envelope.yml` | OpenClaw 内部协议检查 |
| `check-agent-lifecycle.yml` | OpenClaw 内部生命周期检查 |
| `cd.yml.DISABLED` | 当前禁用，后续按需启用 |

---

## 三、ci.yml 适配方案

```yaml
name: MAREF CI

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Install dependencies
        run: pip install -e ".[dev]"
      - name: Ruff lint
        run: ruff check src/maref src/maref_lite
      - name: Ruff format check
        run: ruff format --check src/maref src/maref_lite
      - name: Mypy type check
        run: mypy src/maref src/maref_lite

  test:
    needs: lint
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Install dependencies
        run: pip install -e ".[dev]"
      - name: Run unit tests
        run: |
          coverage run -m pytest tests/ -x -q --timeout=120 -m "not integration and not chaos and not benchmark"
      - name: Coverage report
        run: coverage report --fail-under=70

  security:
    needs: lint
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Install dependencies
        run: pip install -e ".[dev]"
      - name: Bandit SAST
        run: bandit -r src/ -c pyproject.toml
      - name: pip-audit
        run: pip-audit
      - name: TruffleHog Secret Scan
        run: |
          pip install trufflehog
          trufflehog filesystem . --config .trufflehog.yaml --since 2026-01-01

  crypto-test:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Install dependencies
        run: pip install -e ".[dev]"
      - name: Run cryptography tests
        run: |
          pytest tests/compliance/test_crypto_sm2.py tests/compliance/test_crypto_sm3.py tests/compliance/test_crypto_sm4.py -v
```

---

## 四、security-scan.yml 适配方案

```yaml
name: Security Scan

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
  schedule:
    - cron: "0 3 * * *"  # 每天 UTC 3:00

jobs:
  secrets-scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - name: TruffleHog Secret Scan
        run: |
          pip install trufflehog
          trufflehog filesystem . --config .trufflehog.yaml --since 2026-01-01

  semgrep-scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Semgrep Scan
        uses: returntocorp/semgrep-action@v1
        with:
          config: >-
            p/security-audit
            p/owasp-top-ten
            p/cwe-top-25

  dependency-scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: pip-audit
        run: pip-audit
```

---

## 五、formal-verify.yml 适配方案

```yaml
name: Formal Verification

on:
  push:
    paths:
      - 'src/formal/**'
      - 'src/maref/governance/**'
  pull_request:
    paths:
      - 'src/formal/**'
      - 'src/maref/governance/**'
  workflow_dispatch:

jobs:
  tla-verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Setup TLA+
        run: |
          wget -q https://github.com/tlaplus/tlaplus/releases/download/v1.4.5/tla2tools.jar -O /tmp/tla2tools.jar
      - name: Verify Gray Code FSM
        run: |
          java -cp /tmp/tla2tools.jar tlc2.TLC src/formal/MarefLite.tla -config src/formal/MarefLiteMC.cfg
      - name: Verify Consensus
        run: |
          java -cp /tmp/tla2tools.jar tlc2.TLC src/formal/MAREF_Consensus.tla -config src/formal/MAREF_ConsensusMC.cfg
```

---

## 六、release-gate.yml 适配方案

```yaml
name: Release Gate

on:
  pull_request:
    branches: [main]
    types: [opened, synchronize, reopened]

jobs:
  gate-quality:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Install dependencies
        run: pip install -e ".[dev]"
      - name: Ruff lint
        run: ruff check src/maref src/maref_lite
      - name: No hardcoded paths
        run: |
          if grep -rn "/Volumes/" src/ --include="*.py"; then
            echo "::error::Found hardcoded /Volumes/ paths"
            exit 1
          fi
      - name: No nested .git
        run: |
          found=$(find . -name ".git" -not -path "./.git" -type d)
          if [ -n "$found" ]; then
            echo "::error::Found nested .git directories"
            exit 1
          fi

  gate-test:
    needs: gate-quality
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Install dependencies
        run: pip install -e ".[dev]"
      - name: Core tests
        run: pytest tests/governance/ tests/formal/ -v --tb=short -x
      - name: Coverage gate
        run: pytest tests/ --cov=src/maref --cov-fail-under=70

  gate-security:
    needs: gate-quality
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Bandit SAST
        run: bandit -r src/ -c pyproject.toml
      - name: pip-audit
        run: pip-audit
```

---

## 七、与 OpenClaw 的差异对比

| 维度 | OpenClaw | MAREF-ORG |
|------|----------|-----------|
| **仓库结构** | 单体大仓（internal + public） | 独立仓库 |
| **子树拆分** | `subtree-split.yml` 自动拆分 | 不需要 |
| **代码边界** | `internal/` vs `public/` | 全部公开（Apache-2.0） |
| **安全扫描** | 含内部协议检查 | 仅开源代码扫描 |
| **叙事转化** | T3 内容泄露检查 | 不需要（全部公开） |
| **测试范围** | 全量（含内部模块） | 仅 `src/maref/` + `src/maref_lite/` |
| **发布目标** | PyPI + 内部 Registry | PyPI + GitHub Releases |

---

## 八、实施步骤

### Step 1: 创建工作流目录

```bash
cd /Volumes/1TB-M2/public/maref
mkdir -p .github/workflows
```

### Step 2: 复制适配后的工作流

将上述 `ci.yml`, `security-scan.yml`, `formal-verify.yml`, `release-gate.yml` 写入 `.github/workflows/`。

### Step 3: 验证配置

```bash
# 本地验证 YAML 语法
python -c "import yaml; list(map(yaml.safe_load, open('.github/workflows/ci.yml')))"
```

### Step 4: 推送并测试

```bash
git add .github/workflows/
git commit -m "ci: add GitHub Actions workflows for maref-org"
git push origin main
```

### Step 5: 在 GitHub 上验证

- 访问 `https://github.com/maref-org/maref/actions`
- 确认工作流正常触发

---

## 九、文档隔离检查清单

在每次提交前，运行以下检查确保文档未混入代码库：

```bash
#!/bin/bash
# scripts/check-doc-isolation.sh

FORBIDDEN_DIRS=("申报材料" "待执行" "PERCV-研究报告" "策略文档")
FORBIDDEN_PATTERNS=("*.md" "!docs/*.md" "!README.md" "!CHANGELOG.md" "!CONTRIBUTING.md" "!CODE_OF_CONDUCT.md" "!SECURITY.md")

for dir in "${FORBIDDEN_DIRS[@]}"; do
  if [ -d "$dir" ]; then
    echo "ERROR: Forbidden directory found: $dir"
    exit 1
  fi
done

echo "OK: No forbidden documents in code repository"
```

---

*方案版本: v1.0 | 生成日期: 2026-05-25 | 基于 OpenClaw CI 基础设施适配*
