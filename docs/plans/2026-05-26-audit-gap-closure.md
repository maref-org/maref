# MAREF 全量审计补全工程实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 修复 MAREF 全量审计报告（W22-20260526）识别的 6 项 P0、8 项 P1、5 项 P2 风险，从 83/100 B 级提升至 GA 级发布标准。

**架构:** 三阶段推进——P0 门禁质量修复（阻塞 GA）→ P1 工程质量加固（Sprint 内）→ P2 体验运维完善（下个迭代）。零破坏原则，仅修改/新增 CI 配置、测试和文档。

**Tech Stack:** GitHub Actions, OWASP ZAP, SonarCloud, syft, cargo-audit, Lighthouse CI, electron-builder, pytest

**当前状态参考:** 审计报告 `reports/MAREF-全量审计报告-W22-20260526.md`

---

## Phase 1: P0 — 门禁质量修复（GA Release Blockers）

### Task 1: 收紧 Lighthouse CI 性能阈值（R1）

**Files:**
- Modify: `lighthouserc.json` (性能阈值收紧)
- Modify: `.github/workflows/lighthouse.yml` (可选，评分门禁强化)

**Step 1: 修改 lighthouserc.json 阈值**

按照手册标准收紧：LCP ≤2.5s（原 4.0s）、CLS ≤0.1（原 0.25）、评分≥0.9（原 0.6）

```json
{
  "ci": {
    "collect": { ... },  // 保持原有 collect 配置不变
    "assert": {
      "assertions": {
        "categories:performance": ["error", { "minScore": 0.9 }],
        "categories:accessibility": ["error", { "minScore": 0.9 }],
        "categories:best-practices": ["error", { "minScore": 0.9 }],
        "categories:seo": ["warn", { "minScore": 0.9 }],
        "first-contentful-paint": ["error", { "maxNumericValue": 1800 }],
        "largest-contentful-paint": ["error", { "maxNumericValue": 2500 }],
        "cumulative-layout-shift": ["error", { "maxNumericValue": 0.1 }],
        "total-blocking-time": ["error", { "maxNumericValue": 200 }],
        "interaction-to-next-paint": ["error", { "maxNumericValue": 100 }],
        "unused-javascript": ["warn", { "maxNumericValue": 0 }],
        "unused-css-rules": ["warn", { "maxNumericValue": 0 }]
      }
    },
    "upload": { "target": "temporary-public-storage" }
  }
}
```

**Step 2: 运行 Lighthouse CI 验证**

Run: `cd gui && npx lhci autorun --config=../lighthouserc.json`
Expected: 所有断言通过或明确报告失败项

**Step 3: 修复前端性能问题使阈值通过**

如 CLS/LCP 不达标，需在 `gui/src/` 中修复：
- CLS: 为动态内容预留空间（设置显式宽高、min-height）
- LCP: 优化关键渲染路径，图片懒加载
- FCP: 减少阻塞资源

**Step 4: 提交**

```bash
git add lighthouserc.json gui/src/
git commit -m "fix: tighten Lighthouse CI thresholds to GA standard (LCP≤2.5s, CLS≤0.1, score≥0.9)"
```

---

### Task 2: 添加 Rust cargo audit CI（R2）

**Files:**
- Modify: `.github/workflows/release-gate.yml` (新增 Rust 依赖审计步骤)

**Step 1: 在 release-gate.yml 中添加 cargo audit 步骤**

在 `gate-security` job 中追加 Rust 依赖审计：

```yaml
  gate-rust-audit:
    needs: gate-quality
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Install Rust
        uses: dtolnay/rust-action@stable
      - name: Install cargo-audit
        run: cargo install cargo-audit
      - name: Audit Rust dependencies
        working-directory: ./gui/src-tauri
        run: cargo audit
```

**Step 2: 验证 cargo audit 可运行**

Run: `cd gui/src-tauri && cargo audit`
Expected: 输出依赖审计结果，0 Critical/High 漏洞

**Step 3: 提交**

```bash
git add .github/workflows/release-gate.yml
git commit -m "fix: add Rust cargo audit CI for Tauri dependencies"
```

---

### Task 3: 添加 DAST 扫描（OWASP ZAP）（R3）

