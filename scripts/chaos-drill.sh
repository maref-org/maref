#!/bin/bash
set -euo pipefail

MAREF_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REPORT_DIR="$MAREF_ROOT/.chaos-reports"
SIMULATE=true

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

SCENARIOS=(
    "network-latency:NETWORK:Network latency injection"
    "network-partition:NETWORK:Network partition simulation"
    "disk-exhaustion:DISK:Disk space exhaustion"
    "disk-io-pressure:DISK:Disk IO pressure"
    "cpu-overload:CPU:CPU overload"
    "memory-pressure:MEMORY:Memory pressure"
    "process-crash:PROCESS:Process crash"
    "combined-network-cpu:NETWORK+CPU:Combined network + CPU fault"
    "agent-oscillation:NETWORK+LOGICAL:Agent state oscillation"
    "kg-corruption:DISK:KG data corruption"
    "queue-buildup:NETWORK:Message queue buildup"
    "entropy-spike:LOGICAL:Entropy spike"
)

usage() {
    echo "Usage: $0 <command> [options]"
    echo ""
    echo "Commands:"
    echo "  list                    List all available chaos scenarios"
    echo "  run     --scenario <id> Run a single chaos scenario"
    echo "  run-all                 Run all scenarios in sequence"
    echo "  report                  Generate drill report"
    echo ""
    echo "Options:"
    echo "  --scenario <id>  Scenario identifier (e.g. network-latency)"
    echo "  --no-simulate    Disable simulation mode (DANGEROUS)"
    echo ""
    echo "Examples:"
    echo "  $0 list"
    echo "  $0 run --scenario network-latency"
    echo "  $0 run-all"
    echo "  $0 report"
}

list_scenarios() {
    echo "=== MAREF Chaos Drill Scenarios ==="
    echo ""
    printf "%-24s %-16s %s\n" "ID" "Fault Type" "Description"
    printf "%-24s %-16s %s\n" "------------------------" "----------------" "----------------------------------------"
    for entry in "${SCENARIOS[@]}"; do
        IFS=':' read -r id ftype desc <<< "$entry"
        printf "%-24s %-16s %s\n" "$id" "$ftype" "$desc"
    done
    echo ""
    echo "Total: ${#SCENARIOS[@]} scenarios"
    echo "Mode: SIMULATE (safe)"
}

get_scenario_params() {
    local scenario_id=$1
    case "$scenario_id" in
        network-latency)
            echo '{"fault_type":"NETWORK","params":{"latency_ms":500,"host":"127.0.0.1","port":8080},"duration_s":5.0}'
            ;;
        network-partition)
            echo '{"fault_type":"NETWORK","params":{"drop_rate":1.0,"partition_count":2},"duration_s":5.0}'
            ;;
        disk-exhaustion)
            echo '{"fault_type":"DISK","params":{"space_mb":50,"corrupt":false},"duration_s":5.0}'
            ;;
        disk-io-pressure)
            echo '{"fault_type":"DISK","params":{"io_threads":4,"block_size_kb":1024},"duration_s":5.0}'
            ;;
        cpu-overload)
            echo '{"fault_type":"CPU","params":{"load_pct":80},"duration_s":5.0}'
            ;;
        memory-pressure)
            echo '{"fault_type":"MEMORY","params":{"pressure_mb":100},"duration_s":3.0}'
            ;;
        process-crash)
            echo '{"fault_type":"PROCESS","params":{"target":"test_worker","auto_restart":true},"duration_s":5.0}'
            ;;
        combined-network-cpu)
            echo '{"fault_type":"NETWORK","params":{"latency_ms":300,"load_pct":70},"duration_s":5.0}'
            ;;
        agent-oscillation)
            echo '{"fault_type":"NETWORK","params":{"oscillation_cycles":5,"interval_ms":100},"duration_s":5.0}'
            ;;
        kg-corruption)
            echo '{"fault_type":"DISK","params":{"space_mb":10,"corrupt":true},"duration_s":5.0}'
            ;;
        queue-buildup)
            echo '{"fault_type":"NETWORK","params":{"queue_size":100,"processing_delay_ms":500},"duration_s":5.0}'
            ;;
        entropy-spike)
            echo '{"fault_type":"MEMORY","params":{"entropy_value":4.0,"severity":"critical"},"duration_s":5.0}'
            ;;
        *)
            echo ""
            ;;
    esac
}

check_deps() {
    if ! python3 -c "import sys; sys.path.insert(0, '$MAREF_ROOT/src'); from maref.stress.chaos_engine import ChaosEngine; print('OK')" 2>/dev/null; then
        echo -e "${RED}Error: Cannot import ChaosEngine. Ensure MAREF is installed.${NC}"
        exit 1
    fi
}

