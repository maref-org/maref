#!/usr/bin/env python3
"""
MAREF 内存监控和自动保护脚本
- 监控内存压力，超过阈值时自动终止非关键进程
- 监控 maref serve 运行时间，超过 24 小时自动提醒重启
- 检测磁盘 I/O 风暴，防止系统崩溃
"""

import os
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# 配置
MEMORY_THRESHOLD_PERCENT = 85  # 内存使用率警告阈值
MEMORY_CRITICAL_PERCENT = 95  # 内存使用率危险阈值
MAREF_SERVE_MAX_HOURS = 24  # maref serve 最大运行时长
CHECK_INTERVAL_SECONDS = 30  # 检查间隔
LOG_FILE = Path(__file__).parent / "memory_monitor.log"

# 关键进程（永不终止）
CRITICAL_PROCESSES = {"python", "kernel_task", "launchd", "WindowServer", "loginwindow"}

# 可终止的 MAREF 进程
MAREF_PROCESSES = {"maref", "pytest", "athena"}


def get_memory_usage() -> dict:
    """获取当前内存使用情况"""
    try:
        result = subprocess.run(["vm_stat"], capture_output=True, text=True, timeout=5)

        stats = {}
        for line in result.stdout.splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                try:
                    stats[key.strip()] = int(value.strip().rstrip("."))
                except ValueError:
                    pass

        page_size = 16384  # macOS ARM64
        total_pages = (
            stats.get("Pages free", 0)
            + stats.get("Pages active", 0)
            + stats.get("Pages inactive", 0)
            + stats.get("Pages wired down", 0)
            + stats.get("Pages used by compressor", 0)
        )

        free_mb = (stats.get("Pages free", 0) * page_size) / (1024 * 1024)
        active_mb = (stats.get("Pages active", 0) * page_size) / (1024 * 1024)
        wired_mb = (stats.get("Pages wired down", 0) * page_size) / (1024 * 1024)
        compressor_mb = (stats.get("Pages used by compressor", 0) * page_size) / (1024 * 1024)

        total_mb = (total_pages * page_size) / (1024 * 1024)
        used_percent = ((total_mb - free_mb) / total_mb * 100) if total_mb > 0 else 0

        return {
            "total_mb": total_mb,
            "free_mb": free_mb,
            "active_mb": active_mb,
            "wired_mb": wired_mb,
            "compressor_mb": compressor_mb,
            "used_percent": used_percent,
            "swapins": stats.get("Swapins", 0),
            "swapouts": stats.get("Swapouts", 0),
        }
    except Exception as e:
        log(f"获取内存信息失败: {e}")
        return {"total_mb": 0, "free_mb": 0, "used_percent": 0}


def get_process_memory() -> list[dict]:
    """获取所有进程的内存使用情况"""
    try:
        result = subprocess.run(
            ["ps", "aux", "--sort=-%mem"], capture_output=True, text=True, timeout=10
        )

        processes = []
        for line in result.stdout.splitlines()[1:]:  # 跳过标题行
            parts = line.split(None, 10)
            if len(parts) >= 11:
                processes.append(
                    {
                        "user": parts[0],
                        "pid": int(parts[1]),
                        "cpu": float(parts[2]),
                        "mem": float(parts[3]),
                        "rss_mb": int(parts[5]) / 1024,
                        "command": parts[10][:100],  # 截断过长的命令
                    }
                )

        return processes[:20]  # 只返回前 20 个最耗内存的进程
    except Exception as e:
        log(f"获取进程信息失败: {e}")
        return []


def check_maref_serve_uptime() -> list[dict]:
    """检查 maref serve 进程的运行时间"""
    try:
        result = subprocess.run(
            ["ps", "-o", "pid,rss,etime,command", "-A"], capture_output=True, text=True, timeout=5
        )

        long_running = []
        for line in result.stdout.splitlines():
            if "maref serve" in line or "athena.server" in line:
                parts = line.split()
                if len(parts) >= 3:
                    pid = parts[0]
                    etime = parts[2]
                    rss_mb = int(parts[1]) / 1024

                    # 解析运行时间
                    days = 0
                    if "-" in etime:
                        days_str, time_str = etime.split("-", 1)
                        days = int(days_str)
                        hours, minutes, seconds = map(int, time_str.split(":"))
                    else:
                        time_parts = etime.split(":")
                        if len(time_parts) == 3:
                            hours, minutes, seconds = map(int, time_parts)
                        else:
                            hours, minutes = map(int, time_parts)
                            seconds = 0

                    total_hours = days * 24 + hours + minutes / 60

                    if total_hours > MAREF_SERVE_MAX_HOURS:
                        long_running.append(
                            {
                                "pid": pid,
                                "rss_mb": rss_mb,
                                "uptime_hours": total_hours,
                                "command": line,
                            }
                        )

        return long_running
    except Exception as e:
        log(f"检查 maref serve 运行时间失败: {e}")
        return []


def kill_memory_hogs(threshold_mb: int = 500) -> list[dict]:
    """终止占用内存过高的非关键进程"""
    processes = get_process_memory()
    killed = []

    for proc in processes:
        if proc["rss_mb"] > threshold_mb:
            cmd_lower = proc["command"].lower()
            is_critical = any(cp in cmd_lower for cp in CRITICAL_PROCESSES)
            is_maref = any(mp in cmd_lower for mp in MAREF_PROCESSES)

            if not is_critical and is_maref:
                try:
                    log(
                        f"终止内存过高的进程: PID={proc['pid']}, RSS={proc['rss_mb']:.1f}MB, CMD={proc['command'][:80]}"
                    )
                    os.kill(proc["pid"], signal.SIGTERM)
                    killed.append(proc)
                    time.sleep(1)  # 等待进程退出
                except Exception as e:
                    log(f"终止进程 {proc['pid']} 失败: {e}")

    return killed