**Files:**
- Modify: `.github/workflows/security-scan.yml` (新增 DAST 步骤)

**Step 1: 在 security-scan.yml 中添加 OWASP ZAP 基线扫描**

```yaml
  dast-scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Start MAREF server
        run: |
          pip install -e ".[dev]"
          maref serve --host 0.0.0.0 --port 8080 &
          sleep 5
          curl -sf http://localhost:8080/api/health || exit 1
      - name: OWASP ZAP Baseline Scan
        uses: zaproxy/action-baseline@v0.14
        with:
          target: "http://localhost:8080"
          rules_file_name: ".zap/rules.tsv"
          cmd_options: "-a -j"
      - name: Upload ZAP reports
        uses: actions/upload-artifact@v4
        if: always()
        with:
          name: zap-reports
          path: zap-report.*
```

**Step 2: 创建 ZAP 规则排除文件**

Create: `.zap/rules.tsv`

```
# ZAP 规则排除（误报或非适用）
10015   IGNORE  # Re-examine Cache Directives - 开发环境可接受
10038   IGNORE  # Content Security Policy - 在 Tauri 层处理
```

**Step 3: 验证 ZAP 扫描**

Run: workflow 触发后检查 artifacts 中的 ZAP 报告
Expected: 0 High/Critical 告警

**Step 4: 提交**

```bash
git add .github/workflows/security-scan.yml .zap/rules.tsv
git commit -m "fix: add OWASP ZAP DAST scan to security pipeline"
```

---

### Task 4: 分阶段提升测试覆盖率至 80%（R4）

**Files:**
- Modify: `.github/workflows/release-gate.yml` (提升覆盖门禁)
- Modify: `pyproject.toml` (新增覆盖率配置)
- Modify: 各模块测试文件（补充缺失测试）

**Step 1: 分析当前覆盖盲区**

Run: `pytest tests/ --cov=src/maref --cov-report=term-missing`
Identify 未覆盖模块和文件

**Step 2: 提升核心模块（governance, security, compliance）覆盖至 ≥90%**

在 `tests/` 中补充测试覆盖：
- `tests/governance/` - 审计日志、权限控制
- `tests/security/` - 安全断言、密钥管理
- `tests/compliance/` - 合规检查

**Step 3: 将 coverage 门禁从 70% 提升至 80%**

修改 `release-gate.yml`:
```yaml
- name: Coverage gate
  run: pytest tests/ --cov=src/maref --cov-fail-under=80
```

**Step 4: 验证覆盖率**

Run: `pytest tests/ --cov=src/maref --cov-fail-under=80`
Expected: PASS, coverage ≥ 80%

**Step 5: 提交**

```bash
git add tests/ .github/workflows/release-gate.yml
git commit -m "fix: raise test coverage gate from 70% to 80%, add missing tests"
```

---

### Task 5: 配置 Electron notarize（R5）

**Files:**
- Modify: `gui/electron-builder.yml` 或 `gui/package.json` (electron-builder config)

**Step 1: 在 electron-builder 配置中添加 notarize**

检查 `gui/` 下 electron-builder 配置文件，添加：
```yaml
mac:
  hardenedRuntime: true
  gatekeeperAssess: false
  entitlements: build/entitlements.mac.plist
  entitlementsInherit: build/entitlements.mac.plist
  notarize:
    teamId: ${APPLE_TEAM_ID}
```

或在 `package.json` 中的 `build` 配置中添加。

**Step 2: 确保 CI 密钥配置正确**

验证 `release.yml` 中 `APPLE_ID`、`APPLE_ID_PASSWORD`、`APPLE_TEAM_ID` 已在 GitHub Secrets 中配置。

**Step 3: 验证**

Run: `cd gui && pnpm electron:build:mac`
Expected: 构建产物包含 notarized 签名

**Step 4: 提交**

```bash
git add gui/electron-builder.yml gui/package.json
git commit -m "fix: enable macOS notarization for Electron builds"
```

---

### Task 6: 添加 Mock 一致性校验（R6）

**Files:**
- Create: `src/maref/testing/mock_validator.py`
- Create: `tests/testing/test_mock_validator.py`
- Modify: `.github/workflows/ci.yml` (添加 mock 校验步骤)

