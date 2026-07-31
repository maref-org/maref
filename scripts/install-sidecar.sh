#!/usr/bin/env bash
#
# MAREF Sidecar — one-key installer.
#
# Usage:
#   curl -fsSL https://get.maref.dev | sh
#
# Installs the packaged `maref-sidecar` binary to ~/.local/bin (macOS/Linux)
# and verifies it with GET /api/health.
#
# Binary source order:
#   1. Local dev build  (./dist/maref-sidecar, when run from the repo)
#   2. GitHub Releases  (maref-org/maref, tag v*)
#
set -euo pipefail

REPO="maref-org/maref"
BIN_NAME="maref-sidecar"
INSTALL_DIR="${MAREF_INSTALL_DIR:-$HOME/.local/bin}"
VERSION="${MAREF_VERSION:-latest}"

color() { if [ -t 1 ]; then printf "%s" "$2"; fi; }
green() { color "$1" "$(printf '\033[32m')"; }
red() { color "$1" "$(printf '\033[31m')"; }
reset() { color "$1" "$(printf '\033[0m')"; }

say() { printf "%s%s%s\n" "$(green 1)" "$1" "$(reset 1)"; }
err() { printf "%s%s%s\n" "$(red 1)" "$1" "$(reset 1)" >&2; }

os="$(uname -s | tr '[:upper:]' '[:lower:]')"
arch="$(uname -m)"
case "$arch" in
    x86_64|amd64) arch="x86_64" ;;
    arm64|aarch64) arch="arm64" ;;
    *) err "Unsupported architecture: $arch"; exit 1 ;;
esac

echo ""
say "MAREF Sidecar Installer"
echo "  OS:   $os"
echo "  Arch: $arch"
echo "  Dest: $INSTALL_DIR"
echo ""

mkdir -p "$INSTALL_DIR"
TARGET="$INSTALL_DIR/$BIN_NAME"
TMP="$(mktemp -d /tmp/maref-install.XXXXXX)"
trap 'rm -rf "$TMP"' EXIT

# 1. Local dev build first
SRC=""
if [ -f "$PWD/dist/$BIN_NAME" ]; then
    SRC="$PWD/dist/$BIN_NAME"
    say "[1/3] Using local dev build: $SRC"
else
    URL="https://github.com/$REPO/releases/$VERSION/download/$BIN_NAME-$os-$arch"
    say "[1/3] Downloading $URL"
    if ! curl -fsSL --retry 3 --max-time 60 -o "$TMP/$BIN_NAME" "$URL"; then
        # Fallback: legacy unified binary name
        URL="https://github.com/$REPO/releases/$VERSION/download/$BIN_NAME"
        say "    fallback: $URL"
        curl -fsSL --retry 3 --max-time 60 -o "$TMP/$BIN_NAME" "$URL"
    fi
    SRC="$TMP/$BIN_NAME"
fi

# 2. Install
say "[2/3] Installing to $TARGET"
install -m 0755 "$SRC" "$TARGET"

# 3. Verify: start server, hit /api/health, stop
say "[3/3] Verifying /api/health ..."
PORT=8910
VERIFY_HOME="$(mktemp -d /tmp/maref-verify.XXXXXX)"
HOME="$VERIFY_HOME" "$TARGET" --port "$PORT" --host 127.0.0.1 >"$TMP/server.log" 2>&1 &
PID=$!
HEALTH=""
# onefile extraction of the ~75MB payload can take several seconds
sleep 3
for _ in 1 2 3 4 5 6 7 8 9 10; do
    HEALTH="$(curl -s --max-time 2 "http://127.0.0.1:$PORT/api/health" 2>/dev/null || echo "")"
    [ -n "$HEALTH" ] && break
    sleep 2
done
kill "$PID" 2>/dev/null || true
wait "$PID" 2>/dev/null || true
rm -rf "$VERIFY_HOME"

if echo "$HEALTH" | grep -q "healthy"; then
    say "Installed and verified: $TARGET"
    echo ""
    echo "  Run:   maref-sidecar --port 8000"
    echo "  Note:  Ensure $INSTALL_DIR is on your PATH:"
    echo "         export PATH=\"$INSTALL_DIR:\$PATH\""
    echo ""
else
    err "Install failed: /api/health did not respond. Server log:"
    cat "$TMP/server.log" 2>/dev/null || true
    exit 1
fi
