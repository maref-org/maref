"""VolcArkCodeAgent Baseline Benchmark: 20 real API calls.

Purpose: Establish quality baseline for code generation service.
Metrics collected:
- Success rate
- Test coverage rate
- Documentation completeness
- Type hint adoption
- Duration distribution (P50/P99)
- Token usage distribution
"""

from __future__ import annotations

import json
import os
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from maref.stress.volc_ark_code_agent import VolcArkCodeAgent

# ─── Volcengine Ark Configuration ────────────────────────────────────────
# 密钥从环境变量读取，使用 macOS Keychain 管理: maref-volc-ark-api-key
VOLC_ARK_API_KEY = os.environ.get("VOLC_ARK_API_KEY", "")
VOLC_ARK_MODEL = "doubao-seed-code-preview-latest"
VOLC_ARK_BASE_URL = "https://ark.cn-beijing.volces.com/api/coding"

# ─── Diverse Test Prompts (20 unique tasks) ──────────────────────────────
BENCHMARK_PROMPTS = [
    {
        "title": "Fibonacci",
        "prompt": "Write a Python function to calculate the nth Fibonacci number with memoization. Include unit tests.",
        "category": "algorithm",
    },
    {
        "title": "LRU Cache",
        "prompt": "Implement an LRU Cache in Python with O(1) get and put operations. Include unit tests for capacity limits and eviction.",
        "category": "data_structure",
    },
    {
        "title": "HTTP Retry Client",
        "prompt": "Write a Python HTTP client wrapper with retry logic, timeout handling, and proper error handling. Include unit tests using mocks.",
        "category": "network",
    },
    {
        "title": "Data Validator",
        "prompt": "Write a Python data validator class that validates email, phone number, and date formats with clear error messages. Include unit tests.",
        "category": "validation",
    },
    {
        "title": "JSON Parser",
        "prompt": "Write a Python utility to safely parse JSON strings with custom type coercion (e.g., string '42' to int). Include unit tests.",
        "category": "parsing",
    },
    {
        "title": "Rate Limiter",
        "prompt": "Implement a sliding window rate limiter in Python. Include unit tests for rate enforcement and window reset.",
        "category": "algorithm",
    },
    {
        "title": "Event Bus",
        "prompt": "Write a simple event bus/pub-sub system in Python with type-safe event handlers. Include unit tests.",
        "category": "architecture",
    },
    {
        "title": "String Calculator",
        "prompt": "Write a Python string calculator that parses expressions like '1+2*3' and evaluates them safely (no eval()). Include unit tests.",
        "category": "parsing",
    },
    {
        "title": "File Watcher",
        "prompt": "Write a file change watcher that monitors a directory for new/modified files and triggers callbacks. Include unit tests with temp directories.",
        "category": "io",
    },
    {
        "title": "Priority Queue",
        "prompt": "Implement a priority queue in Python with support for dynamic priority updates. Include unit tests.",
        "category": "data_structure",
    },
    {
        "title": "Config Parser",
        "prompt": "Write a YAML/JSON config parser with schema validation and default value support. Include unit tests.",
        "category": "configuration",
    },
    {
        "title": "Thread Pool",
        "prompt": "Implement a simple thread pool executor with task queue and graceful shutdown. Include unit tests.",
        "category": "concurrency",
    },
    {
        "title": "Retry Decorator",
        "prompt": "Write a Python decorator for automatic retry with exponential backoff and jitter. Include unit tests.",
        "category": "utility",
    },
    {
        "title": "Bloom Filter",
        "prompt": "Implement a Bloom Filter data structure in Python with configurable false positive rate. Include unit tests.",
        "category": "data_structure",
    },
    {
        "title": "Template Engine",
        "prompt": "Write a minimal template engine that supports variable substitution and basic conditionals. Include unit tests.",
        "category": "parsing",
    },
    {
        "title": "Circuit Breaker",
        "prompt": "Implement a circuit breaker pattern in Python with open/half-open/closed states. Include unit tests.",
        "category": "resilience",
    },
    {
        "title": "CSV Reader",
        "prompt": "Write a CSV reader that handles various delimiters, quoting, and type inference. Include unit tests.",
        "category": "io",
    },
    {
        "title": "Dependency Injector",
        "prompt": "Write a simple dependency injection container with singleton and transient lifecycles. Include unit tests.",
        "category": "architecture",
    },
    {
        "title": "Timer Scheduler",
        "prompt": "Implement a timer scheduler that can schedule one-time and recurring tasks with cancellation support. Include unit tests.",
        "category": "concurrency",
    },
    {
        "title": "Diff Tool",
        "prompt": "Write a line-by-line diff tool that compares two strings and outputs unified diff format. Include unit tests.",
        "category": "utility",
    },
]


