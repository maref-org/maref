import datetime
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import structlog
from research.dashscope_client import DashscopeClient
logger = structlog.get_logger()

@dataclass
class Phase10ExperimentResult:
    experiment_id: str
    status: str
    start_time: datetime.datetime
    end_time: Optional[datetime.datetime] = None
    metrics: Dict[str, Any] = field(default_factory=dict)
    artifacts: List[str] = field(default_factory=list)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        result = {'experiment_id': self.experiment_id, 'status': self.status, 'start_time': self.start_time.isoformat(), 'metrics': self.metrics, 'artifacts': self.artifacts}
        if self.end_time:
            result['end_time'] = self.end_time.isoformat()
        if self.error:
            result['error'] = self.error
        return result

class Phase10AutoResearch:

    def __init__(self, client: DashscopeClient, config: Optional[Dict[str, Any]]=None) -> None:
        self.client = client
        self.config = config or {}
        self._setup_logging()

    def _setup_logging(self) -> None:
        structlog.configure(processors=[structlog.stdlib.filter_by_level, structlog.stdlib.add_log_level, structlog.processors.TimeStamper(fmt='iso'), structlog.dev.ConsoleRenderer()], context_class=dict, logger_factory=structlog.PrintLoggerFactory(), cache_logger_on_first_use=True)

    def _format_markdown(self, content: str) -> str:
        lines = content.strip().split('\n')
        formatted = []
        for line in lines:
            if line.startswith('#'):
                formatted.append(line)
            elif line.startswith('-'):
                formatted.append(line)
            elif line.strip():
                formatted.append(f'{line}\n')
            else:
                formatted.append('')
        return '\n'.join(formatted)