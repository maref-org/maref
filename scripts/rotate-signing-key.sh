#!/usr/bin/env bash
# rotate-signing-key.sh — Generate a new maref-report-signing key pair and rotate
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
KEY_DIR="${KEY_DIR:-"$PROJECT_DIR"}"
BACKUP_DIR="${KEY_DIR}/key-backups"

# Current key info
CURRENT_KEY="${KEY_DIR}/maref-report-signing.pem"
CURRENT_FP="${KEY_DIR}/fingerprint.txt"

echo "=== MAREF Report Signing Key Rotation ==="
echo "  Key directory: $KEY_DIR"
echo ""

# Check if current key exists
if [ -f "$CURRENT_KEY" ]; then
    echo "[*] Current key found at: $CURRENT_KEY"
    mkdir -p "$BACKUP_DIR"
    TIMESTAMP=$(date -u +"%Y%m%dT%H%M%SZ")
    cp "$CURRENT_KEY" "${BACKUP_DIR}/maref-report-signing-${TIMESTAMP}.pem"
    cp "${KEY_DIR}/maref-report-signing.pub" "${BACKUP_DIR}/maref-report-signing-${TIMESTAMP}.pub"
    echo "[*] Backed up to: ${BACKUP_DIR}/maref-report-signing-${TIMESTAMP}.pem"
fi

echo "[*] Generating new key pair..."

python3 -c "
from maref.signing.signing_key import ReportSigningKey
import getpass
import sys

encrypt = input('Encrypt private key with password? (y/N): ').strip().lower()
if encrypt == 'y':
    key = ReportSigningKey.init_key_pair('${KEY_DIR}', encrypt=True)
    print(f'  Fingerprint: {key.fingerprint}')
    print(f'  Private key: ${KEY_DIR}/maref-report-signing.pem (encrypted, chmod 600)')
else:
    key = ReportSigningKey.init_key_pair('${KEY_DIR}')
    print(f'  Fingerprint: {key.fingerprint}')
    print(f'  Private key: ${KEY_DIR}/maref-report-signing.pem (unencrypted, chmod 600)')

print(f'  Public key:  ${KEY_DIR}/maref-report-signing.pub')
print(f'  Fingerprint written to: ${KEY_DIR}/fingerprint.txt')
"

echo ""
echo "=== Rotation complete ==="
echo ""
echo "Next steps:"
echo "  1. Push docs/verify/ to publish the new fingerprint"
echo "  2. Run: maref report generate --signing-key ${KEY_DIR}/maref-report-signing.pem"
echo "  3. Update any services that trust the old key"
echo ""
echo "WARNING: Keep backups of the old key until all outstanding reports"
echo "have been verified or expired."
