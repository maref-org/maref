#!/bin/bash
#
# MAREF Report Synchronizer
#
# Syncs research reports from default directory to mailbox directory.
# Can be run manually or after each batch.
#
# Environment:
#   MAREF_MAILBOX_DIR - Optional. Destination mailbox directory.
#

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Default mailbox directory: uses MAREF_MAILBOX_DIR env var, or falls back to project_root/mailbox
MAILBOX_DIR="${MAREF_MAILBOX_DIR:-${PROJECT_ROOT}/mailbox}"

# Source and destination directories
SOURCE_DIR="${PROJECT_ROOT}/research_output"
DEST_DIR="${MAILBOX_DIR}/research_output"

# Create destination directory if it doesn't exist
mkdir -p "${DEST_DIR}" 2>/dev/null || true

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting report synchronization..."
echo "  Source: ${SOURCE_DIR}"
echo "  Destination: ${DEST_DIR}"

# Copy all markdown and JSON reports
rsync -av --include="*.md" --include="*.json" --exclude="*" "${SOURCE_DIR}/" "${DEST_DIR}/"

EXIT_CODE=$?

if [[ ${EXIT_CODE} -eq 0 ]]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Synchronization completed successfully."
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Synchronization failed with exit code ${EXIT_CODE}."
    exit ${EXIT_CODE}
fi

# Cleanup old files (keep last 30 days)
find "${DEST_DIR}" -name "*.md" -o -name "*.json" | sort -r | tail -n +31 | xargs rm -f 2>/dev/null || true
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Cleaned up old reports (kept last 30 days)."

exit 0
