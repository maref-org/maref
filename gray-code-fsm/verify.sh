#!/usr/bin/env bash
# gray-code-fsm 一键验证：TLC 模型检查（10 态 + 34 态联合）+ Python validator。
#
# 用法:
#   ./verify.sh                 # 自动定位 java / tla2tools.jar（本目录 → 上级 lib → 自动下载）
#   TLC_JAR=/path/to.jar ./verify.sh
#   JAVA=/path/to/java ./verify.sh
#   SKIP_PY=1 ./verify.sh       # 跳过 Python validator
#
# 验收标准: 两个 TLC 模型均在 5 分钟内完成, 输出 "No error has been found"。

set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

# ---- locate java ----------------------------------------------------------- #
JAVA="${JAVA:-}"
if [[ -z "$JAVA" ]]; then
  # macOS system stub (/usr/bin/java) may lack a JRE; prefer brew/real runtimes.
  for cand in \
    /opt/homebrew/opt/openjdk/bin/java \
    /usr/local/opt/openjdk/bin/java \
    "$(command -v java 2>/dev/null || true)"; do
    if [[ -n "$cand" ]] && [[ -x "$cand" ]] && "$cand" -version >/dev/null 2>&1; then
      JAVA="$cand"; break
    fi
  done
fi
if [[ -z "$JAVA" ]]; then
  echo "ERROR: no Java runtime found (set JAVA=/path/to/java)" >&2
  exit 1
fi
echo "java: $JAVA"

# ---- locate tla2tools.jar -------------------------------------------------- #
TLC_JAR="${TLC_JAR:-}"
if [[ -z "$TLC_JAR" ]]; then
  for cand in "$DIR/tla2tools.jar" "$DIR/../lib/tla2tools.jar"; do
    if [[ -f "$cand" ]]; then TLC_JAR="$cand"; break; fi
  done
fi
if [[ -z "$TLC_JAR" ]]; then
  echo "Downloading tla2tools.jar (TLC 2.19)..."
  curl -sL "https://github.com/tlaplus/tlaplus/releases/download/v1.19.1/tla2tools.jar" -o "$DIR/tla2tools.jar"
  TLC_JAR="$DIR/tla2tools.jar"
fi
echo "tlc jar: $TLC_JAR"

# ---- TLC model checking ---------------------------------------------------- #
fail=0

run_tlc() {
  local cfg="$1" mod="$2"
  echo "==> TLC model: $mod"
  local out
  out="$("$JAVA" -XX:+UseParallelGC -cp "$TLC_JAR" tlc2.TLC -config "$cfg" "$mod" 2>&1)" || true
  if echo "$out" | grep -qE "Error:|Violated"; then
    echo "    FAILED: $mod" >&2
    echo "$out" | grep -E "Error:|Violated" | head -5 >&2
    fail=1
  else
    echo "$out" | grep -E "states generated|No error" | tail -2 | sed 's/^/    /'
    echo "    PASS: $mod"
  fi
}

run_tlc MarefLiteMC.cfg MarefLiteModel
run_tlc MarefJoint34MC.cfg MarefJoint34

# ---- Python validator ------------------------------------------------------ #
if [[ "${SKIP_PY:-0}" != "1" ]]; then
  echo "==> Python validator"
  if ! python3 validator.py; then
    fail=1
  fi
fi

echo "================================================================"
if [[ "$fail" == "0" ]]; then
  echo "All gray-code-fsm checks PASSED."
else
  echo "Some checks FAILED." >&2
fi
echo "================================================================"
exit "$fail"
