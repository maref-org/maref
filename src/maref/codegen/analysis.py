from __future__ import annotations

import ast
import asyncio
import json
import logging
import os
import shutil
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from maref.codegen.tool import (
    Tool,
    ToolContext,
    ToolResult,
    ValidationResult,
)

logger = logging.getLogger(__name__)

_HAVE_PYLSP = shutil.which("pylsp") is not None or (
    shutil.which("python") is not None
    and os.path.exists(os.path.join(os.path.dirname(sys.executable), "pylsp"))
)


class _LspClient:
    """Minimal JSON-RPC LSP client over stdio for pylsp."""

    def __init__(self) -> None:
        self._process: asyncio.subprocess.Process | None = None
        self._request_id: int = 0
        self._ready: asyncio.Event = asyncio.Event()
        self._pending: dict[int, asyncio.Future] = {}
        self._reader_task: asyncio.Task[None] | None = None

    async def start(self) -> bool:
        if self._process is not None:
            return True
        try:
            self._process = await asyncio.create_subprocess_exec(
                sys.executable,
                "-m",
                "pylsp",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError:
            logger.warning("pylsp not found, falling back to AST-based analysis")
            self._process = None
            return False

        self._reader_task = asyncio.create_task(self._reader())
        result = await self._request(
            "initialize",
            {
                "processId": None,
                "capabilities": {
                    "textDocument": {
                        "hover": {"contentFormat": ["plaintext"]},
                        "completion": {"completionItem": {"snippetSupport": False}},
                        "definition": {},
                        "references": {},
                    },
                },
            },
        )
        if result is None:
            return False
        await self._notify("initialized", {})
        self._ready.set()
        return True

    async def _reader(self) -> None:
        buf = b""
        process = self._process
        if process is None or process.stdout is None:
            return
        while True:
            try:
                chunk = await process.stdout.read(4096)
            except Exception:
                break
            if not chunk:
                break
            buf += chunk
            while True:
                header_end = buf.find(b"\r\n\r\n")
                if header_end == -1:
                    break
                header = buf[:header_end].decode("utf-8", errors="replace")
                content_length = 0
                for hline in header.split("\r\n"):
                    if hline.lower().startswith("content-length:"):
                        content_length = int(hline.split(":")[1].strip())
                body_start = header_end + 4
                if len(buf) < body_start + content_length:
                    break
                body = buf[body_start : body_start + content_length]
                buf = buf[body_start + content_length :]
                try:
                    msg = json.loads(body.decode("utf-8"))
                except json.JSONDecodeError:
                    continue
                if "id" in msg and isinstance(msg["id"], int):
                    future = self._pending.pop(msg["id"], None)
                    if future is not None and not future.done():
                        future.set_result(msg)
                elif "method" in msg and msg["method"] == "textDocument/publishDiagnostics":
                    pass

    async def _request(self, method: str, params: dict[str, Any]) -> dict[str, Any] | None:
        self._request_id += 1
        msg_id = self._request_id
        body = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": msg_id,
                "method": method,
                "params": params,
            }
        )
        future: asyncio.Future[dict[str, Any]] = asyncio.Future()
        self._pending[msg_id] = future
        await self._send(body)
        try:
            return await asyncio.wait_for(future, timeout=10)
        except asyncio.TimeoutError:
            self._pending.pop(msg_id, None)
            return None

    async def _notify(self, method: str, params: dict[str, Any]) -> None:
        body = json.dumps(
            {
                "jsonrpc": "2.0",
                "method": method,
                "params": params,
            }
        )
        await self._send(body)

    async def _send(self, body: str) -> None:
        if self._process is None or self._process.stdin is None:
            return
        raw = f"Content-Length: {len(body)}\r\n\r\n{body}".encode()
        self._process.stdin.write(raw)
        await self._process.stdin.drain()

    async def did_open(self, file_path: str, source: str) -> None:
        uri = Path(file_path).absolute().as_uri()
        await self._notify(
            "textDocument/didOpen",
            {
                "textDocument": {
                    "uri": uri,
                    "languageId": "python",
                    "version": 1,
                    "text": source,
                },
            },
        )

    async def did_close(self, file_path: str) -> None:
        uri = Path(file_path).absolute().as_uri()
        await self._notify(
            "textDocument/didClose",
            {
                "textDocument": {"uri": uri},
            },
        )

    async def hover(self, file_path: str, line: int, character: int) -> list[dict[str, Any]]:
        uri = Path(file_path).absolute().as_uri()
        result = await self._request(
            "textDocument/hover",
            {
                "textDocument": {"uri": uri},
                "position": {"line": line - 1, "character": character},
            },
        )
        if result is None:
            return []
        content = result.get("result")
        if content is None:
            return []
        contents = content.get("contents", {})
        if isinstance(contents, str):
            return [{"contents": contents}]
        if isinstance(contents, dict):
            return [{"contents": contents.get("value", str(contents))}]
        return [{"contents": str(contents)}]

    async def diagnostics(self, file_path: str) -> list[dict[str, Any]]:
        result = await self._request(
            "textDocument/diagnostic",
            {
                "textDocument": {"uri": Path(file_path).absolute().as_uri()},
            },
        )
        if result is None:
            return []
        diags = result.get("result", {}).get("items", [])
        return [
            {
                "severity": {1: "error", 2: "warning", 3: "info", 4: "hint"}.get(
                    d.get("severity"), "info"
                ),
                "message": d.get("message", ""),
                "line": (d.get("range", {}) or {}).get("start", {}).get("line", 0) + 1,
            }
            for d in diags
        ]

    async def definition(self, file_path: str, line: int, character: int) -> list[dict[str, Any]]:
        uri = Path(file_path).absolute().as_uri()
        result = await self._request(
            "textDocument/definition",
            {
                "textDocument": {"uri": uri},
                "position": {"line": line - 1, "character": character},
            },
        )
        if result is None:
            return []
        locs = result.get("result")
        if not locs:
            return []
        if not isinstance(locs, list):
            locs = [locs]
        return [
            {
                "uri": loc.get("uri", ""),
                "line": (loc.get("range", {}) or {}).get("start", {}).get("line", 0) + 1,
            }
            for loc in locs
        ]

    async def references(self, file_path: str, line: int, character: int) -> list[dict[str, Any]]:
        uri = Path(file_path).absolute().as_uri()
        result = await self._request(
            "textDocument/references",
            {
                "textDocument": {"uri": uri},
                "position": {"line": line - 1, "character": character},
                "context": {"includeDeclaration": True},
            },
        )
        if result is None:
            return []
        refs = result.get("result", [])
        return [
            {
                "uri": ref.get("uri", ""),
                "line": (ref.get("range", {}) or {}).get("start", {}).get("line", 0) + 1,
            }
            for ref in refs
        ]

    async def completion(self, file_path: str, line: int, character: int) -> list[dict[str, Any]]:
        uri = Path(file_path).absolute().as_uri()
        result = await self._request(
            "textDocument/completion",
            {
                "textDocument": {"uri": uri},
                "position": {"line": line - 1, "character": character},
            },
        )
        if result is None:
            return []
        items = result.get("result", {})
        if isinstance(items, dict):
            items = items.get("items", [])
        return [
            {
                "label": item.get("label", ""),
                "kind": item.get("kind", 0),
                "detail": item.get("detail", ""),
            }
            for item in (items or [])
        ]

    async def stop(self) -> None:
        if self._reader_task is not None:
            self._reader_task.cancel()
        if self._process is not None:
            try:
                self._process.kill()
                await self._process.wait()
            except ProcessLookupError:
                pass


