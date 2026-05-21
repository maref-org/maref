#!/usr/bin/env python3
"""MAREF API 性能基准测试脚本."""

import asyncio
import statistics
import time
from concurrent.futures import ThreadPoolExecutor

import httpx

BASE_URL = "http://localhost:8000"
ENDPOINTS = [
    ("/health", "GET", None),
    ("/status", "GET", None),
    ("/metrics", "GET", None),
]

CONCURRENCY = [1, 10, 50]
DURATION_SECONDS = 30


async def measure_latency(client: httpx.AsyncClient, method: str, path: str, body: dict | None) -> float:
    start = time.perf_counter()
    try:
        if method == "GET":
            await client.get(f"{BASE_URL}{path}", timeout=10.0)
        else:
            await client.post(f"{BASE_URL}{path}", json=body, timeout=10.0)
    except Exception:
        return -1.0
    return time.perf_counter() - start


async def benchmark_endpoint(path: str, method: str, body: dict | None, concurrency: int, duration: int):
    results = []
    start_time = time.time()
    async with httpx.AsyncClient() as client:
        while time.time() - start_time < duration:
            tasks = [
                measure_latency(client, method, path, body)
                for _ in range(concurrency)
            ]
            batch = await asyncio.gather(*tasks)
            results.extend([r for r in batch if r >= 0])
            await asyncio.sleep(0.01)

    if not results:
        return None

    results.sort()
    return {
        "path": path,
        "concurrency": concurrency,
        "requests": len(results),
        "rps": len(results) / duration,
        "min_ms": round(results[0] * 1000, 2),
        "max_ms": round(results[-1] * 1000, 2),
        "mean_ms": round(statistics.mean(results) * 1000, 2),
        "p50_ms": round(results[int(len(results) * 0.5)] * 1000, 2),
        "p95_ms": round(results[int(len(results) * 0.95)] * 1000, 2),
        "p99_ms": round(results[int(len(results) * 0.99)] * 1000, 2),
    }


async def main():
    print("=== MAREF API Performance Benchmark ===\n")

    # Health check
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{BASE_URL}/health", timeout=5.0)
            if resp.status_code != 200:
                print(f"WARNING: /health returned {resp.status_code}")
    except Exception as e:
        print(f"ERROR: Sidecar not reachable at {BASE_URL}: {e}")
        return

    all_results = []
    for path, method, body in ENDPOINTS:
        for conc in CONCURRENCY:
            print(f"Benchmarking {method} {path} @ concurrency={conc}...")
            result = await benchmark_endpoint(path, method, body, conc, DURATION_SECONDS)
            if result:
                all_results.append(result)
                print(f"  RPS: {result['rps']:.1f} | P95: {result['p95_ms']}ms | P99: {result['p99_ms']}ms")
            else:
                print("  FAILED: no successful requests")
            print()

    print("\n=== Summary ===")
    print(f"{'Endpoint':<25} {'Conc':>6} {'RPS':>8} {'P95(ms)':>10} {'P99(ms)':>10} {'Status':>10}")
    print("-" * 75)
    for r in all_results:
        status = "PASS" if r["p99_ms"] < 500 else "WARN" if r["p99_ms"] < 1000 else "FAIL"
        print(f"{r['path']:<25} {r['concurrency']:>6} {r['rps']:>8.1f} {r['p95_ms']:>10.2f} {r['p99_ms']:>10.2f} {status:>10}")


if __name__ == "__main__":
    asyncio.run(main())
