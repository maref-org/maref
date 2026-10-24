#!/bin/sh
# Install / reload the MAREF meta-monitor launchd agent.
set -eu

ROOT="${MAREF_PROJECT_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
PLIST_SRC="$ROOT/scripts/com.maref.meta-monitor.template.plist"
PLIST_DST="$HOME/Library/LaunchAgents/com.maref.meta-monitor.plist"
LABEL="com.maref.meta-monitor"
UID_NUM="$(id -u)"

if [ ! -f "$PLIST_SRC" ]; then
    echo "missing plist: $PLIST_SRC" >&2
    exit 1
fi

if [ ! -f "$ROOT/.maraf_hmac_key" ] && [ -z "${MAREF_HMAC_SECRET_KEY:-}" ]; then
    echo "warning: no .maraf_hmac_key and no MAREF_HMAC_SECRET_KEY; audit writes will fail closed" >&2
fi

PYTHON_BIN="$ROOT/.venv/bin/python3"
[ -x "$PYTHON_BIN" ] || PYTHON_BIN="$(command -v python3)"

mkdir -p "$HOME/Library/LaunchAgents"
sed -e "s|__PROJECT_ROOT__|$ROOT|g" -e "s|__PYTHON__|$PYTHON_BIN|g" \
    "$PLIST_SRC" > "$PLIST_DST"
chmod 644 "$PLIST_DST"

launchctl bootout "gui/$UID_NUM/$LABEL" 2>/dev/null || true
sleep 2
BOOTSTRAPPED=0
# launchd can return EIO while the old KeepAlive job is still draining.
for delay in 1 2 3 5 8; do
    sleep "$delay"
    if launchctl bootstrap "gui/$UID_NUM" "$PLIST_DST" 2>/dev/null; then
        BOOTSTRAPPED=1
        break
    fi
done
if [ "$BOOTSTRAPPED" -ne 1 ]; then
    echo "failed to bootstrap $LABEL after retries" >&2
    exit 1
fi
launchctl kickstart -k "gui/$UID_NUM/$LABEL"

echo "installed $LABEL"
launchctl list | grep "$LABEL" || true