def percentile(data: list[float], p: float) -> float:
    """Calculate the p-th percentile."""
    if not data:
        return 0.0
    sorted_data = sorted(data)
    k = (len(sorted_data) - 1) * (p / 100.0)
    f = int(k)
    c = f + 1
    if c >= len(sorted_data):
        return sorted_data[f]
    return sorted_data[f] + (k - f) * (sorted_data[c] - sorted_data[f])


def run_benchmark() -> dict:
    """Run 20 real API calls and collect metrics."""
    print("\n" + "=" * 70)
    print("VolcArkCodeAgent: Baseline Benchmark (20 tasks)")
    print("=" * 70)

    agent = VolcArkCodeAgent(
        api_key=VOLC_ARK_API_KEY,
        base_url=VOLC_ARK_BASE_URL,
        default_model=VOLC_ARK_MODEL,
    )

    results: list[dict] = []
    category_results: dict[str, list[dict]] = {}

    print(f"\nModel: {VOLC_ARK_MODEL}")
    print(f"Running {len(BENCHMARK_PROMPTS)} benchmark tasks...\n")

    t_start = time.perf_counter()

    for idx, task in enumerate(BENCHMARK_PROMPTS, 1):
        print(
            f"  [{idx:2d}/{len(BENCHMARK_PROMPTS)}] [{task['category']}] {task['title']}... ",
            end="",
            flush=True,
        )

        result = agent.generate_with_retry(
            prompt=task["prompt"],
            language="python",
            temperature=0.0,
            max_retries=1,
        )

        if result.success:
            print(
                f"OK {len(result.code):>5} chars, "
                f"tests={'Y' if result.has_tests else 'N'}, "
                f"docs={'Y' if result.has_docstrings else 'N'}, "
                f"types={'Y' if result.has_type_hints else 'N'}, "
                f"{result.duration_ms / 1000:>5.1f}s, "
                f"{result.total_tokens:>5} tokens"
            )
        else:
            print(f"FAIL {result.error}")

        entry = {
            "task_id": idx,
            "title": task["title"],
            "category": task["category"],
            "success": result.success,
            "code_length": len(result.code) if result.success else 0,
            "has_tests": result.has_tests,
            "has_docstrings": result.has_docstrings,
            "has_type_hints": result.has_type_hints,
            "duration_ms": result.duration_ms,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "total_tokens": result.total_tokens,
            "stop_reason": result.stop_reason,
            "error": result.error,
        }
        results.append(entry)

        cat = task["category"]
        if cat not in category_results:
            category_results[cat] = []
        category_results[cat].append(entry)

    t_end = time.perf_counter()
    total_duration = (t_end - t_start) * 1000

    # ─── Aggregate Statistics ─────────────────────────────────────────
    success_results = [r for r in results if r["success"]]
    success_count = len(success_results)
    total_count = len(results)

    durations = [r["duration_ms"] for r in success_results]
    tokens = [r["total_tokens"] for r in success_results]
    code_lengths = [r["code_length"] for r in success_results]

    has_tests_count = sum(1 for r in success_results if r["has_tests"])
    has_docs_count = sum(1 for r in success_results if r["has_docstrings"])
    has_types_count = sum(1 for r in success_results if r["has_type_hints"])

    # Category statistics
    category_stats = {}
    for cat, cat_results in category_results.items():
        cat_success = [r for r in cat_results if r["success"]]
        category_stats[cat] = {
            "total": len(cat_results),
            "success": len(cat_success),
            "success_rate": len(cat_success) / len(cat_results),
            "avg_duration_ms": statistics.mean([r["duration_ms"] for r in cat_success])
            if cat_success
            else 0,
            "avg_tokens": statistics.mean([r["total_tokens"] for r in cat_success])
            if cat_success
            else 0,
            "tests_rate": sum(1 for r in cat_success if r["has_tests"]) / max(len(cat_success), 1),
        }

    # Print summary
    print("\n" + "=" * 70)
    print("BENCHMARK SUMMARY")
    print("=" * 70)

    print("\n  Overall:")
    print(
        f"    Success rate:      {success_count}/{total_count} ({success_count / total_count * 100:.0f}%)"
    )
    print(
        f"    Total duration:    {total_duration / 1000:.0f}s ({total_duration / 1000 / 60:.1f} min)"
    )
    print(f"    Total tokens:      {sum(r['total_tokens'] for r in success_results):,}")

    if durations:
        print("\n  Duration:")
        print(f"    Mean:              {statistics.mean(durations) / 1000:.1f}s")
        print(f"    Median (P50):      {percentile(durations, 50) / 1000:.1f}s")
        print(f"    P95:               {percentile(durations, 95) / 1000:.1f}s")
        print(f"    P99:               {percentile(durations, 99) / 1000:.1f}s")
        print(
            f"    Std Dev:           {statistics.stdev(durations) / 1000:.1f}s"
            if len(durations) > 1
            else ""
        )
        print(f"    Min:               {min(durations) / 1000:.1f}s")
        print(f"    Max:               {max(durations) / 1000:.1f}s")

    if tokens:
        print("\n  Token Usage:")
        print(f"    Mean:              {statistics.mean(tokens):,.0f}")
        print(f"    Median (P50):      {percentile(tokens, 50):,.0f}")
        print(f"    P95:               {percentile(tokens, 95):,.0f}")
        print(f"    Total:             {sum(tokens):,}")

    if code_lengths:
        print("\n  Code Length:")
        print(f"    Mean:              {statistics.mean(code_lengths):,.0f} chars")
        print(f"    Median (P50):      {percentile(code_lengths, 50):,.0f} chars")

    print("\n  Quality Metrics:")
    print(
        f"    Tests included:    {has_tests_count}/{success_count} ({has_tests_count / success_count * 100:.0f}%)"
    )
    print(
        f"    Docstrings:        {has_docs_count}/{success_count} ({has_docs_count / success_count * 100:.0f}%)"
    )
    print(
        f"    Type hints:        {has_types_count}/{success_count} ({has_types_count / success_count * 100:.0f}%)"
    )

    print("\n  By Category:")
    for cat, stats in sorted(category_stats.items()):
        print(
            f"    {cat:<15} {stats['success']}/{stats['total']} success, "
            f"{stats['avg_duration_ms'] / 1000:.1f}s avg, "
            f"tests={stats['tests_rate'] * 100:.0f}%"
        )

    return {
        "model": VOLC_ARK_MODEL,
        "total_tasks": total_count,
        "success_count": success_count,
        "success_rate": success_count / total_count,
        "total_duration_ms": total_duration,
        "total_tokens": sum(r["total_tokens"] for r in success_results),
        "duration_stats": {
            "mean_ms": statistics.mean(durations) if durations else 0,
            "p50_ms": percentile(durations, 50),
            "p95_ms": percentile(durations, 95),
            "p99_ms": percentile(durations, 99),
            "min_ms": min(durations) if durations else 0,
            "max_ms": max(durations) if durations else 0,
            "std_ms": statistics.stdev(durations) if len(durations) > 1 else 0,
        },
        "token_stats": {
            "mean": statistics.mean(tokens) if tokens else 0,
            "p50": percentile(tokens, 50),
            "p95": percentile(tokens, 95),
            "total": sum(tokens),
        },
        "quality_metrics": {
            "tests_rate": has_tests_count / success_count if success_count else 0,
            "docstrings_rate": has_docs_count / success_count if success_count else 0,
            "type_hints_rate": has_types_count / success_count if success_count else 0,
        },
        "category_stats": category_stats,
        "details": results,
    }


if __name__ == "__main__":
    results = run_benchmark()

    output_path = (
        Path(__file__).parent.parent.parent / "tests" / "stress" / "volc_ark_baseline_results.json"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2, default=str)

    print(f"\nResults saved to: {output_path}")
