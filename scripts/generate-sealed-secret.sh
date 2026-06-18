#!/usr/bin/env bash
set -euo pipefail

if ! command -v kubeseal &>/dev/null; then
  echo "kubeseal not found. Install from https://github.com/bitnami-labs/sealed-secrets"
  exit 1
fi

if ! kubeseal --validate 2>/dev/null; then
  echo "Sealed Secrets controller not detected. Use --controller-namespace and --controller-name if needed."
fi

kubeseal --format yaml < k8s/production/secrets.yaml > k8s/production/sealed-secret.yaml
echo "SealedSecret written to k8s/production/sealed-secret.yaml"
