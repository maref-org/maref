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

# T1-4 (G-04): telemetry.maref.org 已从探测表下线 —— 2026-10-04 实测该子域名
# 无任何 A 记录（maref.org 主域正常），属 INC-2026-08-13-001 遗留的未配置端点，
# 继续探测只会每日报假告警。若日后配置 DNS，把条目加回此处即可。
ENDPOINTS = [
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
            print(f"[OK] local: 本地 SQLite 聚合器离线缓存事件数 {local_count}")
        else:
            print("[INFO] 本地聚合器不可用（pip 未装 maref 包）")

    # 本地聚合器是本地接收端：远程至少一个可用 **或** 本地可用 → rc=0
    # （方案 T1-4:「部署时确保至少一个接收端可用，否则部署健康度无法上报」）
    all_ok = all_ok or (local_count >= 0)
    if not all_ok:
        if not args.quiet:
            print("\n⚠️  遥测端点不可达且本地聚合器缺失。部署健康度无法上报。")
        return 1
    if not args.quiet:
        print("\n✅ 遥测接收端可用（远程/本地聚合器至少其一）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
