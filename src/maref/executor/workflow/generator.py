"""WorkflowScript Generator — 将自然语言任务描述生成为编排脚本。"""

from __future__ import annotations

import json
import re
from typing import Any

from maref.executor.workflow.types import WorkflowScript, WorkflowStep

# 类型: 只要实现了 .complete(prompt) -> str 即可
ModelAdapterLike = Any

_GENERATOR_PROMPT = """You are a workflow engineer. Given a task description, generate a multi-step
orchestration script. Each step has an agent_role that maps to a registered handler.

Available agent roles:
- analyzer: 分析输入, 产生结构化发现
- writer: 根据分析结果撰写文档/代码
- reviewer: 审查输出质量, 标记问题
- executor: 执行具体操作(文件/命令/API)
- validator: 验证前一步输出的正确性
- researcher: 搜索/调研信息
- summarizer: 汇总多来源信息

Output ONLY valid JSON (no markdown, no code fences) with this structure:
{{
  "name": "short script name",
  "description": "what this script does",
  "steps": [
    {{
      "name": "step-name",
      "description": "what this step does",
      "agent_role": "analyzer|writer|reviewer|executor|validator|researcher|summarizer",
      "input_template": "instructions for this step, use {{placeholder}} for runtime inputs",
      "validator_prompt": "optional validation prompt, empty string to skip",
      "timeout_seconds": 120,
      "max_retries": 1,
      "depends_on": [],
      "fallback_step": "",
      "parallel_group": ""
    }}
  ]
}}

Rules:
1. Steps that can run in parallel should have the same parallel_group value.
2. Step A depends_on Step B means B must complete before A starts.
3. First step should have empty depends_on.
4. Keep descriptions under 200 chars each.
5. Use 60-300 seconds for timeout_seconds.
6. Set max_retries to 1 for most steps, 2 for unreliable operations.
7. Set validator_prompt to a validation instruction, or empty string to skip.

Task: {task_description}
"""


def _parse_json(text: str) -> dict[str, Any] | None:
    """从 LLM 输出中提取 JSON。"""
    # 尝试直接解析
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 尝试从 ```json 代码块提取
    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass

    # 尝试从最外层花括号提取
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass

    return None


class WorkflowScriptGenerator:
    """将自然语言任务描述转换为 WorkflowScript。

    两种模式:
    - LLM 模式: 传入 model_adapter, 自动生成脚本
    - 手动模式: 直接传入 dict/list 构建脚本
    """

    def __init__(self, model_adapter: ModelAdapterLike | None = None) -> None:
        self._model = model_adapter

    # ── LLM 生成 ───────────────────────────────────────────────────

    def generate(
        self,
        task_description: str,
        name: str = "",
    ) -> WorkflowScript:
        """用 LLM 将任务描述生成为编排脚本。"""
        if self._model is None:
            raise RuntimeError(
                "No model_adapter provided. Use from_dict() or provide a ModelAdapter."
            )

        prompt = _GENERATOR_PROMPT.format(task_description=task_description)
        response = self._model.complete(prompt)

        parsed = _parse_json(response)
        if parsed is None:
            raise ValueError(f"Failed to parse LLM response as JSON.\nResponse:\n{response[:500]}")

        return self._parsed_to_script(parsed, name=name or task_description[:60])

    def generate_with_prompt(
        self,
        system_prompt: str,
        task_description: str,
    ) -> WorkflowScript:
        """用自定义 system prompt 生成脚本。"""
        if self._model is None:
            raise RuntimeError("No model_adapter provided")

        combined = f"{system_prompt}\n\nTask: {task_description}"
        response = self._model.complete(combined)

        parsed = _parse_json(response)
        if parsed is None:
            raise ValueError(f"Failed to parse LLM response as JSON.\nResponse:\n{response[:500]}")

        return self._parsed_to_script(parsed, name=task_description[:60])

    # ── 手动构建 ───────────────────────────────────────────────────

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkflowScript:
        """从字典构建脚本。"""
        return WorkflowScript.from_dict(data)

    @classmethod
    def from_step_list(
        cls,
        steps: list[dict[str, Any]],
        name: str = "",
        description: str = "",
    ) -> WorkflowScript:
        """从 step 字典列表构建脚本。"""
        return WorkflowScript(
            name=name or "generated-script",
            description=description,
            steps=[WorkflowStep.from_dict(s) for s in steps],
        )

    # ── 内部 ───────────────────────────────────────────────────────

    def _parsed_to_script(self, parsed: dict[str, Any], name: str = "") -> WorkflowScript:
        steps_data = parsed.get("steps", [])
        steps = [WorkflowStep.from_dict(s) for s in steps_data]
        return WorkflowScript(
            name=name or parsed.get("name", "generated-script"),
            description=parsed.get("description", ""),
            steps=steps,
            metadata={"generated_by": "WorkflowScriptGenerator"},
        )
