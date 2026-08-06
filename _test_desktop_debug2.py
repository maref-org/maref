#!/usr/bin/env python3
"""Debug v2: trace click failure in execute_plan."""

from maref.desktop.controller import (
    DesktopController,
    DesktopOperation,
    DesktopOperationType,
    ExecutionPlan,
)

ctrl = DesktopController(dry_run=True)

print("=== Instance check ===")
print(f"Same safety gate: {ctrl._safety_gate is ctrl._input._safety_gate}")
print(f"InputController safety_gate: {type(ctrl._input._safety_gate)}")
print(f"InputController safety_gate.current_app: '{ctrl._input._safety_gate.current_app}'")
print(f"InputController safety_gate.block_list_apps: {ctrl._input._safety_gate.block_list_apps}")
print(f"InputController safety_gate.safe_region: {ctrl._input._safety_gate.safe_region}")

# Test direct mouse safety check
from maref.desktop.input_controller import MouseAction, MouseEvent

event = MouseEvent(action=MouseAction.CLICK, x=100, y=100, button="left", clicks=1)
decision = ctrl._input._safety_gate.check_mouse(event)
print(f"\nDirect check_mouse: {decision.value}")

# Test direct click
result = ctrl.click(100, 100)
print(f"Direct click: success={result.success}, error={result.error_message}")

# Test execute_plan with verbose output
plan = ExecutionPlan(plan_id="debug-plan-2")
plan.add_step(DesktopOperation(op_type=DesktopOperationType.CLICK, params={"x": 100, "y": 100}))

print("\n=== execute_plan ===")
print(f"Plan steps: {len(plan.steps)}")
print(f"Step 0 op: {plan.steps[0].op_type.value}")

result = ctrl.execute_plan(plan)
print(f"Result: success={result.success}, steps={len(result.steps)}")
for step in result.steps:
    print(f"  Step {step.step_index}: {step.operation.op_type.value} -> success={step.success}")
    print(f"    safety_decision: {step.safety_decision}")
    print(f"    error: '{step.error}'")
    if hasattr(step, "verification_passed"):
        print(f"    verification_passed: {step.verification_passed}")

print("\nDone!")
