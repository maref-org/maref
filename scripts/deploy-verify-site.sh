#!/usr/bin/env bash
# deploy-verify-site.sh — Export latest GovernanceReport to docs/verify/ for maref.cc/verify
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

AUDIT_LOG="${AUDIT_LOG:-}"
SIGNING_KEY="${SIGNING_KEY:-}"
OUTPUT_DIR="${OUTPUT_DIR:-"$PROJECT_DIR/docs/verify"}"

if [ -z "$AUDIT_LOG" ]; then
  # Find the most recent audit log
  AUDIT_LOG=$(ls -t "$PROJECT_DIR"/*.jsonl 2>/dev/null | head -1 || true)
  if [ -z "$AUDIT_LOG" ]; then
    echo "ERROR: No audit log found. Set AUDIT_LOG env var or place a .jsonl file in project root."
    exit 1
  fi
fi

if [ -z "$SIGNING_KEY" ]; then
  SIGNING_KEY="$PROJECT_DIR/maref-report-signing.pem"
  if [ ! -f "$SIGNING_KEY" ]; then
    echo "WARNING: No signing key found at $SIGNING_KEY."
    echo "  Generating ephemeral key for testing."
    SIGNING_KEY=""
  fi
fi

mkdir -p "$OUTPUT_DIR"

KEY_ARGS=""
if [ -n "$SIGNING_KEY" ]; then
  KEY_ARGS="--signing-key $SIGNING_KEY"
fi

REPORT_FILE="$OUTPUT_DIR/latest.json"

cd "$PROJECT_DIR"

echo "=== Generating GovernanceReport ==="
python3 -m maref_lite.cli report generate \
  --audit-log "$AUDIT_LOG" \
  $KEY_ARGS \
  --output "$REPORT_FILE"

echo "=== Verifying GovernanceReport ==="
if [ -n "$SIGNING_KEY" ]; then
  PUBKEY="${SIGNING_KEY%.pem}.pub"
  if [ -f "$PUBKEY" ]; then
    python3 -m maref_lite.cli report verify \
      --file "$REPORT_FILE" \
      --pubkey "$PUBKEY"
  else
    echo "WARNING: Public key not found at $PUBKEY — skipping verification."
  fi
fi

echo "=== Exporting HTML ==="
python3 -m maref_lite.cli report export \
  --file "$REPORT_FILE" \
  --format html \
  --output "$OUTPUT_DIR/latest.html"

# Copy JSON with human-readable name
TIMESTAMP=$(date -u +"%Y%m%dT%H%M%SZ")
cp "$REPORT_FILE" "$OUTPUT_DIR/report-${TIMESTAMP}.json"

echo "=== Building index page ==="
python3 -c "
from maref.reporting.exporter import ReportExporter
from pathlib import Path
exporter = ReportExporter()
fp = ''
fp_path = Path('$OUTPUT_DIR/fingerprint.txt')
if fp_path.exists():
    fp = fp_path.read_text().strip()
exporter.export_index(Path('$OUTPUT_DIR'), Path('$OUTPUT_DIR/index.html'), signer_fingerprint=fp)
"

echo "=== Copying fingerprint ==="
if [ -n "$SIGNING_KEY" ] && [ -f "${SIGNING_KEY%.pem}.pub" ]; then
  python3 -c "
from maref.signing.signing_key import ReportSigningKey
key = ReportSigningKey.from_private_key_file('$SIGNING_KEY')
Path('$OUTPUT_DIR/fingerprint.txt').write_text(key.fingerprint + chr(10))
" 2>/dev/null || true
fi

echo ""
echo "=== Deploy complete ==="
echo "  HTML:    $OUTPUT_DIR/latest.html"
echo "  JSON:    $OUTPUT_DIR/latest.json"
echo "  Index:   $OUTPUT_DIR/index.html"
echo "  Fingerprint: $OUTPUT_DIR/fingerprint.txt"
echo ""
echo "To deploy to maref.cc/verify, push docs/verify/ to the production branch."
