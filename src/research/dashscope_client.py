from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import aiohttp
import structlog

logger = structlog.get_logger()

class LLMResponse(Enum):
    SUCCESS = 'success'
    ERROR = 'error'
    TIMEOUT = 'timeout'

@dataclass
class FindingAnalysis:
    finding_id: str
    summary: str
    severity: str
    confidence: float
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass
class BatchAnalysis:
    findings: list[FindingAnalysis] = field(default_factory=list)
    total_confidence: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

class DashScopeClient:

    def __init__(self, api_key: str, base_url: str='https://dashscope.aliyuncs.com') -> None:
        self.api_key = api_key
        self.base_url = base_url
        self.session: aiohttp.ClientSession | None = None

    async def __aenter__(self) -> DashScopeClient:
        self.session = aiohttp.ClientSession(headers={'Authorization': f'Bearer {self.api_key}'})
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self.session:
            await self.session.close()

    async def analyze_finding(self, finding_id: str, content: str) -> FindingAnalysis:
        try:
            if not self.session:
                raise RuntimeError('Client not initialized. Use async with context manager.')
            async with self.session.post(f'{self.base_url}/api/v1/services/text-generation', json={'model': 'qwen-turbo', 'input': {'messages': [{'role': 'user', 'content': content}]}}) as response:
                response.raise_for_status()
                data = await response.json()
                return FindingAnalysis(finding_id=finding_id, summary=data.get('output', {}).get('text', ''), severity='medium', confidence=0.8)
        except Exception as e:
            logger.error('analysis_failed', finding_id=finding_id, error=str(e))
            raise

    async def batch_analyze(self, findings: dict[str, str]) -> BatchAnalysis:
        try:
            results = []
            for (finding_id, content) in findings.items():
                analysis = await self.analyze_finding(finding_id, content)
                results.append(analysis)
            total_confidence = sum(r.confidence for r in results) / len(results) if results else 0.0
            return BatchAnalysis(findings=results, total_confidence=total_confidence)
        except Exception as e:
            logger.error('batch_analysis_failed', error=str(e))
            raise
