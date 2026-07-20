#!/bin/bash
# MAREF v0.28.0 会话恢复助手脚本
# 简化的恢复入口点

set -e

PROJECT_ROOT="$PROJECT_ROOT"
MISSION_DIR=".missions/v0.28.0-operational-layer"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 日志函数
log_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

log_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

log_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

log_error() {
    echo -e "${RED}❌ $1${NC}"
}

# 检查是否在项目目录
check_project_root() {
    if [ ! -f "pyproject.toml" ]; then
        log_error "不在 MAREF 项目根目录"
        log_info "请切换到: $PROJECT_ROOT"
        exit 1
    fi
}

# 基本环境检查
check_environment() {
    log_info "检查开发环境..."

    # Python 版本
    if command -v python3 &> /dev/null; then
        python_version=$(python3 --version | cut -d' ' -f2)
        log_success "Python $python_version"
    else
        log_error "Python3 未安装"
    fi

    # Ruff
    if command -v ruff &> /dev/null; then
        ruff_version=$(ruff --version 2>/dev/null | head -1 || echo "未知")
        log_success "Ruff $ruff_version"
    else
        log_warning "Ruff 未安装 (运行: pip install ruff)"
    fi

    # pytest
    if command -v pytest &> /dev/null; then
        pytest_version=$(pytest --version 2>/dev/null | cut -d' ' -f2 || echo "未知")
        log_success "pytest $pytest_version"
    else
        log_warning "pytest 未安装 (运行: pip install pytest)"
    fi

    # coverage
    if command -v coverage &> /dev/null; then
        coverage_version=$(coverage --version 2>/dev/null | head -1 | cut -d' ' -f2 || echo "未知")
        log_success "coverage $coverage_version"
    else
        log_warning "coverage 未安装 (运行: pip install coverage)"
    fi
}

# 显示会话选项
show_session_options() {
    echo -e "\n${BLUE}🎯 MAREF v0.28.0 会话恢复选项:${NC}"
    echo
    echo "  1. 检测当前状态"
    echo "  2. 验证检查 (详细)"
    echo "  3. 显示下一步建议"
    echo "  4. 从检查点恢复"
    echo "  5. 启动 Phase A1"
    echo "  6. 启动 Phase A2"
    echo "  0. 退出"
    echo
}

# 从检查点恢复
resume_from_checkpoint() {
    local checkpoint_dir="$MISSION_DIR/checkpoints"

    if [ ! -d "$checkpoint_dir" ]; then
        log_error "检查点目录不存在: $checkpoint_dir"
        return 1
    fi

    echo -e "\n${BLUE}📂 可用检查点:${NC}"
    echo

    checkpoints=()
    local index=1

    for dir in "$checkpoint_dir"/*/; do
        if [ -d "$dir" ]; then
            checkpoint_name=$(basename "$dir")
            if [ -f "$dir/resume.md" ]; then
                checkpoints[$index]="$checkpoint_name"
                echo "  $index. $checkpoint_name"
                ((index++))
            fi
        fi
    done

    echo "  0. 返回"
    echo

    read -p "选择检查点编号: " choice

    if [[ "$choice" -ge 1 && "$choice" -lt $index ]]; then
        checkpoint_name="${checkpoints[$choice]}"
        log_info "从检查点恢复: $checkpoint_name"

        if [ -f "$checkpoint_dir/$checkpoint_name/resume.md" ]; then
            echo -e "\n${YELLOW}📄 恢复指南:${NC}"
            cat "$checkpoint_dir/$checkpoint_name/resume.md" | head -30
            echo -e "\n${YELLOW}... (完整指南请查看文件)${NC}"
        fi

        # 特殊检查点处理
        case "$checkpoint_name" in
            "planning-complete")
                log_info "规划阶段已完成，下一步开始 Phase A1"
                echo "运行: ruff check src/ --fix --unsafe-fixes"
                ;;
            "phase-a1-complete")
                log_info "Phase A1 已完成，下一步开始 Phase A2"
                echo "运行: coverage run --source=src/sidecar -m pytest tests/unit/test_sidecar*.py"
                ;;
        esac

    elif [[ "$choice" -eq 0 ]]; then
        return
    else
        log_error "无效选择"
    fi
}

# 启动 Phase A1
start_phase_a1() {
    log_info "🚀 启动 Phase A1: 技术债清理"

    echo -e "\n${YELLOW}Phase A1 任务列表:${NC}"
    echo "  1. Ruff 自动修复"
    echo "  2. GUI 版本对齐"
    echo "  3. 基础测试修复"
    echo "  0. 返回"
    echo

    read -p "选择任务: " task_choice

    case $task_choice in
        1)
            log_info "执行 Ruff 自动修复..."
            if command -v ruff &> /dev/null; then
                ruff check src/ --fix --unsafe-fixes
                log_success "Ruff 自动修复完成"
                echo "运行验证: ruff check src/ --statistics"
            else
                log_error "Ruff 未安装"
            fi
            ;;
        2)
            log_info "对齐 GUI 版本..."
            current_version=$(grep '"version"' gui/src-tauri/tauri.conf.json | head -1 | sed 's/.*"\(.*\)".*/\1/')
            log_info "当前 GUI 版本: $current_version"

            if [ "$current_version" != "0.27.0" ]; then
                log_warning "需要更新版本: 0.26.0 → 0.27.0"
                echo "请手动编辑 gui/src-tauri/tauri.conf.json"
                echo "将 \"version\": \"0.26.0\" 改为 \"version\": \"0.27.0\""
            else
                log_success "GUI 版本已经对齐: 0.27.0"
            fi
            ;;
        3)
            log_info "修复基础测试..."
            log_info "运行测试 (排除 GUI 相关):"
            pytest tests/unit/ tests/integration/ -k 'not gui' -v --tb=short --maxfail=1
            ;;
        0)
            return
            ;;
        *)
            log_error "无效选择"
            ;;
    esac
}

