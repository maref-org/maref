from __future__ import annotations

import ast
import os
from dataclasses import dataclass, field


@dataclass
class CodeNode:
    name: str
    node_type: str
    parent: str = ""
    file_path: str = ""


@dataclass
class ModuleHierarchy:
    root_path: str
    modules: list[CodeNode] = field(default_factory=list)
    classes: list[CodeNode] = field(default_factory=list)
    functions: list[CodeNode] = field(default_factory=list)
    imports: list[tuple[str, str]] = field(default_factory=list)

    @property
    def total_nodes(self) -> int:
        return len(self.modules) + len(self.classes) + len(self.functions)


class CodeParser:
    def extract_module_hierarchy(self, root_path: str) -> ModuleHierarchy:
        hierarchy = ModuleHierarchy(root_path=root_path)

        for dirpath, _dirnames, filenames in os.walk(root_path):
            for fname in filenames:
                if not fname.endswith(".py"):
                    continue
                full_path = os.path.join(dirpath, fname)
                rel_path = os.path.relpath(full_path, root_path)
                module_name = rel_path.replace("/", ".").replace(".py", "")

                if module_name.startswith("__"):
                    continue

                hierarchy.modules.append(CodeNode(
                    name=module_name,
                    node_type="module",
                    file_path=rel_path,
                ))

                try:
                    with open(full_path, encoding="utf-8") as f:
                        tree = ast.parse(f.read())
                except (SyntaxError, UnicodeDecodeError):
                    continue

                self._extract_from_ast(tree, module_name, hierarchy)

        return hierarchy

    def _extract_from_ast(self, tree: ast.Module, module_name: str,
                           hierarchy: ModuleHierarchy) -> None:
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                hierarchy.classes.append(CodeNode(
                    name=f"{module_name}.{node.name}",
                    node_type="class",
                    parent=module_name,
                ))
            elif isinstance(node, ast.FunctionDef) and not node.name.startswith("_"):
                parent = module_name
                hierarchy.functions.append(CodeNode(
                    name=f"{module_name}.{node.name}",
                    node_type="function",
                    parent=parent,
                ))
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    hierarchy.imports.append((module_name, alias.name))
            elif isinstance(node, ast.ImportFrom) and node.module:
                    hierarchy.imports.append((module_name, node.module))
