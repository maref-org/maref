from __future__ import annotations

from maref.recursive.formal_planner import (
    Action,
    CostBasedPlanner,
    ForwardChainingPlanner,
    Plan,
    PlanningDomain,
    PlanValidator,
    Predicate,
    build_agent_task_domain,
)


class TestPredicate:
    def test_create_and_evaluate(self) -> None:
        p = Predicate(name="ready", args=["agent_a"])
        assert p.name == "ready"
        assert p.args == ["agent_a"]
        state = frozenset([p])
        assert p.evaluate(state)
        state_empty = frozenset()
        assert not p.evaluate(state_empty)

    def test_to_string(self) -> None:
        p = Predicate(name="connected", args=["a", "b"])
        assert p.to_string() == "connected(a, b)"

    def test_equality(self) -> None:
        a = Predicate(name="p", args=["x", "y"])
        b = Predicate(name="p", args=["x", "y"])
        assert a == b
        assert hash(a) == hash(b)


class TestAction:
    def test_applicable(self) -> None:
        pre = Predicate(name="ready")
        action = Action(
            name="go",
            preconditions=[pre],
            add_effects=[Predicate(name="done")],
            del_effects=[pre],
        )
        state = frozenset([pre])
        assert action.applicable(state)
        assert not action.applicable(frozenset())

    def test_apply(self) -> None:
        ready = Predicate(name="ready")
        done = Predicate(name="done")
        action = Action(
            name="go",
            preconditions=[ready],
            add_effects=[done],
            del_effects=[ready],
        )
        state = frozenset([ready])
        new_state = action.apply(state)
        assert ready not in new_state
        assert done in new_state


class TestPlanningDomain:
    def test_build_agent_task_domain(self) -> None:
        domain = build_agent_task_domain()
        assert domain.action_count == 9
        assert domain.predicate_count > 0
        assert domain.name == "agent_task_domain"

    def test_get_action(self) -> None:
        domain = build_agent_task_domain()
        action = domain.get_action("run_probes")
        assert action is not None
        assert action.name == "run_probes"
        assert domain.get_action("nonexistent") is None


class TestForwardChainingPlanner:
    def test_plan_optimize_system(self) -> None:
        domain = build_agent_task_domain()
        trust_verified = None
        for p in domain.predicates:
            if p.name == "trust_verified":
                trust_verified = p
                break
        assert trust_verified is not None
        domain.goal_state = frozenset([trust_verified])

        planner = ForwardChainingPlanner(max_depth=20)
        plan = planner.plan(domain)
        assert plan is not None
        assert plan.step_count == 4
        assert plan.actions[0].name == "observe_perf"
        assert plan.actions[-1].name == "verify_trust"

    def test_plan_diagnose_anomaly(self) -> None:
        domain = build_agent_task_domain()
        action_decided = None
        for p in domain.predicates:
            if p.name == "action_decided":
                action_decided = p
                break
        assert action_decided is not None
        domain.goal_state = frozenset([action_decided])

        planner = ForwardChainingPlanner(max_depth=20)
        plan = planner.plan(domain)
        assert plan is not None
        assert plan.step_count == 3

    def test_plan_resolve_identity(self) -> None:
        domain = build_agent_task_domain()
        trust_cross_checked = None
        for p in domain.predicates:
            if p.name == "trust_cross_checked":
                trust_cross_checked = p
                break
        assert trust_cross_checked is not None
        domain.goal_state = frozenset([trust_cross_checked])

        planner = ForwardChainingPlanner(max_depth=20)
        plan = planner.plan(domain)
        assert plan is not None
        assert plan.step_count == 2

    def test_plan_unsatisfiable_goal(self) -> None:
        domain = build_agent_task_domain()
        unreachable = Predicate(name="unreachable")
        domain.goal_state = frozenset([unreachable])

        planner = ForwardChainingPlanner(max_depth=20, max_nodes=1000)
        plan = planner.plan(domain)
        assert plan is None

    def test_plan_empty_when_goal_already_satisfied(self) -> None:
        domain = build_agent_task_domain()
        idle = None
        for p in domain.predicates:
            if p.name == "agent_idle":
                idle = p
                break
        assert idle is not None
        domain.initial_state = frozenset([idle])
        domain.goal_state = frozenset([idle])

        planner = ForwardChainingPlanner()
        plan = planner.plan(domain)
        assert plan is not None
        assert plan.step_count == 0


class TestCostBasedPlanner:
    def test_plan_with_budget(self) -> None:
        domain = build_agent_task_domain()
        trust_verified = None
        for p in domain.predicates:
            if p.name == "trust_verified":
                trust_verified = p
                break
        assert trust_verified is not None
        domain.goal_state = frozenset([trust_verified])

        planner = CostBasedPlanner(max_cost=5.0, max_depth=20)
        plan = planner.plan_with_budget(domain)
        assert plan is not None
        assert plan.estimated_cost <= 5.0

    def test_plan_exceeds_budget(self) -> None:
        domain = build_agent_task_domain()
        trust_verified = None
        for p in domain.predicates:
            if p.name == "trust_verified":
                trust_verified = p
                break
        assert trust_verified is not None
        domain.goal_state = frozenset([trust_verified])

        planner = CostBasedPlanner(max_cost=0.5, max_depth=20)
        plan = planner.plan_with_budget(domain)
        assert plan is None


