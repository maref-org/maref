"""验证网络分区下系统行为"""
import subprocess
import time

import requests


def test_network_partition():
    """切断一个 Service 的网络连接 → 验证降级行为。"""
    subprocess.run(["iptables", "-A", "INPUT", "-s", "10.0.0.0/8", "-j", "DROP"])

    time.sleep(5)
    resp = requests.get("http://localhost:8080/health", timeout=5)
    assert resp.status_code == 200

    subprocess.run(["iptables", "-D", "INPUT", "-s", "10.0.0.0/8", "-j", "DROP"])
