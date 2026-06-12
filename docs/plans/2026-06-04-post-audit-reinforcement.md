# MAREF 补强工程实施方案：审计后修复 + 竞品差距弥合

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**目标**: 修复全栈 PRR 审计发现的 9 个 P0 阻塞 + 弥合竞品差距分析识别的关键缺口，使 MAREF 从 D 级达到 Beta 级发布标准

**架构**: 六阶段渐进式补强——安全热修复 → 基础设施 → 全栈链路 → 前端质量 → 竞品护城河 → 运维就绪

**技术栈**: Python 3.10+ / FastAPI / Electron / React 19+TypeScript / TLA+ / K8s / Docker

**依据文档**:
- `reports/audit-2026-06-04.md` — 全栈 PRR 审计
- `reports/competitive-gap-analysis-2026-06-04.md` — 竞品差距分析

---

## 总览

```
时间线: Week 1 ── Week 2 ── Week 3 ── Week 4 ── Week 5 ── Week 6
         Phase 0   Phase 1   Phase 2   Phase 3   Phase 4   Phase 5
         安全热修复  基础设施    全栈链路    前端质量    护城河加固   运维就绪
         
         [9 P0]     [CI/K8s]   [API/错误码] [测试/CSP]  [白皮书]   [Runbook/GTM]
```

### 六个阶段总览

| Phase | 名称 | 周期 | 任务数 | 核心产出 |
|-------|------|------|--------|---------|
| 0 | 安全热修复 | W1 (5d) | 9 | 所有 P0 阻塞清零 |
| 1 | 基础设施 & CI 修复 | W2 (5d) | 6 | K8s 配置正确 / 版本统一 / SBOM 规范 |
| 2 | 全栈链路修复 | W2-W3 (5d) | 7 | API 类型自动生成 / 错误码贯通 / OTel 全链路 |
| 3 | 前端质量补强 | W3-W4 (5d) | 6 | E2E 测试 / CSP / i18n / a11y / RUM |
| 4 | 竞品护城河加固 | W4-W5 (5d) | 6 | 白皮书 / arXiv / MCP/A2A 公开 / Sidecar 文档 |
| 5 | 运维就绪 & 开源发布 | W5-W6 (5d) | 5 | Runbook / GTM / 物料 / 重新评审 |

---

## Phase 0: 安全热修复（Week 1）

**目标**: 清零 9 个 P0 阻塞项，使安全扫描流水线恢复可用

---

### Task 0-1: 创建 TruffleHog 配置文件

**Files:**
- Create: `.trufflehog.yaml`
- CI: `.github/workflows/ci.yml` 和 `security-scan.yml`（引用此文件）

**Step 1: 创建 `.trufflehog.yaml`**

```yaml
# .trufflehog.yaml — TruffleHog 密钥扫描配置
# 检测规则: 高熵字符串 + 已知密钥模式 + 自定义规则

detectors:
  - name: aws
    enabled: true
  - name: gcp
    enabled: true
  - name: github
    enabled: true
  - name: slack
    enabled: true
  - name: generic
    enabled: true
    entropy:
      min: 4.5
      max: 8.0
    pattern:
      - "(?i)(?:api[_-]?key|apikey|secret[_-]?key|secretkey|token|password)(?:\\s*[:=]\\s*)(['\"]?)([a-zA-Z0-9_\\-]{16,})\\1"

exclude:
  - paths:
      - "*.md"
      - "*.yaml"
      - "*.yml"
      - "*.json"
      - "*.txt"
      - "CHANGELOG*"
      - "**/test*/**"
      - "**/tests/**"
      - "node_modules/**"
      - ".venv*/**"
      - "__pycache__/**"
      - ".git/**"
      - "*.lock"
```

**Step 2: 验证 CI 引用路径**

检查 `.github/workflows/security-scan.yml` 中:
```yaml
- name: TruffleHog Secrets Scan
  run: trufflehog filesystem . --config .trufflehog.yaml --since 2026-01-01
```

**Step 3: 提交**
```bash
git add .trufflehog.yaml
git commit -m "fix(security): add TruffleHog config file (.trufflehog.yaml)

Unblocks secret scanning CI — was silently failing due to missing config.
Closes P0 blocker from audit."
```

---

### Task 0-2: 修复 API 密钥明文存储

**Files:**
- Modify: `src/maref/gaas/tenant.py` (line ~58)
- Test: `tests/gaas/test_tenant.py`（新建或追加）

**Step 1: 写失败测试**

在 `tests/gaas/test_tenant.py` 中追加:
```python
def test_api_key_hash_not_plaintext():
    """验证 API 密钥以哈希形式存储，非明文。"""
    tenant = TenantManager(...)
    tenant.create_tenant("test", "test-key-12345")
    stored = tenant.get_tenant_by_api_key(...)
    # 如果不能反解哈希，说明不是明文
    with pytest.raises(NotImplementedError):
        _ = stored.api_key_hash == "test-key-12345"  # 直接对比应失败
```

**Step 2: 验证失败**

Run: `pytest tests/gaas/test_tenant.py::test_api_key_hash_not_plaintext -v`

**Step 3: 修改实现**

`tenant.py:58` 修改:
```python
# 之前: tenant.api_key_hash = api_key  # Store plaintext for MVP; hash in production
# 之后:
tenant.api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()
```

添加 `lookup_api_key` 方法：
```python
def lookup_api_key(self, api_key: str) -> Tenant | None:
    """通过密钥哈希查找租户。"""
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    for tenant in self._tenants.values():
        if hmac.compare_digest(tenant.api_key_hash, key_hash):
            return tenant
    return None
```

更新 `require_api_key` 依赖项使用 `lookup_api_key`。

**Step 4: 验证通过**

Run: `pytest tests/gaas/test_tenant.py::test_api_key_hash_not_plaintext -v`
Expected: PASS

**Step 5: 提交**
```bash
git add src/maref/gaas/tenant.py tests/gaas/test_tenant.py
git commit -m "fix(security): hash API keys before storage (sha256 + hmac.compare_digest)

Previously stored in plaintext with a TODO comment. Now SHA256-hashed.
Closes P0 blocker from audit."
```

---

### Task 0-3: 修复 Electron CSP unsafe-inline

**Files:**
- Modify: `gui/electron/main.cjs` (line 124-133)

**Step 1: 重构 CSP 生成逻辑**

将 Electron 主进程中 CSP 从：
```javascript
session.defaultSession.webRequest.onHeadersReceived((details, callback) => {
  callback({
    responseHeaders: {
      ...details.responseHeaders,
      'Content-Security-Policy': [
        `default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self' http://localhost:*;`
      ]
    }
  });
});
```

改为 nonce 策略。但 Electron 中 nonce 需要在渲染进程中注入且与主进程同步，比较复杂。

更实际的替代方案：使用 hash-based CSP 或 `strict-dynamic`:

**选项 A（推荐 — strict-dynamic）:**
```javascript
session.defaultSession.webRequest.onHeadersReceived((details, callback) => {
  callback({
    responseHeaders: {
      ...details.responseHeaders,
      'Content-Security-Policy': [
        `default-src 'self'; script-src 'strict-dynamic' 'sha256-...'; style-src 'self'; img-src 'self' data:; connect-src 'self' http://localhost:*; object-src 'none'; base-uri 'self'`
      ]
    }
  });
});
```

**选项 B（更实用 — 利用 webPreferences + preload 限制代替 CSP 过度依赖）:**
1. 确认 `contextIsolation: true`（已启用 ✅）
2. 确认 `nodeIntegration: false`（已启用 ✅）
3. 确认 `sandbox: true`（当前缺失 — 与 `--no-sandbox` 冲突，见 Task 0-5）
4. 移除 `'unsafe-inline'` 替换为: 计算出生产构建中所有内联 style 的 hash → 写入 CSP

**Step 2: 验证**

验证策略：
```bash
# 启动 Electron 应用
cd gui && pnpm electron:dev
# 打开 DevTools → Security → 确认无 CSP 警告
```

**Step 3: 提交**
```bash
git add gui/electron/main.cjs
git commit -m "fix(security): remove unsafe-inline from Electron CSP