class LSPInput(BaseModel):
    file_path: str = Field(..., description="Path to the source file")
    action: str = Field(
        "hover", description="LSP action: hover, completion, references, diagnostics, definition"
    )
    line: int = Field(1, description="Line number")
    character: int = Field(0, description="Character offset on the line")


class LSPOutput(BaseModel):
    action: str
    results: list[dict[str, Any]] = Field(default_factory=list)


class LSPTool(Tool[LSPInput, LSPOutput]):
    name = "LSP"
    description: str = "Language Server Protocol integration for semantic code analysis"

    _supported_extensions: set[str] = {".py", ".pyi"}
    _client: _LspClient | None = None

    def is_read_only(self, input: LSPInput) -> bool:
        return True

    def is_concurrency_safe(self, input: LSPInput) -> bool:
        return True

    async def validate(self, input: LSPInput) -> ValidationResult:
        ext = Path(input.file_path).suffix
        if ext not in self._supported_extensions:
            return ValidationResult(
                is_valid=False,
                message=f"Language not supported for file: {input.file_path}. Supported: {self._supported_extensions}",
            )
        if input.action not in {"hover", "completion", "references", "diagnostics", "definition"}:
            return ValidationResult(is_valid=False, message=f"Unsupported action: {input.action}")
        if not os.path.exists(input.file_path):
            return ValidationResult(is_valid=False, message=f"File not found: {input.file_path}")
        return ValidationResult(is_valid=True)

    async def call(self, input: LSPInput, ctx: ToolContext) -> ToolResult[LSPOutput]:
        if _HAVE_PYLSP:
            lsp_result = await self._call_lsp(input)
            if lsp_result is not None:
                return lsp_result
        return await self._call_ast_fallback(input)

    async def _call_lsp(self, input: LSPInput) -> ToolResult[LSPOutput] | None:
        client = self._get_client()
        if client is None:
            return None
        try:
            await client._ready.wait()
            path = Path(input.file_path)
            source = path.read_text(encoding="utf-8")
            await client.did_open(input.file_path, source)
            try:
                if input.action == "hover":
                    results = await client.hover(input.file_path, input.line, input.character)
                elif input.action == "diagnostics":
                    results = await client.diagnostics(input.file_path)
                elif input.action == "definition":
                    results = await client.definition(input.file_path, input.line, input.character)
                elif input.action == "references":
                    results = await client.references(input.file_path, input.line, input.character)
                elif input.action == "completion":
                    results = await client.completion(input.file_path, input.line, input.character)
                else:
                    results = []
            finally:
                await client.did_close(input.file_path)
            return ToolResult(data=LSPOutput(action=input.action, results=results))
        except Exception as e:
            logger.warning("LSP call failed for %s: %s", input.file_path, e)
            return None

    async def _call_ast_fallback(self, input: LSPInput) -> ToolResult[LSPOutput]:
        path = Path(input.file_path)
        try:
            source = path.read_text(encoding="utf-8")
        except Exception as e:
            return ToolResult(error=f"Failed to read file: {e}")

        results: list[dict[str, Any]] = []

        if input.action == "hover":
            symbol = self._find_symbol_at(source, input.line, input.character)
            if symbol:
                results.append(
                    {
                        "symbol": symbol,
                        "kind": "identifier",
                        "file": input.file_path,
                        "line": input.line,
                    }
                )
        elif input.action == "diagnostics":
            try:
                ast.parse(source)
                results.append({"severity": "ok", "message": "No syntax errors"})
            except SyntaxError as e:
                results.append(
                    {
                        "severity": "error",
                        "message": str(e),
                        "line": e.lineno or 0,
                    }
                )
        elif input.action == "definition":
            symbol = self._find_symbol_at(source, input.line, input.character)
            if symbol:
                results.append(
                    {
                        "symbol": symbol,
                        "file": input.file_path,
                        "line": input.line,
                    }
                )
        elif input.action == "references":
            symbol = self._find_symbol_at(source, input.line, input.character)
            if symbol:
                refs = self._find_references(source, symbol)
                results = [{"symbol": symbol, "file": input.file_path, "line": r} for r in refs]
        elif input.action == "completion":
            completions = self._get_completions(source, input.line, input.character)
            results = [{"label": c, "kind": "keyword"} for c in completions]

        return ToolResult(
            data=LSPOutput(action=input.action, results=results),
        )

    @classmethod
    def _get_client(cls) -> _LspClient | None:
        if cls._client is None:
            cls._client = _LspClient()
        return cls._client

    def _find_symbol_at(self, source: str, line: int, character: int) -> str | None:
        lines = source.split("\n")
        if line < 1 or line > len(lines):
            return None
        line_text = lines[line - 1]
        if character >= len(line_text):
            return None

        start = character
        while start > 0 and (line_text[start - 1].isalnum() or line_text[start - 1] in {"_", "."}):
            start -= 1
        end = character
        while end < len(line_text) and (line_text[end].isalnum() or line_text[end] in {"_", "."}):
            end += 1

        if start < end:
            return line_text[start:end]
        return line_text[character] if character < len(line_text) else None

    def _find_references(self, source: str, symbol: str) -> list[int]:
        refs: list[int] = []
        for i, line in enumerate(source.split("\n"), 1):
            if symbol in line:
                refs.append(i)
        return refs

    def _get_completions(self, source: str, line: int, character: int) -> list[str]:
        completions: list[str] = []
        try:
            tree = ast.parse(source)
            names: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Name):
                    names.add(node.id)
                elif isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                    names.add(node.name)
            current_line = source.split("\n")[line - 1] if line <= len(source.split("\n")) else ""
            partial = current_line[:character].split()[-1] if current_line.split() else ""
            for name in sorted(names):
                if partial and name.startswith(partial):
                    completions.append(name)
        except SyntaxError:
            pass

        if not completions:
            completions = ["pass", "return", "if", "for", "while", "def", "class", "import", "from"]

        return completions


