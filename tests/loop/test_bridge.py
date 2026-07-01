from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from maref.governance.types import GovernanceState
from maref.loop.base import LoopBase, LoopResult
from maref.loop.bridge import LoopGovernanceBridge
from maref.loop.protocols import ToolBoundary, ToolPermission


class TestLoopGovernanceBridge:
    @pytest.mark.asyncio
    async def test_run_governed_success(self, mock_state_machine):
        loop = _SimpleLoop()
        bridge = LoopGovernanceBridge(state_machine=mock_state_machine)
        result = await bridge.run_governed(loop, "input", task_id="test-1")
        assert isinstance(result, LoopResult)
        assert mock_state_machine.transition.called

    @pytest.mark.asyncio
    async def test_run_governed_with_audit(self, mock_state_machine):
        mock_audit = MagicMock()
        loop = _SimpleLoop()
        bridge = LoopGovernanceBridge(state_machine=mock_state_machine, audit_logger=mock_audit)
        await bridge.run_governed(loop, "input", task_id="test-2")
        assert mock_audit.log.called

    @pytest.mark.asyncio
    async def test_tool_boundary_not_allowed_raises(self):
        mock_sm = MagicMock()
        mock_sm.current_state = GovernanceState.VERIFY
        loop = _SimpleLoop(tb=ToolBoundary(permissions={"fs": ToolPermission.WRITE}))
        bridge = LoopGovernanceBridge(state_machine=mock_sm)
        with pytest.raises(RuntimeError, match="TrustBoundary violation"):
            await bridge.run_governed(loop, "input")

    @pytest.mark.asyncio
    async def test_is_tool_boundary_allowed_empty_perms(self, mock_state_machine):
        loop = _SimpleLoop()
        bridge = LoopGovernanceBridge(state_machine=mock_state_machine)
        assert bridge._is_tool_boundary_allowed(loop) is True

    @pytest.mark.asyncio
    async def test_is_tool_boundary_allowed_verify_state(self, mock_state_machine):
        mock_state_machine.current_state = GovernanceState.VERIFY
        loop = _SimpleLoop(tb=ToolBoundary(permissions={"fs": ToolPermission.READ}))
        bridge = LoopGovernanceBridge(state_machine=mock_state_machine)
        assert bridge._is_tool_boundary_allowed(loop) is True

    def test_snapshot(self, mock_state_machine):
        bridge = LoopGovernanceBridge(state_machine=mock_state_machine)
        snap = bridge.snapshot()
        assert "state_machine" in snap


class _SimpleLoop(LoopBase):
    def __init__(self, tb=None):
        super().__init__(tool_boundary=tb)

    async def run(self, *args, **kwargs):
        return LoopResult(output="ok")
