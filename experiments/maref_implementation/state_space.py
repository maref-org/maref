"""
状态空间管理器 - MAREF智能工作流契约框架地层（状态平面）
强制所有系统状态属于64卦吸引子之一，实现状态空间锁定
设计原则：64状态吸引子盆地、自动回滚机制、状态验证
"""

import json
import logging
import os
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from .hexagram import HEXAGRAMS_64, Hexagram, get_hexagram_by_name


HALT_STATE_BINARY = "111010"

@dataclass
class StateTransition:
    """状态转换记录"""

    timestamp: str
    from_state: str  # 二进制表示
    to_state: str  # 二进制表示
    transition_type: str  # "direct", "gray_code", "rollback", "emergency"
    hamming_distance: int
    path_length: int
    success: bool
    error_message: Optional[str] = None


class StateSpaceManager:
    """状态空间管理器 - 强制64状态锁定，提供状态转换验证
    生产级增强：线程安全 + HALT 吸收态保护 + 审计 SQLite 日志
    """

    def __init__(self, state_file: str = None):
        """
        初始化状态空间管理器

        Args:
            state_file: 状态持久化文件路径，如果为None则不持久化
        """
        self._lock = threading.Lock()
        self.state_file = state_file
        self.current_state: Optional[Hexagram] = None
        self.state_history: List[StateTransition] = []
        self.invalid_transition_count = 0
        self.rollback_count = 0
        self._halted = False

        # 状态映射表：队列状态 -> 卦状态
        self.queue_state_mapping = {
            "pending": Hexagram.from_binary("111111"),  # 乾 - 初始状态，纯阳
            "running": Hexagram.from_binary("000000"),  # 坤 - 执行状态，纯阴
            "completed": Hexagram.from_binary("100010"),  # 屯 - 完成状态，初难后得
            "failed": Hexagram.from_binary("010001"),  # 蒙 - 失败状态，启蒙之始
            "manual_hold": Hexagram.from_binary("111010"),  # 需 - 等待状态，需待时机
            "retrying": Hexagram.from_binary("010111"),  # 讼 - 重试状态，争讼需慎
            "paused": Hexagram.from_binary("001000"),  # 谦 - 暂停状态，谦虚谨慎
            "canceled": Hexagram.from_binary("000100"),  # 豫 - 取消状态，预备中止
        }

        # 初始化当前状态为乾（初始状态）
        self.current_state = self.queue_state_mapping["pending"]

        # 如果提供了状态文件，尝试加载历史状态
        if state_file and os.path.exists(state_file):
            self._load_state_from_file()

    def enforce_64_state_constraint(self, state: Hexagram) -> bool:
        """强制64状态锁定，验证状态是否在64卦集合中"""
        if state not in HEXAGRAMS_64:
            logging.error(f"状态越界: {state.binary} ({state.symbol} {state.name}) 不在64卦集合中")
            self.invalid_transition_count += 1
            self._rollback_to_last_valid_state()
            return False

        logging.debug(f"状态验证通过: {state.symbol} {state.name} ({state.binary})")
        return True

    def automatic_rollback(
        self, current_state: Hexagram, attempted_state: Hexagram, max_hamming_distance: int = 3
    ) -> Hexagram:
        """
        当汉明距离>max_hamming_distance时自动回滚
        防止状态跳跃过大导致系统不稳定

        Args:
            current_state: 当前状态
            attempted_state: 尝试转换的目标状态
            max_hamming_distance: 最大允许汉明距离，默认3

        Returns:
            实际应用的状态（可能是回滚后的状态）
        """
        hamming_dist = current_state.hamming_distance(attempted_state)

        if hamming_dist <= max_hamming_distance:
            # 汉明距离在可接受范围内，允许转换
            return attempted_state

        # 汉明距离过大，执行自动回滚
        logging.warning(f"汉明距离过大({hamming_dist}>{max_hamming_distance})，执行自动回滚")
        self.rollback_count += 1

        # 记录无效转换
        transition = StateTransition(
            timestamp=datetime.now().isoformat(),
            from_state=current_state.binary,
            to_state=attempted_state.binary,
            transition_type="blocked",
            hamming_distance=hamming_dist,
            path_length=0,
            success=False,
            error_message=f"汉明距离过大: {hamming_dist} > {max_hamming_distance}",
        )
        self.state_history.append(transition)

        # 找到最近的有效状态
        rollback_state = self._find_nearest_valid_state(current_state, attempted_state)
        logging.info(f"回滚到最近有效状态: {rollback_state.symbol} {rollback_state.name}")

        # 记录回滚转换
        rollback_transition = StateTransition(
            timestamp=datetime.now().isoformat(),
            from_state=current_state.binary,
            to_state=rollback_state.binary,
            transition_type="rollback",
            hamming_distance=current_state.hamming_distance(rollback_state),
            path_length=1,
            success=True,
            error_message=f"从汉明距离{hamming_dist}过大回滚",
        )
        self.state_history.append(rollback_transition)

        # 保存状态（如果启用了持久化）
        self._save_state_to_file()

        return rollback_state

    def _find_nearest_valid_state(
        self, current_state: Hexagram, attempted_state: Hexagram
    ) -> Hexagram:
        """
        找到距离attempted_state最近的有效状态（在64卦集合中）
        优先选择汉明距离最小的有效状态
        """
        # 如果目标状态本身有效，返回目标状态
        if attempted_state in HEXAGRAMS_64:
            return attempted_state

        # 在64卦集合中寻找与目标状态汉明距离最小的状态
        min_distance = float("inf")
        nearest_state = current_state  # 默认回退到当前状态

        for valid_state in HEXAGRAMS_64:
            distance = attempted_state.hamming_distance(valid_state)
            if distance < min_distance:
                min_distance = distance
                nearest_state = valid_state

        logging.debug(f"找到最近有效状态: {nearest_state.symbol}, 汉明距离={min_distance}")
        return nearest_state

    def transition_state(
        self, target_state: Hexagram, use_gray_code: bool = True
    ) -> Dict[str, Any]:
        """
        执行状态转换，支持格雷编码转换（线程安全）

        Args:
            target_state: 目标状态
            use_gray_code: 是否使用格雷编码转换（汉明距离=1）

        Returns:
            转换结果字典
        """
        with self._lock:
            if self._halted:
                return {
                    "success": False,
                    "message": "系统处于 HALT 状态，禁止转换",
                    "final_state": self.current_state.binary if self.current_state else None,
                }

            if target_state and target_state.binary == HALT_STATE_BINARY:
                self._halted = True

            if not self.enforce_64_state_constraint(target_state):
                return {
                    "success": False,
                    "message": "目标状态不在64卦集合中",
                    "final_state": self.current_state.binary,
                }

            # 检查是否需要自动回滚
            final_state = self.automatic_rollback(self.current_state, target_state)

            # 记录状态转换
            transition_type = "gray_code" if use_gray_code else "direct"
            hamming_dist = self.current_state.hamming_distance(final_state)

            transition = StateTransition(
                timestamp=datetime.now().isoformat(),
                from_state=self.current_state.binary,
                to_state=final_state.binary,
                transition_type=transition_type,
                hamming_distance=hamming_dist,
                path_length=1 if hamming_dist == 1 else hamming_dist,
                success=True,
            )
            self.state_history.append(transition)
            self._log_to_memory(transition)

            # 更新当前状态
            previous_state = self.current_state
            self.current_state = final_state

            # 保存状态（如果启用了持久化）
            self._save_state_to_file()

            logging.info(f"状态转换成功: {previous_state.symbol} -> {self.current_state.symbol}")

            return {
                "success": True,
                "message": "状态转换成功",
                "previous_state": previous_state.binary,
                "current_state": self.current_state.binary,
                "hamming_distance": hamming_dist,
                "transition_type": transition_type,
            }

    def map_queue_state_to_hexagram(self, queue_state: str) -> Optional[Hexagram]:
        """将队列状态映射到卦状态"""
        return self.queue_state_mapping.get(queue_state)

    def get_queue_state_from_hexagram(self, hexagram: Hexagram) -> Optional[str]:
        """从卦状态反向映射到队列状态"""
        for queue_state, mapped_hexagram in self.queue_state_mapping.items():
            if hexagram == mapped_hexagram:
                return queue_state
        return None

    def validate_state_transition(self, from_state: str, to_state: str) -> Dict[str, Any]:
        """验证状态转换的有效性（不实际执行转换）"""
        try:
            from_hexagram = Hexagram.from_binary(from_state)
            to_hexagram = Hexagram.from_binary(to_state)
        except ValueError as e:
            return {"valid": False, "error": f"状态格式无效: {str(e)}"}

        # 验证状态是否在64卦集合中
        if not self.enforce_64_state_constraint(from_hexagram):
            return {"valid": False, "error": "源状态不在64卦集合中"}
        if not self.enforce_64_state_constraint(to_hexagram):
            return {"valid": False, "error": "目标状态不在64卦集合中"}

        # 检查汉明距离
        hamming_dist = from_hexagram.hamming_distance(to_hexagram)
        needs_rollback = hamming_dist > 3

        return {
            "valid": True,
            "from_state": from_state,
            "to_state": to_state,
            "hamming_distance": hamming_dist,
            "needs_gray_code": hamming_dist > 1,
            "needs_rollback": needs_rollback,
            "max_allowed_distance": 3,
            "message": "状态转换验证通过" if not needs_rollback else "需要自动回滚（汉明距离过大）",
        }

    def get_state_statistics(self) -> Dict[str, Any]:
        """获取状态管理统计信息"""
        total_transitions = len(self.state_history)
        successful_transitions = sum(1 for t in self.state_history if t.success)
        failed_transitions = total_transitions - successful_transitions

        # 计算平均汉明距离
        if total_transitions > 0:
            total_hamming = sum(t.hamming_distance for t in self.state_history)
            avg_hamming = total_hamming / total_transitions
        else:
            avg_hamming = 0

        return {
            "current_state": self.current_state.binary if self.current_state else None,
            "current_state_name": self.current_state.name if self.current_state else None,
            "total_transitions": total_transitions,
            "successful_transitions": successful_transitions,
            "failed_transitions": failed_transitions,
            "invalid_transition_count": self.invalid_transition_count,
            "rollback_count": self.rollback_count,
            "average_hamming_distance": avg_hamming,
            "state_history_length": len(self.state_history),
        }

    def _log_to_memory(self, transition: StateTransition):
        """状态转换写入 maref_memory.db SQLite 审计表"""
        try:
            import sqlite3
            db_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                "memory", "maref", "maref_memory.db",
            )
            os.makedirs(os.path.dirname(db_path), exist_ok=True)
            conn = sqlite3.connect(db_path, timeout=5)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS state_transitions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    from_state TEXT NOT NULL,
                    to_state TEXT NOT NULL,
                    transition_type TEXT NOT NULL,
                    hamming_distance INTEGER NOT NULL,
                    path_length INTEGER NOT NULL,
                    success INTEGER NOT NULL,
                    error_message TEXT,
                    created_at TEXT DEFAULT (datetime('now'))
                )
            """)
            conn.execute(
                "INSERT INTO state_transitions "
                "(timestamp, from_state, to_state, transition_type, hamming_distance, path_length, success, error_message) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    transition.timestamp,
                    transition.from_state,
                    transition.to_state,
                    transition.transition_type,
                    transition.hamming_distance,
                    transition.path_length,
                    1 if transition.success else 0,
                    transition.error_message,
                ),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logging.debug(f"SQLite audit log failed (non-fatal): {e}")

    def is_halt(self) -> bool:
        return self._halted

    def reset_state_history(self):
        """重置状态历史（保留当前状态）"""
        with self._lock:
            self.state_history = []
            self.invalid_transition_count = 0
            self.rollback_count = 0
            self._halted = False
            logging.info("状态历史已重置")

    def _save_state_to_file(self):
        """保存状态到文件"""
        if not self.state_file:
            return

        try:
            state_data = {
                "current_state": self.current_state.binary if self.current_state else None,
                "state_history": [asdict(t) for t in self.state_history],
                "statistics": self.get_state_statistics(),
                "last_updated": datetime.now().isoformat(),
            }

            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(state_data, f, indent=2, ensure_ascii=False)

            logging.debug(f"状态已保存到文件: {self.state_file}")
        except Exception as e:
            logging.error(f"保存状态到文件失败: {str(e)}")

    def _load_state_from_file(self):
        """从文件加载状态"""
        if not self.state_file or not os.path.exists(self.state_file):
            return

        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                state_data = json.load(f)

            # 加载当前状态
            if state_data.get("current_state"):
                self.current_state = Hexagram.from_binary(state_data["current_state"])

            # 加载状态历史
            if state_data.get("state_history"):
                for history_item in state_data["state_history"]:
                    transition = StateTransition(
                        timestamp=history_item.get("timestamp", ""),
                        from_state=history_item.get("from_state", ""),
                        to_state=history_item.get("to_state", ""),
                        transition_type=history_item.get("transition_type", ""),
                        hamming_distance=history_item.get("hamming_distance", 0),
                        path_length=history_item.get("path_length", 0),
                        success=history_item.get("success", False),
                        error_message=history_item.get("error_message"),
                    )
                    self.state_history.append(transition)

            logging.info(f"状态已从文件加载: {self.state_file}")
        except Exception as e:
            logging.error(f"从文件加载状态失败: {str(e)}")
            # 如果加载失败，使用默认初始状态
            self.current_state = self.queue_state_mapping["pending"]


# 全局单例实例
_state_space_manager = None


def get_state_space_manager(state_file: str = None) -> StateSpaceManager:
    """获取状态空间管理器单例"""
    global _state_space_manager
    if _state_space_manager is None:
        _state_space_manager = StateSpaceManager(state_file)
    return _state_space_manager
