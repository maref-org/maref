#!/bin/bash
# scripts/maref-secrets-setup.sh
# 交互式设置 MAREF 凭据到 macOS Keychain
# 用法: bash scripts/maref-secrets-setup.sh

set -euo pipefail

SERVICE="com.maref.agent"

echo "MAREF Credential Setup"
echo "====================="
echo ""
echo "This script will store your credentials in macOS Keychain."
echo "Press Ctrl+C at any time to abort."
echo ""

# API Keys
echo "1. DashScope API Key"
echo "   Get yours at: https://dashscope.console.aliyun.com/apiKey"
read -sp "   Enter DASHSCOPE_API_KEY: " DASHSCOPE_KEY
echo
security add-generic-password -s "$SERVICE" -a "DASHSCOPE_API_KEY" -w "$DASHSCOPE_KEY" -U 2>/dev/null || \
security generic-password -s "$SERVICE" -a "DASHSCOPE_API_KEY" -w "$DASHSCOPE_KEY" -U
echo "   ✓ Stored"

echo ""
echo "2. OpenAI API Key (optional)"
read -sp "   Enter OPENAI_API_KEY (empty to skip): " OPENAI_KEY
echo
if [ -n "$OPENAI_KEY" ]; then
    security add-generic-password -s "$SERVICE" -a "OPENAI_API_KEY" -w "$OPENAI_KEY" -U 2>/dev/null || \
    security generic-password -s "$SERVICE" -a "OPENAI_API_KEY" -w "$OPENAI_KEY" -U
    echo "   ✓ Stored"
fi

echo ""
echo "3. Cloudflare API Token"
read -sp "   Enter CF_API_TOKEN (empty to skip): " CF_TOKEN
echo
if [ -n "$CF_TOKEN" ]; then
    security add-generic-password -s "maref-cf-api-token" -w "$CF_TOKEN" -U 2>/dev/null || \
    security generic-password -s "maref-cf-api-token" -w "$CF_TOKEN" -U
    echo "   ✓ Stored"
fi

echo ""
echo "4. SMTP Password (for email notifications)"
read -sp "   Enter SMTP_PASSWORD (empty to skip): " SMTP_PWD
echo
if [ -n "$SMTP_PWD" ]; then
    security add-generic-password -s "maref-smtp-password" -w "$SMTP_PWD" -U 2>/dev/null || \
    security generic-password -s "maref-smtp-password" -w "$SMTP_PWD" -U
    echo "   ✓ Stored"
fi

echo ""
echo "5. MAREF HMAC Secret Key"
read -sp "   Enter MAREF_HMAC_SECRET_KEY (empty to generate): " HMAC_KEY
echo
if [ -z "$HMAC_KEY" ]; then
    HMAC_KEY=$(openssl rand -hex 32)
    echo "   Generated: ${HMAC_KEY:0:8}..."
fi
security add-generic-password -s "$SERVICE" -a "MAREF_HMAC_SECRET_KEY" -w "$HMAC_KEY" -U 2>/dev/null || \
security generic-password -s "$SERVICE" -a "MAREF_HMAC_SECRET_KEY" -w "$HMAC_KEY" -U
echo "   ✓ Stored"

echo ""
echo "6. Browser Auth Key"
read -sp "   Enter MAREF_BROWSER_AUTH_KEY (empty to generate): " BROWSER_KEY
echo
if [ -z "$BROWSER_KEY" ]; then
    BROWSER_KEY=$(openssl rand -hex 32)
    echo "   Generated: ${BROWSER_KEY:0:8}..."
fi
security add-generic-password -s "maref-browser-auth-key" -w "$BROWSER_KEY" -U 2>/dev/null || \
security generic-password -s "maref-browser-auth-key" -w "$BROWSER_KEY" -U
echo "   ✓ Stored"

echo ""
echo "7. Credential Encryption Key"
read -sp "   Enter MAREF_CREDENTIAL_ENCRYPTION_KEY (empty to generate): " ENC_KEY
echo
if [ -z "$ENC_KEY" ]; then
    ENC_KEY=$(openssl rand -hex 32)
    echo "   Generated: ${ENC_KEY:0:8}..."
fi
security add-generic-password -s "maref-credential-encryption-key" -w "$ENC_KEY" -U 2>/dev/null || \
security generic-password -s "maref-credential-encryption-key" -w "$ENC_KEY" -U
echo "   ✓ Stored"

echo ""
echo "✓ Setup complete!"
echo ""
echo "Usage:"
echo "  source scripts/maref-secrets.sh  # Load credentials"
echo "  maref-lite keys list              # View stored keys"
echo "  maref-lite keys audit             # Check rotation status"
