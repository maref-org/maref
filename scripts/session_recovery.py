#!/usr/bin/env python3
"""
MAREF v0.28.0 会话恢复智能助手
自动检测状态并提供恢复指南

使用方法:
  python scripts/session_recovery.py           # 检测当前状态并生成恢复计划
  python scripts/session_recovery.py --check   # 运行验证检查
  python scripts/session_recovery.py --next    # 显示下一步建议
"""

import os
import subprocess
import json
import sys
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
import argparse

class SessionRecovery:
    def __init__(self, mission_dir: str = ".missions/v0.28.0-operational-layer"):
        self.mission_dir = Path(mission_dir)
        self.project_root = Path.cwd()
        self.current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
    def detect_state(self) -> Dict[str, Any]:
        """检测当前项目状态"""
        state = {
            "timestamp": self.current_time,
            "git": self._check_git_state(),
            "ruff": self._check_ruff_state(),
            "tests": self._check_test_state(),
            "coverage": self._check_coverage_state(),
            "gui_version": self._check_gui_version(),
            "mission": self._check_mission_state(),
            "last_checkpoint": self._find_last_checkpoint()
        }
        return state
    
    def generate_recovery_plan(self, state: Dict[str, Any]) -> List[Dict[str, Any]]:
        """基于状态生成恢复计划"""
        plan = []
        
        # 优先级1: 修复关键问题
        if state["ruff"]["errors"] > 0:
            plan.append({
                "step": len(plan) + 1,
                "action": "🔧 修复 Ruff 代码质量问题",
                "command": "ruff check src/ --fix --unsafe-fixes",
                "priority": "critical",
                "reason": f"当前有 {state['ruff']['errors']} 个 Ruff 错误",
                "estimated_time": "30分钟"
            })
        
        if state["tests"]["failed"] > 0:
            plan.append({
                "step": len(plan) + 1,
                "action": "🧪 修复失败的测试",
                "command": f"pytest tests/ -v --tb=short --lf",
                "priority": "high",
                "reason": f"当前有 {state['tests']['failed']} 个测试失败",
                "estimated_time": "1小时"
            })
        
        # 优先级2: 版本对齐
        if not state["gui_version"]["aligned"]:
            plan.append({
                "step": len(plan) + 1,
                "action": "🔄 对齐 GUI 版本",
                "command": "更新 gui/src-tauri/tauri.conf.json 中 version 为 '0.27.0'",
                "priority": "high",
                "reason": f"GUI版本 {state['gui_version']['gui']} 与核心版本 {state['gui_version']['core']} 不一致",
                "estimated_time": "10分钟"
            })
        
        # 优先级3: 基于任务状态的恢复
        mission_state = state.get("mission", {})
        if mission_state:
            current_milestone = mission_state.get("current_milestone")
            current_features = mission_state.get("current_features", [])
            
            if current_milestone == "m1" and "A1.1" in current_features:
                # Phase A1 进行中
                plan.append({
                    "step": len(plan) + 1,
                    "action": "📊 继续 Phase A1: 技术债清理",
                    "command": "按照 features.json 中 A1.1 的任务执行",
                    "priority": "high",
                    "reason": f"当前里程碑: {current_milestone}, 进行中特性: {', '.join(current_features)}",
                    "estimated_time": "2小时",
                    "details": "执行 Ruff 修复、版本对齐、基础测试修复"
                })
            elif current_milestone == "m1" and "A2.1" in current_features:
                # Phase A2 进行中
                plan.append({
                    "step": len(plan) + 1,
                    "action": "📈 继续 Phase A2: Sidecar 测试覆盖率攻坚",
                    "command": "coverage run --source=src/sidecar -m pytest tests/unit/test_sidecar*.py",
                    "priority": "high",
                    "reason": f"Sidecar覆盖率: {state['coverage'].get('sidecar_percent', '未知')}%",
                    "estimated_time": "8小时",
                    "details": "编写 sidecar/server.py, mcp_bridge.py, protocol.py 测试"
                })
        
        # 根据最后一个检查点决定下一步
        checkpoint = state.get("last_checkpoint")
        if checkpoint:
            plan.append({
                "step": len(plan) + 1,
                "action": f"📍 从检查点恢复: {checkpoint}",
                "command": f"查看 {self.mission_dir}/checkpoints/{checkpoint}/resume.md",
                "priority": "medium",
                "reason": f"检测到检查点: {checkpoint}",
                "estimated_time": "15分钟"
            })
        
        # 如果没有特定任务，提供通用恢复建议
        if not plan:
            plan.append({
                "step": 1,
                "action": "🚀 启动 MAREF v0.28.0 开发",
                "command": f"查看 {self.mission_dir}/mission.json 了解整体计划",
                "priority": "medium",
                "reason": "项目状态正常，可以开始新工作",
                "estimated_time": "取决于任务"
            })
        
        return plan
    
    def _check_git_state(self) -> Dict[str, Any]:
        """检查 Git 状态"""
        try:
            # 获取当前分支
            branch_result = subprocess.run(
                ["git", "branch", "--show-current"],
                capture_output=True, text=True, cwd=self.project_root
            )
            current_branch = branch_result.stdout.strip() if branch_result.stdout else "unknown"
            
            # 获取状态
            status_result = subprocess.run(
                ["git", "status", "--short"],
                capture_output=True, text=True, cwd=self.project_root
            )
            status_output = status_result.stdout.strip() if status_result.stdout else ""
            
            # 获取最新提交
            commit_result = subprocess.run(
                ["git", "log", "--oneline", "-1"],
                capture_output=True, text=True, cwd=self.project_root
            )
            last_commit = commit_result.stdout.strip() if commit_result.stdout else ""
            
            return {
                "branch": current_branch,
                "status": status_output[:100] + "..." if len(status_output) > 100 else status_output,
                "has_changes": bool(status_output),
                "last_commit": last_commit[:50] + "..." if len(last_commit) > 50 else last_commit,
                "available": True
            }
        except Exception as e:
            return {
                "branch": "error",
                "status": f"Git 检查失败: {e}",
                "has_changes": False,
                "last_commit": "",
                "available": False
            }
    
    def _check_ruff_state(self) -> Dict[str, Any]:
        """检查 Ruff 状态"""
        try:
            # 先尝试运行 ruff --version 检查是否安装
            version_result = subprocess.run(
                ["ruff", "--version"],
                capture_output=True, text=True, cwd=self.project_root
            )
            if version_result.returncode != 0:
                return {"errors": -1, "installed": False, "version": "未安装"}
            
            ruff_version = version_result.stdout.strip()
            
            # 检查错误数量
            check_result = subprocess.run(
                ["ruff", "check", "src/", "--statistics"],
                capture_output=True, text=True, cwd=self.project_root,
                stderr=subprocess.STDOUT
            )
            
            errors = 0
            output = check_result.stdout or check_result.stderr or ""
            
            # 解析输出获取错误数量
            for line in output.split('\n'):
                if "Found" in line and "errors" in line:
                    # 提取数字，如 "Found 1992 errors."
                    match = re.search(r'Found\s+(\d+)\s+errors', line)
                    if match:
                        errors = int(match.group(1))
                        break
            
            # 检查可修复的数量
            fixable = 0
            fixable_match = re.search(r'(\d+)\s+fixable', output)
            if fixable_match:
                fixable = int(fixable_match.group(1))
            
            return {
                "errors": errors,
                "fixable": fixable,
                "installed": True,
                "version": ruff_version,
                "output_snippet": output[:200] + "..." if len(output) > 200 else output
            }
            
        except FileNotFoundError:
            return {"errors": -1, "installed": False, "version": "ruff 命令未找到"}
        except Exception as e:
            return {"errors": -1, "installed": False, "version": f"检查失败: {str(e)[:50]}"}
    
    def _check_test_state(self) -> Dict[str, Any]:
        """检查测试状态"""
        try:
            # 快速运行核心测试
            test_result = subprocess.run(
                ["pytest", "tests/unit/", "tests/integration/", "-q", "--tb=no", "--lf"],
                capture_output=True, text=True, cwd=self.project_root
            )
            
            output = test_result.stdout or test_result.stderr or ""
            
            # 解析测试结果
            passed = 0
            failed = 0
            skipped = 0
            errors = 0
            
            # 匹配模式: "10 passed, 2 failed, 3 skipped, 2 errors"
            patterns = [
                (r'(\d+)\s+passed', 'passed'),
                (r'(\d+)\s+failed', 'failed'),
                (r'(\d+)\s+skipped', 'skipped'),
                (r'(\d+)\s+errors', 'errors')
            ]
            
            for pattern, key in patterns:
                match = re.search(pattern, output)
                if match:
                    if key == 'passed':
                        passed = int(match.group(1))
                    elif key == 'failed':
                        failed = int(match.group(1))
                    elif key == 'skipped':
                        skipped = int(match.group(1))
                    elif key == 'errors':
                        errors = int(match.group(1))
            
            total = passed + failed + skipped + errors
            pass_rate = (passed / total * 100) if total > 0 else 0
            
            return {
                "passed": passed,
                "failed": failed,
                "skipped": skipped,
                "errors": errors,
                "total": total,
                "pass_rate": round(pass_rate, 1),
                "available": True
            }
            
        except Exception as e:
            return {
                "passed": 0,
                "failed": 0,
                "skipped": 0,
                "errors": 0,
                "total": 0,
                "pass_rate": 0,
                "available": False,
                "error": str(e)[:100]
            }
    
    def _check_coverage_state(self) -> Dict[str, Any]:
        """检查覆盖率状态"""
        try:
            # 检查 coverage 是否安装
            version_result = subprocess.run(
                ["coverage", "--version"],
                capture_output=True, text=True, cwd=self.project_root
            )
            if version_result.returncode != 0:
                return {"installed": False}
            
            # 尝试获取覆盖率报告
            report_result = subprocess.run(
                ["coverage", "report", "--include=src/sidecar/*", "--format=total"],
                capture_output=True, text=True, cwd=self.project_root
            )
            
            if report_result.returncode == 0:
                output = report_result.stdout.strip()
                # 尝试解析百分比
                match = re.search(r'(\d+\.?\d*)%', output)
                if match:
                    sidecar_percent = float(match.group(1))
                else:
                    sidecar_percent = 0
            else:
                sidecar_percent = 0
            
            return {
                "installed": True,
                "sidecar_percent": sidecar_percent,
                "check_command": "coverage report --include=src/sidecar/*"
            }
            
        except Exception:
            return {"installed": False}
    
    def _check_gui_version(self) -> Dict[str, Any]:
        """检查 GUI 版本对齐"""
        try:
            # 读取 pyproject.toml 版本
            pyproject_path = self.project_root / "pyproject.toml"
            core_version = "unknown"
            if pyproject_path.exists():
                with open(pyproject_path, 'r') as f:
                    content = f.read()
                    match = re.search(r'version\s*=\s*"([^"]+)"', content)
                    if match:
                        core_version = match.group(1)
            
            # 读取 tauri.conf.json 版本
            tauri_path = self.project_root / "gui" / "src-tauri" / "tauri.conf.json"
            gui_version = "unknown"
            if tauri_path.exists():
                with open(tauri_path, 'r') as f:
                    content = f.read()
                    match = re.search(r'"version":\s*"([^"]+)"', content)
                    if match:
                        gui_version = match.group(1)
            
            return {
                "core": core_version,
                "gui": gui_version,
                "aligned": core_version == gui_version,
                "status": "✅ aligned" if core_version == gui_version else "⚠️ mismatched"
            }
            
        except Exception as e:
            return {
                "core": "error",
                "gui": "error",
                "aligned": False,
                "status": f"检查失败: {str(e)[:50]}"
            }
    
    def _check_mission_state(self) -> Dict[str, Any]:
        """检查任务状态"""
        try:
            mission_file = self.mission_dir / "mission.json"
            if not mission_file.exists():
                return {}
            
            with open(mission_file, 'r') as f:
                mission_data = json.load(f)
            
            features_file = self.mission_dir / "features.json"
            current_features = []
            if features_file.exists():
                with open(features_file, 'r') as f:
                    features_data = json.load(f)
                    # 提取进行中的特性
                    for milestone in features_data.get("milestones", []):
                        for feature in milestone.get("features", []):
                            if feature.get("status") in ["in_progress", "active", "pending"]:
                                current_features.append(feature.get("id", ""))
            
            return {
                "current_milestone": mission_data.get("current_milestone"),
                "progress": mission_data.get("progress"),
                "status": mission_data.get("status"),
                "current_features": current_features,
                "mission_id": mission_data.get("mission_id")
            }
            
        except Exception as e:
            return {"error": str(e)[:100]}
    
    def _find_last_checkpoint(self) -> Optional[str]:
        """查找最新的检查点"""
        try:
            checkpoints_dir = self.mission_dir / "checkpoints"
            if not checkpoints_dir.exists():
                return None
            
            # 查找包含 resume.md 的检查点目录
            checkpoint_dirs = []
            for item in checkpoints_dir.iterdir():
                if item.is_dir():
                    resume_file = item / "resume.md"
                    if resume_file.exists():
                        checkpoint_dirs.append(item.name)
            
            # 按修改时间排序，返回最新的
            if checkpoint_dirs:
                checkpoint_dirs.sort(key=lambda x: (checkpoints_dir / x).stat().st_mtime, reverse=True)
                return checkpoint_dirs[0]
            
            return None
        except Exception:
            return None
    
    def print_recovery_guide(self, verbose: bool = False) -> None:
        """打印恢复指南"""
        state = self.detect_state()
        plan = self.generate_recovery_plan(state)
        
        print(f"\n{'='*60}")
        print(f"🤖 MAREF v0.28.0 会话恢复指南 - {self.current_time}")
        print(f"{'='*60}")
        
        # 打印状态概览
        print(f"\n📊 项目状态概览:")
        print(f"  Git分支: {state['git']['branch']} ({'有未提交更改' if state['git']['has_changes'] else '干净'})")
        ruff_errors = state['ruff']['errors']
        fixable = state['ruff'].get('fixable', 0)
        if fixable > 0:
            print(f"  Ruff错误: {ruff_errors} 个 ({fixable} 个可自动修复)")
        else:
            print(f"  Ruff错误: {ruff_errors} 个")
        print(f"  测试通过率: {state['tests']['pass_rate']}% ({state['tests']['failed']} 个失败)")
        print(f"  GUI版本: {state['gui_version']['status']} (核心: {state['gui_version']['core']}, GUI: {state['gui_version']['gui']})")
        
        if state.get("mission"):
            print(f"  任务进度: {state['mission'].get('progress', '0%')} - {state['mission'].get('current_milestone', '未知')}")
        
        if state["last_checkpoint"]:
            print(f"  上次检查点: {state['last_checkpoint']}")
        
        # 打印恢复计划
        print(f"\n📋 恢复计划 (按优先级排序):")
        if plan:
            for item in plan:
                priority_icon = {
                    "critical": "🟥",
                    "high": "🟧", 
                    "medium": "🟨",
                    "low": "🟩"
                }.get(item["priority"], "⬜")
                
                print(f"  {priority_icon} {item['step']}. {item['action']}")
                print(f"     原因: {item['reason']}")
                print(f"     命令: {item['command']}")
                print(f"     预计时间: {item['estimated_time']}")
                
                if "details" in item:
                    print(f"     详情: {item['details']}")
                print()
        else:
            print("  ✅ 项目状态良好，无需紧急恢复操作")
        
        # 详细状态信息（如果启用了 verbose）
        if verbose:
            print(f"\n🔍 详细状态信息:")
            if state["ruff"]["installed"]:
                print(f"  Ruff版本: {state['ruff']['version']}")
                if state["ruff"]["errors"] > 0:
                    print(f"  Ruff输出片段: {state['ruff']['output_snippet']}")
            
            if state["tests"]["available"]:
                print(f"  测试详情: {state['tests']['passed']}通过/{state['tests']['failed']}失败/{state['tests']['skipped']}跳过/{state['tests']['errors']}错误")
            
            if state["coverage"]["installed"]:
                print(f"  Sidecar覆盖率: {state['coverage']['sidecar_percent']}%")
        
        # 快速启动指南
        print(f"\n🚀 快速启动选项:")
        print(f"  1. 查看任务总览: cat {self.mission_dir}/mission.json | jq '.'")
        print(f"  2. 查看详细计划: cat {self.mission_dir}/features.json | jq '.milestones[] | .name, .features[].name'")
        print(f"  3. 运行验证检查: python scripts/session_recovery.py --check")
        print(f"  4. 查看下一步建议: python scripts/session_recovery.py --next")
        
        # 基于状态的特定建议
        if state["mission"].get("current_milestone") == "m1":
            print(f"\n💡 基于 Phase A (技术债清零) 的建议:")
            print(f"  - 优先执行 Ruff 修复: ruff check src/ --fix --unsafe-fixes")
            print(f"  - 验证测试: pytest tests/ -v --tb=short --maxfail=1")
            print(f"  - 对齐版本: 更新 gui/src-tauri/tauri.conf.json")
        
        print(f"{'='*60}\n")
    
    def run_verification_checks(self) -> None:
        """运行验证检查"""
        print(f"\n🔍 运行验证检查...")
        state = self.detect_state()
        
        checks = []
        
        # Ruff 检查
        if state["ruff"]["errors"] == 0:
            checks.append(("✅ Ruff 代码质量", "通过 (0 errors)"))
        else:
            checks.append(("❌ Ruff 代码质量", f"{state['ruff']['errors']} 个错误"))
        
        # 测试检查
        if state["tests"]["failed"] == 0:
            checks.append(("✅ 测试通过率", f"{state['tests']['pass_rate']}%"))
        else:
            checks.append(("❌ 测试通过率", f"{state['tests']['failed']} 个失败"))
        
        # 版本检查
        if state["gui_version"]["aligned"]:
            checks.append(("✅ 版本对齐", f"核心: {state['gui_version']['core']}"))
        else:
            checks.append(("❌ 版本对齐", f"核心: {state['gui_version']['core']}, GUI: {state['gui_version']['gui']}"))
        
        # 任务状态检查
        if state.get("mission", {}).get("status") == "active":
            checks.append(("✅ 任务状态", f"活跃 - {state['mission'].get('progress', '0%')}"))
        else:
            checks.append(("⚪ 任务状态", "未活跃或未知"))
        
        print(f"\n{'检查项':<20} {'结果':<30}")
        print(f"{'-'*50}")
        for check_name, result in checks:
            print(f"{check_name:<20} {result:<30}")
        
        print(f"\n📋 总结:")
        passed = sum(1 for c, _ in checks if c.startswith("✅"))
        total = len(checks)
        print(f"  通过 {passed}/{total} 项检查 ({passed/total*100:.0f}%)")
        
        if passed == total:
            print("  🎉 所有检查通过，可以继续开发")
        else:
            print("  ⚠️ 有检查未通过，建议先修复")
    
    def suggest_next_steps(self) -> None:
        """建议下一步"""
        state = self.detect_state()
        mission_state = state.get("mission", {})
        current_milestone = mission_state.get("current_milestone")
        
        print(f"\n🎯 下一步建议:")
        
        if not current_milestone or current_milestone == "m0":
            print("  1. 启动 Phase A: 技术债清零")
            print("     执行: 查看 features.json 中的 A1.1 任务")
            print("     命令: ruff check src/ --fix --unsafe-fixes")
        
        elif current_milestone == "m1":
            print("  1. 继续 Phase A: 技术债清零")
            
            features = mission_state.get("current_features", [])
            if "A1.1" in features:
                print("     当前任务: A1.1 - Ruff 自动修复和手动清理")
                print("     命令: ruff check src/ --fix --unsafe-fixes")
                print("     然后: ruff check src/ --statistics 验证")
            
            elif "A1.2" in features:
                print("     当前任务: A1.2 - GUI 版本对齐")
                print("     操作: 更新 gui/src-tauri/tauri.conf.json version 为 '0.27.0'")
            
            elif "A1.3" in features:
                print("     当前任务: A1.3 - 基础测试信号恢复")
                print("     命令: pytest tests/ -v --tb=short --lf")
            
            elif "A2.1" in features:
                print("     当前任务: A2.1 - Sidecar 测试覆盖率攻坚")
                print("     命令: 编写 sidecar/server.py 测试")
                print("     目标: 覆盖率从 0% → ≥60%")
        
        else:
            print("  查看详细任务计划:")
            print(f"     cat {self.mission_dir}/features.json | jq -r '.milestones[] | select(.id==\"{current_milestone}\") | .name, .features[].name'")
        
        print(f"\n💡 通用建议:")
        print(f"  - 每次会话结束时创建检查点")
        print(f"  - 使用 git commit 保存工作进度")
        print(f"  - 运行 python scripts/session_recovery.py 验证状态")

def main():
    parser = argparse.ArgumentParser(description="MAREF v0.28.0 会话恢复助手")
    parser.add_argument("--check", action="store_true", help="运行验证检查")
    parser.add_argument("--next", action="store_true", help="显示下一步建议")
    parser.add_argument("--verbose", "-v", action="store_true", help="显示详细信息")
    args = parser.parse_args()
    
    recovery = SessionRecovery()
    
    if args.check:
        recovery.run_verification_checks()
    elif args.next:
        recovery.suggest_next_steps()
    else:
        recovery.print_recovery_guide(verbose=args.verbose)

if __name__ == "__main__":
    main()