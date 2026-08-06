#!/bin/bash
# RSI 完整每日循环
set -euo pipefail

TAG="rsi-$(date +%Y%m%d-%H%M)"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "[RSI] Starting daily loop: $TAG"

cd "$ROOT"

# Phase 0/1: 多目标 Ratchet 运行
for TARGET in prompts/distill_v1.yaml prompts/project_v1.yaml config/quality_config.yaml; do
    echo "[RSI] Target: $TARGET (3 rounds)"
    uv run maref percv ratchet \
        --target "$TARGET" \
        --rounds 3 \
        --mas-ts \
        --tag "$TAG-$TARGET"
done

# Phase 1: 触发学习循环
uv run maref percv learn

# Phase 2: 跨维度分析
uv run maref percv cross-analyze --window 20

# Phase 3: 元 Ratchet — 检测改进停滞
echo "[RSI] Checking meta-ratchet triggers..."
uv run maref percv meta-diagnose \
    --tag "$TAG"

# 如果有诊断结果，执行沙箱测试
if [ -f ".meta_ratchet_diagnosis.json" ]; then
    echo "[RSI] Protocol change proposed, running sandbox..."
    uv run maref percv meta-sandbox \
        --diagnosis ".meta_ratchet_diagnosis.json" \
        --rounds 10
fi

# Phase 3: 生成 RSI 报告
uv run maref percv rsi-report --output "reports/rsi-$(date +%Y%m%d).md"

# Phase 4: 生成 EvolutionVault 仪表板
echo "[RSI] Generating EvolutionVault dashboard..."
uv run maref percv vault-dashboard --vault "vault" --output "reports/dashboard-$(date +%Y%m%d).html" || true

echo "[RSI] Daily loop complete: $TAG"
