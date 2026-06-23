from __future__ import annotations

from pathlib import Path

from maref.evolution.evo_genotype import AgentGenotype, GenotypePool
from maref.evolution.evo_state import EvoStateManager


def test_evo_state_manager_writes_required_snapshot_files(tmp_path: Path) -> None:
    manager = EvoStateManager(base_dir=tmp_path)
    snapshot = manager.start_cycle(1)
    manager.write_snapshot(
        cycle=1,
        gene_pool=[{"agent_id": "a1", "fitness": 0.8}],
        ruins_pool=[{"agent_id": "a0", "death_reason": "pytest_failure"}],
        market_logs=[{"tx": "t1", "tokens": 10}],
        metrics_timeseries=[{"round": 1, "fnr": 0.02}],
    )

    assert (snapshot / "gene_pool.yaml").exists()
    assert (snapshot / "ruins_pool.yaml").exists()
    assert (snapshot / "market_logs.yaml").exists()
    assert (snapshot / "death_records.yaml").exists()
    assert (snapshot / "pheromone_logs.yaml").exists()
    assert (snapshot / "system_snapshot.yaml").exists()
    assert (snapshot / "metrics_timeseries.yaml").exists()


def test_evo_state_manager_loads_snapshot(tmp_path: Path) -> None:
    manager = EvoStateManager(base_dir=tmp_path)
    manager.start_cycle(2)
    manager.write_snapshot(cycle=2, gene_pool=[{"agent_id": "a2"}])

    loaded = manager.load_snapshot(2)

    assert loaded["gene_pool"] == [{"agent_id": "a2"}]


def test_genotype_pool_round_trips_agents() -> None:
    pool = GenotypePool()
    genotype = AgentGenotype(agent_id="a1", traits={"risk": 0.2}, fitness=0.8)
    pool.add(genotype)

    assert pool.get("a1") == genotype
    assert pool.all()[0].to_dict()["agent_id"] == "a1"
