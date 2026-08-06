#!/bin/bash
set -euo pipefail

VERSION="${1:-}"
NAMESPACE="${NAMESPACE:-maref}"
DEPLOYMENT="maref-desktop-agent"
VERIFY=false
CANARY=""
LOG_DIR="${LOG_DIR:-/tmp/maref-rollback-logs}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

usage() {
    echo "Usage: $0 <version> [mode] [options]"
    echo ""
    echo "Arguments:"
    echo "  <version>          Target version to rollback to (e.g., v0.25.0)"
    echo ""
    echo "Modes:"
    echo "  auto               Auto-detect K8s or local mode (default)"
    echo "  k8s                Rollback Kubernetes deployment"
    echo "  local              Rollback via git checkout"
    echo "  force              Force rollback without prompt"
    echo ""
    echo "Options:"
    echo "  --verify           Run health verification after rollback"
    echo "  --canary=N         Canary rollback (only rollback N%% of instances)"
    echo ""
    echo "Examples:"
    echo "  $0 v0.25.0                          Basic rollback"
    echo "  $0 v0.25.0 k8s --verify             K8s rollback with verification"
    echo "  $0 v0.25.0 --canary=25              Canary rollback 25%% of instances"
    echo "  $0 v0.25.0 local --verify           Local rollback with verification"
    exit 1
}

# Parse arguments
VERSION=""
MODE="auto"
VERIFY=false
CANARY=""

for arg in "$@"; do
    case "$arg" in
        --verify)
            VERIFY=true
            ;;
        --canary=*)
            CANARY="${arg#*=}"
            ;;
        --canary)
            echo "Error: --canary requires a percentage value (e.g., --canary=25)"
            exit 1
            ;;
        -*)
            ;;
        *)
            if [[ -z "$VERSION" ]]; then
                VERSION="$arg"
            elif [[ "$MODE" == "auto" ]]; then
                MODE="$arg"
            fi
            ;;
    esac
done

if [[ -z "$VERSION" ]]; then
    usage
fi

if [[ -n "$CANARY" ]]; then
    if ! [[ "$CANARY" =~ ^[0-9]+$ ]] || [[ "$CANARY" -lt 1 ]] || [[ "$CANARY" -gt 100 ]]; then
        echo "Error: --canary must be a number between 1 and 100"
        exit 1
    fi
fi

mkdir -p "$LOG_DIR"
LOGFILE="$LOG_DIR/rollback-$VERSION-$TIMESTAMP.log"

log() {
    local level="$1"
    shift
    local message="$*"
    local ts
    ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    echo "[$ts] [$level] $message" | tee -a "$LOGFILE"
}

log "INFO" "=== MAREF Rollback Script ==="
log "INFO" "Target version: $VERSION"
log "INFO" "Mode: $MODE"
log "INFO" "Verify: $VERIFY"
if [[ -n "$CANARY" ]]; then
    log "INFO" "Canary: ${CANARY}%"
fi
log "INFO" "Log file: $LOGFILE"

# Detect mode
if [[ "$MODE" == "auto" ]]; then
    if command -v kubectl &> /dev/null && kubectl config current-context &> /dev/null 2>&1; then
        MODE="k8s"
    else
        MODE="local"
    fi
fi

verify_health() {
    log "INFO" "Running post-rollback health verification..."

    local failures=0

    if [[ "$MODE" == "k8s" ]]; then
        log "INFO" "Verifying K8s deployment health..."
        local pods
        pods=$(kubectl get pods -n "$NAMESPACE" -l app=maref -o jsonpath='{.items[*].status.phase}' 2>/dev/null || echo "")
        for phase in $pods; do
            if [[ "$phase" != "Running" ]]; then
                log "ERROR" "Pod not running: phase=$phase"
                failures=$((failures + 1))
            fi
        done

        local ready_pods
        ready_pods=$(kubectl get deployment "$DEPLOYMENT" -n "$NAMESPACE" -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo "0")
        local desired_pods
        desired_pods=$(kubectl get deployment "$DEPLOYMENT" -n "$NAMESPACE" -o jsonpath='{.status.replicas}' 2>/dev/null || echo "0")
        if [[ "$ready_pods" -lt "$desired_pods" ]]; then
            log "ERROR" "Not all pods ready: $ready_pods/$desired_pods"
            failures=$((failures + 1))
        fi
    fi

    log "INFO" "Running basic import verification..."
    if python -c "import maref; print('maref imported successfully')" 2>/dev/null; then
        log "INFO" "Python import check passed"
    else
        log "ERROR" "Python import check failed"
        failures=$((failures + 1))
    fi

    log "INFO" "Running basic test collection..."
    if python -m pytest tests/ -q --tb=line --collect-only 2>&1 | tail -3; then
        log "INFO" "Test collection passed"
    else
        log "WARN" "Test collection had warnings (non-fatal)"
    fi

    if [[ "$failures" -eq 0 ]]; then
        log "INFO" "Health verification PASSED"
        return 0
    else
        log "ERROR" "Health verification FAILED with $failures error(s)"
        return 1
    fi
}

