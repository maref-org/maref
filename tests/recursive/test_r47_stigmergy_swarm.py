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


class TestStigmergySwarmSigning:
    """P1-2: Pheromone Ed25519 signature tests."""

    def test_pheromone_sign_and_verify(self) -> None:
        from maref.crypto.ed25519_keys import Ed25519KeyPair
        keypair = Ed25519KeyPair.generate()

        swarm = StigmergySwarm()
        swarm.create_environment("env_sig")
        swarm.register_member("agent_signer")

        p = swarm.deposit_pheromone(
            "env_sig",
            "agent_signer",
            PheromoneType.TASK_READY,
            "secure_board",
            intensity=0.9,
            signer=keypair,
        )
        assert p is not None
        assert p.signature, "Expected signature"
        assert p.signer_fingerprint == keypair.fingerprint
        assert p.verify_signature(keypair.public_key_pem)

    def test_unsigned_pheromone_fails_verify(self) -> None:
        from maref.crypto.ed25519_keys import Ed25519KeyPair
        keypair = Ed25519KeyPair.generate()

        swarm = StigmergySwarm()
        swarm.create_environment("env_unsigned")
        swarm.register_member("agent_unsigned")

        p = swarm.deposit_pheromone(
            "env_unsigned",
            "agent_unsigned",
            PheromoneType.TASK_READY,
            "board",
        )
        assert p is not None
        assert p.signature == ""
        assert not p.verify_signature(keypair.public_key_pem)

    def test_signature_rejects_wrong_key(self) -> None:
        from maref.crypto.ed25519_keys import Ed25519KeyPair
        keypair = Ed25519KeyPair.generate()
        wrong_keypair = Ed25519KeyPair.generate()

        swarm = StigmergySwarm()
        swarm.create_environment("env_wrong")
        swarm.register_member("agent_signer")

        p = swarm.deposit_pheromone(
            "env_wrong",
            "agent_signer",
            PheromoneType.RECRUITMENT,
            "board",
            signer=keypair,
        )
        assert p is not None
        assert not p.verify_signature(wrong_keypair.public_key_pem)

    def test_signature_binds_fields(self) -> None:
        from maref.crypto.ed25519_keys import Ed25519KeyPair
        keypair = Ed25519KeyPair.generate()

        swarm = StigmergySwarm()
        swarm.create_environment("env_bind")
        swarm.register_member("agent_signer")

        p = swarm.deposit_pheromone(
            "env_bind",
            "agent_signer",
            PheromoneType.COMPLETION_MARKER,
            "result",
            intensity=0.7,
            signer=keypair,
        )
        assert p is not None

        # Tamper with the pheromone data — verify must fail
        p.intensity = 1.0
        assert not p.verify_signature(keypair.public_key_pem)