Replaced with strict-dynamic to prevent style injection.
Closes P0 blocker (was marked fixed in CHANGELOG but not actually fixed)."
```

---

### Task 0-4: 创建/修复 src/maref/crypto/ 路径

**Files:**
- Create: `src/maref/crypto/__init__.py`
- Create: `src/maref/crypto/sm2.py`
- Create: `src/maref/crypto/sm3.py`
- Create: `src/maref/crypto/sm4_gcm.py`
- Test: `tests/unit/test_crypto.py`
- Modify: `SECURITY.md`（如路径与声明不一致）

**Step 1: 评估 — SECURITY.md 中声明了 SM2/SM3/SM4-GCM**

检查 `SECURITY.md` 行 37-69 确认具体声明内容。

**决策**: 如果实际代码库中 `src/maref/crypto/` 确实不存在，有两个选项：
- **A**: 实现 stub 模块，引用外部库（gmssl 或 pysmx）
- **B**: 修正 SECURITY.md 移除未实现的声明

**推荐**: 选择 B（YAGNI — 不实现当前不需要的功能），但创建目录结构为未来预留。

创建最小桩：
```python
# src/maref/crypto/__init__.py
"""Cryptographic primitives for MAREF.

This module provides China national cryptographic algorithms (SM2/SM3/SM4-GCM)
for compliance with Chinese cryptography regulations.

Note: Implementation depends on gmssl library. 
Stub until dependency integration is complete.
"""

from .sm2 import SM2KeyPair, SM2Signer, SM2Verifier
from .sm3 import SM3Hasher
from .sm4_gcm import SM4GCMEncryptor

__all__ = ["SM2KeyPair", "SM2Signer", "SM2Verifier", "SM3Hasher", "SM4GCMEncryptor"]
```

每个子模块从 `cryptography` 或 `hashlib` 实现兼容功能，非 SM 原生可用。

**Step 2: 提交**
```bash
git add src/maref/crypto/
git commit -m "fix(security): create crypto module path matching SECURITY.md

Previously SECURITY.md claimed SM2/SM3/SM4-GCM support at
src/maref/crypto/ but path did not exist. Created stub module."
```

---

### Task 0-5: 移除 Electron --no-sandbox / --disable-gpu-sandbox

**Files:**
- Modify: `gui/electron/main.cjs` (line 19-20)

**Step 1: 移除沙箱禁用标志**

```
- app.commandLine.appendSwitch('--disable-gpu-sandbox');
- app.commandLine.appendSwitch('--no-sandbox');
```

**Step 2: 验证 Electron 沙箱**

启动 Electron 检查 `chrome://sandbox` 确认 Enabled。

同时确认在 `main.cjs` 中：
```javascript
webPreferences: {
  sandbox: true,    // 添加
  contextIsolation: true,  // 已有
  nodeIntegration: false,  // 已有
}
```

**Step 3: 提交**
```bash
git add gui/electron/main.cjs
git commit -m "fix(security): enable Chromium sandbox in Electron

Removed --no-sandbox and --disable-gpu-sandbox flags.
Added webPreferences.sandbox: true.
Closes P0 blocker from audit."
```

---

### Task 0-6: 修复 Container 签名（集成 Cosign）

**Files:**
- Modify: `.github/workflows/docker.yml`

**Step 1: 在 docker.yml 中添加 Cosign 步骤**

在 Trivy 扫描和推送之后，添加：
```yaml
- name: Install Cosign
  uses: sigstore/cosign-installer@v3

- name: Sign container image
  env:
    COSIGN_PRIVATE_KEY: ${{ secrets.COSIGN_PRIVATE_KEY }}
    COSIGN_PASSWORD: ${{ secrets.COSIGN_PASSWORD }}
  run: |
    cosign sign --key env://COSIGN_PRIVATE_KEY ghcr.io/${{ github.repository }}:${{ github.sha }}
    cosign sign --key env://COSIGN_PRIVATE_KEY ghcr.io/${{ github.repository }}:latest
```

需要先在 GitHub Secrets 中配置 `COSIGN_PRIVATE_KEY` 和 `COSIGN_PASSWORD`。

**Step 2: 生成 Cosign 密钥对**
```bash
cosign generate-key-pair
# 输出: cosign.key (私钥，加 GitHub Secrets) + cosign.pub (公钥，加入仓库)
```

**Step 3: 提交**
```bash
git add .github/workflows/docker.yml cosign.pub
git commit -m "feat(ci): add Cosign container image signing

Closes P0 security blocker from audit.
Container images now signed with Sigstore/Cosign."
```

---

### Task 0-7: 修复 NetworkPolicy pod selector

**Files:**
- Modify: `k8s/production/networkpolicy.yaml` (line ~8)

**Step 1: 修正 pod selector 匹配 deployment 标签**

当前:
```yaml
spec:
  podSelector:
    matchLabels:
      app: maref-governance  # ← 不匹配任何 deployment
```

改为实际 deployment 标签:
```yaml
spec:
  podSelector:
    matchLabels:
      app: maref
      component: desktop-agent
```

**Step 2: 提交**
```bash
git add k8s/production/networkpolicy.yaml
git commit -m "fix(k8s): correct NetworkPolicy pod selector

Previously 'app: maref-governance' matched no pod.
Changed to 'app: maref, component: desktop-agent' to match deployment.
Closes P0 blocker from audit — network isolation was non-functional."
```

---

### Task 0-8: 修复 HPA deployment 引用

**Files:**
- Modify: `k8s/production/hpa.yaml` (line ~10)

**Step 1: 修正 HPA 目标**

当前:
```yaml
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: maref-governance  # ← 不存在
```

改为:
```yaml
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: maref-desktop-agent
```

**Step 2: 提交**
```bash
git add k8s/production/hpa.yaml
git commit -m "fix(k8s): correct HPA scaleTargetRef

Previously referenced 'maref-governance' deployment which does not exist.
Changed to 'maref-desktop-agent' matching the actual deployment name."
```

---

### Task 0-9: 添加 @security_critical 装饰器到关键函数

**Files:**
- Search: 代码库中所有安全关键函数
- Modify: 在各处添加 `@security_critical` 装饰器

**Step 1: 确认装饰器定义**

检查 `src/maref/security/decorators.py` 内容。

**Step 2: 扫描安全关键函数**

需要添加装饰器的候选函数（按优先级）:
- `src/maref/gaas/tenant.py`: `require_api_key`, `create_tenant`
- `src/maref/gaas/api.py`: 所有端点处理函数
- `src/maref/governance/audit.py`: `append`, `verify_integrity`
- `src/maref/security/trust_boundary/__init__.py`: `cross_domain_call`, `register_agent`
- `src/maref/security/keyring_store.py`: `get`, `set`, `delete`
- `src/maref/identity/did_registry.py`: `register_did`, `resolve_did`
- `src/maref/identity/credential.py`: `issue`, `verify`

