"""
MAREF Evaluation Module

Contains evaluation scripts for MAS-TS-001 integration,
quality gates, and daily evaluation automation.
"""

__all__ = [
    "MASDailyEvalResult",
    "build_eval_report_from_state",
    "load_evolution_state",
    "run_mas_ts_evaluation",
]


def __getattr__(name: str):
    if name == "MASDailyEvalResult":
        from maref.evaluation.mas_ts_daily_eval import MASDailyEvalResult
        return MASDailyEvalResult
    if name == "build_eval_report_from_state":
        from maref.evaluation.mas_ts_daily_eval import build_eval_report_from_state
        return build_eval_report_from_state
    if name == "load_evolution_state":
        from maref.evaluation.mas_ts_daily_eval import load_evolution_state
        return load_evolution_state
    if name == "run_mas_ts_evaluation":
        from maref.evaluation.mas_ts_daily_eval import run_mas_ts_evaluation
        return run_mas_ts_evaluation
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