def log(message: str) -> None:
    """记录日志"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_line = f"[{timestamp}] {message}"
    print(log_line)

    try:
        with open(LOG_FILE, "a") as f:
            f.write(log_line + "\n")
    except Exception:
        pass


def check_disk_io() -> dict:
    """检查磁盘 I/O 情况"""
    try:
        result = subprocess.run(
            ["iostat", "-c", "1", "2"], capture_output=True, text=True, timeout=10
        )

        lines = result.stdout.strip().splitlines()
        if len(lines) >= 2:
            parts = lines[-1].split()
            if len(parts) >= 6:
                return {
                    "kb_per_sec_in": float(parts[3]),
                    "kb_per_sec_out": float(parts[4]),
                }
    except Exception:
        pass

    return {"kb_per_sec_in": 0, "kb_per_sec_out": 0}


def emergency_cleanup() -> None:
    """紧急情况下的内存清理"""
    log("🚨 紧急内存清理开始...")

    # 1. 释放 purgeable 内存
    subprocess.run(["purge"], capture_output=True, timeout=10)

    # 2. 终止高内存消耗的 MAREF 相关进程
    killed = kill_memory_hogs(threshold_mb=500)
    if killed:
        log(f"已终止 {len(killed)} 个高内存进程")

    # 3. 清理 Python 缓存
    cache_dirs = list(Path(__file__).parent.rglob("__pycache__"))
    cache_dirs += list(Path(__file__).parent.rglob(".pytest_cache"))
    for cache_dir in cache_dirs[:10]:  # 只清理前 10 个
        try:
            subprocess.run(["rm", "-rf", str(cache_dir)], capture_output=True, timeout=10)
        except Exception:
            pass

    log("✅ 紧急清理完成")


def monitor_loop() -> None:
    """主监控循环"""
    log("=" * 60)
    log("MAREF 内存监控器启动")
    log(f"内存警告阈值: {MEMORY_THRESHOLD_PERCENT}%")
    log(f"内存危险阈值: {MEMORY_CRITICAL_PERCENT}%")
    log(f"maref serve 最大运行时长: {MAREF_SERVE_MAX_HOURS} 小时")
    log("=" * 60)

    while True:
        try:
            mem = get_memory_usage()
            used = mem.get("used_percent", 0)
            free_mb = mem.get("free_mb", 0)

            log(
                f"内存使用: {used:.1f}% | 空闲: {free_mb:.0f}MB | 压缩: {mem.get('compressor_mb', 0):.0f}MB"
            )

            # 检查 maref serve 运行时间
            long_running = check_maref_serve_uptime()
            for proc in long_running:
                log(
                    f"⚠️  maref serve 已运行 {proc['uptime_hours']:.1f} 小时，建议重启 (PID: {proc['pid']})"
                )

            # 内存危险 - 紧急清理
            if used > MEMORY_CRITICAL_PERCENT or free_mb < 500:
                log(f"🚨 内存危险! 使用率: {used:.1f}%, 空闲: {free_mb:.0f}MB")
                emergency_cleanup()

            # 内存警告 - 显示 Top 5 进程
            elif used > MEMORY_THRESHOLD_PERCENT:
                log(f"⚠️ 内存警告! 使用率: {used:.1f}%")
                procs = get_process_memory()
                for i, proc in enumerate(procs[:5], 1):
                    log(
                        f"  {i}. PID={proc['pid']} RSS={proc['rss_mb']:.0f}MB MEM={proc['mem']:.1f}% CMD={proc['command'][:60]}"
                    )

            # 检查磁盘 I/O
            io = check_disk_io()
            if io.get("kb_per_sec_out", 0) > 100000:  # 100MB/s
                log(f"⚠️ 磁盘写入过高: {io['kb_per_sec_out']:.0f} KB/s")

        except Exception as e:
            log(f"监控循环异常: {e}")

        time.sleep(CHECK_INTERVAL_SECONDS)


if __name__ == "__main__":
    if "--once" in sys.argv:
        # 只运行一次检查
        mem = get_memory_usage()
        print(f"内存使用: {mem.get('used_percent', 0):.1f}%")
        print(f"空闲内存: {mem.get('free_mb', 0):.0f} MB")
        print("\nTop 5 内存消耗进程:")
        for i, proc in enumerate(get_process_memory()[:5], 1):
            print(
                f"  {i}. PID={proc['pid']} RSS={proc['rss_mb']:.0f}MB MEM={proc['mem']:.1f}% CMD={proc['command'][:80]}"
            )

        print("\nmaref serve 运行时间检查:")
        long_running = check_maref_serve_uptime()
        if long_running:
            for proc in long_running:
                print(
                    f"  ⚠️  PID={proc['pid']} 运行 {proc['uptime_hours']:.1f} 小时 RSS={proc['rss_mb']:.0f}MB"
                )
        else:
            print("  ✅ 无长时间运行的 maref serve 进程")
    else:
        # 持续监控
        monitor_loop()
