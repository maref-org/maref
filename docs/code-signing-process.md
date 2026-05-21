# MAREF 代码签名流程

## 概述

MAREF 桌面端分发需要代码签名以确保用户信任：
- **macOS**: Gatekeeper 验证（Apple Developer ID）
- **Windows**: SmartScreen 验证（EV Code Signing Certificate）

## 先决条件

### macOS
- Apple Developer Program 会员 ($99/年)
- Xcode 命令行工具：`xcode-select --install`
- 证书类型：`Developer ID Application`（分发用）或 `Apple Development`（开发用）

### Windows  
- EV Code Signing Certificate（约 $300/年，如 DigiCert、Sectigo）
- Windows SDK（含 SignTool）

## 配置步骤

### 1. 证书导出

```bash
# macOS: 从 Keychain 导出证书
security find-identity -v -p basic
security export -k ~/Library/Keychains/login.keychain-db \
  -t identities -f pkcs12 -o maref-dev.p12 \
  -P "<export-password>"
```

### 2. CI 环境变量

在 GitHub Secrets 中设置：

| Secret | 用途 |
|--------|------|
| `MACOS_CERTIFICATE` | macOS 证书 (base64 编码 p12) |
| `MACOS_CERTIFICATE_PWD` | macOS 证书密码 |
| `WIN_CERTIFICATE` | Windows 证书 (base64 编码 pfx) |
| `WIN_CERTIFICATE_PWD` | Windows 证书密码 |
| `APPLE_ID` | Apple ID 用于 notarization |
| `APPLE_ID_PASSWORD` | Apple ID app-specific password |
| `APPLE_TEAM_ID` | Apple Developer Team ID |

### 3. Tauri 构建配置

`gui/src-tauri/tauri.conf.json` 中已包含 macOS 最低版本 `"minimumSystemVersion": "12.0"`。  
签名由 Tauri CLI 自动处理（当环境变量配置正确时）。

### 4. CI 集成

在 `.github/workflows/release.yml` 中添加签名步骤：

```yaml
- name: Import macOS Certificate
  if: runner.os == 'macOS'
  run: |
    echo "$MACOS_CERTIFICATE" | base64 --decode > certificate.p12
    security create-keychain -p temp build.keychain
    security default-keychain -s build.keychain
    security unlock-keychain -p temp build.keychain
    security import certificate.p12 -k build.keychain -P "$MACOS_CERTIFICATE_PWD" -T /usr/bin/codesign
    security set-key-partition-list -S apple-tool:,apple:,codesign: -s -k temp build.keychain

- name: Build and Sign (Tauri)
  run: pnpm tauri build
  env:
    APPLE_ID: ${{ secrets.APPLE_ID }}
    APPLE_ID_PASSWORD: ${{ secrets.APPLE_ID_PASSWORD }}
    APPLE_TEAM_ID: ${{ secrets.APPLE_TEAM_ID }}
```

## 验证

```bash
# macOS: 验证签名
codesign -dvvv path/to/MAREF.app

# macOS: 验证 notarization
spctl --assess -vvv path/to/MAREF.app

# Windows: 验证签名
signtool verify /pa /v path/to/MAREF.exe
```
