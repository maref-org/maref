#!/bin/bash
# 安装 post-commit hook: 每次 commit 后在新 Terminal 窗口运行全量测试
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/../../.." && pwd)"
HOOK_FILE="$REPO_DIR/.git/hooks/post-commit"

cat > "$HOOK_FILE" << 'HOOK'
#!/bin/bash
# post-commit — commit 后在新 Terminal 窗口运行全量测试
# 由 install-post-commit-hook.sh 自动安装
REPO_DIR="$(cd "$(dirname "$0")/../.." && pwd)"

# macOS: 打开新 Terminal 窗口运行测试
osascript -e "
tell application \"Terminal\"
    activate
    do script \"cd '$REPO_DIR' && bash scripts/run-full-tests.sh\"
end tell
" 2>/dev/null || {
    # fallback: 无头运行
    nohup bash "$REPO_DIR/scripts/run-full-tests.sh" > /dev/null 2>&1 &
    echo "全量测试在后台启动 (PID: $!)"
}
HOOK

chmod +x "$HOOK_FILE"
echo "✅ post-commit hook 已安装: $HOOK_FILE"
echo "   每次 git commit 后自动在新 Terminal 窗口运行全量测试"
