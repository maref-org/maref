"""
MAREF Desktop Controller — 截图→解析→操作→验证 全链路真实执行器

This is the central orchestrator for desktop automation. It coordinates:
1. ScreenCapture (screenshot)
2. ScreenParser/OmniParser (parse UI elements)
3. InputController (execute mouse/keyboard)
4. ScreenshotVerifier (verify operation result)
5. DesktopSafetyGateV2 (pre-operation safety check)
6. DesktopGovernance (post-operation governance)

All operations go through this controller. No direct calls to lower-level modules.
"""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from maref.desktop.desktop_governance import (
    DesktopGovernance,
)
from maref.desktop.input_controller import (
    InputController,
    InputSafetyGate,
    OperationResult,
    SafetyDecision,
)
from maref.desktop.policy_decision_tree import (
    DecisionResult as TreeDecisionResult,
)
from maref.desktop.policy_decision_tree import (
    DecisionVerdict,
    OperationMode,
    PolicyDecisionTree,
)
from maref.desktop.screen_capture import DownsampleMethod, ScreenCapture, ScreenshotResult
from maref.desktop.screen_parser import OmniParserInterface, ScreenParseResult
from maref.desktop.verification import ScreenshotVerifier
from maref.observability.otel_middleware import _SpanContextManager

try:
    from PIL import Image
except ImportError:
    Image = None  # type: ignore


class DesktopOperationType(str, Enum):
    """Supported desktop operation types."""

    CLICK = "click"
    DOUBLE_CLICK = "double_click"
    RIGHT_CLICK = "right_click"
    TYPE = "type"
    HOTKEY = "hotkey"
    SCROLL = "scroll"
    DRAG = "drag"
    WAIT = "wait"
    SCREENSHOT = "screenshot"
    PARSE = "parse"


@dataclass
class DesktopOperation:
    """A single desktop operation with parameters."""

    op_type: DesktopOperationType
    params: dict[str, Any] = field(default_factory=dict)
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "op_type": self.op_type.value,
            "params": self.params,
            "description": self.description,
        }


@dataclass
class ExecutionStep:
    """Result of executing a single desktop operation."""

    step_index: int
    operation: DesktopOperation
    success: bool
    duration_ms: float = 0.0
    error: str = ""
    safety_decision: str = SafetyDecision.ALLOW.value
    verification_passed: bool = True
    verification_diff_pct: float = 0.0
    screenshot_before: str = ""  # base64 or path
    screenshot_after: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_index": self.step_index,
            "operation": self.operation.to_dict(),
            "success": self.success,
            "duration_ms": round(self.duration_ms, 1),
            "error": self.error,
            "safety_decision": self.safety_decision,
            "verification_passed": self.verification_passed,
            "verification_diff_pct": round(self.verification_diff_pct, 4),
        }


@dataclass
class ExecutionPlan:
    """A sequence of desktop operations to execute."""

    plan_id: str
    description: str = ""
    steps: list[DesktopOperation] = field(default_factory=list)
    safe_apps: set[str] = field(
        default_factory=lambda: {
            "Finder",
            "Safari",
            "终端",
            "Visual Studio Code",
            "Xcode",
            "Google Chrome",
            "Firefox",
            "Mail",
            "Notes",
            "Calendar",
        }
    )

    def add_step(self, op: DesktopOperation) -> None:
        self.steps.append(op)

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "description": self.description,
            "steps": [s.to_dict() for s in self.steps],
            "safe_apps": sorted(self.safe_apps),
        }


@dataclass
class ExecutionResult:
    """Full result of executing an execution plan."""

    plan_id: str
    success: bool
    steps: list[ExecutionStep] = field(default_factory=list)
    total_duration_ms: float = 0.0
    error_summary: str = ""
    governance_state: str = "healthy"

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "success": self.success,
            "steps": [s.to_dict() for s in self.steps],
            "total_duration_ms": round(self.total_duration_ms, 1),
            "error_summary": self.error_summary,
            "governance_state": self.governance_state,
        }