class TestPlanValidator:
    def test_valid_plan(self) -> None:
        domain = build_agent_task_domain()
        trust_verified = None
        for p in domain.predicates:
            if p.name == "trust_verified":
                trust_verified = p
                break
        assert trust_verified is not None
        domain.goal_state = frozenset([trust_verified])

        planner = ForwardChainingPlanner()
        plan = planner.plan(domain)
        assert plan is not None

        validator = PlanValidator()
        result = validator.validate(plan, domain)
        assert result.valid
        assert len(result.errors) == 0

    def test_invalid_plan_missing_precondition(self) -> None:
        ready = Predicate(name="ready")
        done = Predicate(name="done")
        idle = Predicate(name="idle")

        action1 = Action(
            name="step1",
            preconditions=[idle],
            add_effects=[ready],
            del_effects=[idle],
        )
        action2 = Action(
            name="step2",
            preconditions=[ready],
            add_effects=[done],
            del_effects=[],
        )
        domain = PlanningDomain(
            name="test",
            predicates=[ready, done, idle],
            actions=[action1, action2],
            initial_state=frozenset([idle]),
            goal_state=frozenset([done]),
        )
        plan = Plan(actions=[action2])
        validator = PlanValidator()
        result = validator.validate(plan, domain)
        assert not result.valid
        assert len(result.errors) >= 1
        assert any("preconditions" in e.lower() for e in result.errors)

    def test_validator_resource_conflicts(self) -> None:
        resource = Predicate(name="resource")
        idle = Predicate(name="idle")

        action1 = Action(
            name="consume",
            preconditions=[resource],
            add_effects=[idle],
            del_effects=[resource],
        )
        action2 = Action(
            name="use_after_consumed",
            preconditions=[resource],
            add_effects=[Predicate(name="done")],
            del_effects=[],
        )
        domain = PlanningDomain(
            name="resource_conflict",
            predicates=[resource, idle],
            actions=[action1, action2],
            initial_state=frozenset([resource]),
            goal_state=frozenset([idle]),
        )
        plan = Plan(actions=[action1, action2])
        validator = PlanValidator()
        result = validator.validate(plan, domain)
        assert len(result.resource_conflicts) >= 1

    def test_validator_goal_not_achieved(self) -> None:
        idle = Predicate(name="idle")
        done = Predicate(name="done")
        action = Action(
            name="do_nothing",
            preconditions=[idle],
            add_effects=[],
            del_effects=[],
        )
        domain = PlanningDomain(
            name="goal_fail",
            predicates=[idle, done],
            actions=[action],
            initial_state=frozenset([idle]),
            goal_state=frozenset([done]),
        )
        plan = Plan(actions=[action])
        validator = PlanValidator()
        result = validator.validate(plan, domain)
        assert not result.valid


class TestPlanToTaskDAG:
    def test_convert_plan_to_dag(self) -> None:
        from maref.recursive.formal_planner import plan_to_taskdag
        from maref.recursive.task_decomposer import TaskDAG

        domain = build_agent_task_domain()
        trust_verified = None
        for p in domain.predicates:
            if p.name == "trust_verified":
                trust_verified = p
                break
        assert trust_verified is not None
        domain.goal_state = frozenset([trust_verified])

        planner = ForwardChainingPlanner()
        plan = planner.plan(domain)
        assert plan is not None

        dag, _ = plan_to_taskdag(plan, domain)
        assert isinstance(dag, TaskDAG)
        assert dag.node_count == plan.step_count
        assert len(dag.edges) == plan.step_count - 1


class TestTaskDecomposerFormal:
    def test_decompose_formal_optimize(self) -> None:
        from maref.recursive.formal_planner import (
            ForwardChainingPlanner,
            build_agent_task_domain,
        )
        from maref.recursive.task_decomposer import TaskDecomposer

        domain = build_agent_task_domain()
        planner = ForwardChainingPlanner(max_depth=20)
        decomposer = TaskDecomposer(
            use_formal_planner=True,
            planner=planner,
            domain=domain,
        )
        dag = decomposer.decompose("optimize_system")
        assert dag.node_count >= 1

    def test_decompose_formal_fallback_unknown(self) -> None:
        from maref.recursive.formal_planner import (
            ForwardChainingPlanner,
            build_agent_task_domain,
        )
        from maref.recursive.task_decomposer import TaskDecomposer

        domain = build_agent_task_domain()
        planner = ForwardChainingPlanner(max_depth=20)
        decomposer = TaskDecomposer(
            use_formal_planner=True,
            planner=planner,
            domain=domain,
        )
        dag = decomposer.decompose("unknown_task")
        assert dag.root_task == "unknown_task"
        assert dag.node_count == 0

    def test_decompose_without_formal_planner(self) -> None:
        from maref.recursive.task_decomposer import TaskDecomposer

        decomposer = TaskDecomposer()
        dag = decomposer.decompose("optimize_system")
        assert dag.node_count == 4
        assert "observe_perf" in dag.nodes
