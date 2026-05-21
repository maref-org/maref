from __future__ import annotations

from maref.recursive.instance_cloner import (
    EVOLUTION_PATH_PARAMS,
    ClonedExperiencePool,
    ClonedKnowledgeGraph,
    CloneManifest,
    CloneStatus,
    EvolutionPath,
    MAREFInstanceCloner,
)


class TestEvolutionPaths:
    def test_all_paths_exist(self):
        assert len(EvolutionPath) == 5

    def test_path_params_complete(self):
        for path in EvolutionPath:
            params = EVOLUTION_PATH_PARAMS[path]
            assert "mutation_rate" in params
            assert "risk_tolerance" in params
            assert "innovation_bias" in params

    def test_aggressive_highest_mutation(self):
        aggressive = EVOLUTION_PATH_PARAMS[EvolutionPath.AGGRESSIVE]["mutation_rate"]
        conservative = EVOLUTION_PATH_PARAMS[EvolutionPath.CONSERVATIVE]["mutation_rate"]
        assert aggressive > conservative


class TestMAREFInstanceClonerInit:
    def test_default_init(self):
        cloner = MAREFInstanceCloner("parent_1")
        assert cloner.parent_id == "parent_1"
        assert cloner.generation == 0
        assert cloner.clone_count == 0

    def test_init_with_trust(self):
        cloner = MAREFInstanceCloner("parent_1", trust_baseline=0.9)
        assert cloner.clone_count == 0


class TestSnapshotCreation:
    def test_snapshot_knowledge_graph(self):
        cloner = MAREFInstanceCloner("parent_1")
        kg = cloner.snapshot_knowledge_graph()
        assert len(kg.nodes) > 0
        assert len(kg.relations) > 0

    def test_snapshot_experience_pool(self):
        cloner = MAREFInstanceCloner("parent_1")
        exp = cloner.snapshot_experience_pool()
        assert exp.total_entries > 0
        assert len(exp.entries) > 0

    def test_snapshot_audit_chain(self):
        cloner = MAREFInstanceCloner("parent_1")
        audit = cloner.snapshot_audit_chain()
        assert audit.total_events > 0
        assert len(audit.records) > 0


class TestClone:
    def test_single_clone_creates_manifest(self):
        cloner = MAREFInstanceCloner("parent_1")
        manifest = cloner.clone()
        assert manifest is not None
        assert isinstance(manifest, CloneManifest)
        assert manifest.status == CloneStatus.ACTIVE

    def test_clone_inherits_trust(self):
        cloner = MAREFInstanceCloner("parent_1", trust_baseline=0.9)
        manifest = cloner.clone()
        assert manifest is not None
        assert manifest.trust_baseline < 0.9
        assert manifest.trust_baseline > 0.0

    def test_clone_with_exploratory_path(self):
        cloner = MAREFInstanceCloner("parent_1")
        manifest = cloner.clone(evolution_path=EvolutionPath.EXPLORATORY)
        assert manifest is not None
        assert manifest.evolution_path == EvolutionPath.EXPLORATORY
        assert manifest.divergence_score > 0.0

    def test_clone_with_conservative_path(self):
        cloner = MAREFInstanceCloner("parent_1")
        manifest = cloner.clone(evolution_path=EvolutionPath.CONSERVATIVE)
        assert manifest is not None
        assert manifest.evolution_path == EvolutionPath.CONSERVATIVE
        assert manifest.divergence_score < 1.5

    def test_clone_with_specialization(self):
        cloner = MAREFInstanceCloner("parent_1")
        manifest = cloner.clone(specialization="network_healing")
        assert manifest is not None
        assert manifest.specialization == "network_healing"

    def test_clone_kg_has_mutations(self):
        cloner = MAREFInstanceCloner("parent_1")
        manifest = cloner.clone(evolution_path=EvolutionPath.EXPLORATORY)
        assert manifest is not None
        assert len(manifest.kg_snapshot.nodes) > 0

    def test_clone_has_experience(self):
        cloner = MAREFInstanceCloner("parent_1")
        manifest = cloner.clone()
        assert manifest is not None
        assert manifest.experience_snapshot.total_entries > 0

    def test_clone_has_audit(self):
        cloner = MAREFInstanceCloner("parent_1")
        manifest = cloner.clone()
        assert manifest is not None
        assert manifest.audit_snapshot.total_events > 0


