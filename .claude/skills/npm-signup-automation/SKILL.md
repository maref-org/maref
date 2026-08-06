---
name: npm-signup-automation
description: >
  通过 Playwright 自动化 npm 账号注册 + Token 生成 + 发布流程。
  覆盖 Cloudflare 反爬绕过（系统 Chrome CDP 模式）、React SPA 表单交互、
  2FA 绕过 Token 生成、scope 冲突处理等实战经验。
---

# npm 账号注册 + 发布自动化 Skill

## 一、前置条件

```bash
# 安装 Playwright（仅需要 chromium）
pip install playwright
playwright install chromium

# 启动系统 Chrome CDP（最可靠的 Cloudflare 绕过方式）
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --remote-debugging-port=9222 \
  --user-data-dir=/tmp/chrome-npm-tmp \
  --remote-allow-origins=*
```

> `--remote-allow-origins=*` 是 CDP WebSocket 连接所必需的，否则会 403。

---

## 二、注册表单（npmjs.com/signup）

| 字段 | DOM 选择器 | 说明 |
|---|---|---|
| 用户名 | `#signup_name` | **必须全小写**，建议含 `-org` 后缀 |
| 邮箱 | `#signup_email` | 会公开在包元数据中 |
| 密码 | `#signup_password` | 最少 10 字符 |
| EULA | `#signup_eula-agreement` | 点击即可，label 绑定了事件 |
| 提交 | `button:has-text("Create an Account")` | |

> **经验**: 注册后邮箱验证是必要步骤，验证前无法 publish。验证 OTP 通常几分钟内送达。

---

## 三、Token 生成（关键难点）

npm 已弃用 Classic Token。必须使用 **Granular Access Token**。

### 3.1 页面结构

表单 URL: `/settings/{username}/tokens/granular-access-tokens/new`

| 字段 | 选择器 | 说明 |
|---|---|---|
| Token 名称 | `#create-gat_tokenName` | 唯一 |
| 描述 | `#create-gat_tokenDescription` | 可选 |
| Bypass 2FA | `#create-gat_bypass2FA` | **点击 label**，不要直接点 checkbox |
| Packages 权限 | 下拉菜单 `summary` 第 1 个 | 点击后选 "Read and write" |
| 包范围 | `#packagesAll` / `#packagesAndScopesSome` | 选 All packages |
| Organizations | 下拉菜单 `summary` 第 2 个 | 用户账号设为 "No access" |
| 过期 | 下拉菜单 `summary` 第 3 个 | 默认 7 天（可改 30/90 天） |
| 提交 | `button:has-text("Generate token")` | |

### 3.2 ⚠️ Bypass 2FA 复选框陷阱

**这是最常见的坑**。npm 使用 React SPA，直接操作 checkbox 不会更新组件状态：

```python
# ❌ 不行：Playwright .check() 报错 "did not change its state"
page.locator('#create-gat_bypass2FA').check()

# ❌ 不行：JS 原生 click 不触发 React 变更
page.evaluate("document.getElementById('create-gat_bypass2FA').click()")

# ❌ 不行：JS 修改 checked + dispatchEvent 不代表表单提交时会发送正确值
# 这会导致 POST 数据中 bypass2FA=false（因为 React 未更新内部状态）

# ✅ 正确：点击 label 元素（React 监听了 label 的 click 事件）
page.locator('label[for="create-gat_bypass2FA"]').click()
# 此时 POST 数据中 bypass2FA=true
```

> **验证方法**: 用 Playwright 拦截 POST 请求，检查 `request.post_data` 中的 `bypass2FA` 字段。
> 生成后在 Token 详情页检查 `#gat-details_bypass2FA.checked`。

### 3.3 权限下拉菜单操作

下拉菜单使用 `details + summary` + `role="menuitemcheckbox"` 组件：