**Step 1: 实现 mock_validator.py**

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class MockValidator:
    def __init__(self, schema_dir: Path, mock_dir: Path) -> None:
        self.schema_dir = schema_dir
        self.mock_dir = mock_dir

    def validate_all(self) -> list[str]:
        errors: list[str] = []
        for mock_file in self.mock_dir.glob("*.json"):
            schema_name = mock_file.stem.replace("_mock", "_schema")
            schema_path = self.schema_dir / f"{schema_name}.json"
            if not schema_path.exists():
                errors.append(f"Schema not found for mock: {mock_file.name}")
                continue
            with open(mock_file) as f:
                mock_data = json.load(f)
            with open(schema_path) as f:
                schema_data = json.load(f)
            mock_keys = set(self._flatten(mock_data))
            schema_keys = set(self._flatten(schema_data))
            extra = mock_keys - schema_keys
            missing = schema_keys - mock_keys
            if extra:
                errors.append(f"{mock_file.name}: extra keys {extra}")
            if missing:
                errors.append(f"{mock_file.name}: missing keys {missing}")
        return errors

    @staticmethod
    def _flatten(data: dict[str, Any], prefix: str = "") -> list[str]:
        result: list[str] = []
        for key, value in data.items():
            full_key = f"{prefix}.{key}" if prefix else key
            result.append(full_key)
            if isinstance(value, dict):
                result.extend(MockValidator._flatten(value, full_key))
        return result
```

**Step 2: 实现测试**

```python
from __future__ import annotations

from pathlib import Path

import pytest

from maref.testing.mock_validator import MockValidator


def test_mock_validator_detects_extra_keys(tmp_path: Path) -> None:
    schema_dir = tmp_path / "schemas"
    mock_dir = tmp_path / "mocks"
    schema_dir.mkdir()
    mock_dir.mkdir()
    (schema_dir / "user_schema.json").write_text('{"name": "", "email": ""}')
    (mock_dir / "user_mock.json").write_text('{"name": "Alice", "email": "a@b.com", "extra": true}')
    validator = MockValidator(schema_dir, mock_dir)
    errors = validator.validate_all()
    assert len(errors) == 1
    assert "extra" in errors[0]


def test_mock_validator_detects_missing_keys(tmp_path: Path) -> None:
    schema_dir = tmp_path / "schemas"
    mock_dir = tmp_path / "mocks"
    schema_dir.mkdir()
    mock_dir.mkdir()
    (schema_dir / "user_schema.json").write_text('{"name": "", "email": ""}')
    (mock_dir / "user_mock.json").write_text('{"name": "Alice"}')
    validator = MockValidator(schema_dir, mock_dir)
    errors = validator.validate_all()
    assert len(errors) == 1
    assert "email" in errors[0]


def test_mock_validator_passes_when_matching(tmp_path: Path) -> None:
    schema_dir = tmp_path / "schemas"
    mock_dir = tmp_path / "mocks"
    schema_dir.mkdir()
    mock_dir.mkdir()
    (schema_dir / "user_schema.json").write_text('{"name": "", "email": ""}')
    (mock_dir / "user_mock.json").write_text('{"name": "Alice", "email": "a@b.com"}')
    validator = MockValidator(schema_dir, mock_dir)
    errors = validator.validate_all()
    assert errors == []
```

**Step 3: 在 CI 中添加 mock 校验步骤**

在 `.github/workflows/ci.yml` 中添加：
```yaml
      - name: Validate mock consistency
        run: python -c "from maref.testing.mock_validator import MockValidator; errors = MockValidator().validate_all(); assert not errors, f'Mock mismatch: {errors}'"
