#!/usr/bin/env python3
"""stagnation_watcher.py — 卡死三判据 watcher (Phase 1.4)

检测三类卡死模式:
  1. stagnation: 连续视觉反馈截图 OCR 文本相似度 > 阈值 (默认 0.9)
  2. silence: 关键事件源 (agent_bus / failure_events / 截图) 在 2×步时延内无新增
  3. loop: failure_events 中同一 fingerprint 在 K 步内重复 (默认 K=3)

检出即写入失败事件总线 (signal=stagnation/silence/loop) + 截图归档。

launchd 定时: 每 2 分钟 (scripts/com.maref.stagnation-watcher.plist)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

# 可选依赖: easyocr 用于 OCR 相似度
try:
    import easyocr

    HAS_EASYOCR = True
except ImportError:
    HAS_EASYOCR = False

# 配置常量
STAGNATION_SIM_THRESHOLD = 0.90
STAGNATION_MAX_HISTORY = 10  # 保留最近 N 张截图 OCR 文本
SILENCE_MULTIPLIER = 2  # 静默判定 = 2 × 步时延 (默认步时延 60s → 120s)
LOOP_K = 3  # 指纹重复 K 次判循环
STEP_LATENCY_DEFAULT = 60  # 默认步时延 (秒)
ALERT_COOLDOWN_S = 21600  # 同类告警 6h 冷却：空闲期 silence 常态误报不挤占 state.alerts

# 状态文件
STATE_DIR = REPO_ROOT / ".openclaw" / "stagnation_watcher"
STATE_FILE = STATE_DIR / "state.json"
OCR_CACHE_FILE = STATE_DIR / "ocr_cache.json"

# 监控的数据源
SCREENSHOT_DIRS = [
    REPO_ROOT / ".openclaw" / "failure_artifacts",
    Path("/tmp"),
]
AGENT_BUS_DIR = Path("/tmp/opc-agent-bus")
FAILURE_EVENTS_FILE = REPO_ROOT / ".openclaw" / "failure_events" / "events.jsonl"


def _ensure_dirs() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)


def _load_state() -> dict:
    if not STATE_FILE.exists():
        return {"ocr_history": [], "last_check": None, "alerts": []}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"ocr_history": [], "last_check": None, "alerts": []}


def _save_state(state: dict) -> None:
    _ensure_dirs()
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_ocr_cache() -> dict:
    if not OCR_CACHE_FILE.exists():
        return {}
    try:
        return json.loads(OCR_CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_ocr_cache(cache: dict) -> None:
    _ensure_dirs()
    OCR_CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _find_latest_screenshots(max_count: int = STAGNATION_MAX_HISTORY) -> list[Path]:
    """收集最近的截图文件 (按 mtime 降序)。"""
    cands: list[Path] = []
    for d in SCREENSHOT_DIRS:
        if d.exists():
            # 匹配 adb_vf_*.png 和 failure_artifacts/*/*.png
            for p in d.rglob("*.png"):
                try:
                    if p.stat().st_size > 100:  # 忽略空图
                        cands.append(p)
                except OSError:
                    pass
    cands.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return cands[:max_count]


def _ocr_text(image_path: Path) -> str:
    """提取图片文本 (带缓存)。"""
    cache = _load_ocr_cache()
    key = f"{image_path}:{image_path.stat().st_mtime}:{image_path.stat().st_size}"
    if key in cache:
        return cache[key]

    text = ""
    if HAS_EASYOCR:
        try:
            reader = easyocr.Reader(["ch_sim", "en"], gpu=False)
            result = reader.readtext(str(image_path), detail=0)
            text = " ".join(result)
        except Exception:
            text = ""
    cache[key] = text
    _save_ocr_cache(cache)
    return text


def _jaccard_similarity(a: str, b: str) -> float:
    """集合 Jaccard 相似度 (按字分词)。"""
    if not a or not b:
        return 0.0
    set_a = set(a)
    set_b = set(b)
    inter = len(set_a & set_b)
    union = len(set_a | set_b)
    return inter / union if union else 0.0


def _check_stagnation(state: dict) -> tuple[bool, str, Path | None]:
    """检测停滞: 最近两张截图 OCR 文本高度相似。"""
    shots = _find_latest_screenshots(2)
    if len(shots) < 2:
        return False, "", None

    text1 = _ocr_text(shots[0])
    text2 = _ocr_text(shots[1])
    sim = _jaccard_similarity(text1, text2)

    state.setdefault("ocr_history", []).append(
        {
            "path": str(shots[0]),
            "text": text1[:200],
            "ts": _now_iso(),
        }
    )
    if len(state["ocr_history"]) > STAGNATION_MAX_HISTORY:
        state["ocr_history"] = state["ocr_history"][-STAGNATION_MAX_HISTORY:]

    if sim >= STAGNATION_SIM_THRESHOLD:
        detail = f"连续截图 OCR 相似度 {sim:.2f} ≥ {STAGNATION_SIM_THRESHOLD} (stagnation)"
        return True, detail, shots[0]
    return False, "", None


def _check_silence(state: dict, step_latency: int = STEP_LATENCY_DEFAULT) -> tuple[bool, str]:
    """检测静默: 关键数据源在 2×步时延内无更新。"""
    silence_threshold = step_latency * SILENCE_MULTIPLIER
    now = time.time()
    reasons = []

    # 1. agent_bus 最近事件
    if AGENT_BUS_DIR.exists():
        try:
            latest_bus = max(
                (f.stat().st_mtime for f in AGENT_BUS_DIR.glob("*.json") if f.is_file()),
                default=0,
            )
            if latest_bus and (now - latest_bus) > silence_threshold:
                reasons.append(f"agent_bus 无新事件 {(now - latest_bus):.0f}s")
        except Exception:
            pass

    # 2. failure_events 最近事件
    if FAILURE_EVENTS_FILE.exists():
        try:
            latest_fe = FAILURE_EVENTS_FILE.stat().st_mtime
            if (now - latest_fe) > silence_threshold:
                reasons.append(f"failure_events 无新事件 {(now - latest_fe):.0f}s")
        except Exception:
            pass

    # 3. 截图目录最近截图
    shots = _find_latest_screenshots(1)
    if shots:
        latest_shot = shots[0].stat().st_mtime
        if (now - latest_shot) > silence_threshold:
            reasons.append(f"无新截图 {(now - latest_shot):.0f}s")

    if reasons:
        return True, " | ".join(reasons)
    return False, ""


def _check_loop() -> tuple[bool, str, str]:
    """检测循环: failure_events 中同一 fingerprint 在最近 K 条中重复。"""
    if not FAILURE_EVENTS_FILE.exists():
        return False, "", ""

    try:
        lines = FAILURE_EVENTS_FILE.read_text(encoding="utf-8").strip().splitlines()
        if not lines:
            return False, "", ""
        recent = [json.loads(l) for l in lines[-LOOP_K * 2 :]]  # 看最近 2K 条
        fps = [e.get("fingerprint", "") for e in recent if e.get("fingerprint")]
        if len(fps) >= LOOP_K:
            # 滑动窗口检查
            for i in range(len(fps) - LOOP_K + 1):
                window = fps[i : i + LOOP_K]
                if len(set(window)) == 1 and window[0]:
                    return True, f"fingerprint {window[0]} 连续重复 {LOOP_K} 次 (loop)", window[0]
    except Exception:
        pass
    return False, "", ""


def _record_failure_event(signal: str, detail: str, screenshot: Path | None = None) -> bool:
    """调用 failure_event_bus 记录失败事件。"""
    try:
        cmd = [
            sys.executable,
            str(REPO_ROOT / "scripts" / "failure_event_bus.py"),
            "record",
            "--signal",
            signal,
            "--agent",
            "stagnation_watcher",
            "--source",
            "stagnation_watcher",
            "--signature",
            f"stagnation_watcher:{signal}:{hashlib.md5(detail.encode()).hexdigest()[:8]}",
            "--detail",
            detail,
            "--auto-screenshot",  # 也会自动归档最近截图
        ]
        if screenshot and screenshot.exists():
            cmd.extend(["--screenshot", str(screenshot)])
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return result.returncode == 0
    except Exception:
        return False


def run_check(step_latency: int = STEP_LATENCY_DEFAULT) -> dict:
    """执行一次完整检查，返回检测结果。"""
    state = _load_state()
    alerts = []

    # 1. stagnation
    is_stag, stag_detail, stag_shot = _check_stagnation(state)
    if is_stag:
        _emit_alert(state, alerts, "stagnation", stag_detail, stag_shot)

    # 2. silence
    is_sil, sil_detail = _check_silence(state, step_latency)
    if is_sil:
        _emit_alert(state, alerts, "silence", sil_detail)

    # 3. loop
    is_loop, loop_detail, loop_fp = _check_loop()
    if is_loop:
        _emit_alert(state, alerts, "loop", loop_detail)

    state["last_check"] = _now_iso()
    if alerts:
        state.setdefault("alerts", []).extend(alerts)
        # 只保留最近 100 条告警
        state["alerts"] = state["alerts"][-100:]
    _save_state(state)

    return {"checks": ["stagnation", "silence", "loop"], "alerts": alerts}


def _emit_alert(
    state: dict, alerts: list, type_: str, detail: str, screenshot: Path | None = None
) -> None:
    """告警出⼝：同类告警 6h 冷却（防空闲期 silence 常态误报刷屏）→ 入 failure_event_bus。"""
    cd = state.setdefault("alert_cooldown", {})
    # 冷却键抹平动态数字（秒数等），同类模式共用一个冷却窗
    sig = f"{type_}:{re.sub(r'[0-9]+', 'n', str(detail))[:120]}"
    now = time.time()
    last = cd.get(sig, 0)
    # 清理过期冷却键，防 state 膨胀
    for k in [k for k, t in cd.items() if now - t > ALERT_COOLDOWN_S * 4]:
        cd.pop(k, None)
    if now - last < ALERT_COOLDOWN_S:
        return
    cd[sig] = now
    _record_failure_event(type_, detail, screenshot)
    alerts.append({"type": type_, "detail": detail, "ts": _now_iso()})


def main() -> int:
    parser = argparse.ArgumentParser(description="卡死三判据 watcher")
    parser.add_argument(
        "--step-latency",
        type=int,
        default=STEP_LATENCY_DEFAULT,
        help="预估步时延(秒)，静默阈值=2×该值",
    )
    parser.add_argument("--once", action="store_true", help="单次检查并退出")
    parser.add_argument("--interval", type=int, default=120, help="循环间隔(秒)，配合非 --once")
    args = parser.parse_args()

    if args.once:
        result = run_check(args.step_latency)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if not result["alerts"] else 1

    # 循环模式 (供 launchd 守护，但建议用 launchd StartInterval)
    try:
        while True:
            result = run_check(args.step_latency)
            if result["alerts"]:
                print(
                    f"[{_now_iso()}] 检出 {len(result['alerts'])} 个卡死信号: "
                    f"{', '.join(a['type'] for a in result['alerts'])}"
                )
            time.sleep(args.interval)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