```python
page.evaluate("""
() => {
    const summaries = document.querySelectorAll('summary');
    if (summaries[0]) summaries[0].click();  # 打开 packages 下拉
    return new Promise((resolve) => {
        setTimeout(() => {
            const buttons = document.querySelectorAll('button[role="menuitemcheckbox"]');
            for (const btn of buttons) {
                const span = btn.querySelector('span');
                if (span && span.textContent.trim() === 'Read and write') {
                    btn.click();
                    resolve();
                    return;
                }
            }
            resolve();
        }, 200);
    });
}
""")
```

---

## 四、发布到 npm

### 4.1 配置镜像问题

全局 `.npmrc` 可能指向中国镜像（`registry.npmmirror.com`），**必须显式覆盖**：

```bash
# 使用 token 发布（推荐）
echo "//registry.npmjs.org/:_authToken=npm_xxxxx" > /tmp/.npmrc-publish
npm publish --registry=https://registry.npmjs.org/ --access public --userconfig=/tmp/.npmrc-publish

# 或者配置环境变量
NODE_AUTH_TOKEN=npm_xxxxx npm publish --registry=https://registry.npmjs.org/ --access public
```

### 4.2 2FA 注意事项

- 如果发布报错 `Two-factor authentication required`，说明 token 的 Bypass 2FA 未正确设置
- 验证方式：检查 POST 数据中 `bypass2FA` 是否为 `true`
- npm 从 2026 年 8 月起限制 bypass 2FA token 的账户变更，2027 年 1 月起限制直接发布

---

## 五、Scope 冲突处理

| 情况 | 处理 |
|---|---|
| 想要的 scope 已被注册（如 `@maref`） | 用 `@username/package` 格式，如 `@maref-org/sdk` |
| Scope 对应的 org 名不可用 | 尝试 `-org`、`-io`、`_io` 等后缀 |
| 用户名和 scope 不一致 | 发布后可在 npm 页面创建组织来转移 scope，但最简单的是直接用用户名 scope |

> npm 不允许在用户名/组织名之外的其他 scope 下发布包。`@maref/sdk` 不可用是因为 `maref` 用户/组织已存在。

---

## 六、完整自动化流程示例

```python
from playwright.sync_api import sync_playwright
import json, time, re

with sync_playwright() as p:
    # Step 1: 连接已启动的 Chrome CDP
    browser = p.chromium.connect_over_cdp("http://localhost:9222")
    page = browser.contexts[0].pages[0]
    
    # Step 2: 填写表单
    page.locator('#create-gat_tokenName').fill("my-publish-token")
    
    # Step 3: 点击 bypass 2FA 的 label（不是 checkbox）
    page.locator('label[for="create-gat_bypass2FA"]').click()
    
    # Step 4: 设置权限
    # (见第三节代码)
    
    # Step 5: 捕获 POST 数据验证
    post_data = []
    def on_request(req):
        if 'new-gat' in req.url and req.method == 'POST':
            post_data.append(req.post_data)
    page.on('request', on_request)
    
    # Step 6: 生成 token
    page.locator('button:has-text("Generate token")').click()
    time.sleep(3)
    
    # Step 7: 读取 token
    body_text = page.inner_text('body')
    tokens = re.findall(r'npm_[a-zA-Z0-9_]{36,}', body_text)
    if tokens:
        print(f"Token: {tokens[0]}")
```

---

## 七、常见错误速查

| 错误 | 原因 | 修复 |
|---|---|---|
| `Name must be lowercase` | 用户名含大写 | 全小写 |
| `username is already taken` | 用户名占用 | 尝试 `xxx-org` / `xxx_io` |
| `organization name X is not available` | scope 被占用 | 改用 `@username/package` |
| `Checkbox did not change its state` | React 未响应 | **点击 label** 而非 checkbox |
| `Two-factor authentication required` | bypass 2FA 未生效 | 验证 POST 数据确认 |
| `403 Forbidden` | 权限不足 / 2FA | 检查 token scope + bypass 2FA |
| `Duplicate token names are not allowed` | token 名已存在 | 加后缀如 `-v2` |
| `Route not found!` | URL 路径错误 | Classic Token URL 可能已失效 |
| CDP WebSocket `403 Forbidden` | 缺 `--remote-allow-origins` | Chrome 启动参数加该 flag |
