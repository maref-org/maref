"""Tests for code_parser.py — module hierarchy extraction, AST parsing."""
from __future__ import annotations

import os
import tempfile

import pytest

from maref.recursive.code_parser import CodeNode, CodeParser, ModuleHierarchy


class TestModuleHierarchy:
    def test_default_construction(self):
        mh = ModuleHierarchy(root_path="/tmp")
        assert mh.modules == []
        assert mh.classes == []
        assert mh.functions == []
        assert mh.imports == []
        assert mh.total_nodes == 0

    def test_total_nodes(self):
        mh = ModuleHierarchy(
            root_path="/tmp",
            modules=[CodeNode("m", "module")],
            classes=[CodeNode("c", "class")],
        )
        assert mh.total_nodes == 2


class TestCodeParser:
    def test_extract_empty_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            parser = CodeParser()
            hierarchy = parser.extract_module_hierarchy(tmpdir)
            assert hierarchy.total_nodes == 0

    def test_extract_single_module(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mod_dir = os.path.join(tmpdir, "mymod")
            os.makedirs(mod_dir)
            with open(os.path.join(mod_dir, "utils.py"), "w") as f:
                f.write("def helper(): pass\n")
            parser = CodeParser()
            hierarchy = parser.extract_module_hierarchy(tmpdir)
            assert len(hierarchy.modules) == 1
            assert hierarchy.modules[0].name == "mymod.utils"
            assert hierarchy.modules[0].node_type == "module"

    def test_extract_class_and_function(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "example.py"), "w") as f:
                f.write("class MyClass:\n    def method(self): pass\n")
            parser = CodeParser()
            hierarchy = parser.extract_module_hierarchy(tmpdir)
            assert len(hierarchy.classes) == 1
            assert "MyClass" in hierarchy.classes[0].name
            assert hierarchy.classes[0].node_type == "class"

    def test_extract_imports(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "main.py"), "w") as f:
                f.write("import os\nfrom typing import List\n")
            parser = CodeParser()
            hierarchy = parser.extract_module_hierarchy(tmpdir)
            assert len(hierarchy.imports) == 2

    def test_extract_private_functions_skipped(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "mod.py"), "w") as f:
                f.write("def _private(): pass\ndef public(): pass\n")
            parser = CodeParser()
            hierarchy = parser.extract_module_hierarchy(tmpdir)
            names = [fn.name for fn in hierarchy.functions]
            assert any("public" in n for n in names)
            assert not any("_private" in n for n in names)

    def test_extract_non_python_files_skipped(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "readme.md"), "w") as f:
                f.write("# Readme")
            parser = CodeParser()
            hierarchy = parser.extract_module_hierarchy(tmpdir)
            assert hierarchy.total_nodes == 0

    def test_extract_syntax_error_skipped(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "broken.py"), "w") as f:
                f.write("def broken( pass\n")
            parser = CodeParser()
            hierarchy = parser.extract_module_hierarchy(tmpdir)
            assert len(hierarchy.modules) == 1
            assert hierarchy.total_nodes == 1

    def test_extract_init_files_skipped(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "__init__.py"), "w") as f:
                f.write("# package\n")
            parser = CodeParser()
            hierarchy = parser.extract_module_hierarchy(tmpdir)
            assert len(hierarchy.modules) == 0