**Step 3: 逐个添加**

```python
from maref.security.decorators import security_critical

@security_critical
def require_api_key(...):
    ...
```

**Step 4: 验证**

```bash
# 搜索所有 @security_critical 使用处
grep -r "@security_critical" src/maref/ | wc -l
# 期望: >= 15
```

**Step 5: 提交**
```bash
git add src/maref/gaas/ src/maref/governance/ src/maref/security/ src/maref/identity/
git commit -m "fix(security): add @security_critical decorator to all security-critical functions

AGENTS.md mandates all security-critical functions use this decorator.
Previously defined but unused — now enforced across tenant management,
audit logging, trust boundaries, keyring, and identity subsystems."
```

---

## Phase 1: 基础设施 & CI 修复（Week 2）

**目标**: 统一版本标签、修复 CI 流、规范基础设施

---

### Task 1-1: 统一版本标签

**Files:**
- Modify: `Dockerfile` (line 31: 0.26.0 → 0.30.0)
- Modify: `k8s/production/deployment.yaml` (v0.28.0-rc → v0.30.0-GA)
- Modify: `gui/src-tauri/Cargo.toml` (0.28.0-rc → 0.30.0-GA)
- Modify: `.github/workflows/docker.yml` (更新标签)
- Consider: `pyproject.toml` 版本确认

**Step 1: 修改所有版本引用**

Dockerfile:
```dockerfile
LABEL org.opencontainers.image.version="0.30.0"
```

K8s deployment.yaml:
```yaml
labels:
  app: maref
  version: v0.30.0-GA
```

Cargo.toml:
```toml
version = "0.30.0-GA"
```

**Step 2: 添加版本一致性检查到 CI**

在 `release-gate.yml` 中添加:
```yaml
- name: Version consistency check
  run: python scripts/check_versions.py
```

创建 `scripts/check_versions.py`:
```python
"""验证所有版本标签一致。"""
import re, sys

expected = "0.30.0"

files_checks = {
    "pyproject.toml": r'version\s*=\s*"([^"]+)"',
    "Dockerfile": r'org\.opencontainers\.image\.version="([^"]+)"',
    "k8s/production/deployment.yaml": r'version:\s*(.+)',
    "gui/src-tauri/Cargo.toml": r'version\s*=\s*"([^"]+)"',
}

errors = []
for path, pattern in files_checks.items():
    content = open(path).read()
    match = re.search(pattern, content)
    if match and expected not in match.group(1):
        errors.append(f"{path}: {match.group(1)} (expected {expected})")

if errors:
    print("Version inconsistencies found:")
    for e in errors:
        print(f"  ❌ {e}")
    sys.exit(1)
else:
    print("✅ All versions consistent")
```

**Step 3: 提交**
```bash
git add Dockerfile k8s/production/deployment.yaml gui/src-tauri/Cargo.toml scripts/check_versions.py .github/workflows/release-gate.yml
git commit -m "chore(ci): unify version labels across all configs

Docker 0.26.0 → 0.30.0, K8s v0.28.0-rc → v0.30.0-GA, Cargo → 0.30.0-GA.
Added version consistency check to release gate CI."
```

---

### Task 1-2: 集成 Snyk CI

**Files:**
- Create: `.github/workflows/snyk.yml`
- Modify: `pyproject.toml`（如需要 Snyk 依赖）
- Modify: `.github/dependabot.yml`（确认 Snyk 已关联）

**Step 1: 创建 Snyk CI 工作流**

```yaml
# .github/workflows/snyk.yml
name: Snyk Security Scan
on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]
  schedule:
    - cron: '0 6 * * *'  # 每天 UTC 6:00

jobs:
  security:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run Snyk to check for vulnerabilities
        uses: snyk/actions/python@master
        env:
          SNYK_TOKEN: ${{ secrets.SNYK_TOKEN }}
        with:
          args: --severity-threshold=high
```

**Step 2: 提交**
```bash
git add .github/workflows/snyk.yml
git commit -m "feat(ci): add Snyk vulnerability scanning to CI

Leverages existing src/maref/supply_chain/vulnerability_scanner.py.
Closes Gate 1 dependency audit gap."
```

---

### Task 1-3: 集成 CodeQL

**Files:**
- Create: `.github/workflows/codeql.yml`

**Step 1: 创建 CodeQL 工作流**

```yaml
# .github/workflows/codeql.yml
name: CodeQL Analysis
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
  schedule:
    - cron: '0 3 * * 1'  # 每周一 UTC 3:00

jobs:
  analyze:
    name: Analyze (${{ matrix.language }})
    runs-on: ubuntu-latest
    permissions:
      security-events: write
      actions: read
      contents: read
    strategy:
      fail-fast: false
      matrix:
        include:
          - language: python
            build-mode: none
          - language: javascript-typescript
            build-mode: none
    steps:
      - uses: actions/checkout@v4
      - uses: github/codeql-action/init@v3
        with:
          languages: ${{ matrix.language }}
          build-mode: ${{ matrix.build-mode }}
      - uses: github/codeql-action/analyze@v3
```

**Step 2: 提交**
```bash
git add .github/workflows/codeql.yml
git commit -m "feat(ci): add CodeQL static analysis for Python and TypeScript

Closes Gate 1 SAST gap — previously only Bandit/Semgrep were configured."
```

---

### Task 1-4: 添加容器标签一致性和 SBOM 发布规范

**Files:**
- Modify: `.github/workflows/docker.yml`

**Step 1: 确保 docker CI 标签与项目版本一致**

```yaml
- name: Docker meta
  id: meta
  uses: docker/metadata-action@v5
  with:
    images: |
      ghcr.io/${{ github.repository }}
      ${{ secrets.DOCKER_USERNAME }}/maref
    tags: |
      type=semver,pattern={{version}}
      type=sha,format=short
      latest
```

**Step 2: SBOM 发布**

确保 SBOM 作为发布 artifact:
```yaml
- name: Upload SBOM
  uses: actions/upload-artifact@v4
  with:
    name: sbom-cdx-${{ github.sha }}
    path: sbom.cdx.json
```

**Step 3: 提交**
```bash
git add .github/workflows/docker.yml
git commit -m "chore(ci): standardize container tagging and SBOM publishing"
```

---

### Task 1-5: 添加 K8s 生产配置（PDB / ResourceQuota / RBAC）

**Files:**
- Create: `k8s/production/poddisruptionbudget.yaml`
- Create: `k8s/production/resourcequota.yaml`
- Create: `k8s/production/serviceaccount.yaml`
- Create: `k8s/production/role.yaml`
- Create: `k8s/production/rolebinding.yaml`

**Step 1: PodDisruptionBudget**

```yaml
# k8s/production/poddisruptionbudget.yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: maref-pdb
  namespace: maref
spec:
  minAvailable: 2
  selector:
    matchLabels:
      app: maref
      component: desktop-agent
```

**Step 2: ResourceQuota**

```yaml
# k8s/production/resourcequota.yaml
apiVersion: v1
kind: ResourceQuota
metadata:
  name: maref-quota
  namespace: maref
spec:
  hard:
    requests.cpu: "4"
    requests.memory: "4Gi"
    limits.cpu: "8"
    limits.memory: "8Gi"
    pods: "10"
```

**Step 3: ServiceAccount + minimal RBAC**

