from __future__ import annotations

from maref.recursive.stigmergy_swarm import (
    EmergenceResult,
    PheromoneType,
    StigmergySwarm,
)


class TestStigmergySwarm:
    def setup_method(self) -> None:
        self.swarm = StigmergySwarm()

    def test_create_environment(self) -> None:
        env = self.swarm.create_environment("env_1", capacity=20)
        assert env.env_id == "env_1"

    def test_register_member(self) -> None:
        member = self.swarm.register_member("agent_1")
        assert member.agent_id == "agent_1"
        assert member.role == "worker"

    def test_deposit_pheromone(self) -> None:
        self.swarm.create_environment("env_1")
        self.swarm.register_member("agent_1")
        p = self.swarm.deposit_pheromone(
            "env_1",
            "agent_1",
            PheromoneType.TASK_READY,
            "board",
            intensity=1.0,
        )
        assert p is not None
        assert p.pheromone_type == PheromoneType.TASK_READY

    def test_deposit_bad_env(self) -> None:
        self.swarm.register_member("agent_1")
        assert (
            self.swarm.deposit_pheromone(
                "nonexistent",
                "agent_1",
                PheromoneType.TASK_READY,
                "x",
            )
            is None
        )

    def test_sense_pheromones(self) -> None:
        self.swarm.create_environment("env_1")
        self.swarm.register_member("a1")
        self.swarm.register_member("a2")
        self.swarm.deposit_pheromone("env_1", "a1", PheromoneType.TASK_READY, "loc1")
        sensed = self.swarm.sense_pheromones("env_1", "a2")
        assert len(sensed) >= 1

    def test_add_task(self) -> None:
        self.swarm.create_environment("env_1")
        assert self.swarm.add_task("env_1", "task_1")

    def test_assign_task(self) -> None:
        self.swarm.create_environment("env_1")
        self.swarm.register_member("worker_1")
        self.swarm.add_task("env_1", "task_1")
        assert self.swarm.assign_task("env_1", "task_1", "worker_1")

    def test_detect_emergence(self) -> None:
        self.swarm.create_environment("env_1")
        self.swarm.register_member("a1")
        self.swarm.register_member("a2")
        result = self.swarm.detect_emergence("env_1")
        assert isinstance(result, EmergenceResult)

    def test_run_swarm_cycle(self) -> None:
        tasks = ["t1", "t2", "t3"]
        agents = ["a1", "a2", "a3"]
        result = self.swarm.run_swarm_cycle("colony_1", tasks, agents)
        assert result.detected
        assert result.coordination_success

    def test_register_multiple(self) -> None:
        members = self.swarm.register_multiple(25, prefix="bee")
        assert len(members) == 25
        assert self.swarm.member_count == 25

    def test_get_statistics(self) -> None:
        self.swarm.register_member("a1")
        stats = self.swarm.get_statistics()
        assert stats["total_members"] == 1

    def test_pheromone_decay(self) -> None:
        self.swarm.create_environment("env_1")
        self.swarm.register_member("a1")
        p = self.swarm.deposit_pheromone(
            "env_1",
            "a1",
            PheromoneType.TASK_READY,
            "loc",
            intensity=1.0,
        )
        assert p is not None
        assert p.current_intensity <= 1.0