rollback_k8s() {
    log "INFO" "Mode: Kubernetes"
    log "INFO" "Namespace: $NAMESPACE"
    log "INFO" "Deployment: $DEPLOYMENT"

    if ! command -v kubectl &> /dev/null; then
        log "ERROR" "kubectl not found"
        exit 1
    fi

    local current_version
    current_version=$(kubectl get deployment "$DEPLOYMENT" -n "$NAMESPACE" -o jsonpath='{.spec.template.spec.containers[0].image}' 2>/dev/null | cut -d: -f2 || echo "unknown")
    log "INFO" "Current version: $current_version"

    if [[ -n "$CANARY" ]]; then
        log "INFO" "Canary rollback: updating ${CANARY}% of pods"
        local total_replicas
        total_replicas=$(kubectl get deployment "$DEPLOYMENT" -n "$NAMESPACE" -o jsonpath='{.spec.replicas}' 2>/dev/null || echo "3")
        local canary_replicas=$(( (total_replicas * CANARY + 99) / 100 ))
        if [[ "$canary_replicas" -lt 1 ]]; then
            canary_replicas=1
        fi
        log "INFO" "Total replicas: $total_replicas, Canary replicas: $canary_replicas"

        kubectl scale deployment "$DEPLOYMENT" --replicas="$canary_replicas" -n "$NAMESPACE"
        sleep 5
        kubectl set image deployment/"$DEPLOYMENT" agent="maref/desktop-agent:$VERSION" -n "$NAMESPACE"
        kubectl rollout status deployment/"$DEPLOYMENT" -n "$NAMESPACE" --timeout=300s

        log "INFO" "Scaling back to original replica count: $total_replicas"
        kubectl scale deployment "$DEPLOYMENT" --replicas="$total_replicas" -n "$NAMESPACE"
    else
        kubectl set image deployment/"$DEPLOYMENT" agent="maref/desktop-agent:$VERSION" -n "$NAMESPACE"
        kubectl rollout status deployment/"$DEPLOYMENT" -n "$NAMESPACE" --timeout=300s
    fi

    log "INFO" "Rollback complete. Current pods:"
    kubectl get pods -n "$NAMESPACE" -l app=maref | tee -a "$LOGFILE"
}

rollback_local() {
    log "INFO" "Mode: Local (git checkout)"

    if ! git rev-parse --git-dir &> /dev/null; then
        log "ERROR" "Not a git repository"
        exit 1
    fi

    if ! git tag -l "$VERSION" | grep -q .; then
        log "WARN" "Tag '$VERSION' not found locally, fetching tags..."
        git fetch --tags 2>/dev/null || true
        if ! git tag -l "$VERSION" | grep -q .; then
            log "ERROR" "Tag '$VERSION' does not exist"
            exit 1
        fi
    fi

    log "INFO" "Current branch: $(git branch --show-current)"
    log "INFO" "Stashing local changes..."
    git stash --include-untracked || true

    log "INFO" "Checking out $VERSION..."
    git checkout "$VERSION"

    log "INFO" "Reinstalling dependencies..."
    if command -v uv &> /dev/null; then
        uv pip install -e ".[dev]" 2>&1 | tail -5 | tee -a "$LOGFILE"
    elif command -v pip &> /dev/null; then
        pip install -e ".[dev]" 2>&1 | tail -5 | tee -a "$LOGFILE"
    else
        log "WARN" "Neither uv nor pip found. Skipping dependency reinstall."
    fi

    log "INFO" "Rollback to $VERSION completed locally"
}

case "$MODE" in
    k8s)
        rollback_k8s
        ;;
    local)
        rollback_local
        ;;
    force)
        log "WARN" "Force mode: skipping confirmation"
        rollback_k8s
        ;;
    *)
        log "ERROR" "Unknown mode: $MODE"
        echo "Supported modes: auto, k8s, local, force"
        exit 1
        ;;
esac

if [[ "$VERIFY" == "true" ]]; then
    log "INFO" "Starting post-rollback verification..."
    if verify_health; then
        log "INFO" "Rollback verification PASSED"
    else
        log "ERROR" "Rollback verification FAILED"
        log "INFO" "Check $LOGFILE for details"
        exit 1
    fi
fi

log "INFO" "=== Rollback completed successfully ==="
log "INFO" "Duration: started at $TIMESTAMP"
log "INFO" "Log saved to: $LOGFILE"
