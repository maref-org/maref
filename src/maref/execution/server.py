"""FastAPI Harness 服务 — 通过 HTTP 调用 UnifiedHarness。"""

from __future__ import annotations

import threading
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from maref.execution.harness.types import HarnessConfig, HarnessResult, HarnessStatus
from maref.execution.harness.unified import UnifiedHarness

# 运行时状态
_harness_instances: dict[str, UnifiedHarness] = {}
_harness_results: dict[str, HarnessResult] = {}
_harness_threads: dict[str, threading.Thread] = {}
_harness_configs: dict[str, dict[str, Any]] = {}


@dataclass
class RunRequest:
    config: dict[str, Any] = field(default_factory=lambda: {"harness_type": "unified", "level": "L1"})


@dataclass
class RunResponse:
    run_id: str
    status: str
    message: str


@dataclass
class StatusResponse:
    run_id: str
    lifecycle_state: str
    is_terminal: bool
    config: dict[str, Any]


@dataclass
class ResultResponse:
    run_id: str
    status: str
    passed: bool
    duration_s: float
    errors: list[str]
    metrics: dict[str, Any]


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    _harness_instances.clear()
    _harness_results.clear()
    _harness_threads.clear()
    _harness_configs.clear()


app = FastAPI(
    title="MAREF Harness Service",
    version="0.1.0",
    lifespan=lifespan,
)


def _run_harness_in_thread(run_id: str, config_dict: dict[str, Any]) -> None:
    try:
        config = HarnessConfig(**config_dict)
        harness = UnifiedHarness()
        harness.configure(config)
        harness.preflight()
        result = harness.run(round_id=run_id)
        _harness_results[run_id] = result
    except Exception as e:
        _harness_results[run_id] = HarnessResult(
            harness_type=config_dict.get("harness_type", "unified"),
            round_id=run_id,
            status=HarnessStatus.FAILED,
            errors=[str(e)],
        )


@app.post("/harness/run", response_model=RunResponse)
async def run_harness(request: RunRequest) -> RunResponse:
    run_id = f"run_{uuid.uuid4().hex[:8]}"
    _harness_configs[run_id] = request.config

    t = threading.Thread(target=_run_harness_in_thread, args=(run_id, request.config))
    _harness_threads[run_id] = t
    t.start()

    return RunResponse(run_id=run_id, status="started", message="Harness run started")


@app.get("/harness/status/{run_id}", response_model=StatusResponse)
async def get_status(run_id: str) -> StatusResponse:
    if run_id not in _harness_configs:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    _harness_instances.get(run_id)
    is_terminal = False
    lifecycle_state = "unknown"

    if run_id in _harness_results:
        lifecycle_state = _harness_results[run_id].status.value
        is_terminal = True
    elif run_id in _harness_threads and _harness_threads[run_id].is_alive():
        lifecycle_state = "running"

    return StatusResponse(
        run_id=run_id,
        lifecycle_state=lifecycle_state,
        is_terminal=is_terminal,
        config=_harness_configs.get(run_id, {}),
    )


@app.get("/harness/result/{run_id}", response_model=ResultResponse)
async def get_result(run_id: str) -> ResultResponse:
    result = _harness_results.get(run_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Result for {run_id} not found")

    return ResultResponse(
        run_id=run_id,
        status=result.status.value,
        passed=result.passed,
        duration_s=result.duration_s,
        errors=result.errors[:10],
        metrics=result.metrics,
    )


@app.get("/harness/results")
async def list_results() -> list[ResultResponse]:
    return [
        ResultResponse(
            run_id=rid,
            status=r.status.value,
            passed=r.passed,
            duration_s=r.duration_s,
            errors=r.errors[:10],
            metrics=r.metrics,
        )
        for rid, r in _harness_results.items()
    ]


@app.get("/harness/health")
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok", "runs": len(_harness_configs), "completed": len(_harness_results)})


@app.post("/harness/stop/{run_id}")
async def stop_run(run_id: str) -> RunResponse:
    if run_id not in _harness_configs:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    if run_id in _harness_results:
        return RunResponse(run_id=run_id, status="completed", message="Run already completed")

    _harness_results[run_id] = HarnessResult(
        status=HarnessStatus.ABORTED,
        errors=["manually stopped"],
    )
    return RunResponse(run_id=run_id, status="stopped", message="Run stopped")


def start(host: str = "0.0.0.0", port: int = 8000) -> None:
    import uvicorn
    uvicorn.run(app, host=host, port=port)
