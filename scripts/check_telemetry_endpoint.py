#!/usr/bin/env python3
"""遥测端点可用性探测（INC-2026-08-13-001 / G8-1）。

检查 telemetry.maref.org / maref.cc 批量上报端点是否可达。
不可达时给出明确告警并提示本地聚合器 fallback 状态。

用法:
    python3 scripts/check_telemetry_endpoint.py          # 探测 + 退出码
    python3 scripts/check_telemetry_endpoint.py --quiet  # 仅退出码
"""

from __future__ import annotations

import argparse
import sys
import urllib.request

ENDPOINTS = [
    ("telemetry.maref.org", "https://telemetry.maref.org/api/v1/telemetry/batch"),
    ("maref.cc", "https://maref.cc/api/v1/telemetry/batch"),
]


def _probe(url: str, timeout: float = 5.0) -> tuple[bool, str]:
    try:
        req = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return True, f"HTTP {resp.status}"
    except urllib.error.HTTPError as e:
        # 400/405 等说明端点存在；404 说明路径不存在
        return e.code != 404, f"HTTP {e.code}"
    except Exception as e:  # noqa: BLE001
        return False, str(e)


def main() -> int:
    parser = argparse.ArgumentParser(description="遥测端点探测")
    parser.add_argument("--quiet", action="store_true", help="仅输出退出码")
    parser.add_argument("--timeout", type=float, default=5.0)
    args = parser.parse_args()

    # 本地聚合器状态
    try:
        from maref.obs.pipeline import ObsPipeline
        local_count = ObsPipeline.offline_event_count()
    except Exception:  # noqa: BLE001
        local_count = -1

    all_ok = True
    for name, url in ENDPOINTS:
        ok, detail = _probe(url, args.timeout)
        all_ok = all_ok and ok
        if not args.quiet:
            status = "OK" if ok else "UNREACHABLE"
            print(f"[{status}] {name}: {url} → {detail}")

    if not args.quiet:
        if local_count >= 0:
            print(f"[INFO] 本地聚合器离线缓存事件数: {local_count}")
        else:
            print("[INFO] 本地聚合器不可用（pip 未装 maref 包）")

    if not all_ok:
        if not args.quiet:
            print("\n⚠️  遥测端点不可达。数据将由本地 SQLite 聚合器兜底，不会丢失。")
            print("   部署时请确保至少一个接收端可用，否则部署健康度无法上报。")
        return 1
    if not args.quiet:
        print("\n✅ 遥测端点全部可达。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
