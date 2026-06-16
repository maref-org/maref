"""
DashScope (百炼) API Client for MAREF AutoResearch

Provides LLM-powered analysis capabilities for research findings.
Compatible with 阿里云百炼 Pro API.

Usage:
    from research.dashscope_client import DashScopeClient

    client = DashScopeClient()
    analysis = await client.analyze_findings(findings)
"""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from typing import Any

import aiohttp
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class LLMResponse:
    """Structured response from LLM."""

    content: str
    model: str
    usage: dict[str, int]
    finish_reason: str


@dataclass
class FindingAnalysis:
    """Analysis of a research finding."""

    summary: str
    significance: str  # high / medium / low
    related_concepts: list[str]
    suggested_experiments: list[str]
    confidence: float  # 0.0 - 1.0


@dataclass
class BatchAnalysis:
    """Analysis of a full experiment batch."""

    batch_id: int
    key_insights: list[str]
    patterns_detected: list[str]
    anomalies_flagged: list[str]
    recommendations: list[str]
    overall_assessment: str


class DashScopeClient:
    """
    Client for DashScope (百炼) API.

    Supports models:
    - qwen-max (最强推理)
    - qwen-plus (均衡)
    - qwen-turbo (快速)
    """

    DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/api/v1"
    DEFAULT_MODEL = "qwen-plus"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = 60.0,
    ) -> None:
        """
        Initialize DashScope client.

        Args:
            api_key: DashScope API key. If None, reads from DASHSCOPE_API_KEY env var.
            base_url: API base URL. Defaults to official endpoint.
            model: Model to use. Defaults to qwen-plus.
            timeout: Request timeout in seconds.
        """
        self._api_key = api_key or os.environ.get("DASHSCOPE_API_KEY")
        if not self._api_key:
            raise ValueError(
                "DashScope API key required. "
                "Set DASHSCOPE_API_KEY environment variable or pass api_key."
            )

        self._base_url = base_url or self.DEFAULT_BASE_URL
        self._model = model or self.DEFAULT_MODEL
        self._timeout = timeout
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                }
            )
        return self._session

    async def chat_completion(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """
        Send chat completion request.

        Args:
            messages: List of message dicts with 'role' and 'content'.
            temperature: Sampling temperature (0.0 - 2.0).
            max_tokens: Maximum tokens to generate.

        Returns:
            LLMResponse with generated content.
        """
        session = await self._get_session()

        payload: dict[str, Any] = {
            "model": self._model,
            "input": {
                "messages": messages,
            },
            "parameters": {
                "temperature": temperature,
                "result_format": "message",
            },
        }

        if max_tokens:
            payload["parameters"]["max_tokens"] = max_tokens

        url = f"{self._base_url}/services/aigc/text-generation/generation"

        async with session.post(
            url,
            json=payload,
            timeout=aiohttp.ClientTimeout(total=self._timeout),
        ) as response:
            if response.status != 200:
                text = await response.text()
                raise RuntimeError(f"API error {response.status}: {text}")

            data = await response.json()

            if "output" not in data:
                raise RuntimeError(f"Unexpected API response: {data}")

            output = data["output"]
            usage = data.get("usage", {})

            return LLMResponse(
                content=output.get("choices", [{}])[0].get("message", {}).get("content", ""),
                model=data.get("model", self._model),
                usage=usage,
                finish_reason=output.get("choices", [{}])[0].get("finish_reason", "unknown"),
            )

    async def analyze_findings(
        self,
        findings: list[str],
        experiment_type: str,
    ) -> FindingAnalysis:
        """
        Analyze research findings using LLM.

        Args:
            findings: List of finding strings.
            experiment_type: Type of experiment that produced findings.

        Returns:
            Structured analysis of findings.
        """
        if not findings:
            return FindingAnalysis(
                summary="No findings to analyze",
                significance="low",
                related_concepts=[],
                suggested_experiments=[],
                confidence=0.0,
            )

        findings_text = "\n".join(f"- {f}" for f in findings[:20])  # Limit to 20

        prompt = f"""你是一位AI研究分析师，正在分析自主实验的研究发现。

实验类型: {experiment_type}

发现:
{findings_text}

分析这些发现并提供JSON响应:
- summary: 简洁摘要（2-3句话）
- significance: "high"、"medium"或"low"
- related_concepts: 提到的关键概念列表
- suggested_experiments: 建议的后续实验列表
- confidence: 分析置信度（0.0-1.0）

仅返回有效JSON。"""

        messages = [
            {"role": "system", "content": "你是一位研究分析助手。始终用中文回复，仅返回有效JSON。"},
            {"role": "user", "content": prompt},
        ]

        try:
            response = await self.chat_completion(
                messages=messages,
                temperature=0.3,
                max_tokens=1000,
            )

            # Parse JSON response
            content = response.content.strip()
            # Handle markdown code blocks
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()

            data = json.loads(content)

            return FindingAnalysis(
                summary=data.get("summary", "Analysis unavailable"),
                significance=data.get("significance", "low"),
                related_concepts=data.get("related_concepts", []),
                suggested_experiments=data.get("suggested_experiments", []),
                confidence=data.get("confidence", 0.5),
            )
        except (json.JSONDecodeError, KeyError):
            # Fallback if LLM doesn't return valid JSON
            return FindingAnalysis(
                summary=f"Raw analysis: {response.content[:200]}...",
                significance="medium",
                related_concepts=[],
                suggested_experiments=["retry_analysis"],
                confidence=0.5,
            )

    async def analyze_batch(
        self,
        batch_id: int,
        experiment_results: list[dict[str, Any]],
        knowledge_graph_summary: dict[str, Any],
    ) -> BatchAnalysis:
        """
        Analyze a full batch of experiments.

        Args:
            batch_id: Batch identifier.
            experiment_results: List of experiment result dicts.
            knowledge_graph_summary: Summary of knowledge graph state.

        Returns:
            Comprehensive batch analysis.
        """
        # Summarize results for the prompt
        type_counts: dict[str, int] = {}
        all_findings: list[str] = []

        for result in experiment_results:
            exp_type = result.get("experiment_type", "unknown")
            type_counts[exp_type] = type_counts.get(exp_type, 0) + 1
            all_findings.extend(result.get("findings", []))

        findings_sample = all_findings[:15]  # Limit sample size

        prompt = f"""分析这批自主研究实验的结果。

批次ID: {batch_id}
实验分布: {json.dumps(type_counts, ensure_ascii=False)}
发现总数: {len(all_findings)}
知识图谱节点数: {knowledge_graph_summary.get('total_nodes', 0)}

发现样本:
{chr(10).join(f"- {f}" for f in findings_sample)}

提供JSON响应:
- key_insights: 3-5个关键洞察列表
- patterns_detected: 跨实验观察到的模式列表
- anomalies_flagged: 任何异常或意外结果
- recommendations: 下一步应调查什么
- overall_assessment: 简要总体评估（1-2句话）

仅返回有效JSON。"""

        messages = [
            {
                "role": "system",
                "content": "你是一位研究主管，正在分析实验批次结果。始终用中文回复，仅返回有效JSON。",
            },
            {"role": "user", "content": prompt},
        ]

        try:
            response = await self.chat_completion(
                messages=messages,
                temperature=0.4,
                max_tokens=1500,
            )

            content = response.content.strip()
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()

            data = json.loads(content)

            return BatchAnalysis(
                batch_id=batch_id,
                key_insights=data.get("key_insights", []),
                patterns_detected=data.get("patterns_detected", []),
                anomalies_flagged=data.get("anomalies_flagged", []),
                recommendations=data.get("recommendations", []),
                overall_assessment=data.get("overall_assessment", "Analysis complete"),
            )
        except (json.JSONDecodeError, KeyError, NameError) as e:
            return BatchAnalysis(
                batch_id=batch_id,
                key_insights=["Error in LLM analysis, using fallback"],
                patterns_detected=[],
                anomalies_flagged=[str(e)],
                recommendations=["Check API connectivity"],
                overall_assessment="Analysis failed, manual review recommended",
            )

    async def close(self) -> None:
        """Close the HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def __aenter__(self) -> DashScopeClient:
        """Async context manager entry."""
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Async context manager exit."""
        await self.close()

    def __del__(self) -> None:
        """Destructor to ensure session cleanup."""
        if self._session and not self._session.closed:
            # Use asyncio.run_coroutine_threadsafe or similar if needed
            # For now, just log a warning if not closed
            import warnings

            warnings.warn(
                "DashScopeClient session was not properly closed. Use 'async with' or call close().",
                ResourceWarning,
                stacklevel=2,
            )


async def test_client() -> None:
    """Test the DashScope client."""
    client = DashScopeClient()

    # Test simple completion
    logger.info("Testing chat completion...")
    response = await client.chat_completion(
        [
            {"role": "user", "content": "Hello, are you working?"},
        ]
    )
    logger.debug("Response: %s...", response.content[:100])
    logger.info("Model: %s", response.model)
    logger.info("Usage: %s", response.usage)

    # Test finding analysis
    logger.info("Testing finding analysis...")
    findings = [
        "High state coverage: 9/10 states visited",
        "Entropy variance: 2.3 (unstable path)",
        "Self-observation working: 5 events captured",
    ]
    analysis = await client.analyze_findings(findings, "random_walk")
    logger.info("Summary: %s", analysis.summary)
    logger.info("Significance: %s", analysis.significance)
    logger.info("Confidence: %s", analysis.confidence)

    await client.close()
    logger.info("All tests passed!")


if __name__ == "__main__":
    asyncio.run(test_client())
