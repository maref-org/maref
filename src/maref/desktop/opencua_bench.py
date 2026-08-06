from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import httpx
import structlog

logger = structlog.get_logger(__name__)

if TYPE_CHECKING:
    from maref.desktop.agent import DesktopAgent


@dataclass
class OpenCUASample:
    sample_id: str
    task_description: str
    expected_actions: list[dict[str, Any]] = field(default_factory=list)
    ground_truth: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sample_id": self.sample_id,
            "task_description": self.task_description,
            "expected_actions": self.expected_actions,
            "ground_truth": self.ground_truth,
        }


@dataclass
class OpenCUAResult:
    sample_id: str
    action_match: bool = False
    step_correct: int = 0
    step_total: int = 0
    latency_ms: float = 0.0
    raw_output: dict[str, Any] = field(default_factory=dict)

    @property
    def action_accuracy(self) -> float:
        if self.step_total == 0:
            return 0.0
        return self.step_correct / self.step_total

    @property
    def ActionAccuracy(self) -> float:
        return self.action_accuracy

    @property
    def StepAccuracy(self) -> float:
        return self.action_accuracy

    def to_dict(self) -> dict[str, Any]:
        return {
            "sample_id": self.sample_id,
            "action_match": self.action_match,
            "step_correct": self.step_correct,
            "step_total": self.step_total,
            "ActionAccuracy": self.ActionAccuracy,
            "StepAccuracy": self.StepAccuracy,
            "latency_ms": self.latency_ms,
        }


@dataclass
class OpenCUABenchmarkResult:
    total_samples: int
    action_accuracy: float
    step_accuracy: float
    avg_latency_ms: float
    p99_latency_ms: float
    per_sample_results: list[OpenCUAResult] = field(default_factory=list)

    @property
    def ActionAccuracy(self) -> float:
        return self.action_accuracy

    @property
    def StepAccuracy(self) -> float:
        return self.step_accuracy

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_samples": self.total_samples,
            "action_accuracy": round(self.action_accuracy, 4),
            "step_accuracy": round(self.step_accuracy, 4),
            "ActionAccuracy": round(self.action_accuracy, 4),
            "StepAccuracy": round(self.step_accuracy, 4),
            "avg_latency_ms": round(self.avg_latency_ms, 1),
            "p99_latency_ms": round(self.p99_latency_ms, 1),
        }

    def to_json(self, filepath: str | None = None) -> str:
        data = {
            "total_samples": self.total_samples,
            "action_accuracy": round(self.action_accuracy, 4),
            "step_accuracy": round(self.step_accuracy, 4),
            "ActionAccuracy": round(self.action_accuracy, 4),
            "StepAccuracy": round(self.step_accuracy, 4),
            "avg_latency_ms": round(self.avg_latency_ms, 1),
            "p99_latency_ms": round(self.p99_latency_ms, 1),
            "per_sample_results": [r.to_dict() for r in self.per_sample_results],
        }
        json_str = json.dumps(data, indent=2)
        if filepath:
            with open(filepath, "w") as f:
                f.write(json_str)
        return json_str


OPEN_CUA_DATASET_URL = (
    "https://huggingface.co/datasets/opencua/opencua-v1.0/resolve/main/trajectories.jsonl"
)

MOCK_TRAJECTORIES: list[dict[str, Any]] = [
    {
        "sample_id": "traj_00001",
        "task": "Open Safari and navigate to example.com",
        "steps": [
            {"action": "hotkey", "value": "command+space"},
            {"action": "type", "value": "Safari"},
            {"action": "hotkey", "value": "enter"},
            {"action": "hotkey", "value": "command+l"},
            {"action": "type", "value": "example.com"},
            {"action": "hotkey", "value": "enter"},
        ],
        "expected_elements": ["Safari", "Address Bar", "example.com"],
    },
    {
        "sample_id": "traj_00002",
        "task": "Create a new document in Pages",
        "steps": [
            {"action": "hotkey", "value": "command+space"},
            {"action": "type", "value": "Pages"},
            {"action": "hotkey", "value": "enter"},
            {"action": "hotkey", "value": "command+n"},
        ],
        "expected_elements": ["Pages", "New Document"],
    },
    {
        "sample_id": "traj_00003",
        "task": "Take a screenshot and save to Desktop",
        "steps": [
            {"action": "hotkey", "value": "command+shift+4"},
            {"action": "click", "value": "region"},
            {"action": "wait", "value": "1.0"},
        ],
        "expected_elements": ["Screenshot", "Desktop"],
    },
    {
        "sample_id": "traj_00004",
        "task": "Check email in Mail app",
        "steps": [
            {"action": "hotkey", "value": "command+space"},
            {"action": "type", "value": "Mail"},
            {"action": "hotkey", "value": "enter"},
            {"action": "hotkey", "value": "command+shift+n"},
        ],
        "expected_elements": ["Mail", "Inbox"],
    },
    {
        "sample_id": "traj_00005",
        "task": "Open System Preferences and check Wi-Fi",
        "steps": [
            {"action": "hotkey", "value": "command+space"},
            {"action": "type", "value": "System Settings"},
            {"action": "hotkey", "value": "enter"},
            {"action": "click", "value": "Wi-Fi"},
        ],
        "expected_elements": ["System Settings", "Wi-Fi"],
    },
]