class TestCloneMultiple:
    def test_clone_multiple_three(self):
        cloner = MAREFInstanceCloner("parent_1")
        paths = [EvolutionPath.EXPLORATORY, EvolutionPath.CONSERVATIVE, EvolutionPath.SPECIALIZED]
        manifests = cloner.clone_multiple(paths)
        assert len(manifests) == 3
        assert cloner.clone_count == 3

    def test_clone_multiple_different_paths(self):
        cloner = MAREFInstanceCloner("parent_1")
        paths = [EvolutionPath.AGGRESSIVE, EvolutionPath.DEFENSIVE]
        manifests = cloner.clone_multiple(paths)
        assert len(manifests) == 2
        assert manifests[0].evolution_path != manifests[1].evolution_path

    def test_differentiate_clones(self):
        cloner = MAREFInstanceCloner("parent_1")
        cloner.clone_multiple([
            EvolutionPath.EXPLORATORY, EvolutionPath.CONSERVATIVE, EvolutionPath.SPECIALIZED
        ])
        diff = cloner.differentiate_clones()
        assert len(diff) == 3
        paths = {d["path"] for d in diff.values()}
        assert "exploratory" in paths
        assert "conservative" in paths
        assert "specialized" in paths


class TestLineageTree:
    def test_lineage_tree_structure(self):
        cloner = MAREFInstanceCloner("parent_1")
        cloner.clone_multiple([EvolutionPath.EXPLORATORY, EvolutionPath.CONSERVATIVE])
        tree = cloner.get_lineage_tree()
        assert "parent_1" in tree
        assert len(tree["parent_1"]) == 2

    def test_clone_has_lineage(self):
        cloner = MAREFInstanceCloner("parent_1")
        manifest = cloner.clone()
        assert manifest is not None
        lineage = manifest.lineage
        assert lineage.parent_id == "parent_1"
        assert lineage.generation == 1

    def test_lineage_to_dict(self):
        cloner = MAREFInstanceCloner("parent_1")
        manifest = cloner.clone()
        assert manifest is not None
        d = manifest.lineage.to_dict()
        assert d["parent_id"] == "parent_1"
        assert d["generation"] == 1


class TestCloneHealth:
    def test_verify_clone_health(self):
        cloner = MAREFInstanceCloner("parent_1")
        manifest = cloner.clone()
        assert manifest is not None
        health = cloner.verify_clone_health(manifest.clone_id)
        assert health["exists"]
        assert health["status"] == "active"
        assert health["trust_baseline"] > 0.0
        assert health["kg_nodes"] > 0
        assert health["experience_entries"] > 0
        assert health["audit_records"] > 0

    def test_verify_nonexistent_clone(self):
        cloner = MAREFInstanceCloner("parent_1")
        health = cloner.verify_clone_health("nonexistent")
        assert not health["exists"]


class TestClonerLimits:
    def test_max_generations_limit(self):
        cloner = MAREFInstanceCloner("parent_1")
        for _ in range(MAREFInstanceCloner.MAX_GENERATIONS):
            cloner.clone()
        result = cloner.clone()
        assert result is None

    def test_min_clone_interval(self):
        cloner = MAREFInstanceCloner("parent_1")
        cloner.clone()
        result = cloner.clone()
        assert result is None

    def test_get_all_clones(self):
        cloner = MAREFInstanceCloner("parent_1")
        cloner.clone()
        cloner.clone()
        all_clones = cloner.get_all_clones()
        assert len(all_clones) > 0


class TestManifestSerialization:
    def test_manifest_to_dict(self):
        cloner = MAREFInstanceCloner("parent_1")
        manifest = cloner.clone()
        assert manifest is not None
        d = manifest.to_dict()
        assert "clone_id" in d
        assert "parent_id" in d
        assert "evolution_path" in d
        assert "trust_baseline" in d
        assert "lineage" in d
        assert "kg" in d
        assert "experience" in d
        assert "audit" in d

    def test_cloner_to_dict(self):
        cloner = MAREFInstanceCloner("parent_1")
        cloner.clone_multiple([EvolutionPath.EXPLORATORY, EvolutionPath.CONSERVATIVE])
        d = cloner.to_dict()
        assert d["parent_id"] == "parent_1"
        assert d["clone_count"] == 2
        assert "clones" in d
        assert "lineage_tree" in d

    def test_experience_pool_apply_specialization(self):
        pool = ClonedExperiencePool(
            entries=[{"data": "network healing pattern"}],
            total_entries=1,
        )
        result = pool.apply_specialization("network", {"innovation_bias": 0.3})
        assert result is not None

    def test_kg_apply_mutations_high_rate(self):
        kg = ClonedKnowledgeGraph(
            nodes=[{"id": "n1", "mutable": True}, {"id": "n2", "mutable": False}],
        )
        mutated = kg.apply_mutations({"mutation_rate": 0.5})
        assert len(mutated.nodes) == 2
