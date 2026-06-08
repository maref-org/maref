#!/bin/bash
# macOS Keychain 凭据注入脚本
# 用法: source scripts/maref-secrets.sh && <your_command>
# 或: ./scripts/maref-secrets.sh <your_command>

export SMTP_PASSWORD=$(security find-generic-password -s "maref-smtp-password" -w 2>/dev/null)
export CF_API_TOKEN=$(security find-generic-password -s "maref-cf-api-token" -w 2>/dev/null)
export CF_ACCOUNT_ID=""

# 如果带参数执行，直接 exec 参数（不产生子进程）
if [ $# -gt 0 ]; then
    exec "$@"
fi
