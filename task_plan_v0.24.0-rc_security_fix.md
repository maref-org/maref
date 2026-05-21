# MAREF v0.24.0-rc 安全与稳定性修复计划

**创建日期**: 2026-05-13
**审计依据**: MAREF GUI v0.24.0-rc 安全与稳定性审计报告
**目标**: 修复 P0/P1 级别安全问题，稳定 React 重渲染崩溃

---

## 问题总览

| 优先级 | 问题 | 风险等级 |
|--------|------|----------|
| P0 | `.env` API Key 明文暴露 | 严重 - 密钥泄露 |
| P0 | Electron 沙箱完全禁用 | 高危 - RCE 风险 |
| P1 | macOS Hardened Runtime 关闭 | 高危 - 代码注入 |
| P1 | bug_type 309 崩溃 (React 无限重渲染) | 高危 - 稳定性 |
| P1 | 1s 轮询无优化 | 中危 - 资源浪费 |
| P2 | Electron/Tauri 双构建混乱 | 中危 - 维护困难 |
| P2 | `:memory:` 文件泄漏 | 低危 - 清理 |

---

## Phase 1: P0 紧急修复

### 1.1 删除 .env 文件，迁移 API Key 至 Keychain

**Status**: pending

**问题文件**: `.env`
```
DASHSCOPE_API_KEY=sk-REMOVED-FROM-PLACEHOLDER-KEY
```

**修复步骤**:
1. 删除项目根目录 `.env` 文件
2. 创建 `scripts/keychain_inject.py` 从 macOS Keychain 读取密钥
3. 修改启动脚本，通过环境变量注入 API Key
4. 更新 `.gitignore` 确保不再追踪

**验证**:
- `.env` 文件不存在
- 项目可正常启动（通过 Keychain 获取密钥）

---

### 1.2 启用 Electron 沙箱

**Status**: pending

**问题文件**: `gui/electron/main.cjs` (第 5-10, 27 行)

**当前问题代码**:
```javascript
// 第 5-10 行 - 命令行开关
app.commandLine.appendSwitch('disable-gpu-sandbox');
app.commandLine.appendSwitch('no-sandbox');
app.commandLine.appendSwitch('disable-software-rasterizer');
app.commandLine.appendSwitch('enable-features', 'NetworkServiceInProcess');
app.commandLine.appendSwitch('disable-features', 'NetworkService');
process.env.ELECTRON_DISABLE_SANDBOX = '1';

// 第 27 行 - BrowserWindow 配置
sandbox: false,
```

**修复步骤**:
1. 移除第 5-10 行的所有 `appendSwitch` 调用
2. 删除 `process.env.ELECTRON_DISABLE_SANDBOX = '1'` (第 10 行)
3. 将 `sandbox: false` 改为 `sandbox: true` (第 27 行)

**修复后代码**:
```javascript
// 移除所有 appendSwitch 调用

// webPreferences 中
sandbox: true,
```

**验证**:
- `maref serve --gui` 正常启动
- 沙箱已启用（检查 Electron 安全设置）

---

## Phase 2: P1 本周修复

### 2.1 启用 macOS Hardened Runtime

**Status**: pending

**问题文件**: `gui/package.json` (第 72-86 行)

**当前问题配置**:
```json
"mac": {
  "hardenedRuntime": false,
  "extendInfo": {
    "com.apple.security.cs.allow-unsigned-executable-memory": true,
    "com.apple.security.cs.disable-executable-page-protection": true,
    "com.apple.security.cs.disable-library-validation": true
  }
}
```

**修复步骤**:
1. 将 `hardenedRuntime` 改为 `true`
2. 移除 `allow-unsigned-executable-memory`（除非确认需要 JIT）
3. 移除 `disable-executable-page-protection`
4. 移除 `disable-library-validation`
5. 如需 JIT，创建单独的 entitlements 文件

**修复后配置**:
```json
"mac": {
  "hardenedRuntime": true,
  "extendInfo": {
    "com.apple.security.cs.allow-jit": true
  }
}
```

**验证**:
- 构建通过
- 应用签名正常

---

### 2.2 修复 React 无限重渲染 (bug_type 309)

**Status**: pending

**问题文件**: `gui/src/App.tsx` (第 132-195 行)

**问题分析**:
- `shortcutActions` useMemo 依赖 9 个，包含 `terminalTabs.length`
- 每次终端变化重建整个对象
- 可能导致 useEffect 链式触发 → 无限循环

**修复步骤**:
1. 分离 `shortcutActions` 为静态部分和动态部分
2. 使用 `useCallback` 稳定函数引用
3. 添加渲染次数限制或调试日志
4. 检查 SSE 流式更新是否触发频繁 setState

**关键代码位置**:
- `gui/src/App.tsx:132-195` - shortcutActions useMemo
- `gui/src/hooks/useChatStream.ts` - SSE 处理

**验证**:
- 长时间运行无崩溃
- CPU 占用正常
- 内存稳定

---

### 2.3 优化 1s 轮询循环

**Status**: pending

**问题文件**: `src/sidecar/collector.py` (第 168-173 行)

**问题分析**:
- MockAdapter 返回静态数据，每秒轮询无意义
- 24 小时 = 86,400 次无意义调用

**修复步骤**:
1. 检测 adapter 类型
2. 如果是 MockAdapter，跳过轮询或降低到 60s
3. 添加自适配轮询策略（空闲时降低频率）

**修复后代码**:
```python
async def run(self) -> None:
    self._running = True
    while self._running:
        await self.collect_once()
        # 自适应轮询间隔
        interval = self._get_adaptive_interval()
        await asyncio.sleep(interval)
```

**验证**:
- MockAdapter 模式下 CPU 占用降至 0
- 真实 adapter 模式下功能正常

---

## Phase 3: P2 下迭代

### 3.1 统一 Electron/Tauri 构建目标

**Status**: pending

**问题**: 同时存在 Electron (`pnpm electron:dev`) 和 Tauri 构建，用户可能混淆

**修复方案**:
- 在 `gui/package.json` 标注 Electron 仅用于开发调试
- 主构建目标统一为 Tauri
- 添加清晰的启动脚本

---

### 3.2 清理 :memory: 文件

**Status**: pending

**问题**: 根目录存在 1.6MB `:memory:` 文件

**修复步骤**:
1. 删除文件
2. 添加到 `.gitignore`

---

## 执行顺序

```
Phase 1 (立即):
  1.1 删除 .env → 1.2 启用沙箱

Phase 2 (本周):
  2.1 Hardened Runtime → 2.2 React 重渲染 → 2.3 轮询优化

Phase 3 (下迭代):
  3.1 构建统一 → 3.2 文件清理
```

---

## 预期结果

| 指标 | 修复前 | 修复后 |
|------|--------|--------|
| API Key 泄露 | 存在 | 无 |
| 沙箱状态 | 关闭 | 开启 |
| Hardened Runtime | 关闭 | 开启 |
| 崩溃次数 (17min) | 12 次 | 0 次 |
| 每日轮询次数 | 86,400 | ~1,000 (真实 adapter) |

---

## 风险与回滚

- **沙箱启用**: 可能影响某些 node-pty 功能，需测试
- **Hardened Runtime**: 构建签名可能失败，需修复签名配置
- **React 重渲染**: 可能需要多次迭代调试