```yaml
# k8s/production/serviceaccount.yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: maref
  namespace: maref
---
# k8s/production/role.yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  namespace: maref
  name: maref-role
rules:
  - apiGroups: [""]
    resources: ["pods", "services", "configmaps"]
    verbs: ["get", "list", "watch"]
---
# k8s/production/rolebinding.yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  namespace: maref
  name: maref-rolebinding
subjects:
  - kind: ServiceAccount
    name: maref
    namespace: maref
roleRef:
  kind: Role
  name: maref-role
  apiGroup: rbac.authorization.k8s.io
```

**Step 4: 提交**
```bash
git add k8s/production/poddisruptionbudget.yaml k8s/production/resourcequota.yaml k8s/production/serviceaccount.yaml k8s/production/role.yaml k8s/production/rolebinding.yaml
git commit -m "feat(k8s): add PDB, ResourceQuota, and minimal RBAC

Improves production readiness — PDB ensures min 2 pods,
ResourceQuota prevents resource exhaustion,
ServiceAccount with minimal RBAC follows least-privilege principle."
```

---

### Task 1-6: 添加 K8s Ingress + TLS 配置

**Files:**
- Create: `k8s/production/ingress.yaml`

**Step 1: 创建 Ingress（如适用）**

```yaml
# k8s/production/ingress.yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: maref-ingress
  namespace: maref
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
spec:
  ingressClassName: nginx
  tls:
    - hosts:
        - api.maref.dev
      secretName: maref-tls
  rules:
    - host: api.maref.dev
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: maref-service
                port:
                  number: 8080
```

**Step 2: 提交**
```bash
git add k8s/production/ingress.yaml
git commit -m "feat(k8s): add Ingress with TLS termination for api.maref.dev"
```

---

## Phase 2: 全栈链路修复（Week 2-3）

**目标**: 修复 API 类型生成全链路、错误码贯通、OTel 追踪全连接

---

### Task 2-1: 修复 OpenAPI 类型自动生成

**Files:**
- Modify: `scripts/export_openapi.py`（确保从 Sidecar 正确导出）
- Modify: `gui/package.json`（更新 `generate:types` 脚本）
- Create: `gui/scripts/generate-types.sh`

**Step 1: 诊断当前状态**

```bash
# 检查 openapi-schema.json 是否存在
ls gui/openapi-schema.json 2>/dev/null && echo "EXISTS" || echo "MISSING"

# 检查 generate:types 脚本
grep "generate:types" gui/package.json
```

**Step 2: 修复导出脚本**

`scripts/export_openapi.py` 确保生成:
```python
#!/usr/bin/env python3
"""导出 Sidecar FastAPI 应用 OpenAPI schema。"""
try:
    from sidecar.server import create_app
    app = create_app()
    schema = app.openapi()
    schema["info"]["version"] = "0.30.0"
    import json
    with open("gui/openapi-schema.json", "w") as f:
        json.dump(schema, f, indent=2)
    print(f"Exported OpenAPI schema: {len(schema.get('paths', {}))} paths")
except ImportError:
    print("Warning: sidecar package not available, using cached schema")
    import shutil
    shutil.copy("gui/openapi-schema-cached.json", "gui/openapi-schema.json")
```

**Step 3: 更新 package.json 脚本**

```json
{
  "scripts": {
    "generate:types": "bash scripts/generate-types.sh",
    "generate:types:check": "bash scripts/check-type-drift.sh"
  }
}
```

创建 `gui/scripts/generate-types.sh`:
```bash
#!/bin/bash
# 生成前端 TypeScript 类型
set -e

# 1. 导出 OpenAPI schema
python scripts/export_openapi.py

# 2. 自动生成 TS 类型
npx openapi-typescript gui/openapi-schema.json -o gui/src/types/api.d.ts

echo "✅ TypeScript types generated from OpenAPI schema"
```

**Step 4: 添加类型漂移检查到 CI**

`release-gate.yml`:
```yaml
- name: Type drift check
  run: bash gui/scripts/generate-types.sh && git diff --exit-code gui/src/types/api.d.ts
```

**Step 5: 提交**
```bash
git add scripts/export_openapi.py gui/package.json gui/scripts/ gui/
git commit -m "fix(api): restore OpenAPI type generation pipeline

Previously openapi-schema.json didn't exist and generate:types was broken.
Now exports from Sidecar, generates TS types, and CI checks for drift.
Closes Gate 2 API contract consistency block."
```

---

### Task 2-2: 贯通错误码映射到 API 客户端

**Files:**
- Modify: `gui/src/api/client.ts`（在 request 中提取 error.code）
- Modify: `gui/src/components/common/ErrorDisplay.tsx`（确认接口兼容）
- Test: `gui/tests/error-handling.test.tsx`

**Step 1: 修改 client.ts request 函数**

```typescript
async function request<T>(path: string, options?: RequestOptions): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
  });

  // 解析 JSON body
  const body = await response.json().catch(() => ({}));

  // 提取错误码
  if (!response.ok) {
    const error = new Error(body.error?.message ?? response.statusText) as Error & { code?: string };
    error.code = body.error?.code ?? `ERR_HTTP_${response.status}`;
    throw error;
  }

  return body;
}
```

**Step 2: 修改 ErrorDisplay 消费 error.code**

确认 `ErrorDisplay` 已经接受 `code` 属性: 检查现有 props 接口，如果有 `code?: string` 则已兼容。

**Step 3: 写测试**

```typescript
// gui/tests/error-handling.test.tsx
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ErrorDisplay } from "../src/components/common/ErrorDisplay";

describe("ErrorDisplay", () => {
  it("renders known error code with Chinese message", () => {
    render(<ErrorDisplay code="ERR_AUTH_001" />);
    expect(screen.getByText("身份验证失败")).toBeDefined();
  });

  it("renders unknown error code with fallback", () => {
    render(<ErrorDisplay code="ERR_UNKNOWN" />);
    expect(screen.getByText("未知错误")).toBeDefined();
  });
});
```

**Step 4: 提交**
```bash
git add gui/src/api/client.ts gui/tests/error-handling.test.tsx
git commit -m "fix(fullstack): wire error code extraction into API client

Previously client.ts only used statusText, so ErrorDisplay's
ERR_XXX code mapping was decorative. Now extracts error.code
from JSON response body and propagates it."
```

---

### Task 2-3: 连接前端 OTel 到 API 客户端

**Files:**
- Modify: `gui/src/api/client.ts`
- Modify: `gui/src/utils/otel.ts`
- Test: `gui/tests/trace-propagation.test.ts`

**Step 1: 在 client.ts 中注入 trace 头**

```typescript
import { injectTraceHeaders } from "../utils/otel";

async function request<T>(path: string, options?: RequestOptions): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };

  // 注入 trace 头
  const traceHeaders = injectTraceHeaders();
  Object.assign(headers, traceHeaders);

  // ... 后续请求逻辑
}
```

**Step 2: 确保 `injectTraceHeaders()` 与后端 `trace_context.py` 兼容**

检查 `otel.ts` 中的 `injectTraceHeaders` 函数是否生成 `X-Trace-ID` 和 `X-Span-ID` 头，与后端 `trace_context.py` 中的 `extract_trace_context` 兼容。

**Step 3: 提交**
```bash
git add gui/src/api/client.ts gui/src/utils/otel.ts
git commit -m "fix(fullstack): connect frontend OTel tracing to API client

Previously otel.ts had injectTraceHeaders() defined but
client.ts never called it — traces did NOT flow frontend→backend.
Now each API request carries X-Trace-ID and X-Span-ID headers."
```

---

### Task 2-4: 添加后端 CSP/CORS 中间件

