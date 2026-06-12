#!/bin/bash
# 检查前端类型是否与 OpenAPI schema 一致
set -e

# 1. 生成最新类型
python scripts/export_openapi.py
npx openapi-typescript gui/openapi-schema.json -o /tmp/api-drifttest.d.ts

# 2. 比较当前类型文件
if ! diff -q /tmp/api-drifttest.d.ts gui/src/types/api.d.ts 2>/dev/null; then
  echo "❌ Type drift detected! Regenerate with: pnpm generate:types"
  exit 1
fi
echo "✅ Types are in sync with OpenAPI schema"
