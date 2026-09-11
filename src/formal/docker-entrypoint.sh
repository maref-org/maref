#!/bin/sh
set -e

JAVA_OPTS="${JAVA_OPTS:--Xmx2g}"
TLC_JAR="${TLC_JAR:-/usr/local/lib/tla2tools.jar}"
SPEC_DIR="${SPEC_DIR:-/specs}"

run_tlc() {
    local spec="$1"
    local config="$2"
    local label="${3:-$spec}"

    echo "=== TLC: $label ==="
    echo "Spec:   $SPEC_DIR/$spec"
    echo "Config: $SPEC_DIR/$config"

    cd "$SPEC_DIR"

    if java $JAVA_OPTS -cp "$TLC_JAR" tlc2.TLC \
        -config "$config" \
        -deadlock \
        -terse \
        "$spec" 2>&1; then
        echo "=== PASS: $label ==="
        return 0
    else
        echo "=== FAIL: $label ==="
        return 1
    fi
}

FAILED=0

case "${1:-all}" in
    all)
        echo "=== TLC Model Checker — MAREF Formal Verification ==="
        echo ""

        run_tlc "MarefLiteModel.tla" "MarefLiteMC.cfg" "MarefLite (Gray Code FSM)" || FAILED=$((FAILED + 1))
        echo ""

        run_tlc "MAREF_ConstitutionalRedLines.tla" "MAREF_ConstitutionalRedLinesMC.cfg" \
            "Constitutional Red Lines (5 Invariants)" || FAILED=$((FAILED + 1))
        echo ""

        run_tlc "MAREF_Consensus.tla" "MAREF_ConsensusMC.cfg" "Consensus" || FAILED=$((FAILED + 1))
        echo ""

        run_tlc "MAREF_TestIntegration.tla" "MAREF_TestIntegrationMC.cfg" "Test Integration" || FAILED=$((FAILED + 1))
        echo ""

        run_tlc "MAREF_CrossInstance.tla" "MAREF_CrossDimModel.cfg" "Cross-Instance" || FAILED=$((FAILED + 1))
        echo ""

        run_tlc "Vortex369.tla" "Vortex369MC.cfg" "369 Digital Root Theorems (7 Invariants)" || FAILED=$((FAILED + 1))

        echo ""
        echo "=== Summary ==="
        if [ "$FAILED" -eq 0 ]; then
            echo "All specifications verified ✅"
        else
            echo "$FAILED specification(s) failed ❌"
        fi
        ;;

    list)
        echo "Available specs:"
        for spec in "$SPEC_DIR"/*.tla; do
            base=$(basename "$spec" .tla)
            cfg="${SPEC_DIR}/${base}MC.cfg"
            if [ -f "$cfg" ]; then
                echo "  $base (config: ${base}MC.cfg)"
            else
                echo "  $base (no config)"
            fi
        done
        ;;

    *)
        spec_path="${SPEC_DIR}/${1}.tla"
        cfg_path="${SPEC_DIR}/${1}MC.cfg"

        if [ ! -f "$spec_path" ]; then
            echo "Error: spec '$1' not found at $spec_path"
            echo "Use 'list' to see available specs"
            exit 1
        fi
        if [ ! -f "$cfg_path" ]; then
            echo "Error: config '$cfg_path' not found"
            exit 1
        fi
        run_tlc "${1}.tla" "${1}MC.cfg" "$1" || exit 1
        ;;
esac

exit "$FAILED"