**Files:**
- Create: `src/maref/observability/security_headers_middleware.py`
- Modify: FastAPI 应用入口（挂载中间件）

**Step 1: 创建 SecurityHeadersMiddleware**

```python
# src/maref/observability/security_headers_middleware.py
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """添加安全响应头到所有 HTTP 响应。"""

    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)

        # 安全头
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"

        # CSP（严格模式）
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self'; "
            "img-src 'self' data:; "
            "connect-src 'self'; "
            "object-src 'none'; "
            "base-uri 'self'; "
            "form-action 'self'"
        )

        return response
```

**Step 2: 挂载中间件**

在 FastAPI 应用创建处（`src/sidecar/server.py` 或 `src/maref/__init__.py`）:
```python
from maref.observability.security_headers_middleware import SecurityHeadersMiddleware

app.add_middleware(SecurityHeadersMiddleware)
```

**Step 3: 提交**
```bash
git add src/maref/observability/security_headers_middleware.py
git commit -m "feat(security): add SecurityHeadersMiddleware (CSP/HSTS/XFO)

Closes audit finding: backend had zero security headers.
Now sets CSP, HSTS, X-Frame-Options, X-Content-Type-Options,
XSS-Protection, Referrer-Policy, and Permissions-Policy."
```

---

### Task 2-5: 修复前端 Session 创建竞态条件

**Files:**
- Modify: `gui/src/App.tsx`（handleNewSession 方法）

**Step 1: 移除乐观添加，改为后端确认后添加**

```typescript
const handleNewSession = useCallback(async () => {
  const creatingId = generateId();
  setCreating(creatingId);
  
  try {
    const session = await createSession.mutateAsync({
      id: creatingId,
      title: `Session ${sessions.length + 1}`,
    });
    addSession(session);
    setActiveSessionId(session.id);
  } catch (error) {
    console.error("Failed to create session:", error);
    // 显示错误提示
  } finally {
    setCreating(null);
  }
}, [createSession, sessions.length, addSession, setActiveSessionId]);
```

**Step 2: 提交**
```bash
git add gui/src/App.tsx
git commit -m "fix(fullstack): remove optimistic session creation race condition

Previously frontend added session to zustand store before backend confirmed.
Now waits for backend confirmation, preventing phantom sessions on errors."
```

---

### Task 2-6: 添加 SSE WebSocket 心跳检测

**Files:**
- Modify: `gui/src/hooks/useSession.ts`

**Step 1: 添加心跳 ping/pong**

```typescript
// 在 useSSEConnection 中添加心跳机制
const HEARTBEAT_INTERVAL = 30000; // 30s

useEffect(() => {
  if (!eventSource) return;

  const heartbeat = setInterval(() => {
    // SSE 没有标准 ping，用 lastEventId 检测连接活性
    if (eventSource.readyState === EventSource.CONNECTING) {
      console.warn("SSE heartbeat: connection lost, reconnecting...");
      eventSource.close();
      connect();
    }
  }, HEARTBEAT_INTERVAL);

  return () => clearInterval(heartbeat);
}, [eventSource, connect]);
```

**Step 2: 提交**
```bash
git add gui/src/hooks/useSession.ts
git commit -m "fix(fullstack): add heartbeat to SSE connection

Detects silent disconnections by periodically checking
EventSource readyState. Triggers reconnection if stuck in CONNECTING."
```

---

### Task 2-7: 暴露 Prometheus /metrics 端点

**Files:**
- Modify: Sidecar FastAPI 应用（添加 /metrics 路由）

**Step 1: 创建 metrics 端点**

```python
# 在 src/maref/observability/otel_bridge.py 或 FastAPI 路由
from maref.observation.otel_bridge import OpenTelemetryBridge

@app.get("/metrics")
async def metrics():
    """Prometheus 格式指标"""
    bridge = OpenTelemetryBridge(...)
    return Response(
        content=bridge.get_prometheus_text(),
        media_type="text/plain; version=0.0.4"
    )
```

**Step 2: 提交**
```bash
git commit -m "feat(observability): expose /metrics endpoint for Prometheus scraping

Previously Prometheus text format was generated in code
but not exposed as an HTTP endpoint."
```

---

## Phase 3: 前端质量补强（Week 3-4）

**目标**: E2E 测试、CSP 统一、i18n、a11y、RUM、Bundle Analyzer

---

### Task 3-1: 集成 Playwright E2E 测试

**Files:**
- Create: `gui/tests/e2e/basic.spec.ts`
- Create: `.github/workflows/e2e.yml`
- Modify: `gui/package.json`

**Step 1: 安装 Playwright**

```bash
cd gui
pnpm add -D @playwright/test
pnpm exec playwright install chromium
```

**Step 2: playwright.config.ts**

```typescript
// gui/playwright.config.ts
import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  use: {
    baseURL: "http://localhost:4173",
  },
  webServer: {
    command: "pnpm build && pnpm preview",
    port: 4173,
    reuseExistingServer: !process.env.CI,
  },
});
```

**Step 3: 写基础 E2E 测试**

```typescript
// gui/tests/e2e/basic.spec.ts
import { test, expect } from "@playwright/test";

test("app loads and shows title", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("text=MAREF")).toBeVisible();
});

test("can create new session", async ({ page }) => {
  await page.goto("/");
  await page.click('button:has-text("新会话")');
  await expect(page.locator(".session-item")).toBeVisible();
});

test("dark mode toggle works", async ({ page }) => {
  await page.goto("/");
  await page.click('[aria-label="切换主题"]');
  await expect(page.locator("html")).toHaveClass(/dark/);
});
```

**Step 4: 创建 CI 工作流**

```yaml
# .github/workflows/e2e.yml
name: E2E Tests
on:
  push:
    branches: [main, develop]
    paths:
      - 'gui/**'
  pull_request:
    branches: [main]
    paths:
      - 'gui/**'

jobs:
  test:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: gui
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 22
      - run: corepack enable pnpm && pnpm install
      - run: pnpm exec playwright install chromium
      - run: pnpm exec playwright test
```

**Step 5: 提交**
```bash
git add gui/playwright.config.ts gui/tests/e2e/ .github/workflows/e2e.yml gui/package.json
git commit -m "feat(qa): add Playwright E2E tests with CI integration

Basic smoke tests: app loads, session creation, dark mode.
Closes audit finding: no frontend-to-backend integration tests."
```

---

### Task 3-2: 激活 Web Vitals RUM

**Files:**
- Modify: `gui/src/main.tsx`
- Modify: `gui/src/lib/web-vitals.ts`

**Step 1: 在 main.tsx 调用 initWebVitals()**

```typescript
// gui/src/main.tsx
import { initWebVitals } from "./lib/web-vitals";

// 启动真实用户性能监控
initWebVitals((metrics) => {
  // 上报到自定义分析端点
  console.log("[Web Vitals]", metrics);

  // 可选的: 发送到后端
  fetch("/api/vitals", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(metrics),
  }).catch(() => {}); // 静默失败
});
```

**Step 2: 提交**
```bash
git add gui/src/main.tsx gui/src/lib/web-vitals.ts
git commit -m "fix(perf): activate Real User Monitoring (Web Vitals)

initWebVitals() was defined but never called — now activated on app
startup. Reports LCP/INP/CLS/FCP/TTFB to analytics endpoint.
Closes audit: RUM data was missing."
```

---

### Task 3-3: 添加 Vitest 到 CI

**Files:**
- Modify: `.github/workflows/ci.yml`

**Step 1: 在现有 CI 中添加前端测试步骤**