# 启动 Phase A2
start_phase_a2() {
    log_info "📊 启动 Phase A2: 覆盖率攻坚"

    echo -e "\n${YELLOW}Phase A2 任务列表:${NC}"
    echo "  1. 检查 Sidecar 当前覆盖率"
    echo "  2. 编写 sidecar/server.py 测试"
    echo "  3. 编写 sidecar/mcp_bridge.py 测试"
    echo "  4. 编写 sidecar/protocol.py 测试"
    echo "  0. 返回"
    echo

    read -p "选择任务: " task_choice

    case $task_choice in
        1)
            log_info "检查 Sidecar 覆盖率..."
            if command -v coverage &> /dev/null; then
                coverage run --source=src/sidecar -m pytest tests/unit/test_sidecar*.py -q
                coverage report --include='src/sidecar/*'
            else
                log_error "coverage 未安装"
            fi
            ;;
        2)
            log_info "编写 sidecar/server.py 测试..."
            log_info "建议测试范围:"
            echo "  - 健康检查端点 (/api/health)"
            echo "  - MCP 端点 (POST /api/mcp)"
            echo "  - SSE 事件流"
            echo "  - 错误处理"
            ;;
        3)
            log_info "编写 sidecar/mcp_bridge.py 测试..."
            log_info "建议测试范围:"
            echo "  - 消息编解码"
            echo "  - 适配器集成"
            echo "  - 错误处理"
            ;;
        4)
            log_info "编写 sidecar/protocol.py 测试..."
            log_info "建议测试范围:"
            echo "  - 数据类型序列化"
            echo "  - 验证器测试"
            echo "  - 边界情况测试"
            ;;
        0)
            return
            ;;
        *)
            log_error "无效选择"
            ;;
    esac
}

# 主函数
main() {
    check_project_root

    echo -e "\n${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}                      MAREF v0.28.0 会话恢复助手                               ${NC}"
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

    check_environment

    # 显示当前会话信息
    if [ -f "$MISSION_DIR/mission.json" ]; then
        mission_name=$(grep '"name"' "$MISSION_DIR/mission.json" | head -1 | sed 's/.*"\(.*\)".*/\1/')
        current_milestone=$(grep '"current_milestone"' "$MISSION_DIR/mission.json" | head -1 | sed 's/.*"\(.*\)".*/\1/')
        progress=$(grep '"progress"' "$MISSION_DIR/mission.json" | head -1 | sed 's/.*"\(.*\)".*/\1/')

        echo -e "\n${BLUE}📋 任务状态:${NC}"
        echo "  名称: $mission_name"
        echo "  当前里程碑: $current_milestone"
        echo "  进度: $progress"
    fi

    while true; do
        show_session_options

        read -p "选择操作: " choice

        case $choice in
            1)
                log_info "检测当前状态..."
                python scripts/session_recovery.py
                ;;
            2)
                log_info "运行验证检查..."
                python scripts/session_recovery.py --check
                ;;
            3)
                log_info "显示下一步建议..."
                python scripts/session_recovery.py --next
                ;;
            4)
                resume_from_checkpoint
                ;;
            5)
                start_phase_a1
                ;;
            6)
                start_phase_a2
                ;;
            0)
                log_info "退出恢复助手"
                exit 0
                ;;
            *)
                log_error "无效选择"
                ;;
        esac

        echo
        read -p "按 Enter 继续..." dummy
    done
}

# 运行主函数
main "$@"
