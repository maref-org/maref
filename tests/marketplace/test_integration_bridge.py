"""Integration tests: Skill Marketplace → Runtime end-to-end bridge."""

from maref.marketplace import (
    MarketplaceSkillLoader,
    SkillManifest,
    approve_and_execute,
    execute_skill,
)
from maref.marketplace.registry import SkillStatus
from maref.recursive.skill_executor import ExecutionStatus


class TestManifestAdapter:
    def test_to_maref_roundtrip(self):
        from maref.marketplace.adapter import ManifestAdapter

        original = SkillManifest(
            name="test-skill",
            version="1.0.0",
            description="A test skill",
            author="test-author",
            entrypoint="test_module.run",
            input_schema={"type": "object"},
            output_schema={"type": "string"},
            sandbox_config={"mode": "docker"},
        )
        maref = ManifestAdapter.to_maref(original)
        assert maref.meta.name == "test-skill"
        assert maref.meta.version == "1.0.0"
        assert maref.meta.author_did == "test-author"
        assert maref.behavior.get("entrypoint") == "test_module.run"
        assert maref.behavior.get("input_schema") == {"type": "object"}

        back = ManifestAdapter.to_manifest(maref)
        assert back.name == original.name
        assert back.version == original.version
        assert back.author == original.author
        assert back.entrypoint == original.entrypoint

    def test_to_maref_empty_fields(self):
        from maref.marketplace.adapter import ManifestAdapter

        manifest = SkillManifest(
            name="minimal", version="0.0.1", description="Minimal"
        )
        maref = ManifestAdapter.to_maref(manifest)
        assert maref.meta.name == "minimal"
        assert maref.meta.author_did is None
        assert maref.behavior.get("entrypoint") == "default"

    def test_maref_to_manifest(self):
        from maref.marketplace.adapter import ManifestAdapter
        from maref.recursive.skill_schema import (
            DegradationChain,
            HexagramTrigger,
            MarefSkill,
            MarefSkillMeta,
            SkillSource,
        )

        skill = MarefSkill(
            maref_skill="1.0",
            meta=MarefSkillMeta(
                name="code-reviewer",
                version="2.1.0",
                description="Reviews code",
                author_did="did:maref:alice",
            ),
            role_affinity={},
            hexagram_trigger=HexagramTrigger(),
            parameter_injection=None,
            hooks=[],
            context_activation=None,
            degradation_chain=DegradationChain(primary="default"),
            behavior={"entrypoint": "review.run", "sandbox": "gvisor"},
            source=SkillSource.BUILTIN,
        )
        manifest = ManifestAdapter.to_manifest(skill)
        assert manifest.name == "code-reviewer"
        assert manifest.version == "2.1.0"
        assert manifest.entrypoint == "review.run"
        assert manifest.author == "did:maref:alice"
        assert manifest.sandbox_config.get("mode") == "gvisor"