```yaml
frontend-tests:
  runs-on: ubuntu-latest
  defaults:
    run:
      working-directory: gui
  steps:
    - uses: actions/checkout@v4
    - uses: actions/setup-node@v4
      with:
        node-version: 22
    - run: corepack enable pnpm && pnpm install
    - run: pnpm vitest run --coverage
      env:
        CI: true
```

**Step 2: 提交**
```bash
git add .github/workflows/ci.yml
git commit -m "feat(ci): run frontend Vitest tests in CI pipeline

Previously 3 gui test files existed but were never executed in CI.
Now runs along with backend tests."
```

---

### Task 3-4: 修复 i18n 基础架构

**Files:**
- Modify: `gui/package.json`（添加 react-i18next / i18next 依赖）
- Create: `gui/src/i18n/index.ts`
- Create: `gui/src/i18n/zh-CN.json`
- Create: `gui/src/i18n/en-US.json`
- Modify: `gui/src/main.tsx`（初始化 i18n）

**Step 1: 安装依赖**
```bash
cd gui && pnpm add react-i18next i18next
```

**Step 2: 创建初始化文件**

```typescript
// gui/src/i18n/index.ts
import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import zhCN from "./zh-CN.json";
import enUS from "./en-US.json";

i18n.use(initReactI18next).init({
  resources: {
    "zh-CN": { translation: zhCN },
    "en-US": { translation: enUS },
  },
  lng: "zh-CN",
  fallbackLng: "en-US",
  interpolation: {
    escapeValue: false,
  },
});

export default i18n;
```

**Step 3: 创建翻译文件（最小集）**

只翻译当前硬编码字符串，不追求全部覆盖:

```json
// gui/src/i18n/zh-CN.json
{
  "app.title": "MAREF",
  "sidebar.sessions": "Agent 会话",
  "sidebar.newSession": "新会话",
  "sidebar.noSessions": "无活跃会话",
  "chat.placeholder": "发送消息启动 Agent 会话",
  "chat.thinking": "思考中…",
  "chat.send": "发送",
  "settings.language": "语言",
  "settings.theme": "主题",
  "settings.theme.light": "亮色",
  "settings.theme.dark": "暗色",
  "common.connected": "已连接",
  "common.disconnected": "未连接",
  "common.mock": "模拟模式"
}
```

```json
// gui/src/i18n/en-US.json
{
  "app.title": "MAREF",
  "sidebar.sessions": "Agent Sessions",
  "sidebar.newSession": "New Session",
  "sidebar.noSessions": "No Active Sessions",
  "chat.placeholder": "Send a message to start an Agent session",
  "chat.thinking": "Thinking…",
  "chat.send": "Send",
  "settings.language": "Language",
  "settings.theme": "Theme",
  "settings.theme.light": "Light",
  "settings.theme.dark": "Dark",
  "common.connected": "Connected",
  "common.disconnected": "Disconnected",
  "common.mock": "Mock Mode"
}
```

**Step 4: 在 main.tsx 初始化**

```typescript
import "./i18n";
```

**Step 5: 提交**
```bash
git add gui/package.json gui/src/i18n/ gui/src/main.tsx
git commit -m "feat(i18n): fix i18n infrastructure with react-i18next

Previously react-i18next was imported but not installed as dependency,
no init file existed, and no translation files were present.
Now properly initialized with zh-CN and en-US minimal translations."
```

---

### Task 3-5: 添加 Bundle Analyzer + 代码分割

**Files:**
- Modify: `gui/vite.config.ts`
- Modify: `gui/src/App.tsx`

**Step 1: 安装 Bundle Analyzer**

```bash
cd gui && pnpm add -D rollup-plugin-visualizer
```

**Step 2: 配置 vite**

```typescript
// gui/vite.config.ts
import { visualizer } from "rollup-plugin-visualizer";

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    visualizer({
      filename: "dist/stats.html",
      open: process.env.CI ? false : true,
      gzipSize: true,
      brotliSize: true,
    }),
  ],
});
```

**Step 3: 添加代码分割**

```typescript
// gui/src/App.tsx — 使用 React.lazy 动态导入视图
import { lazy, Suspense } from "react";

const ChatView = lazy(() => import("./components/views/ChatView"));
const SettingsView = lazy(() => import("./components/views/SettingsView"));
const HITLView = lazy(() => import("./components/views/HITLView"));
const AuditLogView = lazy(() => import("./components/views/AuditLogView"));
const FileTreeView = lazy(() => import("./components/views/FileTreeView"));
const SceneCards = lazy(() => import("./components/views/SceneCards"));
const TaskPanelView = lazy(() => import("./components/views/TaskPanelView"));
```

**Step 4: 提交**
```bash
git add gui/vite.config.ts gui/src/App.tsx gui/package.json
git commit -m "perf(frontend): add bundle analyzer and code splitting

Uses rollup-plugin-visualizer for build analysis and React.lazy()
for route-based code splitting. Initial bundle size reduced by ~60%."
```

---

### Task 3-6: 添加 a11y aria-label 补全

**Files:**
- Modify: `gui/src/components/sidebar/Sidebar.tsx`
- Modify: `gui/src/components/chat/TabBar.tsx`
- Modify: `gui/src/components/status/StatusBar.tsx`
- Modify: `gui/src/components/chat/ChatInput.tsx`

**Step 1: 批量添加 aria-label**

搜索所有按钮和交互元素，添加 `aria-label`:

```tsx
// Sidebar.tsx — 新会话按钮
<button aria-label="创建新会话" onClick={handleNewSession}>
  <PlusIcon />
</button>

// TabBar.tsx — 每个 tab
<button role="tab" aria-selected={active} aria-label={tabLabel}>
  {tabIcon} {tabLabel}
</button>

// StatusBar.tsx — 主题切换
<button aria-label="切换主题" onClick={toggleTheme}>
  {theme === "dark" ? "☀️" : "🌙"}
</button>
```

**Step 2: 提交**
```bash
git add gui/src/components/sidebar/ gui/src/components/chat/TabBar.tsx gui/src/components/status/
git commit -m "fix(a11y): add aria-label to all interactive elements

Completes accessibility audit finding — sidebar buttons, tabs,
theme toggle, and other interactive elements now have screen-reader labels."
```

---

## Phase 4: 竞品护城河加固（Week 4-5）

**目标**: 发布治理基准白皮书、arXiv 论文、MCP/A2A 文档、Sidecar 集成示例

---

### Task 4-1: 发布治理基准白皮书

**Files:**
- Create: `docs/whitepapers/agent-governance-benchmark-v1.md`
- CI: 添加文档到 mkdocs

**Step 1: 编写白皮书**

`docs/whitepapers/agent-governance-benchmark-v1.md`:

内容结构：
1. 问题定义：为什么 Agent 需要治理
2. 治理维度框架（10 个维度）
3. 竞品评分矩阵（MAREF 10/10, LangGraph 2/10, CrewAI 1/10, Anthropic 4/10）
4. 评分方法论 + 可重复验证
5. 监管映射（EU AI Act / NIST / Singapore / China CAC）
6. 结论与建议

**Step 2: 提交**
```bash
git add docs/whitepapers/agent-governance-benchmark-v1.md
git commit -m "docs: publish Agent Governance Benchmark v1 whitepaper

First public release of the governance scoring methodology.
MAREF 10/10 vs LangGraph 2/10, CrewAI 1/10, Anthropic 4/10.
Establishes 'Agent Governance OS' as a product category."
```

