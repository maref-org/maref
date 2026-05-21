#!/bin/bash
set -euo pipefail

MAREF_ROOT="${MAREF_TEST_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
BACKUP_ROOT="${MAREF_BACKUP_ROOT:-$MAREF_ROOT/backups}"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
BACKUP_NAME=""
BACKUP_FILE=""

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

RETENTION_DAILY="${MAREF_BACKUP_RETENTION_DAILY:-7}"
RETENTION_WEEKLY="${MAREF_BACKUP_RETENTION_WEEKLY:-4}"
RETENTION_MONTHLY="${MAREF_BACKUP_RETENTION_MONTHLY:-6}"
VERIFY="${MAREF_BACKUP_VERIFY:-true}"

BACKUP_DIRS=(
    "$MAREF_ROOT/data"
    "$MAREF_ROOT/config"
    "$MAREF_ROOT/logs"
)

usage() {
    echo "Usage: $0 --mode <mode> [options]"
    echo ""
    echo "Modes:"
    echo "  full            Perform full backup"
    echo "  incremental     Perform incremental backup"
    echo "  restore         Restore from backup"
    echo "  list            List available backups"
    echo "  clean           Clean expired backups"
    echo ""
    echo "Options:"
    echo "  --mode <mode>       Backup mode (required)"
    echo "  --backup-file <path> Backup file path for restore mode"
    echo "  --verify            Verify backup after creation"
    echo "  --weekly            Mark backup as weekly retention"
    echo "  --monthly           Mark backup as monthly retention"
    echo ""
    echo "Examples:"
    echo "  $0 --mode full"
    echo "  $0 --mode incremental"
    echo "  $0 --mode restore --backup-file ./backups/daily/maref-backup-full-20260520-020000.tar.gz"
    echo "  $0 --mode list"
    echo "  $0 --mode clean"
}

check_dirs() {
    local missing=0
    for dir in "${BACKUP_DIRS[@]}"; do
        if [[ ! -d "$dir" ]]; then
            echo -e "${YELLOW}Warning: Backup directory not found: $dir${NC}"
        fi
    done
}

init_backup_dirs() {
    mkdir -p "$BACKUP_ROOT"/{daily,weekly,monthly,incremental}
}