class TestMarketplaceSkillLoader:
    def test_register_and_lookup(self):
        loader = MarketplaceSkillLoader()
        manifest = SkillManifest(
            name="greeter", version="1.0.0", description="Greets user"
        )
        loader.register_manifest(manifest)
        loaded = loader.get_skill("greeter")
        assert loaded is not None
        assert loaded.meta.name == "greeter"
        assert loaded.meta.version == "1.0.0"

    def test_register_and_approve(self):
        loader = MarketplaceSkillLoader()
        manifest = SkillManifest(
            name="safe-fn",
            version="1.0.0",
            description="Safe function",
            entrypoint="safe.run",
        )
        loader.register_and_approve(manifest)
        assert loader.get_status(manifest.skill_id) == SkillStatus.APPROVED

    def test_approve_explicit(self):
        loader = MarketplaceSkillLoader()
        manifest = SkillManifest(
            name="explicit-approve",
            version="1.0.0",
            description="Needs explicit approval",
            entrypoint="ok.run",
        )
        loader.register_manifest(manifest)
        assert loader.get_status(manifest.skill_id) == SkillStatus.PENDING
        loader.approve(manifest.skill_id)
        assert loader.get_status(manifest.skill_id) == SkillStatus.APPROVED

    def test_search_approved_only(self):
        loader = MarketplaceSkillLoader()
        a = SkillManifest(name="alpha", version="1.0.0", description="Alpha skill")
        b = SkillManifest(
            name="beta",
            version="1.0.0",
            description="Beta skill",
            entrypoint="beta.run",
        )
        loader.register_and_approve(b)
        loader.register_manifest(a)
        results = loader.search(["beta"])
        assert len(results) == 1
        assert results[0].name == "beta"

    def test_load_from_yaml(self):
        import tempfile
        from pathlib import Path

        yaml_content = """
maref_skill: "1.0"
meta:
  name: "yaml-skill"
  version: "1.0.0"
  description: "Loaded from YAML"
behavior:
  entrypoint: "yaml.run"
  sandbox: "isolated"
"""
        with tempfile.NamedTemporaryFile(
            suffix=".yaml", mode="w", delete=False
        ) as f:
            f.write(yaml_content)
            tmp_path = f.name
        try:
            loader = MarketplaceSkillLoader()
            maref = loader.load_from_yaml(tmp_path)
            assert maref is not None
            assert maref.meta.name == "yaml-skill"
            manifest = loader.get_manifest("yaml-skill")
            assert manifest is not None
            assert manifest.entrypoint == "yaml.run"
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_list_approved(self):
        loader = MarketplaceSkillLoader()
        loader.register_and_approve(
            SkillManifest(name="approved-1", version="1.0.0", description="A")
        )
        loader.register_and_approve(
            SkillManifest(name="approved-2", version="1.0.0", description="B")
        )
        loader.register_manifest(
            SkillManifest(name="pending-1", version="1.0.0", description="C")
        )
        approved = loader.list_approved()
        names = {m.name for m in approved}
        assert names == {"approved-1", "approved-2"}

    def test_list_all(self):
        loader = MarketplaceSkillLoader()
        loader.register_manifest(
            SkillManifest(name="item-1", version="1.0.0", description="X")
        )
        loader.register_manifest(
            SkillManifest(name="item-2", version="1.0.0", description="Y")
        )
        assert len(loader.list_all()) == 2


class TestExecuteSkill:
    def test_execute_unregistered_fails(self):
        result = execute_skill("nonexistent-skill")
        assert result.status == ExecutionStatus.FAILED
        assert "not found" in (result.error or "")

    def test_execute_unapproved_fails(self):
        loader = MarketplaceSkillLoader()
        manifest = SkillManifest(
            name="not-approved",
            version="1.0.0",
            description="Pending skill",
            entrypoint="test.run",
        )
        loader.register_manifest(manifest)
        result = execute_skill(manifest.skill_id, loader=loader)
        assert result.status == ExecutionStatus.FAILED
        assert "must be approved" in (result.error or "")

    def test_execute_approved_skill(self):
        from maref.recursive.skill_executor import SkillExecutor

        def mock_handler(context):
            return {"greeting": f"Hello, {context.get('name', 'world')}!"}

        executor = SkillExecutor()
        executor.register_handler("default", mock_handler)

        loader = MarketplaceSkillLoader()
        manifest = SkillManifest(
            name="hello",
            version="1.0.0",
            description="Says hello",
            entrypoint="default",
        )
        loader.register_and_approve(manifest)
        result = execute_skill(
            manifest.skill_id,
            context={"name": "MAREF"},
            loader=loader,
            executor=executor,
        )
        assert result.status == ExecutionStatus.SUCCESS
        assert result.result.get("greeting") == "Hello, MAREF!"

    def test_approve_and_execute_shortcut(self):
        from maref.recursive.skill_executor import SkillExecutor

        def echo(context):
            return context

        executor = SkillExecutor()
        executor.register_handler("default", echo)

        manifest = SkillManifest(
            name="echo",
            version="1.0.0",
            description="Echoes input",
            entrypoint="default",
        )
        result = approve_and_execute(
            manifest, context={"msg": "hi"}, executor=executor
        )
        assert result.status == ExecutionStatus.SUCCESS
        assert result.result.get("msg") == "hi"

    def test_execute_with_approved_skill_via_loader(self):
        from maref.recursive.skill_executor import SkillExecutor

        def greet(context):
            return {"message": f"Hello {context.get('name', 'world')}"}

        executor = SkillExecutor()
        executor.register_handler("greeter", greet)

        loader = MarketplaceSkillLoader()
        manifest = SkillManifest(
            name="greeter-pro",
            version="2.0.0",
            description="Professional greeter",
            entrypoint="greeter",
        )
        loader.register_and_approve(manifest)
        result = execute_skill(
            manifest.skill_id,
            context={"name": "MAREF"},
            loader=loader,
            executor=executor,
        )
        assert result.status == ExecutionStatus.SUCCESS
        assert result.result.get("message") == "Hello MAREF"