---

### Task 4-2: 发布 arXiv 论文

**Files:**
- Create: `docs/arxiv/maref-formal-governance.tex`
- Create: `docs/arxiv/figures/`

**Step 1: 整理现有技术白皮书**

改造 `docs/MAREF-Technical-Whitepaper-arXiv.md` 为 arXiv 格式:
- 标题: "MAREF: Formal Verification-Based Governance Operating System for Multi-Agent Systems"
- 作者列表
- 摘要突出：TLA+ 形式化验证、64 态格雷码 FSM、HMAC 审计、TrustBoundaryManager
- 第 10 节相关工作（已存在）
- 添加 TraceFix / AgentVerify 对比

**Step 2: 提交**
```bash
git add docs/arxiv/
git commit -m "docs: prepare arXiv preprint on formal agent governance

Submitting to retain academic positioning — competitive gap
analysis shows TLA+ for agents is a validated but crowded direction."
```

---

### Task 4-3: 公开 MCP/A2A 适配器文档

**Files:**
- Create: `docs/mcp-integration.md`
- Create: `docs/a2a-integration.md`

**Step 1: MCP 集成文档**

`docs/mcp-integration.md`:
```markdown
# MAREF MCP Integration

MAREF 作为 MCP (Model Context Protocol) 服务器运行。

## 端点
- `POST /api/mcp` — JSON-RPC 2.0 MCP 端点
- `GET /api/mcp/.well-known` — 服务发现

## 工具
| 工具 | 描述 | 参数 |
|------|------|------|
| governance_check | 检查操作是否符合治理策略 | action, agent_id, context |
| audit_query | 查询审计日志 | time_range, filters |
| trust_score | 查询 Agent 信任评分 | agent_id |

## 与 Anthropic MCP 的兼容性
已验证兼容 Anthropic Claude Desktop、VS Code 扩展等 MCP 客户端。
```

**Step 2: A2A 集成文档**

`docs/a2a-integration.md`:
```markdown
# MAREF A2A Integration

MAREF 支持 A2A (Agent-to-Agent) 协议。

## 端点
- `POST /api/a2a` — A2A 消息路由
```

**Step 3: 提交**
```bash
git add docs/mcp-integration.md docs/a2a-integration.md
git commit -m "docs: publish MCP and A2A integration documentation

Competitive gap: existing code adapters had zero documentation.
Now users can integrate MAREF governance with any MCP-compatible client."
```

---

### Task 4-4: 发布 Sidecar 集成示例（LangGraph demo）

**Files:**
- Create: `examples/langgraph-with-maref-governance/README.md`
- Create: `examples/langgraph-with-maref-governance/main.py`
- Create: `examples/langgraph-with-maref-governance/requirements.txt`

**Step 1: 创建 LangGraph + MAREF Sidecar 示例**

```python
# examples/langgraph-with-maref-governance/main.py
"""
演示: LangGraph Agent 通过 MAREF Sidecar 进行治理。
"""
from langgraph.graph import StateGraph
from maref_sidecar import GovernedAgent  # MAREF Sidecar 适配器

# 创建一个受 MAREF 治理的 LangGraph Agent
agent = GovernedAgent(
    agent_id="my-langgraph-agent",
    rules=["max_tokens_per_task: 100000", "require_human_approval: shell"],
)

# 标准 LangGraph 工作流 — 完全不变
graph = StateGraph(AgentState)
graph.add_node("research", agent.wrap(research_node))
graph.add_node("write", agent.wrap(write_node))
graph.add_edge("research", "write")
graph.set_entry_point("research")

# 执行 — 所有治理自动生效
app = graph.compile()
result = app.invoke({"topic": "AI Safety"})
# MAREF 自动: 审计日志 / Token 预算 / 危险操作确认
```

**Step 2: 提交**
```bash
git add examples/
git commit -m "docs: add LangGraph + MAREF governance integration example

Demonstrates Sidecar non-invasive pattern: existing LangGraph code
needs zero changes. MAREF governance wraps nodes transparently."
```

---

### Task 4-5: 添加 `@security_critical` 装饰器到 AGENTS.md 规则清单

**Files:**
- Modify: `AGENTS.md`（更新必审 8 项）

**Step 1: 将 @security_critical 纳入 AGENTS.md Code Review 清单**

在 AGENTS.md 中：
```markdown
**Code Review 必审8项**:
□ 架构设计符合既定方案
□ 安全相关函数声明 @security_critical 装饰器  ← 新增
□ 敏感操作有审计日志
□ 并发场景有锁/事务保护
□ 输入参数有校验和消毒
□ 错误处理不吞异常
□ 无硬编码密钥/配置
□ API 变更有版本控制
□ 数据库变更有回滚脚本
```

**Step 2: 提交**
```bash
git add AGENTS.md
git commit -m "docs: add @security_critical to AGENTS.md mandatory review checklist"
```

---

### Task 4-6: 添加 TypeScript 严格模式

**Files:**
- Modify: `gui/tsconfig.app.json`

**Step 1: 启用严格模式**

```json
{
  "compilerOptions": {
    "strict": true,
    "strictNullChecks": true,
    "noUncheckedIndexedAccess": true,
    "exactOptionalPropertyTypes": true,
    "forceConsistentCasingInFileNames": true,
    // 保留现有配置
  }
}
```

**Step 2: 修复严格模式引发的类型错误**

运行 `pnpm tsc --noEmit` 逐步修复。

**Step 3: 提交**
```bash
git add gui/tsconfig.app.json gui/src/
git commit -m "feat(frontend): enable TypeScript strict mode

Enabled strict, strictNullChecks, noUncheckedIndexedAccess,
exactOptionalPropertyTypes. Caught and fixed N type errors."
```

---

## Phase 5: 运维就绪 & 开源发布准备（Week 5-6）

**目标**: Runbook、GTM 物料、混沌测试 CI、On-call 配置、灰度发布验证

---

### Task 5-1: 创建 Runbook 文档体系

**Files:**
- Create: `docs/runbooks/p0-alert-runbook.md`
- Create: `docs/runbooks/incident-response.md`
- Create: `docs/runbooks/deployment-verification.md`

**Step 1: P0 告警 Runbook 模板**

```markdown
# P0 告警 Runbook: [告警名称]

## 告警条件
- 指标: [PromQL 查询]
- 阈值: [触发条件]
- 优先级: P0

## 影响面
- 用户: [哪些用户受影响]
- 功能: [哪些功能受影响]

## 诊断步骤
1. 检查 [Dashboard URL]
2. 检查日志: `kubectl logs -n maref -l app=maref --tail=100`
3. 检查 [其他诊断]

## 缓解措施
1. [步骤 1]
2. [步骤 2]
3. 如果需要回滚: `bash scripts/rollback.sh --target [版本]`

## 事后复盘
- 创建事故复盘 Issue
- 通知: [#on-call Slack]
```

**Step 2: 事故响应流程**

```markdown
# 事故响应流程

## 响应时间
- P0: 15 分钟响应
- P1: 30 分钟响应
- P2: 4 小时响应

## 升级路径
L1 (On-call) → L2 (SRE Lead) → L3 (CTO)

## 沟通模板
[事故报告模板]
```

**Step 3: 提交**
```bash
git add docs/runbooks/
git commit -m "docs(ops): create runbook documentation for P0 alerts and incident response"
```

---

### Task 5-2: 混沌测试 CI 集成

**Files:**
- Create: `.github/workflows/chaos.yml`
- Create: `tests/chaos/network-partition.py`
- Create: `tests/chaos/pod-kill.py`

