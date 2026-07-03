#!/usr/bin/env bash
# Deploy MAREF Wiki to GitHub
# Usage: bash scripts/deploy-wiki.sh
set -euo pipefail

WIKI_DIR="$(cd "$(dirname "$0")/../.wiki" && pwd)"
REPO_URL="https://github.com/maref-org/maref.wiki.git"
TMP_DIR=$(mktemp -d)

trap 'rm -rf "$TMP_DIR"' EXIT

echo "Cloning wiki repo..."
git clone "$REPO_URL" "$TMP_DIR"

echo "Copying wiki pages..."
cp "$WIKI_DIR"/*.md "$TMP_DIR/"

cd "$TMP_DIR"
git add -A
git commit -m "docs: update wiki pages"
git push

echo "Wiki deployed successfully!"
