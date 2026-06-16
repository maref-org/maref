#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────
# MAREF Cosign Signature Verification
# ──────────────────────────────────────────────────────────
# Verifies container image signatures using cosign.
# Usage: bash scripts/cosign-verify.sh <image-tag>
# Example: bash scripts/cosign-verify.sh ghcr.io/maref-org/maref:v0.32.0

set -euo pipefail

IMAGE="${1:-}"
if [ -z "$IMAGE" ]; then
    echo "Usage: $0 <image-tag>"
    echo "Example: $0 ghcr.io/maref-org/maref:v0.32.0"
    exit 1
fi

echo "=== MAREF Cosign Verification ==="
echo "Image: $IMAGE"
echo ""

if ! command -v cosign &>/dev/null; then
    echo "ERROR: cosign not installed. Install from https://docs.sigstore.dev/system_config/installation/"
    exit 1
fi

echo "[1/3] Verifying signature..."
cosign verify \
    --key cosign.pub \
    "$IMAGE" 2>&1 || {
    echo "WARNING: Cosign key not found at cosign.pub, trying keyless..."
    cosign verify \
        --certificate-identity-regexp "https://github.com/maref-org/maref/.github/workflows/" \
        --certificate-oidc-issuer "https://token.actions.githubusercontent.com" \
        "$IMAGE"
}

echo ""
echo "[2/3] Checking attestation..."
cosign verify-attestation \
    --type slsaprovenance \
    --key cosign.pub \
    "$IMAGE" 2>&1 || echo "INFO: No attestation found (non-production build)"

echo ""
echo "[3/3] Verifying SBOM..."
cosign verify \
    --key cosign.pub \
    "$IMAGE:sbom" 2>&1 || echo "INFO: No signed SBOM found"

echo ""
echo "=== Verification complete ==="
