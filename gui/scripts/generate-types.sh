#!/bin/bash
# 生成前端 TypeScript 类型
set -e

# 1. 导出 OpenAPI schema
python scripts/export_openapi.py

# 2. 自动生成 TS 类型
npx openapi-typescript gui/openapi-schema.json -o gui/src/types/api.d.ts

echo "✅ TypeScript types generated from OpenAPI schema"