run_scenario() {
    local scenario_id=$1
    local simulate_mode=${2:-true}

    check_deps

    local params
    params=$(get_scenario_params "$scenario_id")
    if [[ -z "$params" ]]; then
        echo -e "${RED}Unknown scenario: $scenario_id${NC}"
        echo "Use '$0 list' to see available scenarios"
        exit 1
    fi

    local fault_type
    fault_type=$(echo "$params" | python3 -c "import sys,json; print(json.load(sys.stdin)['fault_type'])")
    local inject_params
    inject_params=$(echo "$params" | python3 -c "import sys,json; print(json.dumps(json.load(sys.stdin)['params']))")
    local duration_s
    duration_s=$(echo "$params" | python3 -c "import sys,json; print(json.load(sys.stdin)['duration_s'])")

    mkdir -p "$REPORT_DIR"
    local report_file="$REPORT_DIR/${scenario_id}-$(date +%Y%m%d-%H%M%S).json"

    echo -e "${CYAN}========================================${NC}"
    echo -e "${CYAN}  Scenario: $scenario_id${NC}"
    echo -e "${CYAN}  Fault Type: $fault_type${NC}"
    echo -e "${CYAN}  Mode: $([ "$simulate_mode" = true ] && echo 'SIMULATE (safe)' || echo 'REAL (dangerous)')${NC}"
    echo -e "${CYAN}========================================${NC}"
    echo ""

    local py_simulate
    if [[ "$simulate_mode" == "true" ]]; then
        py_simulate="True"
    else
        py_simulate="False"
    fi

    python3 -c "
import json, sys, time
sys.path.insert(0, '$MAREF_ROOT/src')
from maref.stress.chaos_engine import ChaosEngine, FaultType

engine = ChaosEngine(simulate=$py_simulate)
params = json.loads('$inject_params')
ft = FaultType['$fault_type']

start = time.time()
event = engine.inject(ft, duration_s=$duration_s, params=params)
elapsed = time.time() - start

time.sleep(min($duration_s, 3.0))

result = {
    'scenario': '$scenario_id',
    'fault_type': ft.value,
    'simulate': $py_simulate,
    'inject_success': event.success,
    'inject_detail': event.detail,
    'duration_ms': round(elapsed * 1000, 2),
    'timestamp': time.time(),
}

with open('$report_file', 'w') as f:
    json.dump(result, f, indent=2)

if event.success:
    print(f'  Result: ${GREEN}PASS${NC}')
else:
    print(f'  Result: ${RED}FAIL${NC}')

print(f'  Detail: {event.detail}')
print(f'  Duration: {round(elapsed * 1000, 1)}ms')
print(json.dumps(result))
" || true

    echo ""
    echo -e "  Report saved: ${YELLOW}$report_file${NC}"
    echo ""
}

