#!/bin/bash
#
# MAREF Environment Loader
# 从 ~/.maref.env 加载环境变量到 launchd 会话
# 用于 LaunchAgent 在不硬编码密钥的情况下获取环境变量
#
# 使用方法:
#   在 LaunchAgent plist 中:
#   <key>ProgramArguments</key>
#   <array>
#       <string>/bin/bash</string>
#       <string>-c</string>
#       <string>source ~/.maref_env_loader.sh && exec /path/to/maref_wrapper.sh</string>
#   </array>
#

MAREF_ENV_FILE="${HOME}/.maref.env"

if [[ -f "${MAREF_ENV_FILE}" ]]; then
    # 从配置文件加载环境变量
    set -a
    source "${MAREF_ENV_FILE}"
    set +a

    # 使用 launchctl 将环境变量注入到当前会话
    while IFS='=' read -r key value; do
        # 跳过注释和空行
        [[ "${key}" =~ ^#.*$ ]] && continue
        [[ -z "${key}" ]] && continue

        # 注入到 launchd 环境
        launchctl setenv "${key}" "${value}" 2>/dev/null || true
    done < <(grep -E '^[A-Za-z_][A-Za-z0-9_]*=' "${MAREF_ENV_FILE}" | sed 's/^[[:space:]]*//')

    echo "[$(date '+%Y-%m-%d %H:%M:%S')] MAREF environment loaded from ${MAREF_ENV_FILE}"
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] WARNING: ${MAREF_ENV_FILE} not found"
    echo "  Please create ~/.maref.env with your API keys and configuration"
    echo "  See /path/to/maref-experiments/.env.example for template"
    exit 1
fi
