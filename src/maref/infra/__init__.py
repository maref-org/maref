# MAREF Infra — 基础设施层

# 基础检查
from maref.infra.check_env import check_environment
from maref.infra.circuit_breaker import (
    ActionRecord,
    BreakerConfig,
    BreakerLevel,
    CircuitBreaker,
    StuckDetector,
)

# Phase 2 卡死检测（函数式导出，按实际常量名导出）
from maref.infra.stagnation_watcher import (
    AGENT_BUS_DIR,
    FAILURE_EVENTS_FILE,
    LOOP_K,
    OCR_CACHE_FILE,
    SCREENSHOT_DIRS,
    SILENCE_MULTIPLIER,
    STAGNATION_MAX_HISTORY,
    STAGNATION_SIM_THRESHOLD,
    STATE_DIR,
    STATE_FILE,
    STEP_LATENCY_DEFAULT,
    _check_stagnation,
    _ensure_dirs,
    _jaccard_similarity,
    _load_state,
    _ocr_text,
    _save_state,
)
from maref.infra.stagnation_watcher import (
    main as stagnation_watcher_main,
)
from maref.infra.state import OpenClawState

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