@dataclass
class PersistedExecution:
    """A persisted execution plan in the database."""

    id: int
    plan_id: str
    description: str
    plan_json: str
    result_json: str
    created_at: float
    executed_at: float = 0.0
    success: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "plan_id": self.plan_id,
            "description": self.description,
            "plan": json.loads(self.plan_json),
            "result": json.loads(self.result_json) if self.result_json else None,
            "created_at": self.created_at,
            "executed_at": self.executed_at,
            "success": self.success,
        }


class HistoryDatabase:
    """SQLite-backed operation history persistence."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        if db_path is None:
            import tempfile

            self._path = Path(tempfile.gettempdir()) / "maref_desktop_history.db"
        else:
            self._path = Path(db_path) if not isinstance(db_path, Path) else db_path
        self._init_db()

    def _init_db(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._path))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS executions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plan_id TEXT NOT NULL,
                description TEXT DEFAULT '',
                plan_json TEXT NOT NULL,
                result_json TEXT DEFAULT '',
                created_at REAL NOT NULL,
                executed_at REAL DEFAULT 0,
                success INTEGER DEFAULT 0
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS operations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                execution_id INTEGER NOT NULL,
                step_index INTEGER NOT NULL,
                op_type TEXT NOT NULL,
                params_json TEXT NOT NULL,
                description TEXT DEFAULT '',
                success INTEGER DEFAULT 0,
                duration_ms REAL DEFAULT 0,
                error TEXT DEFAULT '',
                safety_decision TEXT DEFAULT 'allow',
                verification_passed INTEGER DEFAULT 1,
                verification_diff_pct REAL DEFAULT 0,
                created_at REAL NOT NULL,
                FOREIGN KEY (execution_id) REFERENCES executions(id)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ops_execution ON operations(execution_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_exec_plan ON executions(plan_id)")
        conn.close()

    def save_plan(self, plan: ExecutionPlan) -> int:
        conn = sqlite3.connect(str(self._path))
        cursor = conn.execute(
            "INSERT INTO executions (plan_id, description, plan_json, created_at) VALUES (?, ?, ?, ?)",
            (plan.plan_id, plan.description, json.dumps(plan.to_dict()), time.time()),
        )
        conn.commit()
        eid = cursor.lastrowid
        conn.close()
        return eid if eid is not None else 0

    def save_result(self, execution_id: int, result: ExecutionResult) -> None:
        conn = sqlite3.connect(str(self._path))
        conn.execute(
            "UPDATE executions SET result_json = ?, executed_at = ?, success = ? WHERE id = ?",
            (json.dumps(result.to_dict()), time.time(), 1 if result.success else 0, execution_id),
        )
        for step in result.steps:
            conn.execute(
                """INSERT INTO operations (execution_id, step_index, op_type, params_json, description,
                    success, duration_ms, error, safety_decision, verification_passed, verification_diff_pct, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    execution_id,
                    step.step_index,
                    step.operation.op_type.value,
                    json.dumps(step.operation.params),
                    step.operation.description,
                    1 if step.success else 0,
                    step.duration_ms,
                    step.error,
                    step.safety_decision,
                    1 if step.verification_passed else 0,
                    step.verification_diff_pct,
                    time.time(),
                ),
            )
        conn.commit()
        conn.close()

    def get_executions(self, limit: int = 100) -> list[dict[str, Any]]:
        conn = sqlite3.connect(str(self._path))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM executions ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_operations(self, execution_id: int) -> list[dict[str, Any]]:
        conn = sqlite3.connect(str(self._path))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM operations WHERE execution_id = ? ORDER BY step_index", (execution_id,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]


