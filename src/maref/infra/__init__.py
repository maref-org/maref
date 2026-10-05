# MAREF Infra — 基础设施层

# 基础检查
from maref.infra.check_env import check_environment
from maref.infra.state import OpenClawState
from maref.infra.circuit_breaker import (
    CircuitBreaker,
    BreakerConfig,
    ActionRecord,
    StuckDetector,
    BreakerLevel,
)

# Phase 2 卡死检测（函数式导出，按实际常量名导出）
from maref.infra.stagnation_watcher import (
    STAGNATION_MAX_HISTORY,
    STAGNATION_SIM_THRESHOLD,
    SILENCE_MULTIPLIER,
    LOOP_K,
    STEP_LATENCY_DEFAULT,
    STATE_DIR,
    STATE_FILE,
    OCR_CACHE_FILE,
    SCREENSHOT_DIRS,
    AGENT_BUS_DIR,
    FAILURE_EVENTS_FILE,
    _ensure_dirs,
    _load_state,
    _save_state,
    _check_stagnation,
    _ocr_text,
    _jaccard_similarity,
    main as stagnation_watcher_main,
)

__all__ = [
    "check_environment",
    "OpenClawState",
    "CircuitBreaker",
    "BreakerConfig",
    "ActionRecord",
    "StuckDetector",
    "BreakerLevel",
    "STAGNATION_MAX_HISTORY",
    "STAGNATION_SIM_THRESHOLD",
    "SILENCE_MULTIPLIER",
    "LOOP_K",
    "STEP_LATENCY_DEFAULT",
    "STATE_DIR",
    "STATE_FILE",
    "OCR_CACHE_FILE",
    "SCREENSHOT_DIRS",
    "AGENT_BUS_DIR",
    "FAILURE_EVENTS_FILE",
    "_ensure_dirs",
    "_load_state",
    "_save_state",
    "_check_stagnation",
    "_ocr_text",
    "_jaccard_similarity",
    "stagnation_watcher_main",
]
