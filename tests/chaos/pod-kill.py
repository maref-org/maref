"""验证 pod 意外终止后自动恢复。"""
import subprocess
import time

import requests


def test_pod_kill():
    """删除一个 pod → 验证 Deployment 自动重建。"""
    subprocess.run(
        ["kubectl", "delete", "pod", "-n", "maref", "-l", "app=maref", "--wait=false"]
    )

    time.sleep(10)
    result = subprocess.run(
        ["kubectl", "get", "pods", "-n", "maref", "-l", "app=maref", "-o", "json"],
        capture_output=True,
        text=True,
    )
    assert "maref" in result.stdout

    resp = requests.get("http://localhost:8080/health", timeout=5)
    assert resp.status_code == 200
