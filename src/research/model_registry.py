"""Model Registry — 全局模型注册表

记录所有已知 LLM 模型及其能力画像、价格、状态。
这是多 LLM 路由的"知识库"，让路由决策知道：
  - 哪些模型存在，叫什么名字
  - 每个模型擅长什么（编码、推理、创意、分析、视觉）
  - 价格档次（免费 / 低价 / 标准 / 高价）
  - 提供商接入方式（直连 / 平台代理）
  - 模型版本/更新日期（用于感知"模型更新了"）

用法:
    from research.model_registry import registry, ModelCapability, CostTier

    # 按能力找模型
    coding_models = registry.find_by_capability(ModelCapability.CODING)

    # 获取某个模型的完整信息
    info = registry.get_model("kimi-k3")

    # 列出所有提供商及其模型
    for prov in registry.list_providers():
        print(prov.name, [m.model_id for m in prov.models])
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

# ── 能力枚举 ──────────────────────────────────────────────────────────────

class ModelCapability(Enum):
    """模型能力维度 — 路由决策的核心依据"""
    CHAT = "chat"               # 通用对话
    CODING = "coding"           # 代码生成/理解
    REASONING = "reasoning"     # 深度推理/思维链
    CREATIVE = "creative"       # 创意写作/头脑风暴
    ANALYSIS = "analysis"       # 数据分析/结构化输出
    VISION = "vision"           # 多模态/图像理解
    FUNCTION_CALLING = "function_calling"  # 工具调用/函数调用
    RAG = "rag"                 # 检索增强适用
    AGENTIC = "agentic"         # 自主 Agent 循环
    SPEED = "speed"             # 低延迟（流式友好）


class CostTier(Enum):
    """价格档次"""
    FREE = "free"               # 免费
    CHEAP = "cheap"             # 极低价 (< ¥0.005/1K tokens)
    LOW = "low"                 # 低价 (¥0.005–0.02)
    STANDARD = "standard"       # 标准 (¥0.02–0.10)
    HIGH = "high"               # 高价 (¥0.10–0.50)
    PREMIUM = "premium"         # 旗舰 (> ¥0.50)


class ProviderKind(Enum):
    """提供商接入方式"""
    DIRECT = "direct"           # 直连官方 API
    PLATFORM = "platform"       # 通过聚合平台（SiliconFlow / NVCF 等）
    SUBSCRIPTION = "subscription"  # 包月套餐


@dataclass
class ModelInfo:
    """单个模型的完整信息"""
    model_id: str                           # 唯一标识，如 "deepseek-v4"
    provider: str                           # 提供商 key，如 "deepseek"
    display_name: str                       # 人类可读名称，如 "DeepSeek V4"
    api_model_name: str                     # API 调用时用的 model 名
    base_url: str                           # API 端点
    api_key_env: str                        # 环境变量名
    capabilities: set[ModelCapability] = field(default_factory=set)
    cost_tier: CostTier = CostTier.STANDARD
    cost_per_1k_input: float = 0.0          # ¥ / 1K input tokens
    cost_per_1k_output: float = 0.0         # ¥ / 1K output tokens
    context_window: int = 8192
    max_output_tokens: int = 4096
    priority: int = 10                      # 路由优先级（小=优先）
    version: str = ""                       # 版本号 / 发布日期
    tags: list[str] = field(default_factory=list)  # 标签，如 "fast", "reasoning"
    notes: str = ""                         # 备注

    @property
    def cost_per_1k_mixed(self) -> float:
        """按 3:1 input:output 估算混合成本"""
        return (self.cost_per_1k_input * 3 + self.cost_per_1k_output) / 4


@dataclass
class ProviderInfo:
    """提供商信息"""
    key: str
    name: str
    kind: ProviderKind
    base_url: str
    api_key_env: str
    models: list[ModelInfo] = field(default_factory=list)
    notes: str = ""


# ═══════════════════════════════════════════════════════════════════════════
# 模型注册表 — 完整数据
# ═══════════════════════════════════════════════════════════════════════════

# 所有提供商按 key 索引
_PROVIDERS_DATA: dict[str, ProviderInfo] = {}

def _reg(
    provider_key: str,
    provider_name: str,
    kind: ProviderKind,
    base_url: str,
    api_key_env: str,
    notes: str = "",
) -> ProviderInfo:
    p = ProviderInfo(
        key=provider_key,
        name=provider_name,
        kind=kind,
        base_url=base_url,
        api_key_env=api_key_env,
        notes=notes,
    )
    _PROVIDERS_DATA[provider_key] = p
    return p


def _model(
    provider_key: str,
    model_id: str,
    display_name: str,
    api_model_name: str,
    capabilities: set[ModelCapability],
    cost_tier: CostTier = CostTier.STANDARD,
    cost_per_1k_input: float = 0.0,
    cost_per_1k_output: float = 0.0,
    context_window: int = 8192,
    max_output_tokens: int = 4096,
    priority: int = 10,
    version: str = "",
    tags: list[str] | None = None,
    notes: str = "",
) -> ModelInfo:
    m = ModelInfo(
        model_id=model_id,
        provider=provider_key,
        display_name=display_name,
        api_model_name=api_model_name,
        base_url=_PROVIDERS_DATA[provider_key].base_url,
        api_key_env=_PROVIDERS_DATA[provider_key].api_key_env,
        capabilities=capabilities,
        cost_tier=cost_tier,
        cost_per_1k_input=cost_per_1k_input,
        cost_per_1k_output=cost_per_1k_output,
        context_window=context_window,
        max_output_tokens=max_output_tokens,
        priority=priority,
        version=version,
        tags=tags or [],
        notes=notes,
    )
    _PROVIDERS_DATA[provider_key].models.append(m)
    return m


# ─────────────────────────────────────────────────────────────────────────
# 1. DeepSeek 直连
# ─────────────────────────────────────────────────────────────────────────

_reg("deepseek", "DeepSeek 直连", ProviderKind.DIRECT,
    "https://api.deepseek.com/v1", "DEEPSEEK_API_KEY",
    notes="DeepSeek 官方 API，支持 V4 系列")

_model("deepseek", "deepseek-v4-chat", "DeepSeek V4 Chat", "deepseek-chat",
       {ModelCapability.CHAT, ModelCapability.CODING, ModelCapability.ANALYSIS,
        ModelCapability.FUNCTION_CALLING, ModelCapability.AGENTIC},
       cost_tier=CostTier.LOW, cost_per_1k_input=0.012, cost_per_1k_output=0.012,
       context_window=65536, max_output_tokens=8192, priority=5,
       version="2026-06", tags=["chat", "coding", "default"],
       notes="主力对话模型，兼顾速度与质量，默认首选")

_model("deepseek", "deepseek-v4-flash", "DeepSeek V4 Flash", "deepseek-v4-flash",
       {ModelCapability.CHAT, ModelCapability.CODING, ModelCapability.REASONING,
        ModelCapability.FUNCTION_CALLING, ModelCapability.SPEED},
       cost_tier=CostTier.CHEAP, cost_per_1k_input=0.005, cost_per_1k_output=0.005,
       context_window=32768, max_output_tokens=4096, priority=10,
       version="2026-06", tags=["fast", "cheap", "flash", "reasoning"],
       notes="极速推理版，需预留思路 token 空间，¥0.005/1K 超低价")

_model("deepseek", "deepseek-v4-reasoner", "DeepSeek V4 Reasoner", "deepseek-reasoner",
       {ModelCapability.REASONING, ModelCapability.ANALYSIS, ModelCapability.CODING},
       cost_tier=CostTier.LOW, cost_per_1k_input=0.014, cost_per_1k_output=0.028,
       context_window=65536, max_output_tokens=8192, priority=20,
       version="2026-06", tags=["reasoning", "deep-think"],
       notes="深度推理版，适合复杂逻辑、数学、代码生成")


# ─────────────────────────────────────────────────────────────────────────
# 2. 硅基流动 (SiliconFlow)
# ─────────────────────────────────────────────────────────────────────────

_reg("siliconflow", "硅基流动", ProviderKind.PLATFORM,
    "https://api.siliconflow.cn/v1", "SILICONFLOW_API_KEY",
    notes="国内聚合平台，提供多种开源/商业模型代理")

_model("siliconflow", "sf-deepseek-v4-pro", "SF DeepSeek V4 Pro", "deepseek-ai/DeepSeek-V4-Pro",
       {ModelCapability.CHAT, ModelCapability.CODING, ModelCapability.ANALYSIS,
        ModelCapability.FUNCTION_CALLING},
       cost_tier=CostTier.LOW, cost_per_1k_input=0.010, cost_per_1k_output=0.010,
       context_window=65536, max_output_tokens=8192, priority=15,
       tags=["chat", "coding", "proxy"], notes="通过硅基流动代理 DeepSeek V4 Pro")

_model("siliconflow", "sf-deepseek-v4-flash", "SF DeepSeek V4 Flash", "deepseek-ai/DeepSeek-V4-Flash",
       {ModelCapability.CHAT, ModelCapability.CODING, ModelCapability.SPEED,
        ModelCapability.FUNCTION_CALLING},
       cost_tier=CostTier.CHEAP, cost_per_1k_input=0.005, cost_per_1k_output=0.005,
       context_window=32768, max_output_tokens=4096, priority=10,
       tags=["fast", "cheap", "proxy"],
       notes="通过硅基流动代理 DeepSeek V4 Flash，低价高速")

_model("siliconflow", "sf-deepseek-r1", "SF DeepSeek R1", "deepseek-ai/DeepSeek-R1",
       {ModelCapability.REASONING, ModelCapability.ANALYSIS},
       cost_tier=CostTier.LOW, cost_per_1k_input=0.010, cost_per_1k_output=0.020,
       context_window=65536, max_output_tokens=8192, priority=25,
       tags=["reasoning", "proxy"],
       notes="通过硅基流动代理 DeepSeek R1 推理模型")

_model("siliconflow", "sf-qwen3.5-35b", "SF Qwen3.5 35B", "Qwen/Qwen3.5-35B-A3B",
       {ModelCapability.CHAT, ModelCapability.CODING, ModelCapability.REASONING,
        ModelCapability.FUNCTION_CALLING},
       cost_tier=CostTier.LOW, cost_per_1k_input=0.010, cost_per_1k_output=0.010,
       context_window=32768, max_output_tokens=8192, priority=30,
       tags=["chat", "coding", "moE"],
       notes="Qwen3.5 35B (MoE)，性价比优秀")

_model("siliconflow", "sf-glm-4", "SF GLM-4", "THUDM/GLM-4-9B-Chat",
       {ModelCapability.CHAT, ModelCapability.ANALYSIS},
       cost_tier=CostTier.CHEAP, cost_per_1k_input=0.002, cost_per_1k_output=0.002,
       context_window=8192, max_output_tokens=4096, priority=40,
       tags=["chat", "proxy"],
       notes="GLM-4 通过硅基流动代理，9B 轻量版")


# ─────────────────────────────────────────────────────────────────────────
# 3. 英伟达 NVCF (NVIDIA Cloud Functions)
# ─────────────────────────────────────────────────────────────────────────

_reg("nvidia", "英伟达 NVCF", ProviderKind.PLATFORM,
    "https://integrate.api.nvidia.com/v1", "NVIDIA_API_KEY",
    notes="NVIDIA 云函数平台，提供多种开源模型的免费/付费推理")

_model("nvidia", "nv-deepseek-v4-pro", "NV DeepSeek V4 Pro", "deepseek-ai/deepseek-v4-pro",
       {ModelCapability.CHAT, ModelCapability.CODING, ModelCapability.REASONING,
        ModelCapability.ANALYSIS, ModelCapability.FUNCTION_CALLING},
       cost_tier=CostTier.LOW, cost_per_1k_input=0.010, cost_per_1k_output=0.010,
       context_window=65536, max_output_tokens=8192, priority=14,
       tags=["chat", "coding", "nvidia"],
       notes="NVCF 上的 DeepSeek V4，配合 NIM 优化推理")

_model("nvidia", "nv-glm-5.2", "NV GLM-5.2", "z-ai/glm-5.2",
       {ModelCapability.CHAT, ModelCapability.REASONING, ModelCapability.CREATIVE,
        ModelCapability.CODING, ModelCapability.ANALYSIS},
       cost_tier=CostTier.LOW, cost_per_1k_input=0.010, cost_per_1k_output=0.010,
       context_window=131072, max_output_tokens=16384, priority=1,
       version="2026-07", tags=["chat", "creative", "nvidia"],
       notes="NVCF 托管的 GLM-5.2，替代已下线的 Qwen3 80B (qwen3-next-80b 于 2026-07-27 EOL)，保留 CREATIVE 能力")


# ─────────────────────────────────────────────────────────────────────────
# 4. Kimi / Moonshot 直连 (含 K3)
# ─────────────────────────────────────────────────────────────────────────

_reg("kimi", "Kimi (Moonshot)", ProviderKind.DIRECT,
    "https://api.moonshot.cn/v1", "KIMI_API_KEY",
    notes="月之暗面 Moonshot 官方 API。K3 是 2026 年新旗舰")

_model("kimi", "kimi-k2.7-code", "Kimi K2.7 Code", "kimi-k2.7-code",
       {ModelCapability.CHAT, ModelCapability.CODING, ModelCapability.ANALYSIS,
        ModelCapability.FUNCTION_CALLING, ModelCapability.SPEED},
       cost_tier=CostTier.LOW, cost_per_1k_input=0.008, cost_per_1k_output=0.024,
       context_window=131072, max_output_tokens=8192, priority=6,
       version="2026-07", tags=["fast", "coding", "chat"],
       notes="Kimi K2.7 Code，编程优化版，131K 上下文，支持温度调节")

_model("kimi", "kimi-k2.7-code-highspeed", "Kimi K2.7 Code HighSpeed", "kimi-k2.7-code-highspeed",
       {ModelCapability.CHAT, ModelCapability.CODING, ModelCapability.SPEED,
        ModelCapability.FUNCTION_CALLING},
       cost_tier=CostTier.LOW, cost_per_1k_input=0.012, cost_per_1k_output=0.036,
       context_window=32768, max_output_tokens=8192, priority=7,
       version="2026-07", tags=["fast", "coding", "cheap"],
       notes="K2.7 Code 极速版，固定 temperature=1，低延迟适合高频编码场景")

_model("kimi", "kimi-k3", "Kimi K3", "kimi-k3",
       {ModelCapability.CHAT, ModelCapability.CODING, ModelCapability.REASONING,
        ModelCapability.ANALYSIS, ModelCapability.CREATIVE,
        ModelCapability.FUNCTION_CALLING, ModelCapability.VISION,
        ModelCapability.AGENTIC},
       cost_tier=CostTier.STANDARD, cost_per_1k_input=0.02, cost_per_1k_output=0.06,
       context_window=131072, max_output_tokens=16384, priority=5,
       version="2026-07", tags=["flagship", "long-context", "vision", "k3"],
       notes="Kimi K3 — 2026年7月新旗舰，131K 超长上下文，支持视觉/工具调用/Agent 循环")

_model("kimi", "kimi-k2.6", "Kimi K2.6", "kimi-k2.6",
       {ModelCapability.CHAT, ModelCapability.ANALYSIS, ModelCapability.CODING},
       cost_tier=CostTier.LOW, cost_per_1k_input=0.006, cost_per_1k_output=0.018,
       context_window=131072, max_output_tokens=8192, priority=20,
       tags=["chat", "long-context", "cheap"],
       notes="Kimi K2.6，性价比长上下文版本")


# ─────────────────────────────────────────────────────────────────────────
# 5. GLM 直连 (智谱 AI)
# ─────────────────────────────────────────────────────────────────────────

_reg("glm", "智谱 GLM", ProviderKind.DIRECT,
    "https://open.bigmodel.cn/api/paas/v4", "GLM_API_KEY",
    notes="智谱 AI 官方 API，GLM-5 系列")

_model("glm", "glm-5.2", "GLM-5.2", "glm-5.2",
       {ModelCapability.CHAT, ModelCapability.CODING, ModelCapability.ANALYSIS,
        ModelCapability.REASONING, ModelCapability.FUNCTION_CALLING,
        ModelCapability.CREATIVE},
       cost_tier=CostTier.STANDARD, cost_per_1k_input=0.05, cost_per_1k_output=0.05,
       context_window=131072, max_output_tokens=16384, priority=5,
       version="2026-07", tags=["flagship", "chat", "reasoning", "creative"],
       notes="GLM-5.2 — 智谱最新旗舰，推理能力大幅提升，兼作 CREATIVE 路由候选")

_model("glm", "glm-5", "GLM-5", "glm-5",
       {ModelCapability.CHAT, ModelCapability.CODING, ModelCapability.ANALYSIS,
        ModelCapability.FUNCTION_CALLING},
       cost_tier=CostTier.LOW, cost_per_1k_input=0.03, cost_per_1k_output=0.03,
       context_window=131072, max_output_tokens=8192, priority=10,
       version="2026-06", tags=["chat", "stable"],
       notes="GLM-5，稳定版旗舰，工具调用能力强")

_model("glm", "glm-4.7", "GLM-4.7", "glm-4.7",
       {ModelCapability.CHAT, ModelCapability.CODING, ModelCapability.ANALYSIS},
       cost_tier=CostTier.FREE, cost_per_1k_input=0.0, cost_per_1k_output=0.0,
       context_window=131072, max_output_tokens=8192, priority=6,
       version="2026-06", tags=["free", "review", "cheap"],
       notes="GLM-4.7 免费版，适合 Code Review、简单分析等低成本任务")

_model("glm", "glm-5-turbo", "GLM-5 Turbo", "glm-5-turbo",
       {ModelCapability.CHAT, ModelCapability.ANALYSIS, ModelCapability.SPEED},
       cost_tier=CostTier.LOW, cost_per_1k_input=0.01, cost_per_1k_output=0.01,
       context_window=32768, max_output_tokens=4096, priority=8,
       tags=["fast", "cheap", "turbo"],
       notes="GLM-5 Turbo，高速版，延迟更低价格更优")

_model("glm", "glm-4-flash", "GLM-4 Flash", "GLM-4-Flash",
       {ModelCapability.CHAT, ModelCapability.ANALYSIS, ModelCapability.SPEED},
       cost_tier=CostTier.CHEAP, cost_per_1k_input=0.001, cost_per_1k_output=0.001,
       context_window=8192, max_output_tokens=4096, priority=15,
       tags=["fast", "cheap", "flash"],
       notes="GLM-4 Flash，极低价高速版，适合简单对话")


# ─────────────────────────────────────────────────────────────────────────
# 6. 火山引擎 / 豆包
# ─────────────────────────────────────────────────────────────────────────

_reg("volcengine", "火山引擎", ProviderKind.SUBSCRIPTION,
    "https://ark.cn-beijing.volces.com/api/plan/v3", "VOLCANO_API_KEY",
    notes="火山方舟 Coding Plan（Medium 套餐）。使用 Responses API 协议接入，勿用 /api/v3（会额外计费）")

_model("volcengine", "volc-deepseek-v4-flash", "火山 DeepSeek V4 Flash", "deepseek-v4-flash-260425",
       {ModelCapability.CHAT, ModelCapability.CODING, ModelCapability.ANALYSIS,
        ModelCapability.FUNCTION_CALLING, ModelCapability.SPEED, ModelCapability.AGENTIC},
       cost_tier=CostTier.CHEAP, cost_per_1k_input=0.003, cost_per_1k_output=0.003,
       context_window=65536, max_output_tokens=8192, priority=10,
       version="260425", tags=["coding", "flash", "coding-plan"],
       notes="火山方舟 DeepSeek V4 Flash，当前唯一可用模型")

_model("volcengine", "volc-doubao-seed2", "火山 Doubao Seed 2.0 Pro", "doubao-seed-2-0-pro-260215",
       {ModelCapability.CHAT, ModelCapability.CODING, ModelCapability.ANALYSIS,
        ModelCapability.REASONING, ModelCapability.FUNCTION_CALLING},
       cost_tier=CostTier.STANDARD, cost_per_1k_input=0.015, cost_per_1k_output=0.015,
       context_window=65536, max_output_tokens=8192, priority=20,
       version="260215", tags=["chat", "reasoning", "need-activate"],
       notes="需在 ARK 控制台开通模型服务后才可用")


# ─────────────────────────────────────────────────────────────────────────
# 7. MiniMax (M4)
# ─────────────────────────────────────────────────────────────────────────

_reg("minimax", "MiniMax（M3）", ProviderKind.DIRECT,
    "https://api.minimax.chat/v1", "MINIMAX_API_KEY",
    notes="MiniMax 官方 API。当前 key 可用 M3/M2.7，M4 需在 platform.minimax.chat 申请权限")

_model("minimax", "minimax-m3", "MiniMax M3", "MiniMax-M3",
       {ModelCapability.CHAT, ModelCapability.CODING, ModelCapability.ANALYSIS,
        ModelCapability.REASONING, ModelCapability.FUNCTION_CALLING,
        ModelCapability.CREATIVE},
       cost_tier=CostTier.LOW, cost_per_1k_input=0.015, cost_per_1k_output=0.015,
       context_window=131072, max_output_tokens=8192, priority=10,
       version="2026-Q2", tags=["chat", "coding", "reasoning", "creative"],
       notes="MiniMax M3，131K 上下文，支持推理和工具调用，兼作 CREATIVE 路由候选")

_model("minimax", "minimax-m27", "MiniMax M2.7", "MiniMax-M2.7",
       {ModelCapability.CHAT, ModelCapability.CODING},
       cost_tier=CostTier.LOW, cost_per_1k_input=0.010, cost_per_1k_output=0.010,
       context_window=65536, max_output_tokens=4096, priority=15,
       tags=["chat", "coding"],
       notes="MiniMax M2.7")

_model("minimax", "minimax-m27-highspeed", "MiniMax M2.7 HighSpeed", "MiniMax-M2.7-highspeed",
       {ModelCapability.CHAT, ModelCapability.CODING, ModelCapability.SPEED},
       cost_tier=CostTier.CHEAP, cost_per_1k_input=0.005, cost_per_1k_output=0.005,
       context_window=32768, max_output_tokens=2048, priority=20,
       tags=["fast", "cheap", "highspeed"],
       notes="MiniMax M2.7 HighSpeed，高速低价版")


# ═══════════════════════════════════════════════════════════════════════════
# API
# ═══════════════════════════════════════════════════════════════════════════

class ModelRegistry:
    """模型注册表 API"""

    def list_providers(self) -> list[ProviderInfo]:
        return list(_PROVIDERS_DATA.values())

    def list_models(self) -> list[ModelInfo]:
        models = []
        for p in _PROVIDERS_DATA.values():
            models.extend(p.models)
        return models

    def get_model(self, model_id: str) -> ModelInfo | None:
        for m in self.list_models():
            if m.model_id == model_id:
                return m
        return None

    def find_by_capability(
        self,
        capability: ModelCapability,
        max_results: int = 5,
    ) -> list[ModelInfo]:
        """按能力维度查找模型，按优先级排序"""
        matches = [m for m in self.list_models() if capability in m.capabilities]
        matches.sort(key=lambda m: m.priority)
        return matches[:max_results]

    def find_by_tag(self, tag: str) -> list[ModelInfo]:
        return [m for m in self.list_models() if tag in m.tags]

    def get_models_for_provider(self, provider_key: str) -> list[ModelInfo]:
        p = _PROVIDERS_DATA.get(provider_key)
        return list(p.models) if p else []

    def get_provider(self, provider_key: str) -> ProviderInfo | None:
        return _PROVIDERS_DATA.get(provider_key)

    def to_dict(self) -> dict[str, Any]:
        """导出为可序列化的 dict（用于状态文件）"""
        return {
            "providers": {
                pk: {
                    "name": p.name,
                    "kind": p.kind.value,
                    "base_url": p.base_url,
                    "api_key_env": p.api_key_env,
                    "models": [
                        {
                            "model_id": m.model_id,
                            "display_name": m.display_name,
                            "api_model_name": m.api_model_name,
                            "capabilities": [c.value for c in m.capabilities],
                            "cost_tier": m.cost_tier.value,
                            "cost_per_1k_input": m.cost_per_1k_input,
                            "cost_per_1k_output": m.cost_per_1k_output,
                            "context_window": m.context_window,
                            "max_output_tokens": m.max_output_tokens,
                            "priority": m.priority,
                            "version": m.version,
                            "tags": m.tags,
                            "notes": m.notes,
                        }
                        for m in p.models
                    ],
                }
                for pk, p in _PROVIDERS_DATA.items()
            },
        }

    def save_to(self, path: str) -> None:
        """持久化到 JSON 文件"""
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)

    def diff_report(self, old: dict[str, Any] | None = None) -> list[str]:
        """生成模型变更报告（用于发现模型更新了）"""
        changes: list[str] = []
        current = self.to_dict()

        if old is None:
            changes.append("🆕 模型注册表初始建立")
            for pk, info in current["providers"].items():
                for m in info["models"]:
                    changes.append(f"  + [{pk}] {m['model_id']} ({m['display_name']})")
            return changes

        old_models = {(pk, m["model_id"]) for pk, info in old.get("providers", {}).items() for m in info.get("models", [])}
        new_models = {(pk, m["model_id"]) for pk, info in current["providers"].items() for m in info.get("models", [])}

        added = new_models - old_models
        removed = old_models - new_models

        for pk, mid in sorted(added):
            m = self.get_model(mid)
            changes.append(f"  ➕ [{pk}] {mid} ({m.display_name if m else '?'}) — NEW")

        for pk, mid in sorted(removed):
            changes.append(f"  ➖ [{pk}] {mid} — REMOVED")

        # Check version changes
        if old:
            for pk, info in current["providers"].items():
                old_info = old.get("providers", {}).get(pk, {})
                old_models_dict = {om["model_id"]: om for om in old_info.get("models", [])}
                for m in info["models"]:
                    old_m = old_models_dict.get(m["model_id"])
                    if old_m and old_m.get("version") != m.get("version"):
                        changes.append(f"  🔄 [{pk}] {m['model_id']}: {old_m.get('version', '?')} → {m['version']} — UPDATED")

        return changes


# ── 单例 ──────────────────────────────────────────────────────────────────

registry = ModelRegistry()
