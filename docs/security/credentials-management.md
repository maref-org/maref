# 凭据管理指南

## 概述

MAREF 使用中央凭据管理系统（CredentialManager）统一管理所有敏感数据。

## 凭据类型

| 类型 | 说明 | 轮转周期 |
|------|------|----------|
| `API_KEY` | 外部 API 密钥 | 90 天 |
| `SIGNING_KEY` | Ed25519 签名密钥 | 1 年 |
| `HMAC_KEY` | HMAC 签名密钥 | 180 天 |
| `BROWSER_SESSION` | 浏览器登录状态 | 24 小时 |
| `OAUTH_TOKEN` | OAuth 令牌 | 1 小时 |

## 快速开始

### 1. 设置凭据

```bash
# 交互式设置
bash scripts/maref-secrets-setup.sh

# 或手动添加
security add-generic-password -s "com.maref.agent" -a "DASHSCOPE_API_KEY" -w "sk-xxx"
```

### 2. 加载凭据

```bash
source scripts/maref-secrets.sh
```

### 3. 查看状态

```bash
maref-lite keys list
maref-lite keys audit
```

## 架构

```
┌─────────────────────────────────────────┐
│      AgentIdentityService (门面)        │
└──────────────┬──────────────────────────┘
               │
┌──────────────▼──────────────────────────┐
│        CredentialManager (中央)         │
│  ┌─────────┐  ┌─────────────────────┐   │
│  │ 密钥管理 │  │ 浏览器状态持久化    │   │
│  │ (轮转/  │  │ (Cookie/LS 加密)   │   │
│  │  撤销)  │  │                     │   │
│  └────┬────┘  └──────────┬──────────┘   │
│       │                  │              │
│  ┌────▼──────────────────▼──────────┐   │
│  │        审计日志 (HMAC签名)       │   │
│  └──────────────────────────────────┘   │
└──────────────┬──────────────────────────┘
               │
    ┌──────────▼──────────┐
    │   OS Keychain       │
    │   (KeyringStore)    │
    └─────────────────────┘
```

## CLI 命令

```bash
# 列出所有凭据
maref-lite keys list

# 设置凭据
maref-lite keys set --key DASHSCOPE_API_KEY

# 轮转凭据
maref-lite keys rotate --key DASHSCOPE_API_KEY

# 审计状态
maref-lite keys audit

# 诊断问题
maref-lite keys diagnose
```

## 安全注意事项

1. **永远不要**将凭据提交到 Git
2. **始终使用** OS Keychain 存储生产凭据
3. **定期轮转** API 密钥（建议 90 天）
4. **监控** `maref-lite keys audit` 输出的告警