class DesktopController:
    """全链路桌面操控执行器：截图→解析→操作→验证

    这是桌面 Agent 的核心控制器。所有桌面操作都必须通过此控制器，
    确保每个操作都经过安全门、治理层、和事后验证。

    执行流程:
    1. capture() — 截图 (ScreenCapture)
    2. parse() — 解析 UI 元素 (OmniParserInterface)
    3. plan() — 规划操作序列 (用户或 LLM 定义)
    4. execute() — 逐步骤执行 (InputController)
    5. verify() — 验证操作结果 (ScreenshotVerifier)
    6. record() — 持久化到 SQLite (HistoryDatabase)
    """

    def __init__(
        self,
        dry_run: bool = False,
        history_db: str | Path | None = None,
        parser_backend: str = "auto",
        diff_threshold: float = 0.05,
        operation_mode: OperationMode = OperationMode.SEMI_AUTO,
        safe_apps: set[str] | None = None,
    ) -> None:
        self._safety_gate = InputSafetyGate()
        self._input = InputController(
            dry_run=dry_run,
        )
        self._capture = ScreenCapture(
            downsample_method=DownsampleMethod.BILINEAR, downsample_factor=0.5
        )
        self._parser = OmniParserInterface(backend=parser_backend)
        self._parser.initialize()
        self._verifier = ScreenshotVerifier(diff_threshold=diff_threshold)
        self._history = HistoryDatabase(history_db)
        self._governance = DesktopGovernance()
        self._policy_tree = PolicyDecisionTree(mode=operation_mode)
        self._safe_apps = safe_apps or {
            "Finder",
            "Safari",
            "Google Chrome",
            "Firefox",
            "Notes",
            "Calendar",
            "TextEdit",
            "Preview",
        }
        self._dry_run = dry_run
        self._last_screenshot: ScreenshotResult | None = None
        self._last_parse_result: ScreenParseResult | None = None
        self._execution_count: int = 0
        self._pending_hitl_decision: TreeDecisionResult | None = None

    @property
    def dry_run(self) -> bool:
        return self._dry_run

    def enable_real_mode(self) -> bool:
        """切换到真实执行模式（非 dry-run）"""
        if not self._input.pyautogui_available:
            return False
        self._dry_run = False
        self._input.enable_real_mode()
        return True

    def check_permissions(self) -> dict[str, bool]:
        """检查 macOS 桌面操控所需权限"""
        return self._input.check_permissions()

    def calibrate(self) -> dict[str, Any]:
        """校准屏幕和输入配置"""
        return self._input.calibrate()

    def capture(self) -> ScreenshotResult:
        """截图当前屏幕"""
        with _SpanContextManager("capture"):
            self._last_screenshot = self._capture.capture_fullscreen()
            return self._last_screenshot

    def parse(self, screenshot_path: str = "") -> ScreenParseResult:
        """解析截图中的 UI 元素"""
        with _SpanContextManager("parse", attributes={"screenshot_path": screenshot_path}):
            if not screenshot_path and self._last_screenshot and self._last_screenshot.image:
                import tempfile

                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                    self._last_screenshot.save(f.name)
                    screenshot_path = f.name
            if not screenshot_path:
                return ScreenParseResult(screen_width=1920, screen_height=1080, parse_time_ms=0)
            self._last_parse_result = self._parser.parse(screenshot_path)
            return self._last_parse_result

    def get_ui_elements(self) -> list[dict[str, Any]]:
        """获取最近解析的 UI 元素列表"""
        if self._last_parse_result is None:
            return []
        return [e.to_dict() for e in self._last_parse_result.elements]

    def click(self, x: int, y: int) -> OperationResult:
        """点击指定坐标"""
        return self._input.click(x, y)

    def double_click(self, x: int, y: int) -> OperationResult:
        """双击指定坐标"""
        return self._input.double_click(x, y)

    def right_click(self, x: int, y: int) -> OperationResult:
        """右键点击指定坐标"""
        return self._input.right_click(x, y)

    def type_text(self, text: str) -> OperationResult:
        """输入文本"""
        return self._input.type_text(text)

    def hotkey(self, *keys: str) -> OperationResult:
        """组合键"""
        return self._input.hotkey(*keys)

    def scroll(self, clicks: int) -> OperationResult:
        """滚动"""
        return self._input.scroll(clicks)

    def drag(self, x1: int, y1: int, x2: int, y2: int, duration: float = 0.5) -> OperationResult:
        """拖拽"""
        return self._input.drag(x1, y1, x2, y2, duration)

    def wait(self, seconds: float = 1.0) -> OperationResult:
        """等待"""
        import time as _time

        start = _time.time()
        _time.sleep(seconds)
        return OperationResult(
            success=True,
            action_type="wait",
            details=f"Waited {seconds}s",
            duration_ms=(_time.time() - start) * 1000,
        )

    def execute_operation(self, op: DesktopOperation) -> OperationResult:
        """执行单个操作"""
        op_map = {
            DesktopOperationType.CLICK: lambda: self.click(
                op.params.get("x", 0), op.params.get("y", 0)
            ),
            DesktopOperationType.DOUBLE_CLICK: lambda: self.double_click(
                op.params.get("x", 0), op.params.get("y", 0)
            ),
            DesktopOperationType.RIGHT_CLICK: lambda: self.right_click(
                op.params.get("x", 0), op.params.get("y", 0)
            ),
            DesktopOperationType.TYPE: lambda: self.type_text(op.params.get("text", "")),
            DesktopOperationType.HOTKEY: lambda: self.hotkey(*op.params.get("keys", [])),
            DesktopOperationType.SCROLL: lambda: self.scroll(op.params.get("clicks", 1)),
            DesktopOperationType.DRAG: lambda: self.drag(
                op.params.get("x1", 0),
                op.params.get("y1", 0),
                op.params.get("x2", 0),
                op.params.get("y2", 0),
                op.params.get("duration", 0.5),
            ),
            DesktopOperationType.WAIT: lambda: self.wait(op.params.get("seconds", 1.0)),
            DesktopOperationType.SCREENSHOT: lambda: OperationResult(
                success=self.capture().width > 0,
                action_type="screenshot",
                details=f"Captured {self._last_screenshot.width}x{self._last_screenshot.height}"
                if self._last_screenshot
                else "No screenshot",
            ),
            DesktopOperationType.PARSE: lambda: OperationResult(
                success=bool(self.parse()),
                action_type="parse",
                details=f"Parsed {len(self._last_parse_result.elements)} elements"
                if self._last_parse_result
                else "No elements",
            ),
        }
        fn = op_map.get(op.op_type)
        if fn is None:
            return OperationResult(
                success=False,
                action_type=op.op_type.value,
                error_message=f"Unknown operation: {op.op_type}",
            )
        return fn()

    def execute_plan(self, plan: ExecutionPlan) -> ExecutionResult:
        """执行完整操作计划 — 截图→解析→操作→验证 全链路

        这是桌面 Agent 的核心执行入口。对每个步骤：
        1. 截图 (before)
        2. 执行操作
        3. 截图 (after)
        4. 验证差异
        5. 记录结果
        """
        with _SpanContextManager(
            "execute_plan",
            attributes={
                "plan_id": plan.plan_id,
                "step_count": len(plan.steps),
            },
        ):
            return self._execute_plan_inner(plan)

    def _execute_plan_inner(self, plan: ExecutionPlan) -> ExecutionResult:
        """Internal implementation of execute_plan (wrapped by OTel span)."""
        self._execution_count += 1
        result = ExecutionResult(plan_id=plan.plan_id, success=True)
        start_total = time.time()

        for idx, op in enumerate(plan.steps):
            step_start = time.time()

            # 安全门检查
            safety = self._check_safety(op)
            if safety == SafetyDecision.BLOCK:
                tree_result = self._pending_hitl_decision
                step = ExecutionStep(
                    step_index=idx,
                    operation=op,
                    success=False,
                    error=f"Blocked by policy tree: {tree_result.reason if tree_result else 'safety gate'}",
                    safety_decision=safety.value,
                    duration_ms=(time.time() - step_start) * 1000,
                )
                result.steps.append(step)
                result.success = False
                result.error_summary = f"Step {idx} blocked by policy decision tree"
                break

            if safety == SafetyDecision.ASK_USER:
                tree_result = self._pending_hitl_decision
                step = ExecutionStep(
                    step_index=idx,
                    operation=op,
                    success=False,
                    error="HITL: waiting for user confirmation",
                    safety_decision=safety.value,
                    duration_ms=(time.time() - step_start) * 1000,
                )
                result.steps.append(step)
                result.success = False
                result.error_summary = f"Step {idx} requires human-in-the-loop confirmation"
                break

            # 截图 before
            before_img: Image.Image | None = None
            if Image is not None and op.op_type != DesktopOperationType.SCREENSHOT:
                before_capture = self._capture.capture_fullscreen()
                before_img = before_capture.image

            # 执行操作
            exec_result = self.execute_operation(op)
            step_duration = (time.time() - step_start) * 1000

            # 截图 after + 验证
            verification_passed = True
            verification_diff = 0.0
            if before_img is not None and op.op_type not in (
                DesktopOperationType.WAIT,
                DesktopOperationType.PARSE,
            ):
                time.sleep(0.3)
                after_capture = self._capture.capture_fullscreen()
                after_img = after_capture.image
                if before_img and after_img and before_img.size == after_img.size:
                    ver_result = self._verifier.compare(before_img, after_img)
                    verification_passed = ver_result.passed
                    verification_diff = ver_result.diff_percentage

            step = ExecutionStep(
                step_index=idx,
                operation=op,
                success=exec_result.success,
                duration_ms=step_duration,
                error=exec_result.error_message,
                safety_decision=safety.value,
                verification_passed=verification_passed,
                verification_diff_pct=verification_diff,
            )
            result.steps.append(step)

            # 上报治理层
            target = op.description or op.op_type.value
            self._governance.record_operation_result(
                success=exec_result.success and verification_passed,
                operation_type=op.op_type.value,
                target=target,
            )

            # 检查治理干预
            intervention = self._governance.check_and_intervene()
            if intervention is not None:
                result.success = False
                result.error_summary = (
                    f"Governance intervention: {intervention.value} at step {idx}"
                )
                break

            if not exec_result.success:
                result.success = False
                result.error_summary = f"Step {idx} failed: {exec_result.error_message}"
                break

        result.total_duration_ms = (time.time() - start_total) * 1000
        return result

    def execute_and_persist(self, plan: ExecutionPlan) -> dict[str, Any]:
        """执行计划并持久化到 SQLite"""
        eid = self._history.save_plan(plan)
        result = self.execute_plan(plan)
        self._history.save_result(eid, result)
        return result.to_dict()

    def get_history(self, limit: int = 50) -> list[dict[str, Any]]:
        """获取操作历史"""
        return self._history.get_executions(limit)

    def get_execution_details(self, execution_id: int) -> dict[str, Any]:
        """获取执行详情"""
        executions = self._history.get_executions(1000)
        ex = next((e for e in executions if e["id"] == execution_id), None)
        if ex is None:
            return {"error": "Execution not found"}
        ops = self._history.get_operations(execution_id)
        return {**ex, "operations": ops}

    def _check_safety(self, op: DesktopOperation) -> SafetyDecision:
        """安全门检查 — 连接 PolicyDecisionTree 四级决策树"""
        # 应用名未知时设为 None，跳过应用边界检查
        app_name = self._input._safety_gate.current_app or None
        element_text = op.params.get("element_text", "")
        input_text = ""
        if op.op_type == DesktopOperationType.TYPE:
            input_text = op.params.get("text", "")
        if op.op_type == DesktopOperationType.HOTKEY:
            input_text = "+".join(op.params.get("keys", []))

        tree_result = self._policy_tree.evaluate(
            operation=op.op_type.value,
            app_name=app_name or "",
            element_text=element_text,
            input_text=input_text,
            safe_apps=self._safe_apps,
        )

        if tree_result.verdict == DecisionVerdict.BLOCK:
            return SafetyDecision.BLOCK
        if tree_result.verdict == DecisionVerdict.ASK_USER:
            self._pending_hitl_decision = tree_result
            return SafetyDecision.ASK_USER
        return SafetyDecision.ALLOW

    @property
    def pending_hitl_decision(self) -> TreeDecisionResult | None:
        return self._pending_hitl_decision

    def approve_hitl(self) -> bool:
        if self._pending_hitl_decision is None:
            return False
        self._pending_hitl_decision = None
        return True

    def reject_hitl(self) -> bool:
        if self._pending_hitl_decision is None:
            return False
        self._pending_hitl_decision = None
        return False

    def set_operation_mode(self, mode: OperationMode) -> None:
        self._policy_tree.set_mode(mode)

    def get_policy_decision_log(self) -> list[dict[str, Any]]:
        return [d.to_dict() for d in self._policy_tree.get_decision_log()]

    def get_governance_status(self) -> dict[str, Any]:
        """获取治理状态看板数据"""
        state = self._governance.state
        event_log = self._governance.event_log
        recent_events = [e.to_dict() for e in event_log[-20:]]

        action_counts: dict[str, int] = {}
        state_counts: dict[str, int] = {}
        for e in event_log:
            action_counts[e.action.value] = action_counts.get(e.action.value, 0) + 1
            state_counts[e.new_state.value] = state_counts.get(e.new_state.value, 0) + 1

        safety = self._governance._safety_gate
        return {
            "state": state.value,
            "autonomy_level": self._governance.get_autonomy_level(),
            "is_healthy": self._governance.is_healthy,
            "consecutive_failures": safety.consecutive_failures,
            "is_locked": safety.is_locked,
            "total_events": len(event_log),
            "recent_events": recent_events,
            "action_distribution": action_counts,
            "state_distribution": state_counts,
            "operation_history_count": len(safety._operation_history),
            "last_operation_time": safety._last_operation_time,
        }

    def set_governance_mode(self, mode: str) -> None:
        """设置治理模式"""
        if mode == "degrade":
            self._governance.degrade_mode("Manual degradation via API")
        elif mode == "escalate":
            self._governance.escalate_to_human("Manual escalation via API")

    def get_governance_events(self, limit: int = 50) -> list[dict[str, Any]]:
        """获取治理事件日志"""
        events = self._governance.event_log
        return [e.to_dict() for e in events[-limit:]]

    @staticmethod
    def create_plan_from_template(template_name: str) -> ExecutionPlan:
        """从模板创建执行计划"""
        templates: dict[str, list[tuple[str, dict]]] = {
            "open_finder": [
                ("hotkey", {"keys": ["command", "space"]}),
                ("wait", {"seconds": 0.5}),
                ("type", {"text": "Finder"}),
                ("wait", {"seconds": 0.5}),
                ("hotkey", {"keys": ["return"]}),
            ],
            "open_browser": [
                ("hotkey", {"keys": ["command", "space"]}),
                ("wait", {"seconds": 0.5}),
                ("type", {"text": "Safari"}),
                ("wait", {"seconds": 0.5}),
                ("hotkey", {"keys": ["return"]}),
            ],
            "open_terminal": [
                ("hotkey", {"keys": ["command", "space"]}),
                ("wait", {"seconds": 0.5}),
                ("type", {"text": "Terminal"}),
                ("wait", {"seconds": 0.5}),
                ("hotkey", {"keys": ["return"]}),
            ],
            "screenshot_and_parse": [
                ("screenshot", {}),
                ("parse", {}),
            ],
        }
        steps = templates.get(template_name, [])
        plan = ExecutionPlan(plan_id=f"template_{template_name}_{int(time.time())}")
        for op_type_str, params in steps:
            op_type = DesktopOperationType(op_type_str)
            plan.add_step(DesktopOperation(op_type=op_type, params=params))
        return plan