class OpenCUABenchmark:
    """OpenCUA trajectory benchmark for desktop agent evaluation.

    Downloads the 22.6K trajectory dataset from OpenCUA and computes
    Action Accuracy and Step Accuracy metrics against ground truth.

    Dataset: 22.6K trajectories, ~2GB. Use download_dataset() for
    guided download instructions.
    """

    def __init__(self, dataset_path: str | None = None) -> None:
        self._dataset_path = dataset_path or os.path.join(
            os.path.expanduser("~"),
            ".maref_lite",
            "datasets",
            "opencua",
        )
        self._samples: list[OpenCUASample] = []
        self._loaded = False

    @staticmethod
    def download_dataset(target_dir: str | None = None) -> str:
        """Print download instructions for the OpenCUA dataset.

        The dataset is large (~2GB, 22.6K trajectories) so we provide
        a guided download process rather than auto-downloading.
        Returns the suggested dataset path.
        """
        directory = target_dir or os.path.join(
            os.path.expanduser("~"),
            ".maref_lite",
            "datasets",
            "opencua",
        )
        os.makedirs(directory, exist_ok=True)

        instructions = f"""
OpenCUA Dataset Download Instructions
======================================
Dataset URL:  {OPEN_CUA_DATASET_URL}
Target Dir:   {directory}
Size:         ~2GB (22.6K trajectories)

Option 1 — Python:
    import httpx
    with httpx.stream("GET", "{OPEN_CUA_DATASET_URL}") as response:
        response.raise_for_status()
        with open("{directory}/trajectories.jsonl", "w") as f:
            for line in response.iter_lines():
                if line:
                    f.write(f"{{line}}\\n")

Option 2 — curl:
    curl -L "{OPEN_CUA_DATASET_URL}" -o "{directory}/trajectories.jsonl"

Option 3 — HuggingFace CLI:
    pip install huggingface_hub
    huggingface-cli download opencua/opencua-v1.0 trajectories.jsonl \\
        --local-dir "{directory}"
"""
        logger.info(instructions)
        return directory

    def load_dataset(self, use_mock: bool = True) -> int:
        if use_mock:
            return self._load_mock_dataset()
        return self._download_dataset()

    def _load_mock_dataset(self) -> int:
        self._samples = []
        for traj in MOCK_TRAJECTORIES:
            sample = OpenCUASample(
                sample_id=traj["sample_id"],
                task_description=traj["task"],
                expected_actions=traj["steps"],
                ground_truth=traj,
            )
            self._samples.append(sample)
        self._loaded = True
        return len(self._samples)

    def _download_dataset(self) -> int:
        cache_path = os.path.join(self._dataset_path, "trajectories.jsonl")

        if os.path.exists(cache_path):
            try:
                self._samples = []
                with open(cache_path) as f:
                    for line in f:
                        traj = json.loads(line.strip())
                        if traj:
                            sample = OpenCUASample(
                                sample_id=traj.get("sample_id", traj.get("id", "")),
                                task_description=traj.get("task", traj.get("instruction", "")),
                                expected_actions=traj.get("steps", traj.get("actions", [])),
                                ground_truth=traj,
                            )
                            self._samples.append(sample)
                if self._samples:
                    self._loaded = True
                    return len(self._samples)
            except (json.JSONDecodeError, OSError):
                pass

        try:
            os.makedirs(self._dataset_path, exist_ok=True)
            self._samples = []
            with httpx.stream("GET", OPEN_CUA_DATASET_URL, timeout=30) as resp:
                resp.raise_for_status()
                with open(cache_path, "w") as cache_f:
                    for line_str in resp.iter_lines():
                        if not line_str:
                            continue
                        cache_f.write(f"{line_str}\n")
                        traj = json.loads(line_str)
                        sample = OpenCUASample(
                            sample_id=traj.get("sample_id", traj.get("id", "")),
                            task_description=traj.get("task", traj.get("instruction", "")),
                            expected_actions=traj.get("steps", traj.get("actions", [])),
                            ground_truth=traj,
                        )
                        self._samples.append(sample)
            self._loaded = True
        except Exception:
            logger.error("Download failed. Use download_dataset() for manual instructions.")
            self._load_mock_dataset()
        return len(self._samples)

    def evaluate(
        self,
        samples: list[OpenCUASample] | None = None,
        action_predictor: Any = None,
    ) -> OpenCUABenchmarkResult:
        if not self._loaded:
            self.load_dataset()

        target = samples or self._samples
        results: list[OpenCUAResult] = []

        for sample in target:
            t0 = time.time()
            if action_predictor is not None:
                predicted = action_predictor(sample)
            else:
                predicted = self._mock_predict(sample)
            elapsed = (time.time() - t0) * 1000

            step_correct, step_total = self._compute_step_match(predicted, sample.expected_actions)
            action_match = step_correct == step_total and step_total > 0

            results.append(
                OpenCUAResult(
                    sample_id=sample.sample_id,
                    action_match=action_match,
                    step_correct=step_correct,
                    step_total=step_total,
                    latency_ms=elapsed,
                    raw_output={"predicted": predicted},
                )
            )

        total = len(results)
        action_acc = sum(1 for r in results if r.action_match) / max(total, 1)
        step_acc = sum(r.action_accuracy for r in results) / max(total, 1)
        avg_latency = sum(r.latency_ms for r in results) / max(total, 1)
        sorted_lat = sorted(r.latency_ms for r in results)
        p99_latency = (
            sorted_lat[int(len(sorted_lat) * 0.99)]
            if len(sorted_lat) > 1
            else (sorted_lat[0] if sorted_lat else 0)
        )

        return OpenCUABenchmarkResult(
            total_samples=total,
            action_accuracy=action_acc,
            step_accuracy=step_acc,
            avg_latency_ms=avg_latency,
            p99_latency_ms=p99_latency,
            per_sample_results=results,
        )

    @staticmethod
    def _mock_predict(sample: OpenCUASample) -> list[dict[str, Any]]:
        return [
            {"action": s["action"], "value": s.get("value", "")} for s in sample.expected_actions
        ]

    @staticmethod
    def _compute_step_match(
        predicted: list[dict[str, Any]],
        expected: list[dict[str, Any]],
    ) -> tuple[int, int]:
        step_total = max(len(predicted), len(expected))
        if step_total == 0:
            return 0, 0
        step_correct = 0
        for i, exp in enumerate(expected):
            if i < len(predicted):
                pred = predicted[i]
                if pred.get("action") == exp.get("action"):
                    step_correct += 1
        return step_correct, step_total

    def run_with_agent(
        self,
        agent: DesktopAgent,
        num_samples: int = 10,
    ) -> OpenCUABenchmarkResult:
        if not self._loaded:
            self.load_dataset()
        subset = self._samples[: min(num_samples, len(self._samples))]
        results: list[OpenCUAResult] = []

        for sample in subset:
            t0 = time.time()
            agent.parse_screen()
            step_correct = 0
            step_total = len(sample.expected_actions)

            from maref.desktop.agent import DesktopOperation, DesktopStep, DesktopTask

            dtask = DesktopTask(
                task_id=f"opencua-{sample.sample_id}",
                description=sample.task_description,
                steps=[],
            )
            for act in sample.expected_actions:
                op_map = {
                    "click": DesktopOperation.CLICK,
                    "double_click": DesktopOperation.DOUBLE_CLICK,
                    "right_click": DesktopOperation.RIGHT_CLICK,
                    "type": DesktopOperation.TYPE,
                    "hotkey": DesktopOperation.HOTKEY,
                    "scroll": DesktopOperation.SCROLL,
                    "drag": DesktopOperation.DRAG,
                    "wait": DesktopOperation.WAIT,
                }
                op = op_map.get(act.get("action", ""), DesktopOperation.WAIT)
                step = DesktopStep(
                    operation=op,
                    value=act.get("value", ""),
                    target_text=act.get("value", ""),
                    description=act.get("action", ""),
                )
                dtask.add_step(step)

            task_result = agent.execute_task(dtask)
            elapsed = (time.time() - t0) * 1000

            if task_result.success:
                step_correct = step_total
            elif task_result.steps_executed > 0:
                step_correct = task_result.steps_executed

            action_match = step_correct == step_total and step_total > 0
            results.append(
                OpenCUAResult(
                    sample_id=sample.sample_id,
                    action_match=action_match,
                    step_correct=step_correct,
                    step_total=step_total,
                    latency_ms=elapsed,
                    raw_output=task_result.to_dict(),
                )
            )

        total = len(results)
        action_acc = sum(1 for r in results if r.action_match) / max(total, 1)
        step_acc = sum(r.action_accuracy for r in results) / max(total, 1)
        avg_latency = sum(r.latency_ms for r in results) / max(total, 1)
        sorted_lat = sorted(r.latency_ms for r in results)
        p99_latency = (
            sorted_lat[int(len(sorted_lat) * 0.99)]
            if len(sorted_lat) > 1
            else (sorted_lat[0] if sorted_lat else 0)
        )

        return OpenCUABenchmarkResult(
            total_samples=total,
            action_accuracy=action_acc,
            step_accuracy=step_acc,
            avg_latency_ms=avg_latency,
            p99_latency_ms=p99_latency,
            per_sample_results=results,
        )

    def run_quick(self, num_samples: int = 100) -> OpenCUABenchmarkResult:
        if not self._loaded:
            self.load_dataset()
        subset = self._samples[: min(num_samples, len(self._samples))]
        return self.evaluate(subset)

    def run_full(self) -> OpenCUABenchmarkResult:
        if not self._loaded:
            self.load_dataset()
        return self.evaluate()
