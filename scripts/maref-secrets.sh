#!/bin/bash
# scripts/maref-secrets.sh
# 从 OS Keychain 注入环境变量
# 用法: source scripts/maref-secrets.sh

set -euo pipefail

echo "Loading MAREF credentials from macOS Keychain..."

# 从 Keychain 读取并导出
export DASHSCOPE_API_KEY=$(security find-generic-password -s "com.maref.agent" -a "DASHSCOPE_API_KEY" -w 2>/dev/null || echo "")
export OPENAI_API_KEY=$(security find-generic-password -s "com.maref.agent" -a "OPENAI_API_KEY" -w 2>/dev/null || echo "")
export ANTHROPIC_API_KEY=$(security find-generic-password -s "com.maref.agent" -a "ANTHROPIC_API_KEY" -w 2>/dev/null || echo "")

# Cloudflare
export CF_API_TOKEN=$(security find-generic-password -s "maref-cf-api-token" -w 2>/dev/null || echo "")
export CF_ACCOUNT_ID=$(security find-generic-password -s "maref-cf-account-id" -w 2>/dev/null || echo "")

# SMTP
export SMTP_PASSWORD=$(security find-generic-password -s "maref-smtp-password" -w 2>/dev/null || echo "")

# MAREF 内部
export MAREF_API_KEY=$(security find-generic-password -s "com.maref.agent" -a "MAREF_ADMIN_TOKEN" -w 2>/dev/null || echo "")
export MAREF_HMAC_SECRET_KEY=$(security find-generic-password -s "com.maref.agent" -a "MAREF_HMAC_SECRET_KEY" -w 2>/dev/null || echo "")

# 浏览器认证密钥
export MAREF_BROWSER_AUTH_KEY=$(security find-generic-password -s "maref-browser-auth-key" -w 2>/dev/null || echo "")

# 凭据管理器加密密钥
export MAREF_CREDENTIAL_ENCRYPTION_KEY=$(security find-generic-password -s "maref-credential-encryption-key" -w 2>/dev/null || echo "")

echo "✓ Credentials loaded"