run_all_scenarios() {
    local simulate_mode=${1:-true}
    local total=${#SCENARIOS[@]}
    local passed=0
    local failed=0
    local summary_file="$REPORT_DIR/full-run-$(date +%Y%m%d-%H%M%S).json"

    mkdir -p "$REPORT_DIR"

    echo "============================================"
    echo "  MAREF Full Chaos Drill - $(date +%Y-%m-%d\ %H:%M)"
    echo "  Mode: SIMULATE (safe)"
    echo "  Scenarios: $total"
    echo "============================================"
    echo ""

    local results=()
    local idx=0

    for entry in "${SCENARIOS[@]}"; do
        IFS=':' read -r id ftype desc <<< "$entry"
        echo -e "${CYAN}[$((idx+1))/$total]${NC} $id - $desc"

        local params
        params=$(get_scenario_params "$id")
        local inj_params
        inj_params=$(echo "$params" | python3 -c "import sys,json; print(json.dumps(json.load(sys.stdin)['params']))")
        local ft
        ft=$(echo "$params" | python3 -c "import sys,json; print(json.load(sys.stdin)['fault_type'])")
        local ds
        ds=$(echo "$params" | python3 -c "import sys,json; print(json.load(sys.stdin)['duration_s'])")

        local py_simulate_all
        if [[ "$simulate_mode" == "true" ]]; then
            py_simulate_all="True"
        else
            py_simulate_all="False"
        fi

        local output
        output=$(python3 -c "
import json, sys, time
sys.path.insert(0, '$MAREF_ROOT/src')
from maref.stress.chaos_engine import ChaosEngine, FaultType

engine = ChaosEngine(simulate=$py_simulate_all)
params = json.loads('$inj_params')
ft = FaultType['$ft']

start = time.time()
event = engine.inject(ft, duration_s=$ds, params=params)
elapsed = time.time() - start

result = {
    'scenario': '$id',
    'fault_type': ft.value,
    'inject_success': event.success,
    'detail': event.detail,
    'duration_ms': round(elapsed * 1000, 2),
}
print(json.dumps(result))
" 2>/dev/null || echo '{"inject_success":false,"detail":"python error"}')

        local success
        success=$(echo "$output" | python3 -c "import sys,json; print(json.load(sys.stdin).get('inject_success', False))" 2>/dev/null || echo "false")

        if [[ "$success" == "True" ]]; then
            echo -e "  ${GREEN}✓ PASS${NC}"
            passed=$((passed + 1))
            results+=("$output")
        else
            echo -e "  ${RED}✗ FAIL${NC}"
            failed=$((failed + 1))
            results+=("$output")
        fi
        echo ""
        idx=$((idx + 1))
    done

    local summary
    summary=$(python3 -c "
import json
results = ${results[@]}
summary = {
    'timestamp': $(date +%s),
    'mode': 'simulate',
    'total': $total,
    'passed': $passed,
    'failed': $failed,
    'pass_rate': round($passed / $total * 100, 1),
    'results': [json.loads(r) for r in '$results'],
}
print(json.dumps(summary, indent=2))
" 2>/dev/null || echo "{}")

    echo "$summary" > "$summary_file"

    echo "============================================"
    echo -e "  Summary: ${GREEN}${passed} passed${NC} / ${RED}${failed} failed${NC} / $total total"
    echo -e "  Pass rate: $(echo "$summary" | python3 -c "import sys,json; print(json.load(sys.stdin).get('pass_rate', 0))" 2>/dev/null)%"
    echo -e "  Report: ${YELLOW}$summary_file${NC}"
    echo "============================================"
}

generate_report() {
    echo "=== MAREF Chaos Drill Report ==="
    echo ""

    if [[ ! -d "$REPORT_DIR" ]]; then
        echo -e "${YELLOW}No reports found. Run some scenarios first.${NC}"
        exit 0
    fi

    local report_files
    report_files=$(ls "$REPORT_DIR"/*.json 2>/dev/null | sort || true)
    if [[ -z "$report_files" ]]; then
        echo -e "${YELLOW}No reports found in $REPORT_DIR${NC}"
        exit 0
    fi

    local total=0
    local passed=0
    local failed=0

    echo "Drill History"
    echo "-------------"
    for f in $report_files; do
        local name
        name=$(basename "$f")
        local success
        success=$(python3 -c "import json; d=json.load(open('$f')); print(d.get('inject_success', False))" 2>/dev/null || echo "unknown")
        local detail
        detail=$(python3 -c "import json; d=json.load(open('$f')); print(d.get('inject_detail', 'N/A'))" 2>/dev/null || echo "N/A")

        if [[ "$success" == "True" ]]; then
            echo -e "  ${GREEN}✓${NC} $name - $detail"
            passed=$((passed + 1))
        elif [[ "$success" == "False" ]]; then
            echo -e "  ${RED}✗${NC} $name - $detail"
            failed=$((failed + 1))
        else
            echo -e "  ${YELLOW}?${NC} $name - $detail"
        fi
        total=$((total + 1))
    done

    echo ""
    echo "Summary"
    echo "-------"
    echo -e "  Total scenarios run: $total"
    echo -e "  Passed: ${GREEN}$passed${NC}"
    echo -e "  Failed: ${RED}$failed${NC}"
    if [[ $total -gt 0 ]]; then
        local rate
        rate=$(awk "BEGIN {printf \"%.1f\", $passed * 100 / $total}")
        echo -e "  Pass rate: ${rate}%"
    fi
}

COMMAND="${1:-help}"
shift || true

case "$COMMAND" in
    list)
        list_scenarios
        ;;
    run)
        SCENARIO_ID=""
        while [[ $# -gt 0 ]]; do
            case "$1" in
                --scenario) SCENARIO_ID="$2"; shift 2 ;;
                --no-simulate) SIMULATE=false; shift ;;
                *) echo "Unknown option: $1"; usage; exit 1 ;;
            esac
        done
        if [[ -z "$SCENARIO_ID" ]]; then
            echo "Error: --scenario is required for 'run' command"
            usage
            exit 1
        fi
        run_scenario "$SCENARIO_ID" "$SIMULATE"
        ;;
    run-all)
        while [[ $# -gt 0 ]]; do
            case "$1" in
                --no-simulate) SIMULATE=false; shift ;;
                *) echo "Unknown option: $1"; usage; exit 1 ;;
            esac
        done
        run_all_scenarios "$SIMULATE"
        ;;
    report)
        generate_report
        ;;
    help|--help|-h)
        usage
        ;;
    *)
        echo "Unknown command: $COMMAND"
        usage
        exit 1
        ;;
esac
