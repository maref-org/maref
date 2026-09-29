"""AgentDispatcher model-diversity 维度测试 (P2-9)."""

from __future__ import annotations

from maref.identity.did_registry import AgentDID
from maref.orchestration.decomposer import SubTask
from maref.orchestration.dispatcher import AgentDispatcher


def _task() -> SubTask:
    return SubTask("t0", "Test", 0.5, ["general"], [])


class TestModelDiversity:
    def test_disabled_when_no_models_registered(self) -> None:
        dispatcher = AgentDispatcher()
        dispatcher.register_agent(AgentDID.generate(), ["general"])
        assert "model_diversity" not in dispatcher._dimension_weights
        result = dispatcher.dispatch(_task())
        assert result is not None
        assert result.match_dimensions["model_diversity"] == 0.0

    def test_enabled_on_model_registration(self) -> None:
        dispatcher = AgentDispatcher()
        did = AgentDID.generate()
        dispatcher.register_agent(did, ["general"], model_id="model-a")
        assert "model_diversity" in dispatcher._dimension_weights
        result = dispatcher.dispatch(_task())
        assert result is not None
        # 单一模型池中，唯一模型的 diversity 为 0（无多样性可言）
        assert result.match_dimensions["model_diversity"] == 0.0

    def test_minority_model_preferred(self) -> None:
        dispatcher = AgentDispatcher()
        # 3 个 agent 用 model-a，1 个用 model-b，能力相同
        for _ in range(3):
            dispatcher.register_agent(AgentDID.generate(), ["general"], model_id="model-a")
        minority = AgentDID.generate()
        dispatcher.register_agent(minority, ["general"], model_id="model-b")

        result = dispatcher.dispatch(_task())
        assert result is not None
        assert result.agent_did == minority
        assert result.match_dimensions["model_diversity"] > 0.0

    def test_diversity_score_scales_with_scarcity(self) -> None:
        dispatcher = AgentDispatcher()
        common = AgentDID.generate()
        for _ in range(4):
            dispatcher.register_agent(AgentDID.generate(), ["general"], model_id="model-a")
        dispatcher.register_agent(common, ["general"], model_id="model-b")
        # model-b 现在占 1/5；score = 1 - 1/5 = 0.8
        assert dispatcher._model_diversity_score(common) == 0.8

    def test_unregister_clears_model(self) -> None:
        dispatcher = AgentDispatcher()
        did = AgentDID.generate()
        dispatcher.register_agent(did, ["general"], model_id="model-a")
        dispatcher.unregister_agent(did)
        assert did not in dispatcher._agent_models
