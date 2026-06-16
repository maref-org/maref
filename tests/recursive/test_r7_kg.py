from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from maref.recursive.code_parser import CodeParser
from maref.recursive.self_knowledge import ArchHypothesis, SelfKnowledge


class TestCodeParser:
    def test_extract_python_module(self) -> None:
        parser = CodeParser()
        with tempfile.TemporaryDirectory() as tmp:
            src_dir = Path(tmp) / "src" / "mypkg"
            src_dir.mkdir(parents=True)
            (src_dir / "__init__.py").write_text("")
            (src_dir / "core.py").write_text(
                "class Foo:\n    def bar(self):\n        pass\n\ndef helper():\n    pass\n"
            )
            hierarchy = parser.extract_module_hierarchy(str(Path(tmp) / "src"))
            modules = [n.name for n in hierarchy.modules if "mypkg" in n.name]
            assert len(modules) >= 1
            class_names = [n.name for n in hierarchy.classes]
            assert any("Foo" in c for c in class_names)
            func_names = [n.name for n in hierarchy.functions]
            assert any("helper" in f for f in func_names)

    def test_extract_imports(self) -> None:
        parser = CodeParser()
        with tempfile.TemporaryDirectory() as tmp:
            src_dir = Path(tmp) / "src" / "mypkg"
            src_dir.mkdir(parents=True)
            (src_dir / "__init__.py").write_text("")
            (src_dir / "main.py").write_text("import os\nfrom sys import path\n")
            hierarchy = parser.extract_module_hierarchy(str(Path(tmp) / "src"))
            assert ("mypkg.main", "os") in hierarchy.imports
            assert ("mypkg.main", "sys") in hierarchy.imports

    def test_empty_directory(self) -> None:
        parser = CodeParser()
        with tempfile.TemporaryDirectory() as tmp:
            hierarchy = parser.extract_module_hierarchy(tmp)
            assert hierarchy.total_nodes >= 0

    def test_module_hierarchy_structure(self) -> None:
        parser = CodeParser()
        with tempfile.TemporaryDirectory() as tmp:
            src_dir = Path(tmp) / "pkg"
            src_dir.mkdir(parents=True)
            (src_dir / "__init__.py").write_text("")
            (src_dir / "mod.py").write_text("class A:\n    pass\nclass B:\n    pass\n")
            hierarchy = parser.extract_module_hierarchy(str(tmp))
            assert hierarchy.total_nodes >= 3
            assert any("mod" in n.name for n in hierarchy.modules)


class TestSelfKnowledge:
    @pytest.fixture
    def sk(self) -> SelfKnowledge:
        return SelfKnowledge()

    def test_extract_arch_kg_builds_nodes(self, sk: SelfKnowledge) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src_dir = Path(tmp) / "pkg"
            src_dir.mkdir(parents=True)
            (src_dir / "__init__.py").write_text("")
            (src_dir / "a.py").write_text("class X:\n    def f(self):\n        pass\n")
            (src_dir / "b.py").write_text("import pkg.a\n")
            sk.extract_arch_kg(str(tmp))
            assert sk.node_count() > 0
            assert "module" in sk.node_types()
            assert "precedes" in sk.relation_types()

    def test_extract_test_coverage_relations(self, sk: SelfKnowledge) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src_dir = Path(tmp) / "src" / "pkg"
            src_dir.mkdir(parents=True)
            (src_dir / "__init__.py").write_text("")
            (src_dir / "mod.py").write_text("def target_function():\n    pass\n")
            sk.extract_arch_kg(str(Path(tmp) / "src"))

            test_dir = Path(tmp) / "tests"
            test_dir.mkdir(parents=True)
            (test_dir / "__init__.py").write_text("")
            (test_dir / "test_pkg_mod.py").write_text("def test_target():\n    pass\n")
            test_count = sk.extract_test_coverage_relations(str(test_dir), "")
            assert test_count >= 1

    def test_arch_hypothesis_cycle(self, sk: SelfKnowledge) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src_dir = Path(tmp) / "pkg"
            src_dir.mkdir(parents=True)
            (src_dir / "__init__.py").write_text("")
            (src_dir / "hub.py").write_text("class Hub:\n    pass\n")
            for name in ["c1", "c2", "c3", "c4"]:
                (src_dir / f"{name}.py").write_text(
                    f"import pkg.hub\nclass {name.upper()}:\n    pass\n"
                )
            sk.extract_arch_kg(str(tmp))
            hypotheses = sk.arch_hypothesis_cycle()
            assert len(hypotheses) >= 1
            for h in hypotheses:
                assert isinstance(h, ArchHypothesis)
                assert h.hypothesis_id != ""
                assert h.description != ""

    def test_query_coverage_gaps(self, sk: SelfKnowledge) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src_dir = Path(tmp) / "src" / "pkg"
            src_dir.mkdir(parents=True)
            (src_dir / "__init__.py").write_text("")
            (src_dir / "untested.py").write_text("def f():\n    pass\n")
            sk.extract_arch_kg(str(Path(tmp) / "src"))

            gaps = sk.query_coverage_gaps()
            assert "pkg.untested" in gaps

    def test_node_count_tracks_changes(self, sk: SelfKnowledge) -> None:
        initial = sk.node_count()
        with tempfile.TemporaryDirectory() as tmp:
            src_dir = Path(tmp) / "pkg"
            src_dir.mkdir(parents=True)
            (src_dir / "__init__.py").write_text("")
            (src_dir / "x.py").write_text("class Z:\n    pass\n")
            sk.extract_arch_kg(str(tmp))
        assert sk.node_count() > initial

    def test_node_types_return_breakdown(self, sk: SelfKnowledge) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src_dir = Path(tmp) / "pkg"
            src_dir.mkdir(parents=True)
            (src_dir / "__init__.py").write_text("")
            (src_dir / "x.py").write_text("class A:\n    def f(self):\n        pass\n")
            sk.extract_arch_kg(str(tmp))
        types = sk.node_types()
        assert "module" in types
        assert "class" in types
        assert "function" in types

    def test_relation_types_non_empty(self, sk: SelfKnowledge) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src_dir = Path(tmp) / "pkg"
            src_dir.mkdir(parents=True)
            (src_dir / "__init__.py").write_text("")
            (src_dir / "a.py").write_text("class X:\n    pass\n")
            (src_dir / "b.py").write_text("import pkg.a\n")
            sk.extract_arch_kg(str(tmp))
        assert len(sk.relation_types()) >= 1