class CodeCompletionInput(BaseModel):
    file_path: str = Field(..., description="Path to the source file")
    cursor_line: int = Field(1, description="Line number for cursor position")
    cursor_character: int = Field(0, description="Character offset for cursor position")
    context_before: str = Field("", description="Code before cursor")
    context_after: str = Field("", description="Code after cursor")


class CodeCompletionOutput(BaseModel):
    generated_code: str = ""
    alternatives: list[str] = Field(default_factory=list)
    confidence: float = 0.0


class CodeCompletionTool(Tool[CodeCompletionInput, CodeCompletionOutput]):
    name = "CodeCompletion"
    description: str = "AI-powered code completion using CodeIndexer and LLM backend"

    def __init__(self, code_indexer: Any | None = None, llm_backend: Any | None = None) -> None:
        self._code_indexer = code_indexer
        self._llm_backend = llm_backend

    def is_read_only(self, input: CodeCompletionInput) -> bool:
        return True

    def is_concurrency_safe(self, input: CodeCompletionInput) -> bool:
        return True

    async def validate(self, input: CodeCompletionInput) -> ValidationResult:
        return ValidationResult(is_valid=True)

    async def call(
        self, input: CodeCompletionInput, ctx: ToolContext
    ) -> ToolResult[CodeCompletionOutput]:
        nearby_symbols: list[str] = []
        if self._code_indexer is not None:
            try:
                if input.context_before:
                    last_token = input.context_before.split()[-1].strip(" (,")
                    results = self._code_indexer.search_symbols(query=last_token, limit=10)
                    nearby_symbols = [r.get("name", "") for r in results if isinstance(r, dict)]
            except Exception:
                pass

        prompt = self._build_completion_prompt(
            input.context_before,
            input.context_after,
            nearby_symbols,
        )

        if self._llm_backend is not None:
            try:
                result = self._llm_backend.generate(prompt)
                generated = (
                    result.get("completion", "") if isinstance(result, dict) else str(result)
                )
            except Exception:
                generated = self._fallback_completion(input.context_before, input.context_after)
        else:
            generated = self._fallback_completion(input.context_before, input.context_after)

        return ToolResult(
            data=CodeCompletionOutput(
                generated_code=generated,
                alternatives=[],
                confidence=0.85 if self._llm_backend is not None else 0.5,
            )
        )

    def _build_completion_prompt(self, before: str, after: str, nearby: list[str]) -> str:
        parts = ["Complete the following code:"]
        if nearby:
            parts.append(f"Nearby symbols: {', '.join(nearby[:5])}")
        parts.append("```python")
        if before:
            parts.append(before)
        parts.append("<|CURSOR|>")
        if after:
            parts.append(after)
        parts.append("```")
        return "\n".join(parts)

    def _fallback_completion(self, before: str, after: str) -> str:
        lines = before.split("\n")
        last_line = lines[-1].strip() if lines else ""
        indent = " " * (len(lines[-1]) - len(lines[-1].lstrip())) if lines else ""

        if "def " in last_line and last_line.endswith(":"):
            return f"{indent}    pass\n"
        if "class " in last_line and last_line.endswith(":"):
            return f"{indent}    pass\n"
        if "if " in last_line and last_line.endswith(":"):
            return f"{indent}    pass\n"
        if "for " in last_line and last_line.endswith(":"):
            return f"{indent}    pass\n"
        if "try" in last_line and last_line.endswith(":"):
            return f"{indent}    pass\n"

        return "pass\n"
