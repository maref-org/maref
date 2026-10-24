# mypy: ignore-errors
import structlog
import yaml

from maref_lite.governance import AuditLogger, CircuitBreaker, MetaGovernance
from maref_lite.state_machine import StateMachine
from research.dashscope_client import DashScopeClient as DashscopeClient
from research.finding_models import Finding, Metric
from sidecar.collector import Collector
from sidecar.monitor import Monitor

logger = structlog.get_logger()

class DailyReport:

    def __init__(self, date: str) -> None:
        self.date = date
        self.findings: list[Finding] = []
        self.metrics: list[Metric] = []

    def add_finding(self, finding: Finding) -> None:
        self.findings.append(finding)

    def add_metric(self, metric: Metric) -> None:
        self.metrics.append(metric)

class MAREFAutoResearch:

    def __init__(self, config_path: str) -> None:
        self.config_path = config_path
        self.config: dict = {}
        self.circuit_breaker: CircuitBreaker | None = None
        self.state_machine: StateMachine | None = None
        self.audit_logger: AuditLogger | None = None
        self.meta_governance: MetaGovernance | None = None
        self.dashscope_client: DashscopeClient | None = None
        self.collector: Collector | None = None
        self.monitor: Monitor | None = None
        self._load_config()
        self._setup_governance()

    def _load_config(self) -> None:
        try:
            with open(self.config_path) as f:
                self.config = yaml.safe_load(f)
        except Exception as e:
            logger.error('config_load_failed', error=str(e))
            self.config = {}

    def _setup_governance(self) -> None:
        try:
            self.circuit_breaker = CircuitBreaker()
            self.state_machine = StateMachine()
            self.audit_logger = AuditLogger()
            self.meta_governance = MetaGovernance()
            self.dashscope_client = DashscopeClient()
            self.collector = Collector()
            self.monitor = Monitor()
        except Exception as e:
            logger.error('governance_setup_failed', error=str(e))
