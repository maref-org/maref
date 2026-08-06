from __future__ import annotations

import ast
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def _row_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row}


_EXCLUDED_DIRS = frozenset({
    ".git", "__pycache__", "node_modules", ".venv", "venv",
    ".codedepth", ".claude", ".mypy_cache", ".pytest_cache",
    ".egg-info", "dist", "build", ".tox",
})


@dataclass
class SymbolInfo:
    name: str
    kind: str
    file_path: str
    lineno: int
    end_lineno: int
    parent_name: str
    signature: str


@dataclass
class CallEdge:
    caller_name: str
    caller_file: str
    caller_lineno: int
    callee_name: str


class CodeIndexer:
    """Build + 查询 Python 代码的 SQLite 索引。

    用法:
        idx = CodeIndexer("/path/to/repo")
        idx.build()                    # 全量索引
        idx.search_symbols("readline") # 搜索符号
        idx.get_file_outline("path")   # 文件大纲
        idx.close()
    """

    SCHEMA = """
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            path TEXT UNIQUE NOT NULL,
            last_modified REAL NOT NULL,
            size INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS symbols (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            kind TEXT NOT NULL,
            lineno INTEGER NOT NULL,
            end_lineno INTEGER,
            parent_name TEXT DEFAULT '',
            signature TEXT DEFAULT '',
            FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS call_edges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            caller_file_id INTEGER NOT NULL,
            caller_name TEXT NOT NULL,
            caller_lineno INTEGER NOT NULL,
            callee_name TEXT NOT NULL,
            FOREIGN KEY (caller_file_id) REFERENCES files(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_sym_name ON symbols(name);
        CREATE INDEX IF NOT EXISTS idx_sym_kind ON symbols(kind);
        CREATE INDEX IF NOT EXISTS idx_sym_file ON symbols(file_id);
        CREATE INDEX IF NOT EXISTS idx_cc_caller ON call_edges(caller_name);
        CREATE INDEX IF NOT EXISTS idx_cc_callee ON call_edges(callee_name);
    """

    def __init__(self, repo_path: str | None = None) -> None:
        self._repo = Path(repo_path or os.getcwd()).resolve()
        self._db = self._repo / ".codedepth" / "index.db"
        self._conn: sqlite3.Connection | None = None

    # ── properties ──────────────────────────────────────────

    @property
    def repo_path(self) -> Path:
        return self._repo

    @property
    def is_built(self) -> bool:
        return self._db.is_file()

    # ── connection ──────────────────────────────────────────

    def _db_conn(self) -> sqlite3.Connection:
        if self._conn is not None:
            return self._conn
        self._db.parent.mkdir(parents=True, exist_ok=True)
        c = sqlite3.connect(str(self._db))
        c.execute("PRAGMA journal_mode=WAL")
        c.row_factory = sqlite3.Row
        c.executescript(self.SCHEMA)
        self._conn = c
        return c

    def _query_conn(self) -> sqlite3.Connection:
        if self._conn is not None:
            return self._conn
        if not self._db.is_file():
            raise RuntimeError(f"No index at {self._db} — call build() first")
        c = sqlite3.connect(str(self._db))
        c.row_factory = sqlite3.Row
        self._conn = c
        return c

    # ── build index ─────────────────────────────────────────

    def build(self) -> dict[str, Any]:
        """遍历仓库，解析所有 .py 文件，构建索引。返回统计。"""
        c = self._db_conn()
        c.execute("DELETE FROM call_edges")
        c.execute("DELETE FROM symbols")
        c.execute("DELETE FROM files")

        files_total = 0
        sym_total = 0
        call_total = 0
        errors: list[str] = []

        py_files = sorted(self._repo.rglob("*.py"))
        py_files = [f for f in py_files if not any(
            p in f.parts for p in _EXCLUDED_DIRS
        )]

        for fp in py_files:
            rel = str(fp.relative_to(self._repo))
            try:
                stat = fp.stat()
                with open(fp, encoding="utf-8") as fh:
                    source = fh.read()
                tree = ast.parse(source)
            except (SyntaxError, UnicodeDecodeError, OSError) as e:
                errors.append(f"{rel}: {e}")
                continue

            cur = c.execute(
                "INSERT INTO files (path, last_modified, size) VALUES (?, ?, ?)",
                (rel, stat.st_mtime, stat.st_size),
            )
            fid = cur.lastrowid
            files_total += 1

            syms = self._extract_symbols(tree, rel)
            for s in syms:
                c.execute(
                    "INSERT INTO symbols (file_id, name, kind, lineno, end_lineno, parent_name, signature) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (fid, s.name, s.kind, s.lineno, s.end_lineno, s.parent_name, s.signature),
                )
                sym_total += 1

            calls = self._extract_calls(tree, rel)
            for cl in calls:
                c.execute(
                    "INSERT INTO call_edges (caller_file_id, caller_name, caller_lineno, callee_name) "
                    "VALUES (?, ?, ?, ?)",
                    (fid, cl.caller_name, cl.caller_lineno, cl.callee_name),
                )
                call_total += 1

        c.commit()
        return {
            "files": files_total, "symbols": sym_total,
            "call_edges": call_total, "errors": len(errors),
        }

    # ── AST extraction ──────────────────────────────────────

    def _extract_symbols(self, tree: ast.AST, rel_path: str) -> list[SymbolInfo]:
        result: list[SymbolInfo] = []
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.ClassDef):
                bases = self._format_bases(node)
                result.append(SymbolInfo(
                    name=node.name, kind="class", file_path=rel_path,
                    lineno=node.lineno, end_lineno=node.end_lineno or node.lineno,
                    parent_name="", signature=f"class {node.name}({bases})" if bases else f"class {node.name}",
                ))
                for child in ast.iter_child_nodes(node):
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        result.append(self._make_method(child, node.name, rel_path))
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                result.append(self._make_function(node, rel_path))
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    as_part = f" as {alias.asname}" if alias.asname else ""
                    result.append(SymbolInfo(
                        name=alias.name, kind="import", file_path=rel_path,
                        lineno=node.lineno, end_lineno=node.lineno,
                        parent_name="", signature=f"import {alias.name}{as_part}",
                    ))
            elif isinstance(node, ast.ImportFrom) and node.module:
                for alias in node.names:
                    as_part = f" as {alias.asname}" if alias.asname else ""
                    full = f"{node.module}.{alias.name}"
                    result.append(SymbolInfo(
                        name=full, kind="import", file_path=rel_path,
                        lineno=node.lineno, end_lineno=node.lineno,
                        parent_name=node.module,
                        signature=f"from {node.module} import {alias.name}{as_part}",
                    ))
        return result

    def _make_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef, rel_path: str) -> SymbolInfo:
        args = ", ".join(a.arg for a in node.args.args[:6])
        if len(node.args.args) > 6:
            args += "..."
        return SymbolInfo(
            name=node.name, kind="function", file_path=rel_path,
            lineno=node.lineno, end_lineno=node.end_lineno or node.lineno,
            parent_name="", signature=f"def {node.name}({args})",
        )

    def _make_method(self, node: ast.FunctionDef | ast.AsyncFunctionDef, class_name: str, rel_path: str) -> SymbolInfo:
        args = [a.arg for a in node.args.args if a.arg != "self"]
        arg_str = ", ".join(args[:6])
        if len(args) > 6:
            arg_str += "..."
        return SymbolInfo(
            name=node.name, kind="method", file_path=rel_path,
            lineno=node.lineno, end_lineno=node.end_lineno or node.lineno,
            parent_name=class_name, signature=f"def {node.name}({arg_str})",
        )

    @staticmethod
    def _format_bases(node: ast.ClassDef) -> str:
        bases = []
        for b in node.bases:
            if isinstance(b, ast.Name):
                bases.append(b.id)
            elif isinstance(b, ast.Attribute):
                bases.append(b.attr)
        return ", ".join(bases)

    def _extract_calls(self, tree: ast.AST, rel_path: str) -> list[CallEdge]:
        calls: list[CallEdge] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            callee: str | None = None
            if isinstance(node.func, ast.Name):
                callee = node.func.id
            elif isinstance(node.func, ast.Attribute):
                callee = node.func.attr
            if callee and not callee.startswith("_"):
                caller = self._find_enclosing_func(tree, node)
                if caller:
                    calls.append(CallEdge(caller, rel_path, node.lineno, callee))
        return calls

    @staticmethod
    def _find_enclosing_func(tree: ast.AST, target: ast.AST) -> str | None:
        """找到包含 target 的最近（最内层）函数。"""
        enclosing = None
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for child in ast.walk(node):
                    if child is target:
                        enclosing = node
                        break  # 继续找更内层的
        return enclosing.name if enclosing else None

    # ── query API ───────────────────────────────────────────

    def search_symbols(self, query: str, kind: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        c = self._query_conn()
        pat = f"%{query}%"
        sql = ("SELECT s.name, s.kind, f.path AS file_path, s.lineno, "
               "s.parent_name, s.signature FROM symbols s JOIN files f ON s.file_id = f.id "
               "WHERE s.name LIKE ?")
        params: list[Any] = [pat]
        if kind:
            sql += " AND s.kind = ?"
            params.append(kind)
        sql += " LIMIT ?"
        params.append(limit)
        return [_row_dict(r) for r in c.execute(sql, params).fetchall()]

    @staticmethod
    def _sanitize_like_path(file_path: str) -> str:
        return file_path.replace("%", "").replace("_", "")

    def get_file_outline(self, file_path: str) -> dict[str, Any]:
        c = self._query_conn()
        safe_path = self._sanitize_like_path(file_path)
        path_pat = safe_path if safe_path.startswith("/") else f"%/{safe_path}"
        rows = c.execute(
            "SELECT s.name, s.kind, s.lineno, s.end_lineno, s.parent_name, s.signature "
            "FROM symbols s JOIN files f ON s.file_id = f.id "
            "WHERE (f.path = ? OR f.path LIKE ?) AND s.kind NOT IN ('import') "
            "ORDER BY s.lineno",
            (file_path, path_pat),
        ).fetchall()
        return {"file": file_path, "symbols": [_row_dict(r) for r in rows]}

    def get_call_graph(self, symbol_name: str) -> dict[str, Any]:
        c = self._query_conn()
        callers = c.execute(
            "SELECT c.caller_name, c.caller_lineno, f.path AS file_path "
            "FROM call_edges c JOIN files f ON c.caller_file_id = f.id "
            "WHERE c.callee_name = ?",
            (symbol_name,),
        ).fetchall()
        callees = c.execute(
            "SELECT c.callee_name, c.caller_lineno, f.path AS file_path "
            "FROM call_edges c JOIN files f ON c.caller_file_id = f.id "
            "WHERE c.caller_name = ?",
            (symbol_name,),
        ).fetchall()
        return {
            "symbol": symbol_name,
            "callers": [_row_dict(r) for r in callers],
            "callees": [_row_dict(r) for r in callees],
        }

    def get_imports(self, file_path: str) -> dict[str, Any]:
        c = self._query_conn()
        safe_path = self._sanitize_like_path(file_path)
        path_pat = safe_path if safe_path.startswith("/") else f"%/{safe_path}"
        entries = c.execute(
            "SELECT s.name, s.signature, s.lineno FROM symbols s "
            "JOIN files f ON s.file_id = f.id "
            "WHERE s.kind = 'import' AND (f.path = ? OR f.path LIKE ?) "
            "ORDER BY s.lineno",
            (file_path, path_pat),
        ).fetchall()

        # 入站：哪些文件导入了此模块
        module_prefix = self._file_to_module(file_path)
        inbound = []
        if module_prefix:
            rows = c.execute(
                "SELECT f.path, COUNT(*) AS import_count "
                "FROM symbols s JOIN files f ON s.file_id = f.id "
                "WHERE s.kind = 'import' AND (s.name = ? OR s.name LIKE ?) "
                "GROUP BY f.path ORDER BY import_count DESC LIMIT 20",
                (module_prefix, f"{module_prefix}.%"),
            ).fetchall()
            inbound = [_row_dict(r) for r in rows]

        return {
            "file": file_path,
            "imports": [_row_dict(r) for r in entries],
            "imported_by": inbound,
        }

    @staticmethod
    def _file_to_module(file_path: str) -> str:
        """从文件路径猜测模块名（如 src/maref/tools/registry.py → maref.tools.registry）。"""
        path = file_path.replace("\\", "/")
        # 移除常见源代码根前缀
        for prefix in ("src/", "lib/", "python/", "app/", "source/"):
            if path.startswith(prefix):
                path = path[len(prefix):]
                break
        # 移除 .py 扩展名
        for ext in (".py", ".pyi", ".pyx"):
            if path.endswith(ext):
                path = path[: -len(ext)]
                break
        # 移除 __init__ → 模块名是父目录
        if path.endswith("/__init__"):
            path = path[: -len("/__init__")]
        # 文件系统中的 __init__ 在模块中不存在
        parts = path.split("/")
        # 移除不以字母开头的部分（可能是版本目录或数字前缀）
        parts = [p for p in parts if p and (p[0].isalpha() or p == parts[-1])]
        return ".".join(parts)

    def get_references(self, symbol_name: str) -> dict[str, Any]:
        """跨文件查找符号的所有引用。结合调用边、导入和定义。

        注意: 这是查询时分析，使用已有索引数据（调用边 + 导入 + 定义匹配），
        不存储独立的引用表（存储成本过高）。
        """
        c = self._query_conn()

        # 1) 谁调用了该符号
        calls = c.execute(
            "SELECT c.caller_name, c.caller_lineno, f.path AS file_path "
            "FROM call_edges c JOIN files f ON c.caller_file_id = f.id "
            "WHERE c.callee_name = ? ORDER BY f.path, c.caller_lineno",
            (symbol_name,),
        ).fetchall()

        # 2) 哪里导入了该符号
        imports = c.execute(
            "SELECT s.name, s.signature, s.lineno, f.path AS file_path "
            "FROM symbols s JOIN files f ON s.file_id = f.id "
            "WHERE s.kind = 'import' AND s.name LIKE ? "
            "ORDER BY f.path, s.lineno",
            (f"%{symbol_name}%",),
        ).fetchall()

        # 3) 同名的定义（类/函数/方法）
        definitions = c.execute(
            "SELECT s.name, s.kind, s.lineno, f.path AS file_path "
            "FROM symbols s JOIN files f ON s.file_id = f.id "
            "WHERE s.name = ? AND s.kind != 'import' "
            "ORDER BY f.path, s.lineno",
            (symbol_name,),
        ).fetchall()

        return {
            "symbol": symbol_name,
            "calls": [_row_dict(r) for r in calls],
            "imports": [_row_dict(r) for r in imports],
            "definitions": [_row_dict(r) for r in definitions],
            "total": len(calls) + len(imports) + len(definitions),
        }

    def get_stats(self) -> dict[str, Any]:
        c = self._query_conn()
        return {
            "files": c.execute("SELECT COUNT(*) FROM files").fetchone()[0],
            "symbols": c.execute("SELECT COUNT(*) FROM symbols").fetchone()[0],
            "call_edges": c.execute("SELECT COUNT(*) FROM call_edges").fetchone()[0],
            "by_kind": dict(c.execute(
                "SELECT kind, COUNT(*) FROM symbols GROUP BY kind"
            ).fetchall()),
        }

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