do_full_backup() {
    local label=${1:-daily}
    local target_dir="$BACKUP_ROOT/$label"
    mkdir -p "$target_dir"

    check_dirs

    BACKUP_NAME="maref-backup-full-${TIMESTAMP}.tar.gz"
    local backup_path="$target_dir/$BACKUP_NAME"

    echo -e "${CYAN}=== MAREF Full Backup ===${NC}"
    echo "  Timestamp: $TIMESTAMP"
    echo "  Label: $label"
    echo "  Target: $backup_path"
    echo ""

    local tar_args=()
    for dir in "${BACKUP_DIRS[@]}"; do
        if [[ -d "$dir" ]]; then
            local rel_path
            rel_path=$(python3 -c "import os; print(os.path.relpath('$dir', '$MAREF_ROOT'))")
            tar_args+=("$rel_path")
            echo "  Adding: $rel_path"
        fi
    done

    if [[ ${#tar_args[@]} -eq 0 ]]; then
        echo -e "${YELLOW}No directories to backup. Creating empty archive.${NC}"
    fi

    if [[ ${#tar_args[@]} -gt 0 ]]; then
        tar -czf "$backup_path" -C "$MAREF_ROOT" "${tar_args[@]}"
    else
        tar -czf "$backup_path" --files-from /dev/null
    fi

    local size
    size=$(du -h "$backup_path" | cut -f1)
    echo ""
    echo -e "  Backup created: ${GREEN}$backup_path${NC}"
    echo "  Size: $size"

    if [[ "$VERIFY" == "true" ]]; then
        verify_backup "$backup_path"
    fi

    echo -e "${GREEN}=== Full backup completed ===${NC}"
}

do_incremental_backup() {
    local target_dir="$BACKUP_ROOT/incremental"
    mkdir -p "$target_dir"

    check_dirs

    BACKUP_NAME="maref-backup-inc-${TIMESTAMP}.tar.gz"
    local backup_path="$target_dir/$BACKUP_NAME"

    local latest_full
    latest_full=$(ls -t "$BACKUP_ROOT"/daily/maref-backup-full-*.tar.gz 2>/dev/null | head -1 || echo "")

    if [[ -z "$latest_full" ]]; then
        echo -e "${YELLOW}No full backup found. Falling back to full backup.${NC}"
        do_full_backup "daily"
        return
    fi

    echo -e "${CYAN}=== MAREF Incremental Backup ===${NC}"
    echo "  Timestamp: $TIMESTAMP"
    echo "  Based on: $(basename "$latest_full")"
    echo "  Target: $backup_path"
    echo ""

    local full_timestamp
    full_timestamp=$(echo "$latest_full" | grep -oE '[0-9]{8}-[0-9]{6}' | head -1 || echo "19700101-000000")
    local full_date
    full_date=$(echo "$full_timestamp" | cut -d- -f1)

    local tar_args=()
    for dir in "${BACKUP_DIRS[@]}"; do
        if [[ -d "$dir" ]]; then
            local rel_path
            rel_path=$(python3 -c "import os; print(os.path.relpath('$dir', '$MAREF_ROOT'))")
            local changed_files
            changed_files=$(find "$dir" -type f -newer "$latest_full" 2>/dev/null || true)
            if [[ -n "$changed_files" ]]; then
                tar_args+=("$rel_path")
                echo "  Changed: $rel_path"
            fi
        fi
    done

    if [[ ${#tar_args[@]} -eq 0 ]]; then
        echo -e "${YELLOW}No files changed since last full backup.${NC}"
        touch "$backup_path"
        echo "  Created empty incremental backup marker."
    else
        tar -czf "$backup_path" -C "$MAREF_ROOT" "${tar_args[@]}"
    fi

    local size
    size=$(du -h "$backup_path" 2>/dev/null | cut -f1 || echo "0B")
    echo ""
    echo -e "  Backup created: ${GREEN}$backup_path${NC}"
    echo "  Size: $size"

    if [[ "$VERIFY" == "true" ]]; then
        verify_backup "$backup_path"
    fi

    echo -e "${GREEN}=== Incremental backup completed ===${NC}"
}

do_restore() {
    if [[ ! -f "$BACKUP_FILE" ]]; then
        echo -e "${RED}Error: Backup file not found: $BACKUP_FILE${NC}"
        exit 1
    fi

    echo -e "${CYAN}=== MAREF Restore ===${NC}"
    echo "  Backup: $BACKUP_FILE"
    echo ""

    local restore_dir="$MAREF_ROOT/.restore-tmp"
    mkdir -p "$restore_dir"

    echo "  Extracting to temporary directory..."
    tar -xzf "$BACKUP_FILE" -C "$restore_dir"

    local file_count
    file_count=$(find "$restore_dir" -type f 2>/dev/null | wc -l)
    echo "  Extracted $file_count files"

    echo ""
    echo -e "${YELLOW}  Would restore to: $MAREF_ROOT${NC}"
    echo "  To apply: cp -r $restore_dir/* $MAREF_ROOT/"
    echo ""

    echo "  Verifying restore..."
    verify_restore "$restore_dir"

    rm -rf "$restore_dir"
    echo -e "${GREEN}=== Restore verification completed ===${NC}"
}

list_backups() {
    echo -e "${CYAN}=== MAREF Backups ===${NC}"
    echo ""

    for category in daily weekly monthly incremental; do
        local dir="$BACKUP_ROOT/$category"
        echo -e "${YELLOW}[$category]${NC}"
        if [[ -d "$dir" ]]; then
            local count
            count=$(ls "$dir"/*.tar.gz 2>/dev/null | wc -l || echo 0)
            if [[ "$count" -gt 0 ]]; then
                ls -lh "$dir"/*.tar.gz 2>/dev/null | awk '{printf "  %s %s %s\n", $6, $7, $9}'
            else
                echo "  (empty)"
            fi
        else
            echo "  (not found)"
        fi
        echo ""
    done

    local total_size
    total_size=$(du -sh "$BACKUP_ROOT" 2>/dev/null | cut -f1 || echo "0B")
    echo "Total backup size: $total_size"
}

clean_backups() {
    echo -e "${CYAN}=== MAREF Backup Cleanup ===${NC}"
    echo ""

    local cleaned=0

    local daily_dir="$BACKUP_ROOT/daily"
    if [[ -d "$daily_dir" ]]; then
        local daily_count
        daily_count=$(ls "$daily_dir"/*.tar.gz 2>/dev/null | wc -l || echo 0)
        if [[ "$daily_count" -gt "$RETENTION_DAILY" ]]; then
            local to_remove=$((daily_count - RETENTION_DAILY))
            echo "  Daily: keeping $RETENTION_DAILY, removing $to_remove"
            ls -t "$daily_dir"/*.tar.gz 2>/dev/null | tail -n "$to_remove" | while read -r f; do
                rm -f "$f"
                echo "    Removed: $(basename "$f")"
                cleaned=$((cleaned + 1))
            done
        else
            echo "  Daily: $daily_count backups (≤ $RETENTION_DAILY, no cleanup needed)"
        fi
    fi

    local weekly_dir="$BACKUP_ROOT/weekly"
    if [[ -d "$weekly_dir" ]]; then
        local weekly_count
        weekly_count=$(ls "$weekly_dir"/*.tar.gz 2>/dev/null | wc -l || echo 0)
        if [[ "$weekly_count" -gt "$RETENTION_WEEKLY" ]]; then
            local to_remove=$((weekly_count - RETENTION_WEEKLY))
            echo "  Weekly: keeping $RETENTION_WEEKLY, removing $to_remove"
            ls -t "$weekly_dir"/*.tar.gz 2>/dev/null | tail -n "$to_remove" | while read -r f; do
                rm -f "$f"
                echo "    Removed: $(basename "$f")"
                cleaned=$((cleaned + 1))
            done
        else
            echo "  Weekly: $weekly_count backups (≤ $RETENTION_WEEKLY, no cleanup needed)"
        fi
    fi

    local monthly_dir="$BACKUP_ROOT/monthly"
    if [[ -d "$monthly_dir" ]]; then
        local monthly_count
        monthly_count=$(ls "$monthly_dir"/*.tar.gz 2>/dev/null | wc -l || echo 0)
        if [[ "$monthly_count" -gt "$RETENTION_MONTHLY" ]]; then
            local to_remove=$((monthly_count - RETENTION_MONTHLY))
            echo "  Monthly: keeping $RETENTION_MONTHLY, removing $to_remove"
            ls -t "$monthly_dir"/*.tar.gz 2>/dev/null | tail -n "$to_remove" | while read -r f; do
                rm -f "$f"
                echo "    Removed: $(basename "$f")"
                cleaned=$((cleaned + 1))
            done
        else
            echo "  Monthly: $monthly_count backups (≤ $RETENTION_MONTHLY, no cleanup needed)"
        fi
    fi

    local inc_dir="$BACKUP_ROOT/incremental"
    if [[ -d "$inc_dir" ]]; then
        local latest_full
        latest_full=$(ls -t "$daily_dir"/*.tar.gz 2>/dev/null | head -1 || echo "")
        if [[ -n "$latest_full" ]]; then
            echo "  Incremental: keeping all since last full backup ($(basename "$latest_full"))"
        else
            echo "  Incremental: no full backup found, keeping all"
        fi
    fi

    if [[ "$cleaned" -eq 0 ]]; then
        echo "  No backups needed cleanup"
    else
        echo ""
        echo -e "  ${GREEN}Cleaned $cleaned expired backup(s)${NC}"
    fi

    echo -e "${GREEN}=== Cleanup completed ===${NC}"
}

verify_backup() {
    local backup_path=$1

    if [[ ! -f "$backup_path" ]]; then
        echo -e "  ${RED}VERIFY FAIL: Backup file does not exist${NC}"
        return 1
    fi

    local file_size
    file_size=$(stat -f%z "$backup_path" 2>/dev/null || stat -c%s "$backup_path" 2>/dev/null || echo 0)
    if [[ "$file_size" -lt 1024 ]]; then
        echo -e "  ${YELLOW}VERIFY WARN: Backup file is very small (${file_size} bytes)${NC}"
    fi

    if tar -tzf "$backup_path" > /dev/null 2>&1; then
        local count
        count=$(tar -tzf "$backup_path" 2>/dev/null | wc -l)
        echo -e "  ${GREEN}VERIFY PASS: Archive integrity OK, $count entries${NC}"
        return 0
    else
        echo -e "  ${RED}VERIFY FAIL: Archive integrity check failed${NC}"
        return 1
    fi
}

verify_restore() {
    local restore_dir=$1

    local file_count
    file_count=$(find "$restore_dir" -type f 2>/dev/null | wc -l)

    if [[ "$file_count" -eq 0 ]]; then
        echo -e "  ${YELLOW}VERIFY: No files restored${NC}"
        return 1
    fi

    local config_files
    config_files=$(find "$restore_dir" -name "*.yaml" -o -name "*.yml" -o -name "*.json" 2>/dev/null | wc -l)
    echo -e "  ${GREEN}VERIFY PASS: $file_count files restored ($config_files config files)${NC}"
    return 0
}

MODE=""
WEEKLY=false
MONTHLY=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --mode) MODE="$2"; shift 2 ;;
        --backup-file) BACKUP_FILE="$2"; shift 2 ;;
        --verify) VERIFY=true; shift ;;
        --weekly) WEEKLY=true; shift ;;
        --monthly) MONTHLY=true; shift ;;
        *) echo "Unknown option: $1"; usage; exit 1 ;;
    esac
done

if [[ -z "$MODE" ]]; then
    echo "Error: --mode is required"
    usage
    exit 1
fi

init_backup_dirs

case "$MODE" in
    full)
        if [[ "$WEEKLY" == true ]]; then
            do_full_backup "weekly"
        elif [[ "$MONTHLY" == true ]]; then
            do_full_backup "monthly"
        else
            do_full_backup "daily"
        fi
        ;;
    incremental)
        do_incremental_backup
        ;;
    restore)
        if [[ -z "$BACKUP_FILE" ]]; then
            echo "Error: --backup-file is required for restore mode"
            usage
            exit 1
        fi
        do_restore
        ;;
    list)
        list_backups
        ;;
    clean)
        clean_backups
        ;;
    *)
        echo "Unknown mode: $MODE"
        usage
        exit 1
        ;;
esac