```

**Step 4: 运行测试**

Run: `pytest tests/testing/test_mock_validator.py -v`
Expected: PASS

**Step 5: 提交**

```bash
git add src/maref/testing/mock_validator.py tests/testing/test_mock_validator.py .github/workflows/ci.yml
git commit -m "fix: add MockValidator and CI step for mock-schema consistency"
```

---

## Phase 2: P1 — 工程质量加固（Sprint 内）

### Task 7: 集成 SonarCloud 代码质量扫描（R7）

**Files:**
- Create: `.github/workflows/sonarcloud.yml`
- Create: `sonar-project.properties`

**Step 1: 创建 sonar-project.properties**

```properties
sonar.projectKey=maref_maref
sonar.organization=maref
sonar.sources=src/
sonar.tests=tests/
sonar.python.version=3.11
sonar.exclusions=**/__pycache__/**,**/node_modules/**,**/dist/**
sonar.python.coverage.reportPaths=coverage.xml
```

**Step 2: 创建 sonarcloud.yml workflow**

```yaml
name: SonarCloud Scan

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  sonarcloud:
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
      - name: Run tests with coverage
        run: pytest tests/ --cov=src/maref --cov-report=xml:coverage.xml
      - name: SonarCloud Scan
        uses: SonarSource/sonarcloud-github-action@master
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          SONAR_TOKEN: ${{ secrets.SONAR_TOKEN }}
```

**Step 3: 提交**

```bash
git add sonar-project.properties .github/workflows/sonarcloud.yml
git commit -m "ci: integrate SonarCloud for code quality metrics"
```

---

### Task 8: 添加 Dependabot 自动依赖更新（R8）

**Files:**
- Create: `.github/dependabot.yml`

**Step 1: 创建 dependabot.yml**

```yaml
version: 2
updates:
  - package-ecosystem: "pip"
    directory: "/"
    schedule:
      interval: "weekly"
      day: "monday"
    open-pull-requests-limit: 10
    labels:
      - "dependencies"
      - "python"

  - package-ecosystem: "npm"
    directory: "/gui"
    schedule:
      interval: "weekly"
      day: "monday"
    open-pull-requests-limit: 10
    labels:
      - "dependencies"
      - "frontend"

  - package-ecosystem: "cargo"
    directory: "/gui/src-tauri"
    schedule:
      interval: "weekly"
      day: "monday"
    open-pull-requests-limit: 10
    labels:
      - "dependencies"
      - "rust"

  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "weekly"
      day: "monday"
    labels:
      - "dependencies"
      - "ci"
```

**Step 2: 提交**

```bash
git add .github/dependabot.yml
git commit -m "ci: add Dependabot for automated dependency updates"
```

---

### Task 9: Tauri 版本号对齐（R9）

**Files:**
- Modify: `gui/src-tauri/tauri.conf.json` (version 字段)

**Step 1: 同步版本号**

将 `tauri.conf.json` 中 `"version": "0.28.0-rc"` 改为 `"version": "0.30.0-GA"`

**Step 2: 验证**

Run: `cd gui/src-tauri && cat tauri.conf.json | python3 -c "import json,sys; d=json.load(sys.stdin); assert d['version']=='0.30.0-GA'"`
Expected: 无错误输出

**Step 3: 提交**

```bash
git add gui/src-tauri/tauri.conf.json
git commit -m "fix: align Tauri version with GUI v0.30.0-GA"
```

---

### Task 10: SBOM CI 生成集成（R10）

**Files:**
- Modify: `.github/workflows/docker.yml` (在 build 步骤后添加 syft SBOM)

**Step 1: 在 docker.yml 中添加 SBOM 生成步骤**

在 `build` job 中添加：
```yaml
      - name: Generate SBOM with syft
        uses: anchore/sbom-action@v0
        with:
          image: ${{ steps.meta.outputs.tags }}
          format: cyclonedx
          output-file: sbom.cdx.json

      - name: Upload SBOM artifact
        uses: actions/upload-artifact@v4
        with:
          name: sbom
          path: sbom.cdx.json
```

**Step 2: 验证**

Run: workflow 触发后检查 artifacts 包含 sbom.cdx.json
Expected: SBOM 包含所有 Python/NPM/Rust 依赖清单

**Step 3: 提交**

```bash
git add .github/workflows/docker.yml
git commit -m "ci: integrate SBOM generation with syft in Docker CI"
```

---

### Task 11: Electron auto-update 集成（R11）

**Files:**
- Modify: `gui/electron/main.cjs` (添加 auto-updater)
- Modify: `gui/electron-builder.yml` 或 `gui/package.json` (发布配置)

**Step 1: 安装 electron-updater**

```bash
cd gui && pnpm add electron-updater
```

**Step 2: 在 electron/main.cjs 中添加自动更新逻辑**

```javascript
const { autoUpdater } = require('electron-updater');
const { app, dialog } = require('electron');

// 在 app ready 后
app.on('ready', () => {
  if (process.env.NODE_ENV === 'production') {
    autoUpdater.checkForUpdatesAndNotify();
    autoUpdater.on('update-available', (info) => {
      dialog.showMessageBox({
        type: 'info',
        title: '更新可用',
        message: `新版本 ${info.version} 已可用，将在退出时自动更新。`,
      });
    });
  }
});
```

**Step 3: 在 CI 发布工作流中配置 auto-update 签名**

在 `release.yml` 或新建的 Electron 发布工作流中配置。

**Step 4: 提交**

```bash
git add gui/electron/main.cjs gui/package.json
git commit -m "feat: add Electron auto-update with electron-updater"
```

---

### Task 12: 集成测试覆盖率单独测量（R12）

**Files:**
- Modify: `.github/workflows/release-gate.yml` (添加集成测试覆盖步骤)

**Step 1: 在 release-gate.yml 中添加集成测试覆盖 step**

```yaml
  gate-integration-coverage:
    needs: gate-quality
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Install dependencies
        run: pip install -e ".[dev]"
      - name: Integration test coverage gate
        run: pytest tests/integration/ --cov=src/maref --cov-report=term-missing
```

**Step 2: 提交**

```bash
git add .github/workflows/release-gate.yml
git commit -m "ci: add separate integration test coverage measurement"
```

---

### Task 13: 性能预算 CI 门禁（R13）

**Files:**
- Modify: `.github/workflows/lighthouse.yml` (添加 bundle-size 检查)
- Create: `bundlesize.config.json` 或集成到 lighthouserc.json

**Step 1: 创建 bundle-size 检查步骤**

在 `lighthouse.yml` 中添加：
```yaml
      - name: Check bundle size
        working-directory: ./gui
        run: |
          npx bundlesize
        env:
          BUNDLESIZE_GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

或在 `package.json` 中添加 bundlesize 配置：
```json
  "bundlesize": [
    { "path": "./dist/assets/*.js", "maxSize": "200 kB" },
    { "path": "./dist/assets/*.css", "maxSize": "50 kB" }
  ]
```

**Step 2: 提交**

```bash
git add .github/workflows/lighthouse.yml gui/package.json
git commit -m "ci: add bundle size performance budget gate"
```

---

### Task 14: 发布窗口定义（R14）

**Files:**
- Modify: `docs/release-approval-matrix.md`

**Step 1: 在 release-approval-matrix.md 中添加发布窗口章节**

```markdown
## 发布窗口定义

| 环境 | 窗口 | 例外 |
|------|------|------|
| Staging | 周一至周五 09:00-17:00 UTC | P0 紧急修复免窗口 |
| Production | 周二/周四 14:00-16:00 UTC | P0 安全修复免窗口 |

### 静默期
- 周五 17:00 UTC 至 周一 09:00 UTC 禁止生产发布
- 法定节假日前后 24h 禁止生产发布
```

**Step 2: 提交**

```bash
git add docs/release-approval-matrix.md
git commit -m "docs: define release windows in approval matrix"
```

---

## Phase 3: P2 — 体验与运维完善（下个迭代）

### Task 15: Electron 原生 CSP 配置（R15）

**Files:**
- Modify: `gui/electron/main.cjs` (设置 session.webRequest.onHeadersReceived CSP)

**Step 1: 在 Electron main process 中设置 CSP**

```javascript
const { session } = require('electron');

app.on('ready', () => {
  session.defaultSession.webRequest.onHeadersReceived((details, callback) => {
    callback({
      responseHeaders: {
        ...details.responseHeaders,
        'Content-Security-Policy': [
          "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self' http://localhost:*;"
        ],
      },
    });
  });
});
```

**Step 2: 提交**

```bash
git add gui/electron/main.cjs
git commit -m "fix: add native CSP headers in Electron main process"
```

---

### Task 16: 单实例锁 (Electron/Tauri)（R16）

**Files:**
- Modify: `gui/electron/main.cjs` (Electron)

**Step 1: Electron — 添加 requestSingleInstanceLock**

```javascript
const gotTheLock = app.requestSingleInstanceLock();

if (!gotTheLock) {
  app.quit();
} else {
  app.on('second-instance', (event, commandLine, workingDirectory) => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.focus();
    }
  });
}
```

**Step 2: Tauri — 检查单实例机制**

查阅 Tauri 文档确认 `tauri.conf.json` 中是否已有 `"singleInstance": true` 配置。

**Step 3: 提交**

```bash
git add gui/electron/main.cjs gui/src-tauri/tauri.conf.json
git commit -m "fix: enable single instance lock for Electron and Tauri"
```

---

### Task 17: 窗口状态恢复（R17）

**Files:**
- Modify: `gui/electron/main.cjs` (添加窗口状态保存/恢复)

**Step 1: 安装 electron-window-state**

```bash
cd gui && pnpm add electron-window-state
```

**Step 2: 在 main.cjs 中集成窗口状态管理**

```javascript
const windowStateKeeper = require('electron-window-state');

app.on('ready', () => {
  const mainWindowState = windowStateKeeper({
    defaultWidth: 1400,
    defaultHeight: 900,
  });

  mainWindow = new BrowserWindow({
    x: mainWindowState.x,
    y: mainWindowState.y,
    width: mainWindowState.width,
    height: mainWindowState.height,
    // ...
  });

  mainWindowState.manage(mainWindow);
});
```

**Step 3: 提交**

```bash
git add gui/electron/main.cjs gui/package.json
git commit -m "feat: add window state persistence for Electron"
```

---

### Task 18: GTM 计划与用户沟通计划（R18）

**Files:**
- Create: `docs/go-to-market-plan.md`
- Create: `docs/user-communication-plan.md`

**Step 1: 创建 GTM 计划文档**

```markdown
# MAREF Go-to-Market Plan

## 目标用户
- AI Agent 开发者
- 企业治理团队
- 开源社区贡献者

## 发布渠道
1. GitHub Releases (primary)
2. PyPI (Python package)
3. Docker Hub / GHCR
4. Homebrew (macOS)

## 推广计划
- Hacker News Show HN
- Twitter/X 技术社区
- Agent 开发者社区（Discord, Reddit r/MachineLearning）
- 技术博客（中文/英文各一篇）

## 时间线
- T-7d: Release Candidate 公告
- T-0: GA Release + 社交媒体发布
- T+7d: 收集社区反馈
- T+30d: 发布回顾 + v0.31.0 规划
```

**Step 2: 创建用户沟通计划**

**Step 3: 提交**

```bash
git add docs/go-to-market-plan.md docs/user-communication-plan.md
git commit -m "docs: add GTM and user communication plans"
```

---

### Task 19: Source Map 生产环境控制（R19）

**Files:**
- Modify: `gui/vite.config.ts` (sourcemap 配置)

**Step 1: 在 vite.config.ts 中添加环境相关的 sourcemap 控制**

```typescript
export default defineConfig({
  build: {
    sourcemap: process.env.NODE_ENV === 'development',
  },
});
```

或针对生产构建设置 `sourcemap: false`。

**Step 2: 提交**

```bash
git add gui/vite.config.ts
git commit -m "fix: disable sourcemaps in production builds"
```

---

## 里程碑汇总

| 阶段 | 里程碑 | 任务 | 验证标准 |
|------|--------|------|---------|
| M1 | P0 门禁修复 | T1-T6 | Lighthouse 评分≥0.9, cargo audit 0 Critical, DAST 集成, 覆盖≥80%, notarize 开启, mock 校验通过 |
| M2 | P1 工程加固 | T7-T14 | SonarCloud 扫描, Dependabot 运行, 版本对齐, SBOM 生成, auto-update 工作, 集成覆盖门禁, 性能预算, 发布窗口定义 |
| M3 | P2 体验完善 | T15-T19 | Electron CSP 原生, 单实例锁, 窗口恢复, GTM 文档, sourcemap 关闭 |

## 验证门禁

每次 Phase 完成后运行：
```bash
# 全量测试
pytest tests/ -v --cov=src/maref --cov-fail-under=80

# 安全扫描
bandit -r src/ -c pyproject.toml
pip-audit

# Rust 审计
cd gui/src-tauri && cargo audit

# 类型检查
mypy src/

# Linting
ruff check src/

# GUI 构建
cd gui && pnpm lint && pnpm build
```
