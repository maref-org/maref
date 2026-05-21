#!/bin/bash
# MAREF 紧急内存清理脚本
# 当系统内存不足时运行此脚本

set -e

echo "======================================"
echo "MAREF 紧急内存清理"
echo "======================================"
echo ""

# 1. 显示当前内存状况
echo "📊 当前内存状况:"
vm_stat | head -20
echo ""

# 2. 停止正在运行的 pytest 进程（最耗内存）
echo "🛑 停止 pytest 进程..."
ps aux | grep "[p]ytest" | awk '{print $2}' | while read pid; do
    echo "  终止 pytest PID: $pid"
    kill -TERM "$pid" 2>/dev/null || true
done
sleep 2

# 3. 停止基于 pytest 的子进程
echo "🛑 停止 pytest 子进程..."
ps aux | grep "[m]emory_monitor.py --once" | awk '{print $2}' | while read pid; do
    echo "  终止监控 PID: $pid"
    kill -TERM "$pid" 2>/dev/null || true
done

# 4. 清理 Python 缓存
echo "🧹 清理 Python 缓存..."
find /Volumes/1TB-M2/maref-experiments -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find /Volumes/1TB-M2/maref-experiments -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
find /Volumes/1TB-M2/maref-experiments -name "*.pyc" -delete 2>/dev/null || true

# 5. 清理测试覆盖率报告
echo "🧹 清理测试覆盖率报告..."
rm -rf /Volumes/1TB-M2/maref-experiments/htmlcov 2>/dev/null || true
rm -f /Volumes/1TB-M2/maref-experiments/.coverage* 2>/dev/null || true

# 6. 显示清理后的内存状况
echo ""
echo "📊 清理后内存状况:"
vm_stat | head -20
echo ""

# 7. 检查 maref serve 状态
echo "🔍 检查 maref serve 状态:"
ps aux | grep "[m]aref serve"
echo ""

# 8. 建议
echo "======================================"
echo "✅ 清理完成"
echo "======================================"
echo ""
echo "💡 建议:"
echo "  1. 关闭 Trae CN 中不必要的标签页"
echo "  2. 重启 Trae CN 以释放 AI Agent 内存"
echo "  3. 如果 maref serve 运行超过 24 小时，建议重启"
echo "  4. 基于 BasedPyright 的配置已优化，下次打开项目会减少索引压力"
echo ""
echo "运行以下命令重启 maref serve:"
echo "  kill -TERM 44631 && maref serve --port 8000 --gui &"
echo ""