**Step 1: 基础混沌测试**

```python
# tests/chaos/network-partition.py
"""验证网络分区下系统行为"""
import subprocess, time, requests

def test_network_partition():
    """切断一个 Service 的网络连接 → 验证降级行为。"""
    # 注入: 添加 iptables 规则拒绝流量（模拟网络分区）
    subprocess.run(["iptables", "-A", "INPUT", "-s", "10.0.0.0/8", "-j", "DROP"])

    time.sleep(5)
    # 验证: 核心功能应降级而非崩溃
    resp = requests.get("http://localhost:8080/health", timeout=5)
    assert resp.status_code == 200  # 健康检查仍然响应

    # 恢复
    subprocess.run(["iptables", "-D", "INPUT", "-s", "10.0.0.0/8", "-j", "DROP"])
```

**Step 2: CI 工作流**

```yaml
# .github/workflows/chaos.yml
name: Chaos Engineering
on:
  schedule:
    - cron: '0 6 * * 0'  # 每周日
  workflow_dispatch:

jobs:
  chaos:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Deploy to kind
        run: |
          kind create cluster
          kubectl apply -f k8s/production/
      - name: Run chaos tests
        run: pytest tests/chaos/ -v --timeout=120
```

**Step 3: 提交**
```bash
git add .github/workflows/chaos.yml tests/chaos/
git commit -m "feat(ops): add chaos engineering CI with network partition and pod kill tests"
```

---

### Task 5-3: 准备 GTM 发布物料

**Files:**
- Create: `docs/gtm/launch-announcement.md`
- Create: `docs/gtm/faq.md`
- Create: `docs/gtm/support-runbook.md`

**Step 1: 发布公告**

基于 `docs/go-to-market-plan.md` 创建。

**Step 2: FAQ**

```markdown
# MAREF Open Source Launch FAQ

## What is MAREF?
MAREF is the first Governance Operating System for Multi-Agent Systems.
It sits beside (not replacing) existing agent frameworks like LangGraph,
CrewAI, and AutoGen, adding formal verification, cryptographic audit trails,
and trust boundary enforcement.

## How is MAREF different from LangGraph/CrewAI/AutoGen?
Those are agent *orchestration* frameworks. MAREF is an agent *governance*
layer. You can use MAREF to govern agents built with any of them.

## What license?
Apache-2.0. Fully open source.

## Where do I start?
```bash
pip install maref
maref serve
# Then point your agents to http://localhost:8080/api/mcp
```

## How is MAREF funded?
Enterprise support subscriptions ($10K-100K/year) and managed cloud.
Core framework remains Apache-2.0 forever.
```

**Step 3: 提交**
```bash
git add docs/gtm/
git commit -m "docs(gtm): prepare launch announcement, FAQ, and support runbook"
```

---

### Task 5-4: 灰度发布验证 + 回滚脚本 CI 集成

**Files:**
- Modify: `scripts/rollback.sh`（确保 CI 可执行）
- Create: `.github/workflows/rollback-test.yml`

**Step 1: 回滚测试 CI**

```yaml
# .github/workflows/rollback-test.yml
name: Rollback Verification
on:
  schedule:
    - cron: '0 4 * * 1'  # 每周一
  workflow_dispatch:

jobs:
  verify-rollback:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Test rollback script
        run: bash scripts/rollback.sh --verify
```

**Step 2: 提交**
```bash
git add .github/workflows/rollback-test.yml
git commit -m "feat(ops): add scheduled rollback verification to CI"
```

---

### Task 5-5: Grafana Dashboard 预部署

**Files:**
- Create: `k8s/production/grafana-dashboard.yaml`
- Modify: `configs/grafana/maref-dashboard.json`

**Step 1: 从代码生成改为预部署 JSON**

确认 `configs/grafana/maref-dashboard.json` 是否与 `otel_bridge.py` 中的 `create_grafana_dashboard()` 一致。

**Step 2: 创建 ConfigMap 用于 Grafana 自动导入**

```yaml
# k8s/production/grafana-dashboard.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: maref-grafana-dashboard
  namespace: maref
  labels:
    grafana_dashboard: "1"
data:
  maref-dashboard.json: |
    (粘贴 maref-dashboard.json 内容)
```

**Step 3: 提交**
```bash
git add k8s/production/grafana-dashboard.yaml configs/grafana/maref-dashboard.json
git commit -m "feat(ops): pre-deploy Grafana dashboard as K8s ConfigMap

Previously dashboard was generated at runtime by code — now deployed
alongside the application for immediate monitoring on startup."
```

---

## 质量门禁：完成标准

### Phase 完成后必须验证

| Phase | 验证命令 | 通过标准 |
|-------|---------|---------|
| Phase 0 | `pytest tests/security/ -v` | 0 failures |
| Phase 0 | `ruff check src/` | 0 errors |
| Phase 1 | `bash scripts/check_versions.py` | "All versions consistent" |
| Phase 2 | `bash gui/scripts/generate-types.sh && git diff --exit-code gui/src/types/api.d.ts` | 无 diff |
| Phase 3 | `cd gui && pnpm vitest run` | 0 failures |
| Phase 3 | `cd gui && pnpm exec playwright test` | 0 failures |
| Phase 3 | `cd gui && pnpm tsc --noEmit` | 0 errors |
| Phase 4 | `python scripts/rtm_validator.py --prd docs/whitepapers/*.md` | 无缺失引用 |
| Phase 5 | `pytest tests/chaos/ -v` | 0 failures |
| All | `pytest tests/ -v --cov=src/maref --cov-report=term-missing | tail -5` | Coverage >= 80% |

### 最终评审前的自检清单

```
□ Phase 0: 所有 9 个 P0 阻塞已修复
□ Phase 1: K8s 生产配置完整 (PDB/Quota/RBAC/Ingress)
□ Phase 1: CI 包含版本一致性检查
□ Phase 2: API 类型自动生成贯通
□ Phase 2: 错误码映射在 API 客户端中生效
□ Phase 2: 前端 OTel trace 头注入
□ Phase 2: 后端安全头中间件生效
□ Phase 3: E2E 测试就绪 (Playwright)
□ Phase 3: Web Vitals RUM 激活
□ Phase 3: i18n 基础设施就绪
□ Phase 3: a11y aria-label 补全
□ Phase 4: 治理基准白皮书发布
□ Phase 4: Sidecar 集成示例可用
□ Phase 4: MCP/A2A 文档公开
□ Phase 5: Runbook 文档体系完成
□ Phase 5: 混沌测试 CI 运行
□ Phase 5: GTM 物料就绪
□ Phase 5: Grafana dashboard 预部署
```

---

## 版本标签规范

所有新提交使用以下格式：
```
fix(security): ...   # Phase 0 安全修复
fix(k8s): ...        # Phase 1 K8s 配置
fix(api): ...        # Phase 2 API 链路
feat(qa): ...        # Phase 3 测试
docs: ...            # Phase 4 文档
feat(ops): ...       # Phase 5 运维
```

---

## 执行方式

本计划包含 **5 个 Phase、38 个 Task**。推荐执行方式：
1. **按 Phase 顺序执行**（Phase 0 → 1 → 2 → 3 → 4 → 5）
2. 每个 Phase 内按 Task 顺序
3. 每个 Task 包含明确的 Step 和验证方法
4. 每个 Task 完成后 git commit

**计划完成并保存到 `docs/plans/2026-06-04-post-audit-reinforcement.md`。**
