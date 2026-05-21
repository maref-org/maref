"""
格雷编码转换器 - MAREF智能工作流契约框架核心组件
实现汉明距离=1的状态转换，确保系统演化的连续性和平滑性
基于格雷编码拓扑，防止灾难性跳跃
"""

import logging
import threading
from functools import lru_cache
from typing import List, Tuple

from .hexagram import Hexagram, binary_gray_code_transform


class GrayCodeTransformer:
    """格雷编码转换器 - 确保状态转换遵循汉明距离=1原则
    生产级增强：线程安全 + LRU 缓存 + HALT 吸收态保护
    """

    def __init__(self):
        self._lock = threading.Lock()
        self.conversion_history = []
        self.violation_count = 0
        self._halted = False

    @lru_cache(maxsize=128)
    def _cached_transform(self, from_bits: str, to_bits: str) -> Tuple[str, ...]:
        """带缓存的格雷编码转换（返回二进制串元组）"""
        return tuple(binary_gray_code_transform(from_bits, to_bits))

    def transform(self, from_state: Hexagram, to_state: Hexagram) -> List[Hexagram]:
        """计算格雷编码转换路径，确保汉明距离=1（线程安全，带缓存）"""
        with self._lock:
            if self._halted:
                logging.warning("系统处于HALT状态，拒绝转换")
                raise RuntimeError("System is in HALT state, no transitions allowed")

            from_bits = from_state.binary
            to_bits = to_state.binary

            logging.info(
                f"计算格雷编码转换: {from_state.symbol}({from_bits}) -> {to_state.symbol}({to_bits})"
            )

            # 检查是否需要多步转换
            hamming_dist = from_state.hamming_distance(to_state)

            if hamming_dist == 0:
                logging.info("源状态和目标状态相同，无需转换")
                return [from_state]

            if hamming_dist == 1:
                logging.info("汉明距离=1，单步转换")
                return [to_state]

            # 计算格雷编码路径（使用缓存）
            path_bits = list(self._cached_transform(from_bits, to_bits))

            # 转换为卦对象列表
            path_hexagrams = []
            for bits in path_bits:
                hexagram = Hexagram.from_binary(bits)
                path_hexagrams.append(hexagram)

            # 验证路径的连续性（每个相邻状态汉明距离=1）
            self._validate_path_continuity(path_hexagrams)

            # 记录转换
            self.conversion_history.append(
                {
                    "from": from_state.binary,
                    "to": to_state.binary,
                    "path_length": len(path_hexagrams),
                    "hamming_distance": hamming_dist,
                    "path": [h.binary for h in path_hexagrams],
                }
            )

            logging.info(f"转换路径计算完成: {len(path_hexagrams)} 步")
            for i, hexagram in enumerate(path_hexagrams):
                logging.info(f"  步骤 {i+1}: {hexagram.symbol} {hexagram.name} ({hexagram.binary})")

            return path_hexagrams

    def _validate_path_continuity(self, path: List[Hexagram]) -> bool:
        """验证路径中每个相邻状态的汉明距离=1"""
        violations = []

        for i in range(len(path) - 1):
            current = path[i]
            next_state = path[i + 1]
            dist = current.hamming_distance(next_state)

            if dist != 1:
                violation = {
                    "index": i,
                    "current": current.binary,
                    "next": next_state.binary,
                    "distance": dist,
                }
                violations.append(violation)
                logging.error(f"路径连续性违规: 步骤 {i} -> {i+1}, 汉明距离={dist}")

        if violations:
            self.violation_count += len(violations)
            logging.warning(f"发现 {len(violations)} 个路径连续性违规")
            return False

        return True

    def is_valid_conversion(
        self, from_state: Hexagram, to_state: Hexagram, max_hamming_distance: int = 3
    ) -> Tuple[bool, str]:
        """验证转换是否有效（检查汉明距离是否过大）"""
        hamming_dist = from_state.hamming_distance(to_state)

        if hamming_dist == 0:
            return True, "相同状态，无需转换"

        if hamming_dist == 1:
            return True, "汉明距离=1，有效单步转换"

        if hamming_dist <= max_hamming_distance:
            # 需要多步转换但距离可接受
            return True, f"需要 {hamming_dist} 步转换（汉明距离={hamming_dist}）"

        # 距离过大，需要熔断
        self.violation_count += 1
        error_msg = f"汉明距离过大: {hamming_dist} > {max_hamming_distance}，需要熔断保护"
        logging.error(error_msg)
        return False, error_msg

    def calculate_optimal_path(
        self, from_state: Hexagram, to_state: Hexagram, constraints: List[str] = None
    ) -> List[Hexagram]:
        """
        计算最优转换路径，考虑约束条件
        约束可以是：避免特定状态、优先特定路径等
        """
        from_bits = from_state.binary
        to_bits = to_state.binary

        # 基础格雷编码路径
        base_path = self.transform(from_state, to_state)

        if not constraints:
            return base_path

        # 应用约束
        filtered_path = []
        for hexagram in base_path:
            if self._satisfies_constraints(hexagram, constraints):
                filtered_path.append(hexagram)
            else:
                # 需要绕开约束状态
                alternative = self._find_alternative_state(hexagram, constraints, base_path)
                if alternative:
                    filtered_path.append(alternative)
                else:
                    # 无法找到替代状态，保持原状态
                    filtered_path.append(hexagram)

        # 重新验证连续性
        if self._validate_path_continuity(filtered_path):
            return filtered_path
        else:
            logging.warning("约束路径连续性验证失败，返回基础路径")
            return base_path

    def _satisfies_constraints(self, hexagram: Hexagram, constraints: List[str]) -> bool:
        """检查卦状态是否满足约束条件"""
        if not constraints:
            return True

        for constraint in constraints:
            if constraint.startswith("avoid_"):
                # 避免特定卦名或卦符号
                target = constraint[6:]
                if target == hexagram.name or target == hexagram.symbol:
                    return False

            elif constraint.startswith("prefer_"):
                # 偏好特定卦名或卦符号（这里只是检查，不返回False）
                pass

        return True

    def _find_alternative_state(
        self, hexagram: Hexagram, constraints: List[str], base_path: List[Hexagram]
    ) -> Optional[Hexagram]:
        """为违反约束的状态寻找替代状态"""
        # 尝试翻转一位比特
        for i in range(6):
            alternative = hexagram.flip_bit(i)
            if self._satisfies_constraints(alternative, constraints):
                # 检查替代状态是否在合理范围内
                if alternative in HEXAGRAMS_64:
                    return alternative

        return None

    def get_conversion_statistics(self) -> dict:
        """获取转换统计信息"""
        total_conversions = len(self.conversion_history)
        if total_conversions == 0:
            return {
                "total_conversions": 0,
                "violation_count": self.violation_count,
                "average_path_length": 0,
                "hamming_distribution": {},
            }

        total_steps = sum(record["path_length"] for record in self.conversion_history)
        average_path_length = total_steps / total_conversions

        # 汉明距离分布
        hamming_distribution = {}
        for record in self.conversion_history:
            dist = record["hamming_distance"]
            hamming_distribution[dist] = hamming_distribution.get(dist, 0) + 1

        return {
            "total_conversions": total_conversions,
            "violation_count": self.violation_count,
            "average_path_length": average_path_length,
            "hamming_distribution": hamming_distribution,
        }

    def reset_statistics(self):
        """重置转换统计信息"""
        self.conversion_history = []
        self.violation_count = 0
        logging.info("格雷编码转换统计信息已重置")


# 全局单例实例
_gray_code_transformer = None


def get_gray_code_transformer() -> GrayCodeTransformer:
    """获取格雷编码转换器单例"""
    global _gray_code_transformer
    if _gray_code_transformer is None:
        _gray_code_transformer = GrayCodeTransformer()
    return _gray_code_transformer
