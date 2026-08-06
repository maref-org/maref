from __future__ import annotations

import asyncio
import os
import re
import shutil
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from maref.codegen.tool import (
    Tool,
    ToolContext,
    ToolResult,
    ValidationResult,
)

_HAVE_RG = shutil.which("rg") is not None


class GrepInput(BaseModel):
    pattern: str = Field(..., description="Regex pattern to search for")
    path: str | None = Field(None, description="Single file or directory to search")
    include: str | None = Field(None, description="File pattern to include (e.g. *.py)")
    max_results: int = Field(50, description="Maximum number of results")
    context_lines: int = Field(0, description="Lines of context around matches")


class GrepOutput(BaseModel):
    matches: list[dict[str, Any]]
    count: int
    truncated: bool = False


class GrepTool(Tool[GrepInput, GrepOutput]):
    name = "Grep"
    description: str = "Search file contents using ripgrep (fallback to pure Python)"

    def is_read_only(self, input: GrepInput) -> bool:
        return True

    def is_concurrency_safe(self, input: GrepInput) -> bool:
        return True

    async def validate(self, input: GrepInput) -> ValidationResult:
        if not input.pattern.strip():
            return ValidationResult(is_valid=False, message="Pattern must not be empty")
        try:
            re.compile(input.pattern)
        except re.error as e:
            return ValidationResult(is_valid=False, message=f"Invalid regex: {e}")
        return ValidationResult(is_valid=True)

    async def call(self, input: GrepInput, ctx: ToolContext) -> ToolResult[GrepOutput]:
        if _HAVE_RG:
            return await self._call_rg(input, ctx)
        return await self._call_python(input, ctx)

    async def _call_rg(self, input: GrepInput, ctx: ToolContext) -> ToolResult[GrepOutput]:
        search_root = input.path or ctx.workspace_root or os.getcwd()
        args = [
            "rg",
            "--no-heading",
            "--line-number",
            "--color", "never",
            "-E", "utf-8",
        ]
        if input.context_lines > 0:
            args.extend(["-C", str(input.context_lines)])
        if input.include:
            args.extend(["--glob", input.include])
        args.extend(["--max-count", str(input.max_results)])
        args.append(input.pattern)
        args.append(search_root)

        try:
            process = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout_bytes, _ = await asyncio.wait_for(process.communicate(), timeout=30)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                return ToolResult(data=GrepOutput(matches=[], count=0, truncated=False))

            stdout = stdout_bytes.decode("utf-8", errors="replace")
            matches: list[dict[str, Any]] = []
            seen: set[tuple[str, int]] = set()
            for raw_line in stdout.split("\n"):
                if not raw_line.strip():
                    continue
                parts = raw_line.split(":", 2)
                if len(parts) < 3:
                    continue
                file_path, line_num, content = parts[0], parts[1], parts[2]
                key = (file_path, int(line_num))
                if key in seen:
                    continue
                seen.add(key)
                match_record: dict[str, Any] = {
                    "file": file_path,
                    "line": int(line_num),
                    "content": content,
                }
                matches.append(match_record)
                if len(matches) >= input.max_results:
                    break

            truncated = len(matches) >= input.max_results
            return ToolResult(
                data=GrepOutput(matches=matches, count=len(matches), truncated=truncated),
            )
        except Exception as e:
            return ToolResult(
                data=GrepOutput(matches=[], count=0, truncated=False),
                metadata={"error": str(e), "fallback": "rg failed"},
            )

    async def _call_python(self, input: GrepInput, ctx: ToolContext) -> ToolResult[GrepOutput]:
        regex = re.compile(input.pattern)
        search_root = Path(input.path) if input.path else Path(ctx.workspace_root) if ctx.workspace_root else Path.cwd()

        matches: list[dict[str, Any]] = []
        truncated = False

        if search_root.is_file():
            files = [search_root]
        else:
            files = list(search_root.rglob("*"))
            if input.include:
                files = [f for f in files if f.match(input.include)]

        for file_path in files:
            if not file_path.is_file():
                continue
            try:
                content = file_path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue

            for i, line in enumerate(content.split("\n"), 1):
                if regex.search(line):
                    match_record: dict[str, Any] = {
                        "file": str(file_path),
                        "line": i,
                        "content": line,
                    }
                    if input.context_lines > 0:
                        lines = content.split("\n")
                        start = max(0, i - 1 - input.context_lines)
                        end = min(len(lines), i + input.context_lines)
                        match_record["context"] = "\n".join(lines[start:end])
                    matches.append(match_record)

                    if len(matches) >= input.max_results:
                        truncated = True
                        break

            if truncated:
                break

        return ToolResult(
            data=GrepOutput(matches=matches, count=len(matches), truncated=truncated),
        )
