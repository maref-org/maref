#!/usr/bin/env python3
"""阈值自动推送 (Phase Beta B3) — 将重校准阈值推送到 sidecar API"""
import json, os, urllib.request
from pathlib import Path
from maref_config import config_path, sidecar_url

THRESHOLD_CONFIG = str(config_path("probe_thresholds.json"))
SIDECAR_URL = sidecar_url()


def push_thresholds():
    if not os.path.exists(THRESHOLD_CONFIG):
        print("阈值配置文件不存在，请先运行 probe_threshold_calibrate.py")
        return

    with open(THRESHOLD_CONFIG) as f:
        config = json.load(f)

    payload = {
        "config_id": config.get("calibrated_at", "unknown"),
        "probes": {},
    }
    for probe_name, thresholds in config.get("probes", {}).items():
        payload["probes"][probe_name] = {
            "normal_max": thresholds["normal_max"],
            "critical_min": thresholds["critical_min"],
        }

    try:
        req = urllib.request.Request(
            f"{SIDECAR_URL}/api/config/probe-thresholds",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        resp = urllib.request.urlopen(req, timeout=5)
        print(f"阈值推送成功: {resp.status}")
        print(f"oscillation: normal<={payload['probes'].get('oscillation',{}).get('normal_max')}, critical>={payload['probes'].get('oscillation',{}).get('critical_min')}")
        print(f"entropy: normal<={payload['probes'].get('entropy',{}).get('normal_max')}, critical>={payload['probes'].get('entropy',{}).get('critical_min')}")
    except Exception as e:
        print(f"阈值推送失败 (sidecar 可能未运行): {e}")


if __name__ == "__main__":
    push_thresholds()