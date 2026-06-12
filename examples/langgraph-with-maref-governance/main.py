"""
演示: LangGraph Agent 通过 MAREF Sidecar 进行治理。
"""
from langgraph.graph import StateGraph
from maref_sidecar import GovernedAgent  # MAREF Sidecar 适配器

# 创建一个受 MAREF 治理的 LangGraph Agent
agent = GovernedAgent(
    agent_id="my-langgraph-agent",
    rules=["max_tokens_per_task: 100000", "require_human_approval: shell"],
)

# 标准 LangGraph 工作流 — 完全不变
graph = StateGraph(AgentState)
graph.add_node("research", agent.wrap(research_node))
graph.add_node("write", agent.wrap(write_node))
graph.add_edge("research", "write")
graph.set_entry_point("research")

# 执行 — 所有治理自动生效
app = graph.compile()
result = app.invoke({"topic": "AI Safety"})
# MAREF 自动: 审计日志 / Token 预算 / 危险操作确认
