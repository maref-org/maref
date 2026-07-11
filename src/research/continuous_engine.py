import datetime
import structlog
from research.dashscope_client import DashscopeClient
from research.discovery_engine import DiscoveryEngine
from research.experiment_registry import ExperimentRegistry
from research.fault_recovery import FaultRecovery
from research.knowledge_graph import KnowledgeGraph
from research.orchestrator import Orchestrator
from research.vector_store import VectorStore
logger = structlog.get_logger()

class ContinuousReport:

    def __init__(self, report_id: str, title: str, findings: list[dict]) -> None:
        self.report_id = report_id
        self.title = title
        self.findings = findings
        self.created_at = datetime.datetime.utcnow()

    def to_dict(self) -> dict:
        return {'report_id': self.report_id, 'title': self.title, 'findings': self.findings, 'created_at': self.created_at.isoformat()}

class ContinuousAutoResearch:

    def __init__(self, dashscope_client: DashscopeClient, discovery_engine: DiscoveryEngine, experiment_registry: ExperimentRegistry, fault_recovery: FaultRecovery, knowledge_graph: KnowledgeGraph, orchestrator: Orchestrator, vector_store: VectorStore) -> None:
        self.dashscope_client = dashscope_client
        self.discovery_engine = discovery_engine
        self.experiment_registry = experiment_registry
        self.fault_recovery = fault_recovery
        self.knowledge_graph = knowledge_graph
        self.orchestrator = orchestrator
        self.vector_store = vector_store

    def _ngrams(self, tokens: list[str], n: int) -> list[tuple[str, ...]]:
        return [tuple(tokens[i:i + n]) for i in range(len(tokens) - n + 1)]

    def _compute_similarity(self, text1: str, text2: str) -> float:
        tokens1 = text1.lower().split()
        tokens2 = text2.lower().split()
        set1 = set(self._ngrams(tokens1, 2))
        set2 = set(self._ngrams(tokens2, 2))
        if not set1 or not set2:
            return 0.0
        intersection = set1 & set2
        return len(intersection) / max(len(set1), len(set2))

    def _detect_truncation(self, text: str, max_length: int=1000) -> bool:
        return len(text) > max_length

    def _format_markdown(self, findings: list[dict]) -> str:
        lines = ['# Continuous Research Report\n']
        for finding in findings:
            lines.append(f"## {finding.get('title', 'Untitled')}\n")
            lines.append(f"{finding.get('content', '')}\n")
            if 'source' in finding:
                lines.append(f"*Source: {finding['source']}*\n")
            lines.append('---\n')
        return '\n'.join(lines)

    def _post_process_findings(self, findings: list[dict]) -> list[dict]:
        processed = []
        for finding in findings:
            if self._detect_truncation(finding.get('content', '')):
                finding['content'] = finding['content'][:1000] + '...'
            processed.append(finding)
        return processed