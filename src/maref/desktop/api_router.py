"""
MAREF Desktop FastAPI Router — RESTful API for desktop operations.

Exposes the DesktopController through HTTP endpoints for GUI integration.
All endpoints follow MAREF coding conventions (/api/v1/ prefix).
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from maref.desktop.controller import (
    DesktopController,
    DesktopOperation,
    DesktopOperationType,
    ExecutionPlan,
)

router = APIRouter(prefix="/api/v1/desktop", tags=["desktop"])

# Shared controller instance (lazy-initialized)
_controller: DesktopController | None = None


def get_controller() -> DesktopController:
    """Get or create the shared DesktopController instance."""
    global _controller
    if _controller is None:
        _controller = DesktopController(dry_run=True, parser_backend="auto")
    return _controller


# ── Request/Response models ──────────────────────────────────────

class OperationRequest(BaseModel):
    op_type: str = Field(..., description="Operation type: click, type, hotkey, etc.")
    params: dict[str, Any] = Field(default_factory=dict, description="Operation parameters")
    description: str = Field(default="", description="Human-readable description")


class PlanRequest(BaseModel):
    description: str = Field(default="", description="Plan description")
    steps: list[OperationRequest] = Field(..., description="List of operations")
    dry_run: bool = Field(default=True, description="If true, simulate without executing")


class TemplateRequest(BaseModel):
    template_name: str = Field(..., description="Template name: open_finder, open_browser, etc.")
    dry_run: bool = Field(default=True, description="If true, simulate without executing")


# ── Endpoints ────────────────────────────────────────────────────

@router.get("/status")
async def get_status():
    """Get desktop controller status and capabilities."""
    ctrl = get_controller()
    return {
        "dry_run": ctrl.dry_run,
        "pyautogui_available": ctrl._input.pyautogui_available,
        "parser_backend": ctrl._parser.actual_backend,
        "parser_info": ctrl._parser.backend_info,
        "parser_initialized": ctrl._parser.initialized,
        "execution_count": ctrl._execution_count,
    }


@router.post("/permissions")
async def check_permissions():
    """Check OS-level permissions for desktop control."""
    ctrl = get_controller()
    perms = ctrl.check_permissions()
    return {"permissions": perms}


@router.post("/calibrate")
async def calibrate():
    """Calibrate screen and input configuration."""
    ctrl = get_controller()
    info = ctrl.calibrate()
    return {"calibration": info}


@router.post("/capture")
async def capture_screenshot():
    """Capture current screen and return metadata."""
    ctrl = get_controller()
    result = ctrl.capture()
    return {
        "width": result.width,
        "height": result.height,
        "capture_time_ms": round(result.capture_time_ms, 1),
        "mode": result.mode.value,
        "redactions_applied": result.redactions_applied,
    }


@router.post("/parse")
async def parse_screenshot(screenshot_path: str = ""):
    """Parse screenshot and return detected UI elements."""
    ctrl = get_controller()
    parse_result = ctrl.parse(screenshot_path)
    return {
        "screen_width": parse_result.screen_width,
        "screen_height": parse_result.screen_height,
        "element_count": len(parse_result.elements),
        "elements": [e.to_dict() for e in parse_result.elements],
        "parse_time_ms": round(parse_result.parse_time_ms, 1),
        "model_name": parse_result.model_name,
    }


@router.get("/ui-elements")
async def get_ui_elements():
    """Get recently parsed UI elements."""
    ctrl = get_controller()
    return {"elements": ctrl.get_ui_elements()}


@router.post("/execute")
async def execute_operation(req: OperationRequest):
    """Execute a single desktop operation."""
    ctrl = get_controller()
    try:
        op_type = DesktopOperationType(req.op_type)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid operation type: {req.op_type}") from e

    op = DesktopOperation(op_type=op_type, params=req.params, description=req.description)
    result = ctrl.execute_operation(op)
    return {
        "success": result.success,
        "action_type": result.action_type,
        "details": result.details,
        "duration_ms": round(result.duration_ms, 1),
        "safety_decision": result.safety_decision.value,
        "error_message": result.error_message,
    }


@router.post("/execute-plan")
async def execute_plan(req: PlanRequest):
    """Execute a sequence of desktop operations."""
    ctrl = get_controller()

    # Update dry-run mode based on request
    if req.dry_run != ctrl.dry_run:
        if req.dry_run:
            ctrl._input.dry_run = True
            ctrl._dry_run = True
        else:
            enabled = ctrl.enable_real_mode()
            if not enabled:
                raise HTTPException(status_code=400, detail="Cannot enable real mode: PyAutoGUI not available or permissions denied")

    plan = ExecutionPlan(plan_id=f"plan_{int(time.time())}", description=req.description)
    for step in req.steps:
        try:
            op_type = DesktopOperationType(step.op_type)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid operation type: {step.op_type}") from e
        plan.add_step(DesktopOperation(op_type=op_type, params=step.params, description=step.description))

    result = ctrl.execute_and_persist(plan)
    return result


@router.post("/execute-template")
async def execute_template(req: TemplateRequest):
    """Execute a pre-defined operation template."""
    ctrl = get_controller()

    # Update dry-run mode
    if req.dry_run != ctrl.dry_run:
        if req.dry_run:
            ctrl._input.dry_run = True
            ctrl._dry_run = True
        else:
            enabled = ctrl.enable_real_mode()
            if not enabled:
                raise HTTPException(status_code=400, detail="Cannot enable real mode: PyAutoGUI not available or permissions denied")

    plan = ctrl.create_plan_from_template(req.template_name)
    result = ctrl.execute_and_persist(plan)
    return result


@router.get("/history")
async def get_history(limit: int = 50):
    """Get operation history."""
    ctrl = get_controller()
    return {"executions": ctrl.get_history(limit)}


@router.get("/history/{execution_id}")
async def get_execution_details(execution_id: int):
    """Get details of a specific execution."""
    ctrl = get_controller()
    details = ctrl.get_execution_details(execution_id)
    if "error" in details:
        raise HTTPException(status_code=404, detail=details["error"])
    return details


@router.get("/policy-status")
async def get_policy_status():
    """Get policy decision tree status and mode."""
    ctrl = get_controller()
    return {
        "operation_mode": ctrl._policy_tree.mode.value,
        "decision_log_count": len(ctrl._policy_tree.get_decision_log()),
        "level_distribution": ctrl._policy_tree.get_level_distribution(),
        "pending_hitl": ctrl.pending_hitl_decision.to_dict() if ctrl.pending_hitl_decision else None,
    }


@router.post("/set-mode")
async def set_operation_mode(mode: str):
    """Set operation mode: full_auto, semi_auto, ask_mode."""
    from maref.desktop.policy_decision_tree import OperationMode
    ctrl = get_controller()
    try:
        ctrl.set_operation_mode(OperationMode(mode))
        return {"mode": mode, "success": True}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid mode: {mode}") from e


@router.post("/hitl/approve")
async def approve_hitl():
    """Approve pending HITL decision."""
    ctrl = get_controller()
    approved = ctrl.approve_hitl()
    return {"approved": approved}


@router.post("/hitl/reject")
async def reject_hitl():
    """Reject pending HITL decision."""
    ctrl = get_controller()
    rejected = ctrl.reject_hitl()
    return {"rejected": rejected}


@router.get("/decision-log")
async def get_decision_log():
    """Get policy decision log."""
    ctrl = get_controller()
    return {"decisions": ctrl.get_policy_decision_log()}


@router.get("/governance-status")
async def get_governance_status():
    """Get governance dashboard status."""
    ctrl = get_controller()
    return ctrl.get_governance_status()


@router.post("/governance/mode")
async def set_governance_mode(mode: str):
    """Set governance mode: degrade or escalate."""
    ctrl = get_controller()
    ctrl.set_governance_mode(mode)
    return {"mode": mode, "success": True}


@router.get("/governance-events")
async def get_governance_events(limit: int = 50):
    """Get governance event log."""
    ctrl = get_controller()
    return {"events": ctrl.get_governance_events(limit)}
