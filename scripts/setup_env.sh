#!/bin/bash
#
# MAREF Environment Setup Script
# 帮助用户安全地配置环境变量
# 不会将密钥写入任何 Git 追踪的文件
#

set -e

echo "=========================================="
echo "  MAREF Environment Setup"
echo "=========================================="
echo ""

# 检查项目根目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${SCRIPT_DIR}/.."

echo "Project root: ${PROJECT_ROOT}"
echo ""

# 步骤 1: 检查并创建 ~/.maref.env
MAREF_USER_ENV="${HOME}/.maref.env"
if [[ -f "${MAREF_USER_ENV}" ]]; then
    echo "✓ Found existing ${MAREF_USER_ENV}"
else
    echo "Creating ${MAREF_USER_ENV}..."
    cp "${PROJECT_ROOT}/.env.example" "${MAREF_USER_ENV}"
    chmod 600 "${MAREF_USER_ENV}"
    echo "✓ Created ${MAREF_USER_ENV} (permissions: 600)"
    echo ""
    echo "IMPORTANT: Edit ${MAREF_USER_ENV} and replace placeholder keys with your actual API keys"
fi

# 步骤 2: 检查并创建 .env (项目级)
PROJECT_ENV="${PROJECT_ROOT}/.env"
if [[ -f "${PROJECT_ENV}" ]]; then
    echo "✓ Found existing ${PROJECT_ENV}"
else
    echo "Creating ${PROJECT_ENV}..."
    cp "${PROJECT_ROOT}/.env.example" "${PROJECT_ENV}"
    chmod 600 "${PROJECT_ENV}"
    echo "✓ Created ${PROJECT_ENV} (permissions: 600)"
fi

# 步骤 3: 检查 keyring 可用性
echo ""
echo "Checking keyring availability..."
if python3 -c "import keyring; print('keyring backend:', keyring.get_keyring().name)" 2>/dev/null; then
    echo "✓ keyring is available"
    echo ""
    echo "To store API keys in macOS Keychain (recommended):"
    echo "  python3 -c \"import keyring; keyring.set_password('com.maref.agent', 'DASHSCOPE_API_KEY', 'sk-your-actual-key')\""
else
    echo "⚠ keyring not found. Install with: pip install keyring"
    echo "  Using environment variables for now."
fi

# 步骤 4: 验证配置
echo ""
echo "Verifying configuration..."
if [[ -f "${MAREF_USER_ENV}" ]]; then
    # 检查是否有实际的 key (不是 placeholder)
    if grep -q "sk-your-key-here" "${MAREF_USER_ENV}" 2>/dev/null; then
        echo "⚠ ${MAREF_USER_ENV} still contains placeholder keys"
        echo "  Please edit and replace with your actual API keys"
    else
        echo "✓ ${MAREF_USER_ENV} appears configured"
    fi
fi

# 步骤 5: 测试环境变量加载
echo ""
echo "Testing environment loader..."
if [[ -f "${SCRIPT_DIR}/maref_env_loader.sh" ]]; then
    echo "✓ maref_env_loader.sh exists"
else
    echo "✗ maref_env_loader.sh not found"
fi

if [[ -f "${SCRIPT_DIR}/maref_wrapper.sh" ]]; then
    echo "✓ maref_wrapper.sh exists"
    if grep -q "/Volumes/1TB-M2" "${SCRIPT_DIR}/maref_wrapper.sh" 2>/dev/null; then
        echo "⚠ maref_wrapper.sh still contains hardcoded /Volumes/1TB-M2 paths"
    else
        echo "✓ maref_wrapper.sh uses relative/configurable paths"
    fi
fi

# 步骤 6: 生成 LaunchAgent plist 配置
echo ""
echo "Generating LaunchAgent plist..."
PLIST_TEMPLATE="${SCRIPT_DIR}/com.maref.autoresearch.plist.template"
PLIST_DEST="${SCRIPT_DIR}/com.maref.autoresearch.plist"
SCRIPTS_DIR="${HOME}/scripts"

if [[ -f "${PLIST_TEMPLATE}" ]]; then
    sed -e "s|{{SCRIPTS_DIR}}|${SCRIPTS_DIR}|g" \
        -e "s|{{HOME_DIR}}|${HOME}|g" \
        "${PLIST_TEMPLATE}" > "${PLIST_DEST}"
    echo "✓ Generated ${PLIST_DEST} with your paths"
    echo "  Scripts dir: ${SCRIPTS_DIR}"
    echo "  Home dir: ${HOME}"
else
    echo "⚠ ${PLIST_TEMPLATE} not found, using existing plist"
fi

# 步骤 7: 验证 plist 配置
if [[ -f "${PLIST_DEST}" ]]; then
    echo ""
    echo "Checking LaunchAgent plist..."
    if grep -q "sk-" "${PLIST_DEST}" 2>/dev/null; then
        echo "✗ CRITICAL: ${PLIST_DEST} still contains hardcoded API keys!"
        echo "  This is a security risk. Please run the security fix."
    else
        echo "✓ ${PLIST_DEST} does not contain API keys"
    fi
    if grep -q "/Users/[a-z]*/" "${PLIST_DEST}" 2>/dev/null; then
        echo "✗ CRITICAL: ${PLIST_DEST} contains hardcoded /Users/ paths!"
    else
        echo "✓ ${PLIST_DEST} uses placeholder paths"
    fi
fi

echo ""
echo "=========================================="
echo "  Setup Complete"
echo "=========================================="
echo ""
echo "Next steps:"
echo "  1. Edit ~/.maref.env with your actual API keys"
echo "  2. Copy wrapper script to internal drive:"
echo "     mkdir -p ~/scripts"
echo "     cp ${SCRIPT_DIR}/maref_wrapper.sh ~/scripts/"
echo "     chmod +x ~/scripts/maref_wrapper.sh"
echo "  3. Install LaunchAgent:"
echo "     cp ${SCRIPT_DIR}/com.maref.autoresearch.plist ~/Library/LaunchAgents/"
echo "     launchctl load ~/Library/LaunchAgents/com.maref.autoresearch.plist"
echo "  4. Test: bash ${SCRIPT_DIR}/maref_wrapper.sh"
echo ""
echo "Security checklist:"
echo "  [~/.maref.env has 600 permissions]"
echo "  [No API keys in Git-tracked files]"
echo "  [keyring installed (optional, recommended)]"
echo ""
