from __future__ import annotations

import ast
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

from maref.recursive.unified_audit import UnifiedAuditStore

if TYPE_CHECKING:
    pass


class ChangeType(Enum):
    ADD_TEST = "add_test"
    EXTRACT_FUNCTION = "extract_function"
    REMOVE_UNUSED_IMPORT = "remove_unused_import"
    SPLIT_MODULE = "split_module"
    GENERAL_REFACTOR = "general_refactor"


@dataclass
class ArchitectureProposal:
    proposal_id: str
    timestamp: float
    current_arch: str
    proposed_arch: str
    rationale: str
    risk_assessment: str
    confidence: float
    coupling_metrics: dict[str, Any] = field(default_factory=dict)
    target_files: list[str] = field(default_factory=list)
    change_type: ChangeType = ChangeType.GENERAL_REFACTOR
    affected_symbols: list[str] = field(default_factory=list)
    estimated_new_lines: int = 0
    preconditions: list[str] = field(default_factory=list)


class SelfArchitect:
    def __init__(self, audit_store: UnifiedAuditStore) -> None:
        self._audit_store = audit_store
        self._proposals: list[ArchitectureProposal] = []
        self._arch_snapshot: dict[str, Any] = {}

    def snapshot_architecture(self, modules: dict[str, Any]) -> dict[str, Any]:
        snapshot = {
            "timestamp": time.time(),
            "module_count": len(modules),
            "modules": dict(modules),
        }
        self._arch_snapshot = snapshot
        return snapshot

    def analyze_bottlenecks(self) -> list[dict[str, Any]]:
        bottlenecks: list[dict[str, Any]] = []
        events = self._audit_store.query_by_event("healing")
        high_fail_modules: dict[str, int] = {}
        for e in events:
            mod = e.source_module
            high_fail_modules[mod] = high_fail_modules.get(mod, 0) + 1

        for mod, count in high_fail_modules.items():
            if count >= 3:
                bottlenecks.append(
                    {
                        "module": mod,
                        "heal_attempts": count,
                        "severity": "high" if count >= 5 else "medium",
                    }
                )
        return bottlenecks

    def analyze_low_coverage(
        self, source_dir: str = "src", threshold: float = 80.0
    ) -> list[dict[str, Any]]:
        import subprocess
        import sys

        low_modules: list[dict[str, Any]] = []
        try:
            result = subprocess.run(
                [sys.executable, "-m", "coverage", "report", "-m"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            for line in result.stdout.split("\n"):
                stripped = line.strip()
                if stripped and not stripped.startswith("-") and not stripped.startswith("Name"):
                    parts = stripped.split()
                    if len(parts) >= 4 and parts[-1].endswith("%"):
                        try:
                            pct = float(parts[-1].replace("%", ""))
                            file_path = parts[0]
                            if pct < threshold and file_path.endswith(".py"):
                                low_modules.append(
                                    {
                                        "file": file_path,
                                        "coverage_pct": pct,
                                        "statements": parts[1] if len(parts) > 1 else "?",
                                        "missing": parts[3] if len(parts) > 3 else "?",
                                    }
                                )
                        except ValueError:
                            continue
        except Exception:
            pass
        return low_modules

    def analyze_module_dependencies(
        self,
        source_dir: str = "src",
        ignore_dirs: tuple[str, ...] = ("__pycache__", ".venv", "venv"),
    ) -> dict[str, dict[str, Any]]:
        import_graph: dict[str, dict[str, Any]] = {}
        project_root = Path(source_dir)
        if not project_root.exists():
            return import_graph

        for py_file in project_root.rglob("*.py"):
            rel_path = str(
                py_file.relative_to(project_root.parent) if project_root != Path("src") else py_file
            )
            mod_name = rel_path.replace("/", ".").replace(".py", "")
            imports = self._extract_imports(py_file)
            import_graph[mod_name] = {
                "file": rel_path,
                "imports": imports,
                "import_count": len(imports),
            }

        return import_graph

    def _extract_imports(self, file_path: Path) -> list[str]:
        imports: list[str] = []
        try:
            tree = ast.parse(file_path.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.append(alias.name)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imports.append(node.module)
        except (SyntaxError, UnicodeDecodeError, OSError):
            pass
        return imports

    def detect_unused_imports(
        self,
        source_dir: str = "src",
    ) -> dict[str, list[str]]:
        unused_map: dict[str, list[str]] = {}
        project_root = Path(source_dir)
        if not project_root.exists():
            return unused_map

        for py_file in project_root.rglob("*.py"):
            if "__pycache__" in str(py_file):
                continue
            try:
                tree = ast.parse(py_file.read_text())
                imported_names: set[str] = set()
                import_nodes: list[tuple[str, str | None]] = []
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            name = alias.asname if alias.asname else alias.name.split(".")[-1]
                            imported_names.add(name)
                            import_nodes.append((alias.name, alias.asname))
                    elif isinstance(node, ast.ImportFrom):
                        for alias in node.names:
                            name = alias.asname if alias.asname else alias.name
                            imported_names.add(name)
                            import_nodes.append(
                                (
                                    f"{node.module}.{alias.name}" if node.module else alias.name,
                                    alias.asname,
                                )
                            )
                used_names: set[str] = set()
                for node in ast.walk(tree):
                    if isinstance(node, ast.Name):
                        used_names.add(node.id)
                file_unused = imported_names - used_names
                if file_unused:
                    rel = str(
                        py_file.relative_to(project_root.parent)
                        if project_root != Path("src")
                        else py_file
                    )
                    unused_map[rel] = sorted(file_unused)
            except (SyntaxError, UnicodeDecodeError, OSError):
                continue
        return unused_map

    def compute_coupling_metrics(
        self,
        import_graph: dict[str, dict[str, Any]],
    ) -> dict[str, dict[str, float]]:
        metrics: dict[str, dict[str, float]] = {}
        if not import_graph:
            return metrics

        all_modules = set(import_graph.keys())

        for mod_name, info in import_graph.items():
            internal_imports = [
                i
                for i in info["imports"]
                if i in all_modules or any(i.startswith(m) for m in all_modules)
            ]
            fan_out = len(internal_imports)

            fan_in = sum(
                1
                for other_mod, other_info in import_graph.items()
                if other_mod != mod_name
                and any(i == mod_name or i.startswith(mod_name) for i in other_info["imports"])
            )

            total = fan_in + fan_out
            instability = fan_out / max(total, 1)

            metrics[mod_name] = {
                "fan_in": float(fan_in),
                "fan_out": float(fan_out),
                "instability": instability,
            }

        return metrics

    def propose_test_addition(
        self, low_coverage: list[dict[str, Any]]
    ) -> list[ArchitectureProposal]:
        proposals: list[ArchitectureProposal] = []
        for module in low_coverage[:5]:
            file_path = module.get("file", "")
            if not file_path:
                continue
            test_file = file_path.replace("src/", "tests/").replace(".py", "_test.py")
            proposals.append(
                ArchitectureProposal(
                    proposal_id=f"add_test_{int(time.time())}_{hash(file_path) % 10000}",
                    timestamp=time.time(),
                    current_arch=str(self._arch_snapshot.get("module_count", 0)),
                    proposed_arch=f"add_tests_{Path(file_path).stem}",
                    rationale=f"Module {file_path} at {module.get('coverage_pct', 0)}% coverage. Add targeted tests.",
                    risk_assessment="low",
                    confidence=0.85,
                    target_files=[test_file],
                    change_type=ChangeType.ADD_TEST,
                    affected_symbols=[],
                    estimated_new_lines=30,
                    preconditions=[f"coverage_pct < 80 for {file_path}"],
                )
            )
        return proposals

    def propose_import_cleanup(
        self, unused_imports: dict[str, list[str]]
    ) -> list[ArchitectureProposal]:
        proposals: list[ArchitectureProposal] = []
        for file_path, unused in list(unused_imports.items())[:5]:
            proposals.append(
                ArchitectureProposal(
                    proposal_id=f"cleanup_imports_{int(time.time())}_{hash(file_path) % 10000}",
                    timestamp=time.time(),
                    current_arch=str(self._arch_snapshot.get("module_count", 0)),
                    proposed_arch=f"cleanup_imports_{Path(file_path).stem}",
                    rationale=f"Remove {len(unused)} unused imports from {file_path}: {', '.join(unused[:5])}",
                    risk_assessment="low",
                    confidence=0.95,
                    target_files=[file_path],
                    change_type=ChangeType.REMOVE_UNUSED_IMPORT,
                    affected_symbols=list(unused),
                    estimated_new_lines=-len(unused),
                    preconditions=[f"unused imports verified by AST for {file_path}"],
                )
            )
        return proposals

    def propose_redesign(self) -> ArchitectureProposal:
        bottlenecks = self.analyze_bottlenecks()
        bottleneck_count = len(bottlenecks)

        coupling_metrics: dict[str, Any] = {}
        module_count = self._arch_snapshot.get("module_count", 0)
        proposed = str(module_count)

        if bottleneck_count == 0:
            rationale = "No significant bottlenecks detected. Architecture is healthy."
            risk = "low"
            confidence = 0.95
        elif bottleneck_count <= 2:
            mod_names = [b["module"] for b in bottlenecks]
            rationale = (
                f"Minor bottlenecks in: {', '.join(mod_names)}. Recommend targeted refactoring."
            )
            risk = "medium"
            confidence = 0.75
            proposed = f"refactor_{'_'.join(mod_names)}"
        else:
            mod_names = [b["module"] for b in bottlenecks]
            rationale = f"Significant bottlenecks in: {', '.join(mod_names)}. Recommend architectural redesign."
            risk = "high"
            confidence = 0.55
            proposed = f"redesign_{len(mod_names)}_modules"

        try:
            import_graph = self.analyze_module_dependencies()
            coupling_metrics = self.compute_coupling_metrics(import_graph)
            high_coupling = {
                m: v for m, v in coupling_metrics.items() if v.get("instability", 0) > 0.8
            }
            if high_coupling and bottleneck_count == 0:
                rationale += f" High coupling detected in {len(high_coupling)} modules."
                risk = "medium"
                confidence = max(confidence - 0.1, 0.5)
        except Exception:
            pass

        proposal = ArchitectureProposal(
            proposal_id=f"arch_proposal_{int(time.time())}",
            timestamp=time.time(),
            current_arch=str(module_count),
            proposed_arch=proposed,
            rationale=rationale,
            risk_assessment=risk,
            confidence=confidence,
            coupling_metrics=coupling_metrics,
            change_type=ChangeType.GENERAL_REFACTOR,
        )
        self._proposals.append(proposal)
        return proposal

    def propose_all(self) -> list[ArchitectureProposal]:
        all_proposals: list[ArchitectureProposal] = []

        high_level = self.propose_redesign()
        all_proposals.append(high_level)

        try:
            unused = self.detect_unused_imports()
            if unused:
                all_proposals.extend(self.propose_import_cleanup(unused))
        except Exception:
            pass

        try:
            low_cov = self.analyze_low_coverage()
            if low_cov:
                all_proposals.extend(self.propose_test_addition(low_cov))
        except Exception:
            pass

        return all_proposals

    def validate_proposal(self, proposal: ArchitectureProposal) -> bool:
        if proposal.confidence < 0.5:
            return False
        return not (proposal.risk_assessment == "high" and proposal.confidence < 0.7)

    def audit_all_decisions(self) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for layer in ["inner", "outer", "meta", "evolution"]:
            records = self._audit_store.query_by_layer(layer)
            if records:
                results.append(
                    {
                        "layer": layer,
                        "decision_count": len(records),
                        "success_rate": sum(1 for r in records if r.outcome == "success")
                        / max(len(records), 1),
                    }
                )
        return results

    def to_llm_plan(self, proposal: ArchitectureProposal) -> dict[str, Any]:
        return {
            "proposal_id": proposal.proposal_id,
            "change_type": proposal.change_type.value
            if hasattr(proposal.change_type, "value")
            else str(proposal.change_type),
            "rationale": proposal.rationale,
            "target_files": list(proposal.target_files),
            "affected_symbols": list(proposal.affected_symbols),
            "current_structure": self._extract_ast_summary(proposal.target_files),
        }

    def _extract_ast_summary(self, file_paths: list[str]) -> list[dict[str, Any]]:
        summaries: list[dict[str, Any]] = []
        for fp in file_paths:
            path = Path(fp)
            if not path.exists():
                continue
            try:
                tree = ast.parse(path.read_text())
                classes = [n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
                functions = [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
                imports = [
                    (n.names[0].name if isinstance(n, ast.Import) else n.module)
                    for n in ast.walk(tree)
                    if isinstance(n, (ast.Import, ast.ImportFrom))
                ][:30]
                summaries.append(
                    {
                        "file_path": fp,
                        "classes": classes,
                        "functions": functions,
                        "imports": imports,
                        "line_count": len(tree.body),
                    }
                )
            except (SyntaxError, OSError):
                continue
        return summaries

    @property
    def proposals(self) -> list[ArchitectureProposal]:
        return list(self._proposals)
