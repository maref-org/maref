#!/usr/bin/env bash
# sync-content.sh — 从知识库和 public/maref 同步内容到网站
# 用法: ./scripts/sync-content.sh [--dry-run] [--blog]
# 频率: 每周 (WEBSITE_SPEC §10.3)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
WEBSITE_CONTENT="$PROJECT_DIR/src/content"
PUBLIC_MAREF="$PROJECT_ROOT"
KNOWLEDGE_BASE="$PROJECT_ROOT/Athena知识库/执行项目/2026/003-open human（碳硅基共生）/018-v0.2.0-活跃/021-架构设计/MAREF递归演进框架"

DRY_RUN=false
SYNC_BLOG=false

for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=true ;;
    --blog) SYNC_BLOG=true ;;
  esac
done

sync_file() {
  local src="$1" dst="$2" desc="$3"
  if [ ! -f "$src" ]; then
    echo "  ⚠️  Source not found: $src"
    return
  fi
  if $DRY_RUN; then
    echo "  [DRY-RUN] Would sync: $desc"
    return
  fi
  mkdir -p "$(dirname "$dst")"
  cp "$src" "$dst"
  echo "  ✅ $desc"
}

echo "=== Content Sync: $(date '+%Y-%m-%d %H:%M') ==="
echo ""

# 1. README — product description reference
echo "[1/4] Syncing product descriptions..."
sync_file \
  "$PUBLIC_MAREF/README.md" \
  "$WEBSITE_CONTENT/pages/product-overview.md" \
  "README → content/pages/product-overview.md"

# 2. CHANGELOG — release notes
echo "[2/4] Syncing changelog..."
sync_file \
  "$PUBLIC_MAREF/CHANGELOG.md" \
  "$WEBSITE_CONTENT/pages/changelog.md" \
  "CHANGELOG → content/pages/changelog.md"

# 3. CONTRIBUTING — community guide
echo "[3/4] Syncing contributing guide..."
sync_file \
  "$PUBLIC_MAREF/CONTRIBUTING.md" \
  "$WEBSITE_CONTENT/pages/contributing.md" \
  "CONTRIBUTING → content/pages/contributing.md"

# 4. Feature descriptions from knowledge base (governance/defense/crypto/evolution)
echo "[4/4] Syncing feature descriptions..."
for f in governance defense evolution cryptography; do
  src="$WEBSITE_CONTENT/features/$f.md"
  # Features are maintained directly in website content; check if source exists
  if [ -f "$src" ]; then
    echo "  ✅ Feature page exists: $f"
  else
    echo "  ⚠️  Feature page not yet created: $f (src/content/features/$f.md)"
  fi
done

echo ""
echo "=== Sync complete ==="
echo ""
echo "Next step: Run 'pnpm build' to verify content renders correctly."
