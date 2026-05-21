"""
三才六层编排器 - MAREF智能工作流契约框架核心编排组件
实现三才（天地人）六层模型到Athena队列系统的映射
设计原则：分层隔离、状态锁定、格雷编码转换、互补网络
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from .gray_code import get_gray_code_transformer
from .hexagram import Hexagram, get_hexagram_by_name
from .state_space import get_state_space_manager


@dataclass
class AgentRole:
    """卦象角色 - 对应8个硬编码智能体角色"""

    name: str  # 角色名称
    function: str  # 功能描述
    hexagram: Optional[Hexagram] = None  # 对应的卦象
    complementary_role: Optional[str] = None  # 互补角色名称
    mirror_role: Optional[str] = None  # 镜像角色名称


class MAREFWorkflowOrchestrator:
    """基于MAREF框架的智能工作流编排器"""

    def __init__(self, config_file: str = None):
        """
        初始化MAREF工作流编排器

        Args:
            config_file: 配置文件路径
        """
        # 核心组件初始化
        self.current_state: Hexagram = Hexagram.from_binary("111111")  # 初始：乾
        self.state_history: List[Hexagram] = [self.current_state]

        # 初始化三才六层组件
        self.agent_roles: Dict[str, AgentRole] = self._initialize_agent_roles()
        self.complementary_pairs: Dict[Hexagram, Hexagram] = self._setup_complementary_pairs()
        self.mirror_agents: Dict[str, str] = self._setup_mirror_agents()

        # 初始化工具组件
        self.gray_code_transformer = get_gray_code_transformer()
        self.state_space_manager = get_state_space_manager()

        # 任务映射表：任务类型 -> 卦状态
        self.task_type_mapping = {
            "build": Hexagram.from_binary("100010"),  # 屯 - 构建任务，初难后得
            "review": Hexagram.from_binary("010001"),  # 蒙 - 审查任务，启蒙之始
            "plan": Hexagram.from_binary("111010"),  # 需 - 计划任务，需待时机
            "scan": Hexagram.from_binary("010111"),  # 讼 - 扫描任务，争讼需慎
            "audit": Hexagram.from_binary("001000"),  # 谦 - 审计任务，谦虚谨慎
            "test": Hexagram.from_binary("000100"),  # 豫 - 测试任务，预备中止
            "deploy": Hexagram.from_binary("101111"),  # 同人 - 部署任务，类族辨物
            "monitor": Hexagram.from_binary("111101"),  # 大有 - 监控任务，遏恶扬善
        }

        # 加载配置
        self.config = self._load_config(config_file) if config_file else {}

        logging.info(f"MAREF工作流编排器初始化完成，初始状态: {self.current_state.symbol}")

    def _initialize_agent_roles(self) -> Dict[str, AgentRole]:
        """初始化8个卦象角色（经层）"""
        roles = {
            "乾": AgentRole(
                name="Coordinator",
                function="路由与共识",
                hexagram=get_hexagram_by_name("乾"),
                complementary_role="坤",
                mirror_role="坤",
            ),
            "坤": AgentRole(
                name="Memory",
                function="存储与检索",
                hexagram=get_hexagram_by_name("坤"),
                complementary_role="乾",
                mirror_role="乾",
            ),
            "震": AgentRole(
                name="Executor",
                function="执行与工具使用",
                hexagram=get_hexagram_by_name("震"),
                complementary_role="巽",
                mirror_role="艮",
            ),
            "巽": AgentRole(
                name="Critic",
                function="验证与错误修正",
                hexagram=get_hexagram_by_name("巽"),
                complementary_role="震",
                mirror_role="兑",
            ),
            "坎": AgentRole(
                name="Explorer",
                function="搜索与发现",
                hexagram=get_hexagram_by_name("坎"),
                complementary_role="离",
                mirror_role="离",
            ),
            "离": AgentRole(
                name="Communicator",
                function="界面与表达",
                hexagram=get_hexagram_by_name("离"),
                complementary_role="坎",
                mirror_role="坎",
            ),
            "艮": AgentRole(
                name="Guardian",
                function="安全与约束",
                hexagram=get_hexagram_by_name("艮"),
                complementary_role="兑",
                mirror_role="震",
            ),
            "兑": AgentRole(
                name="Learner",
                function="适应与训练",
                hexagram=get_hexagram_by_name("兑"),
                complementary_role="艮",
                mirror_role="巽",
            ),
        }
        return roles

    def _setup_complementary_pairs(self) -> Dict[Hexagram, Hexagram]:
        """设置互补对（错卦）网络"""
        complementary_pairs = {}

        # 乾 ↔ 坤（纯阳 ↔ 纯阴）
        qian = get_hexagram_by_name("乾")
        kun = get_hexagram_by_name("坤")
        complementary_pairs[qian] = kun
        complementary_pairs[kun] = qian

        # 震 ↔ 巽（雷 ↔ 风）
        zhen = get_hexagram_by_name("震")
        xun = get_hexagram_by_name("巽")
        complementary_pairs[zhen] = xun
        complementary_pairs[xun] = zhen

        # 坎 ↔ 离（水 ↔ 火）
        kan = get_hexagram_by_name("坎")
        li = get_hexagram_by_name("离")
        complementary_pairs[kan] = li
        complementary_pairs[li] = kan

        # 艮 ↔ 兑（山 ↔ 泽）
        gen = get_hexagram_by_name("艮")
        dui = get_hexagram_by_name("兑")
        complementary_pairs[gen] = dui
        complementary_pairs[dui] = gen

        logging.info(f"已设置 {len(complementary_pairs)} 对互补关系")
        return complementary_pairs

    def _setup_mirror_agents(self) -> Dict[str, str]:
        """设置镜像智能体（综卦）"""
        mirror_agents = {
            "乾": "坤",  # 乾的镜像是坤（纯阳 ↔ 纯阴）
            "坤": "乾",
            "震": "艮",  # 震的镜像是艮（雷 ↔ 山）
            "巽": "兑",  # 巽的镜像是兑（风 ↔ 泽）
            "坎": "离",  # 坎的镜像是离（水 ↔ 火）
            "离": "坎",
            "艮": "震",  # 艮的镜像是震（山 ↔ 雷）
            "兑": "巽",  # 兑的镜像是巽（泽 ↔ 风）
        }
        return mirror_agents

    def _load_config(self, config_file: str) -> Dict[str, Any]:
        """加载配置文件"""
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                config = json.load(f)
            logging.info(f"配置文件加载成功: {config_file}")
            return config
        except Exception as e:
            logging.warning(f"配置文件加载失败: {str(e)}，使用默认配置")
            return {}

    def transition_state(self, target_state: Hexagram) -> Dict[str, Any]:
        """
        执行格雷编码状态转换

        Args:
            target_state: 目标卦状态

        Returns:
            转换结果字典
        """
        logging.info(f"开始状态转换: {self.current_state.symbol} -> {target_state.symbol}")

        # 验证状态转换有效性
        validation = self.state_space_manager.validate_state_transition(
            self.current_state.binary, target_state.binary
        )

        if not validation["valid"]:
            logging.error(f"状态转换验证失败: {validation.get('error')}")
            return {
                "success": False,
                "message": f"状态转换验证失败: {validation.get('error')}",
                "current_state": self.current_state.binary,
                "target_state": target_state.binary,
            }

        # 检查是否需要自动回滚
        if validation["needs_rollback"]:
            logging.warning(f"汉明距离过大({validation['hamming_distance']}>3)，需要自动回滚")
            rollback_result = self.state_space_manager.automatic_rollback(
                self.current_state, target_state
            )
            if rollback_result != target_state:
                logging.info(f"自动回滚到: {rollback_result.symbol}")
                target_state = rollback_result

        # 执行状态转换
        if validation["hamming_distance"] == 1:
            # 单步转换（汉明距离=1）
            self._execute_single_transition(target_state)
            path = [target_state]
        else:
            # 多步格雷编码转换
            path = self._calculate_gray_code_path(self.current_state, target_state)
            for intermediate_state in path:
                self._execute_single_transition(intermediate_state)

        # 记录转换历史
        self.state_history.append(self.current_state)

        result = {
            "success": True,
            "message": "状态转换成功",
            "previous_state": (
                self.state_history[-2].binary if len(self.state_history) > 1 else None
            ),
            "current_state": self.current_state.binary,
            "target_state": target_state.binary,
            "path_length": len(path),
            "hamming_distance": validation["hamming_distance"],
            "path": [state.binary for state in path],
            "path_symbols": [state.symbol for state in path],
        }

        logging.info(f"状态转换完成: {result['path_length']} 步转换")
        return result

    def _calculate_gray_code_path(self, from_state: Hexagram, to_state: Hexagram) -> List[Hexagram]:
        """计算格雷编码转换路径"""
        return self.gray_code_transformer.transform(from_state, to_state)

    def _execute_single_transition(self, target_state: Hexagram):
        """执行单步状态转换"""
        logging.debug(f"执行单步转换: {self.current_state.symbol} -> {target_state.symbol}")

        # 更新当前状态
        previous_state = self.current_state
        self.current_state = target_state

        # 触发状态转换事件
        self._on_state_transition(previous_state, target_state)

    def _on_state_transition(self, from_state: Hexagram, to_state: Hexagram):
        """状态转换事件处理"""
        # 1. 更新状态空间管理器
        self.state_space_manager.transition_state(to_state)

        # 2. 检查是否需要激活互补对
        if self._should_activate_complementary_pair(from_state, to_state):
            complementary_state = self.complementary_pairs.get(to_state)
            if complementary_state:
                logging.info(f"激活互补对: {to_state.symbol} ↔ {complementary_state.symbol}")

        # 3. 检查是否需要切换镜像智能体
        if self._should_switch_mirror_agent(from_state, to_state):
            mirror_hexagram_name = self.mirror_agents.get(to_state.name)
            if mirror_hexagram_name:
                logging.info(f"切换到镜像智能体: {to_state.name} → {mirror_hexagram_name}")

        # 4. 记录转换日志
        logging.info(
            f"状态转换事件: {from_state.symbol}({from_state.name}) → {to_state.symbol}({to_state.name})"
        )

    def _should_activate_complementary_pair(self, from_state: Hexagram, to_state: Hexagram) -> bool:
        """检查是否需要激活互补对"""
        # 如果状态转换涉及极端变化（如乾↔坤），激活互补对
        extreme_changes = [("乾", "坤"), ("坤", "乾"), ("坎", "离"), ("离", "坎")]

        change_pair = (from_state.name, to_state.name)
        return change_pair in extreme_changes

    def _should_switch_mirror_agent(self, from_state: Hexagram, to_state: Hexagram) -> bool:
        """检查是否需要切换镜像智能体"""
        # 如果状态停滞或振荡，切换镜像智能体
        if len(self.state_history) < 3:
            return False

        # 检查最近3次状态是否相同（停滞）
        recent_states = self.state_history[-3:]
        if all(state == to_state for state in recent_states):
            return True

        # 检查状态振荡（A->B->A->B模式）
        if len(self.state_history) >= 4:
            states = [s.name for s in self.state_history[-4:]]
            if states == [from_state.name, to_state.name, from_state.name, to_state.name]:
                return True

        return False

    def route_task(self, task_metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        智能路由任务到合适的卦状态和执行器

        Args:
            task_metadata: 任务元数据

        Returns:
            路由决策字典
        """
        task_type = task_metadata.get("type", "unknown")
        entry_stage = task_metadata.get("entry_stage", "")
        resources = task_metadata.get("resources", {})

        # 1. 基于任务类型映射到卦状态
        hexagram_state = self.task_type_mapping.get(task_type, self.current_state)

        # 2. 考虑系统当前状态和负载
        system_load = self._estimate_system_load()
        if system_load > 0.8:  # 高负载
            # 降级到更稳定的卦状态
            hexagram_state = self._select_stable_state(hexagram_state)

        # 3. 考虑资源需求
        if resources.get("memory_mb", 0) > 4096:
            # 大内存任务需要更稳定的状态
            hexagram_state = Hexagram.from_binary("000000")  # 坤 - 稳定执行

        # 4. 选择执行器角色
        agent_role = self._select_agent_role(hexagram_state)

        decision = {
            "task_type": task_type,
            "hexagram_state": hexagram_state.binary,
            "hexagram_symbol": hexagram_state.symbol,
            "hexagram_name": hexagram_state.name,
            "agent_role": agent_role.name,
            "agent_function": agent_role.function,
            "complementary_role": agent_role.complementary_role,
            "mirror_role": agent_role.mirror_role,
            "system_load": system_load,
            "routing_reason": f"基于task_type={task_type}, entry_stage={entry_stage}, 系统负载={system_load:.2f}",
        }

        logging.info(f"任务路由决策: {task_type} -> {hexagram_state.symbol} ({agent_role.name})")
        return decision

    def _estimate_system_load(self) -> float:
        """估算系统负载（0.0-1.0）"""
        # 简化实现：基于状态历史变化频率估算负载
        if len(self.state_history) < 5:
            return 0.3  # 低负载

        recent_changes = 0
        for i in range(1, min(10, len(self.state_history))):
            if self.state_history[i] != self.state_history[i - 1]:
                recent_changes += 1

        load = recent_changes / min(9, len(self.state_history) - 1)
        return min(load, 1.0)

    def _select_stable_state(self, original_state: Hexagram) -> Hexagram:
        """选择更稳定的卦状态（用于高负载时降级）"""
        stable_states = [
            Hexagram.from_binary("000000"),  # 坤 - 最稳定
            Hexagram.from_binary("111111"),  # 乾 - 初始稳定
            Hexagram.from_binary("001000"),  # 谦 - 谦虚稳定
        ]

        # 选择与原始状态汉明距离最小的稳定状态
        min_distance = float("inf")
        best_state = original_state

        for stable_state in stable_states:
            distance = original_state.hamming_distance(stable_state)
            if distance < min_distance:
                min_distance = distance
                best_state = stable_state

        return best_state

    def _select_agent_role(self, hexagram_state: Hexagram) -> AgentRole:
        """根据卦状态选择执行器角色"""
        # 默认使用乾（Coordinator）
        default_role = self.agent_roles["乾"]

        # 尝试根据卦名查找对应的角色
        hexagram_name = hexagram_state.name
        if hexagram_name in self.agent_roles:
            return self.agent_roles[hexagram_name]

        # 如果没有直接对应，根据卦的二进制特征选择
        if hexagram_state.binary.startswith("1"):
            # 阳爻为主的卦，使用Executor
            return self.agent_roles["震"]
        else:
            # 阴爻为主的卦，使用Memory
            return self.agent_roles["坤"]

    def get_system_status(self) -> Dict[str, Any]:
        """获取系统状态信息"""
        gray_code_stats = self.gray_code_transformer.get_conversion_statistics()
        state_space_stats = self.state_space_manager.get_state_statistics()

        return {
            "current_state": {
                "binary": self.current_state.binary,
                "symbol": self.current_state.symbol,
                "name": self.current_state.name,
                "description": self.current_state.description,
            },
            "state_history_length": len(self.state_history),
            "agent_roles_count": len(self.agent_roles),
            "complementary_pairs_count": len(self.complementary_pairs),
            "mirror_agents_count": len(self.mirror_agents),
            "gray_code_transformer": gray_code_stats,
            "state_space_manager": state_space_stats,
            "system_load": self._estimate_system_load(),
            "timestamp": datetime.now().isoformat(),
        }

    def reset_system(self):
        """重置系统到初始状态"""
        self.current_state = Hexagram.from_binary("111111")  # 乾
        self.state_history = [self.current_state]
        self.gray_code_transformer.reset_statistics()
        self.state_space_manager.reset_state_history()

        logging.info("MAREF系统已重置到初始状态（乾）")


# 全局单例实例
_maref_orchestrator = None


def get_maref_orchestrator(config_file: str = None) -> MAREFWorkflowOrchestrator:
    """获取MAREF编排器单例"""
    global _maref_orchestrator
    if _maref_orchestrator is None:
        _maref_orchestrator = MAREFWorkflowOrchestrator(config_file)
    return _maref_orchestrator
