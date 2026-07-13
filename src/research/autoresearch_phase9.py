# mypy: ignore-errors
import asyncio
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import structlog

from drift_guard.ab_testing import ABTestManager
from drift_guard.policy_sandbox import PolicySandbox
from drift_guard.types import ExperimentConfig, VariantConfig
from research.dashscope_client import DashscopeClient

logger = structlog.get_logger()

@dataclass
class Phase9ExperimentResult:
    experiment_id: str
    variant: str
    metrics: dict[str, float]
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)

class Phase9AutoResearch:

    def __init__(self, config_path: str | None=None) -> None:
        self.config_path = config_path or os.getenv('PHASE9_CONFIG_PATH', 'config/phase9.json')
        self.config: dict[str, Any] = {}
        self.ab_test_manager = ABTestManager()
        self.policy_sandbox = PolicySandbox()
        self.dashscope_client = DashscopeClient()
        self.results: list[Phase9ExperimentResult] = []
        self._load_config()

    def _load_config(self) -> None:
        try:
            with open(self.config_path) as f:
                self.config = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.error('config_load_failed', path=self.config_path, error=str(e))
            self.config = {'experiments': [], 'default_variant': 'control'}

    async def run_experiment(self, experiment_id: str, variants: list[str]) -> Phase9ExperimentResult:
        try:
            config = ExperimentConfig(experiment_id=experiment_id, variants=[VariantConfig(name=v, weight=1.0 / len(variants)) for v in variants])
            selected_variant = await self.ab_test_manager.assign_variant(config)
            sandbox_result = await self.policy_sandbox.execute(experiment_id, selected_variant)
            metrics = {'accuracy': sandbox_result.get('accuracy', 0.0), 'latency': sandbox_result.get('latency', 0.0)}
            result = Phase9ExperimentResult(experiment_id=experiment_id, variant=selected_variant, metrics=metrics)
            self.results.append(result)
            return result
        except Exception as e:
            logger.error('experiment_failed', experiment_id=experiment_id, error=str(e))
            raise

    async def run_batch(self, experiments: list[dict[str, Any]]) -> list[Phase9ExperimentResult]:
        try:
            tasks = [self.run_experiment(exp['id'], exp['variants']) for exp in experiments]
            return await asyncio.gather(*tasks, return_exceptions=True)
        except Exception as e:
            logger.error('batch_failed', error=str(e))
            raise

    def _generate_report(self, results: list[Phase9ExperimentResult]) -> str:
        try:
            report_lines = ['# Phase 9 Auto Research Report', f'Generated: {datetime.utcnow().isoformat()}', '']
            for result in results:
                report_lines.append(f'## Experiment: {result.experiment_id}')
                report_lines.append(f'- Variant: {result.variant}')
                report_lines.append(f'- Metrics: {json.dumps(result.metrics, indent=2)}')
                report_lines.append('')
            return '\n'.join(report_lines)
        except Exception as e:
            logger.error('report_generation_failed', error=str(e))
            return ''

    def save_report(self, output_path: str | None=None) -> None:
        try:
            path = output_path or 'reports/phase9_report.md'
            report = self._generate_report(self.results)
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            with open(path, 'w') as f:
                f.write(report)
            logger.info('report_saved', path=path)
        except Exception as e:
            logger.error('report_save_failed', path=output_path, error=str(e))
            raise

    def _format_markdown(self, text: str) -> str:
        try:
            text = re.sub('\\n{3,}', '\n\n', text)
            return text.strip()
        except Exception as e:
            logger.error('markdown_format_failed', error=str(e))
            return text
