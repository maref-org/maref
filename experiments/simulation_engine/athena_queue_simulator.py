#!/usr/bin/env python3
"""
Athena队列系统模拟器

模拟当前Athena队列系统的5个系统性缺陷：
1. 任务身份规范化失败：ID以`-`开头被`argparse`误识别
2. Manifest数据质量缺陷：重复条目，数据不一致
3. 进程可靠性契约缺失：先标记running再启动进程
4. 活跃占位检测延迟：死进程检测延迟5分钟
5. Lane混合与路由混淆：执行器选择混乱

用于建立基线性能基准，与MAREF系统对比。
"""

import hashlib
import json
import random
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any


class TaskStatus(Enum):
    """任务状态枚举"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    MANUAL_HOLD = "manual_hold"
    RETRYING = "retrying"


class ExecutorType(Enum):
    """执行器类型枚举（当前系统混淆使用）"""

    CLAUDE_CODE_CLI = "claude_code_cli"
    OPENCODE_BUILD = "opencode_build"
    CODEX_REVIEW = "codex_review"
    QWEN_ALTERNATIVE = "qwen_alternative"  # 混淆使用


@dataclass
class Task:
    """任务定义（模拟当前系统的问题）"""

    # 缺陷1: ID以`-`开头，会被argparse误识别
    id: str  # 可能以`-`开头的ID
    name: str
    status: TaskStatus
    created_at: str
    updated_at: str
    executor: ExecutorType
    manifest_entry: dict[str, Any]  # 缺陷2: 可能有重复的manifest条目

    # 缺陷3: 进程状态管理
    process_pid: int | None = None
    process_start_time: str | None = None
    process_status_updated_before_start: bool = False  # 标记是否先更新状态再启动进程

    # 缺陷4: 活跃检测
    last_heartbeat: str | None = None
    heartbeat_delay_minutes: int = 5  # 5分钟检测延迟

    # 缺陷5: Lane混淆标记
    lane_confusion: bool = False  # 是否发生了Lane混淆
    confusion_details: str | None = None


class AthenaQueueSimulator:
    """Athena队列系统模拟器"""

    def __init__(self, simulation_id: str = "baseline"):
        self.simulation_id = simulation_id
        self.tasks: dict[str, Task] = {}
        self.queues: dict[str, dict[str, Any]] = {}
        self.manifest_entries: list[dict[str, Any]] = []
        self.performance_metrics: dict[str, list[float]] = {
            "task_completion_times": [],
            "error_rates": [],
            "resource_waste": [],
            "state_inconsistencies": [],
        }

        # 模拟配置
        self.config = {
            "argparse_issue_enabled": True,  # 启用argparse误识别问题
            "manifest_duplication_rate": 0.24,  # 24%的重复率（51/211）
            "process_reliability_issue": True,  # 启用进程可靠性问题
            "heartbeat_delay_minutes": 5,  # 5分钟心跳延迟
            "lane_confusion_rate": 0.15,  # 15%的Lane混淆率
            "task_failure_rate": 0.10,  # 10%的任务失败率
        }

        # 统计计数器
        self.stats = {
            "tasks_created": 0,
            "tasks_completed": 0,
            "tasks_failed": 0,
            "argparse_errors": 0,
            "manifest_duplicates": 0,
            "process_reliability_errors": 0,
            "lane_confusions": 0,
            "zombie_processes": 0,
        }

        self._initialize_simulation()

    def _initialize_simulation(self):
        """初始化模拟环境"""
        print(f"[{self.simulation_id}] 初始化Athena队列系统模拟器")
        print(f"配置: {json.dumps(self.config, indent=2, ensure_ascii=False)}")

        # 创建示例队列
        self.queues = {
            "openhuman_aiplan_build_priority": {
                "queue_status": "running",
                "current_item_id": "-engineering-plan-20260413-095918-task-20260413-095918",  # 以-开头
                "counts": {
                    "pending": 0,
                    "running": 0,
                    "completed": 0,
                    "failed": 0,
                    "manual_hold": 0,
                },
                "updated_at": datetime.now().isoformat(),
            },
            "gene_management_queue": {
                "queue_status": "manual_hold",
                "current_item_id": None,
                "counts": {
                    "pending": 5,
                    "running": 0,
                    "completed": 3,
                    "failed": 6,
                    "manual_hold": 5,
                },
                "updated_at": (datetime.now() - timedelta(days=2)).isoformat(),  # 2天未更新
            },
        }

        # 生成有缺陷的manifest数据
        self._generate_defective_manifest()

        print(f"[{self.simulation_id}] 模拟器初始化完成")
        print(f"队列数量: {len(self.queues)}")
        print(f"初始manifest条目: {len(self.manifest_entries)}")

    def _generate_defective_manifest(self):
        """生成有缺陷的manifest数据（包含重复条目）"""
        print(f"[{self.simulation_id}] 生成有缺陷的manifest数据...")

        base_entries = []
        unique_ids = set()

        # 生成160个唯一任务条目
        for i in range(160):
            task_id = f"task-{uuid.uuid4().hex[:8]}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
            unique_ids.add(task_id)

            entry = {
                "id": task_id,
                "name": f"Task {i+1}",
                "type": random.choice(["build", "review", "plan", "scan"]),
                "entry_stage": random.choice(["phase1", "phase2", "phase3", "phase4"]),
                "resources": {
                    "memory_mb": random.randint(512, 4096),
                    "cpu_cores": random.randint(1, 4),
                    "timeout_seconds": random.randint(300, 1800),
                },
                "created_at": datetime.now().isoformat(),
                "hash": hashlib.sha256(task_id.encode()).hexdigest()[:8],
            }
            base_entries.append(entry)

        # 添加51个重复条目（24%重复率）
        duplicate_count = int(len(base_entries) * self.config["manifest_duplication_rate"])
        duplicates = random.sample(base_entries, duplicate_count)

        # 稍微修改重复条目，但保持核心ID相同
        for dup in duplicates:
            modified_dup = dup.copy()
            modified_dup["name"] = f"{dup['name']} (duplicate)"
            modified_dup["created_at"] = (
                datetime.now() + timedelta(seconds=random.randint(1, 60))
            ).isoformat()
            base_entries.append(modified_dup)

        self.manifest_entries = base_entries
        self.stats["manifest_duplicates"] = duplicate_count

        print(f"[{self.simulation_id}] Manifest生成完成:")
        print(f"  - 总条目数: {len(self.manifest_entries)}")
        print(f"  - 唯一ID数: {len(unique_ids)}")
        print(f"  - 重复条目数: {duplicate_count}")
        print(f"  - 重复率: {duplicate_count/len(self.manifest_entries)*100:.1f}%")

    def create_task(self, name: str, task_type: str = "build") -> tuple[bool, str, str | None]:
        """创建新任务（模拟argparse ID问题）"""
        self.stats["tasks_created"] += 1

        # 缺陷1: 生成可能以`-`开头的任务ID
        if random.random() < 0.3:  # 30%的概率生成有问题的ID
            task_id = f"-{task_type}-{datetime.now().strftime('%Y%m%d-%H%M%S')}-task"
            self.stats["argparse_errors"] += 1
            id_problem = "argparse_problem"
        else:
            task_id = f"{task_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{random.randint(1000, 9999)}"
            id_problem = None

        # 缺陷5: Lane混淆
        executor = self._select_executor_with_confusion(task_type)
        lane_confusion = executor != self._correct_executor_for_type(task_type)

        if lane_confusion:
            self.stats["lane_confusions"] += 1

        task = Task(
            id=task_id,
            name=name,
            status=TaskStatus.PENDING,
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
            executor=executor,
            manifest_entry=self._get_random_manifest_entry(),
            lane_confusion=lane_confusion,
            confusion_details=(
                f"应为{self._correct_executor_for_type(task_type).value}，实际为{executor.value}"
                if lane_confusion
                else None
            ),
            heartbeat_delay_minutes=self.config["heartbeat_delay_minutes"],
        )

        self.tasks[task_id] = task

        # 更新队列计数
        queue_name = "openhuman_aiplan_build_priority"
        if queue_name in self.queues:
            self.queues[queue_name]["counts"]["pending"] += 1
            self.queues[queue_name]["updated_at"] = datetime.now().isoformat()

        print(f"[{self.simulation_id}] 创建任务: {task_id}")
        if id_problem:
            print(f"  ⚠️  ID问题: {id_problem}")
        if lane_confusion:
            print(f"  ⚠️  Lane混淆: {task.confusion_details}")

        return True, task_id, id_problem

    def _select_executor_with_confusion(self, task_type: str) -> ExecutorType:
        """选择执行器（模拟Lane混淆）"""
        correct_executor = self._correct_executor_for_type(task_type)

        # 有概率选择错误的执行器
        if random.random() < self.config["lane_confusion_rate"]:
            # 随机选择一个错误的执行器
            wrong_executors = [e for e in ExecutorType if e != correct_executor]
            return random.choice(wrong_executors)

        return correct_executor

    def _correct_executor_for_type(self, task_type: str) -> ExecutorType:
        """根据任务类型返回正确的执行器"""
        mapping = {
            "build": ExecutorType.OPENCODE_BUILD,
            "review": ExecutorType.CODEX_REVIEW,
            "plan": ExecutorType.CLAUDE_CODE_CLI,
            "scan": ExecutorType.CLAUDE_CODE_CLI,
        }
        return mapping.get(task_type, ExecutorType.CLAUDE_CODE_CLI)

    def _get_random_manifest_entry(self) -> dict[str, Any]:
        """获取随机的manifest条目（可能有重复）"""
        if not self.manifest_entries:
            return {}
        return random.choice(self.manifest_entries)

    def start_task(self, task_id: str) -> tuple[bool, str | None]:
        """启动任务（模拟进程可靠性问题）"""
        if task_id not in self.tasks:
            return False, f"任务不存在: {task_id}"

        task = self.tasks[task_id]

        # 缺陷3: 先更新状态为running
        task.status = TaskStatus.RUNNING
        task.updated_at = datetime.now().isoformat()
        task.process_status_updated_before_start = True

        # 更新队列状态
        queue_name = "openhuman_aiplan_build_priority"
        if queue_name in self.queues:
            self.queues[queue_name]["current_item_id"] = task_id
            self.queues[queue_name]["counts"]["pending"] = max(
                0, self.queues[queue_name]["counts"]["pending"] - 1
            )
            self.queues[queue_name]["counts"]["running"] += 1
            self.queues[queue_name]["updated_at"] = datetime.now().isoformat()

        print(f"[{self.simulation_id}] 启动任务: {task_id}")
        print(f"  - 状态更新为: {task.status.value}")
        print("  - 进程可靠性问题: 先更新状态再启动进程")

        # 模拟进程启动（有失败概率）
        time.sleep(0.1)  # 模拟进程启动延迟

        if random.random() < 0.05:  # 5%的进程启动失败率
            # 进程秒退，但状态已经是running
            task.process_pid = None
            self.stats["process_reliability_errors"] += 1

            print("  ⚠️ 进程启动失败，但状态已标记为running")

            # 缺陷4: 由于心跳检测延迟，这个僵尸进程会存在5分钟
            task.last_heartbeat = datetime.now().isoformat()
            self.stats["zombie_processes"] += 1

            return False, "进程启动失败（状态不一致）"
        else:
            # 进程启动成功
            task.process_pid = random.randint(10000, 99999)
            task.process_start_time = datetime.now().isoformat()
            task.last_heartbeat = datetime.now().isoformat()

            print(f"  - 进程PID: {task.process_pid}")
            print(f"  - 启动时间: {task.process_start_time}")

            return True, None

    def complete_task(self, task_id: str, success: bool = True) -> bool:
        """完成任务"""
        if task_id not in self.tasks:
            return False

        task = self.tasks[task_id]

        if success:
            task.status = TaskStatus.COMPLETED
            self.stats["tasks_completed"] += 1
        else:
            # 根据配置的失败率决定是否失败
            if random.random() < self.config["task_failure_rate"]:
                task.status = TaskStatus.FAILED
                self.stats["tasks_failed"] += 1
            else:
                task.status = TaskStatus.COMPLETED
                self.stats["tasks_completed"] += 1

        task.updated_at = datetime.now().isoformat()
        task.process_pid = None  # 清理进程

        # 更新队列状态
        queue_name = "openhuman_aiplan_build_priority"
        if queue_name in self.queues:
            self.queues[queue_name]["counts"]["running"] = max(
                0, self.queues[queue_name]["counts"]["running"] - 1
            )

            if task.status == TaskStatus.COMPLETED:
                self.queues[queue_name]["counts"]["completed"] += 1
            elif task.status == TaskStatus.FAILED:
                self.queues[queue_name]["counts"]["failed"] += 1

            # 如果当前任务完成，清空current_item_id
            if self.queues[queue_name]["current_item_id"] == task_id:
                self.queues[queue_name]["current_item_id"] = None

            self.queues[queue_name]["updated_at"] = datetime.now().isoformat()

        print(f"[{self.simulation_id}] 完成任务: {task_id}")
        print(f"  - 最终状态: {task.status.value}")

        # 记录性能指标
        if task.process_start_time:
            start_time = datetime.fromisoformat(task.process_start_time)
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            self.performance_metrics["task_completion_times"].append(duration)

        return True

    def detect_and_cleanup_stale_processes(self) -> int:
        """检测并清理僵尸进程（模拟5分钟延迟）"""
        print(f"[{self.simulation_id}] 检测僵尸进程...")

        cleaned_count = 0
        current_time = datetime.now()

        for task_id, task in self.tasks.items():
            if task.status == TaskStatus.RUNNING and task.last_heartbeat:
                last_heartbeat = datetime.fromisoformat(task.last_heartbeat)
                minutes_since_heartbeat = (current_time - last_heartbeat).total_seconds() / 60

                # 缺陷4: 5分钟延迟检测
                if minutes_since_heartbeat > self.config["heartbeat_delay_minutes"]:
                    print(
                        f"  ⚠️ 发现僵尸进程: {task_id} (最后心跳: {minutes_since_heartbeat:.1f}分钟前)"
                    )

                    # 标记为失败
                    task.status = TaskStatus.FAILED
                    task.updated_at = current_time.isoformat()

                    # 更新队列
                    queue_name = "openhuman_aiplan_build_priority"
                    if queue_name in self.queues:
                        self.queues[queue_name]["counts"]["running"] = max(
                            0, self.queues[queue_name]["counts"]["running"] - 1
                        )
                        self.queues[queue_name]["counts"]["failed"] += 1
                        if self.queues[queue_name]["current_item_id"] == task_id:
                            self.queues[queue_name]["current_item_id"] = None

                    cleaned_count += 1
                    self.stats["zombie_processes"] -= 1

        if cleaned_count > 0:
            print(f"  ✅ 清理了 {cleaned_count} 个僵尸进程")

        return cleaned_count

    def check_state_inconsistencies(self) -> list[dict[str, Any]]:
        """检查状态不一致问题"""
        inconsistencies = []

        # 检查队列计数与实际任务状态是否一致
        queue_name = "openhuman_aiplan_build_priority"
        if queue_name in self.queues:
            queue_counts = self.queues[queue_name]["counts"]

            # 统计实际任务状态
            actual_counts = {
                "pending": 0,
                "running": 0,
                "completed": 0,
                "failed": 0,
                "manual_hold": 0,
            }

            for task in self.tasks.values():
                if task.status.value in actual_counts:
                    actual_counts[task.status.value] += 1

            # 比较差异
            for status in actual_counts:
                if actual_counts[status] != queue_counts[status]:
                    inconsistency = {
                        "type": "queue_count_mismatch",
                        "status": status,
                        "queue_count": queue_counts[status],
                        "actual_count": actual_counts[status],
                        "difference": actual_counts[status] - queue_counts[status],
                    }
                    inconsistencies.append(inconsistency)

        # 检查进程状态更新时序问题
        for task_id, task in self.tasks.items():
            if task.process_status_updated_before_start and task.process_pid is None:
                inconsistency = {
                    "type": "process_status_timing",
                    "task_id": task_id,
                    "issue": "状态在进程启动前被更新为running",
                    "status": task.status.value,
                    "process_pid": task.process_pid,
                }
                inconsistencies.append(inconsistency)

        # 记录性能指标
        if inconsistencies:
            self.performance_metrics["state_inconsistencies"].append(len(inconsistencies))

        return inconsistencies

    def run_simulation_cycle(self, num_tasks: int = 10) -> dict[str, Any]:
        """运行一个模拟周期"""
        print(f"\n[{self.simulation_id}] ===== 开始模拟周期 =====")

        # 创建任务
        for i in range(num_tasks):
            task_type = random.choice(["build", "review", "plan", "scan"])
            success, task_id, id_problem = self.create_task(
                name=f"模拟任务 {i+1}", task_type=task_type
            )

            if success:
                # 启动任务
                start_success, error = self.start_task(task_id)

                if start_success:
                    # 模拟任务执行时间
                    execution_time = random.uniform(1.0, 10.0)
                    time.sleep(execution_time / 10)  # 加速模拟

                    # 完成任务
                    self.complete_task(task_id, success=random.random() > 0.1)

        # 检测僵尸进程
        cleaned = self.detect_and_cleanup_stale_processes()

        # 检查状态不一致
        inconsistencies = self.check_state_inconsistencies()

        # 计算错误率
        total_errors = (
            self.stats["argparse_errors"]
            + self.stats["process_reliability_errors"]
            + self.stats["lane_confusions"]
            + len(inconsistencies)
        )

        error_rate = total_errors / max(1, self.stats["tasks_created"]) * 100

        # 记录性能指标
        self.performance_metrics["error_rates"].append(error_rate)

        # 计算资源浪费（僵尸进程占用资源时间）
        resource_waste = (
            self.stats["zombie_processes"] * self.config["heartbeat_delay_minutes"] * 60
        )  # 秒
        self.performance_metrics["resource_waste"].append(resource_waste)

        # 汇总结果
        results = {
            "simulation_id": self.simulation_id,
            "tasks_created": self.stats["tasks_created"],
            "tasks_completed": self.stats["tasks_completed"],
            "tasks_failed": self.stats["tasks_failed"],
            "argparse_errors": self.stats["argparse_errors"],
            "manifest_duplicates": self.stats["manifest_duplicates"],
            "process_reliability_errors": self.stats["process_reliability_errors"],
            "lane_confusions": self.stats["lane_confusions"],
            "zombie_processes": self.stats["zombie_processes"],
            "zombie_processes_cleaned": cleaned,
            "state_inconsistencies": len(inconsistencies),
            "error_rate_percent": error_rate,
            "resource_waste_seconds": resource_waste,
            "inconsistency_details": inconsistencies,
            "timestamp": datetime.now().isoformat(),
        }

        print(f"[{self.simulation_id}] ===== 模拟周期完成 =====")
        print("结果摘要:")
        print(f"  - 任务总数: {results['tasks_created']}")
        print(f"  - 错误率: {results['error_rate_percent']:.1f}%")
        print(f"  - 状态不一致: {results['state_inconsistencies']}")
        print(f"  - 僵尸进程: {results['zombie_processes']}")
        print(f"  - 资源浪费: {results['resource_waste_seconds']:.0f}秒")

        return results

    def get_performance_summary(self) -> dict[str, Any]:
        """获取性能摘要"""
        if not self.performance_metrics["task_completion_times"]:
            avg_completion_time = 0
        else:
            avg_completion_time = sum(self.performance_metrics["task_completion_times"]) / len(
                self.performance_metrics["task_completion_times"]
            )

        if not self.performance_metrics["error_rates"]:
            avg_error_rate = 0
        else:
            avg_error_rate = sum(self.performance_metrics["error_rates"]) / len(
                self.performance_metrics["error_rates"]
            )

        if not self.performance_metrics["resource_waste"]:
            avg_resource_waste = 0
        else:
            avg_resource_waste = sum(self.performance_metrics["resource_waste"]) / len(
                self.performance_metrics["resource_waste"]
            )

        if not self.performance_metrics["state_inconsistencies"]:
            avg_inconsistencies = 0
        else:
            avg_inconsistencies = sum(self.performance_metrics["state_inconsistencies"]) / len(
                self.performance_metrics["state_inconsistencies"]
            )

        return {
            "avg_completion_time_seconds": avg_completion_time,
            "avg_error_rate_percent": avg_error_rate,
            "avg_resource_waste_seconds": avg_resource_waste,
            "avg_state_inconsistencies": avg_inconsistencies,
            "total_tasks": self.stats["tasks_created"],
            "total_errors": (
                self.stats["argparse_errors"]
                + self.stats["process_reliability_errors"]
                + self.stats["lane_confusions"]
                + sum(self.performance_metrics["state_inconsistencies"])
            ),
            "config": self.config,
        }


def run_baseline_simulation():
    """运行基线模拟"""
    print("=" * 60)
    print("Athena队列系统基线模拟")
    print("模拟5个系统性缺陷:")
    print("1. 任务身份规范化失败（ID以'-'开头）")
    print("2. Manifest数据质量缺陷（24%重复率）")
    print("3. 进程可靠性契约缺失（先标记running再启动进程）")
    print("4. 活跃占位检测延迟（5分钟检测延迟）")
    print("5. Lane混合与路由混淆（15%混淆率）")
    print("=" * 60)

    simulator = AthenaQueueSimulator(simulation_id="baseline_v1")

    # 运行多个模拟周期
    all_results = []
    for cycle in range(3):
        print(f"\n{'='*40}")
        print(f"模拟周期 {cycle + 1}/3")
        print(f"{'='*40}")

        results = simulator.run_simulation_cycle(num_tasks=5)
        all_results.append(results)

        # 短暂暂停
        time.sleep(1)

    # 获取最终性能摘要
    performance_summary = simulator.get_performance_summary()

    print(f"\n{'='*60}")
    print("基线模拟完成")
    print(f"{'='*60}")

    print("性能摘要:")
    print(f"  平均任务完成时间: {performance_summary['avg_completion_time_seconds']:.2f}秒")
    print(f"  平均错误率: {performance_summary['avg_error_rate_percent']:.1f}%")
    print(f"  平均资源浪费: {performance_summary['avg_resource_waste_seconds']:.0f}秒")
    print(f"  平均状态不一致: {performance_summary['avg_state_inconsistencies']:.1f}")
    print(f"  总任务数: {performance_summary['total_tasks']}")
    print(f"  总错误数: {performance_summary['total_errors']}")

    return simulator, all_results, performance_summary


if __name__ == "__main__":
    run_baseline_simulation()
