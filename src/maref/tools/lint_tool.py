from __future__ import annotations

import asyncio
import os
import sys

from pydantic import BaseModel, Field

from maref.codegen.tool import (
    Tool,
    ToolContext,
    ToolResult,
    ValidationResult,
)


class LintInput(BaseModel):
    file_path: str = Field(..., description="Path to the file or directory to lint")
    tool_name: str = Field("ruff", description="Lint tool to use: ruff or mypy")


class LintOutput(BaseModel):
    tool_name: str
    exit_code: int
    stdout: str
    stderr: str
    passed: bool


class LintTool(Tool[LintInput, LintOutput]):
    name = "Lint"
    description: str = "Run ruff or mypy linting on a file or directory"

    def is_read_only(self, input: LintInput) -> bool:
        return True

    def is_concurrency_safe(self, input: LintInput) -> bool:
        return True

    async def validate(self, input: LintInput) -> ValidationResult:
        if input.tool_name not in {"ruff", "mypy"}:
            return ValidationResult(is_valid=False, message=f"Unsupported lint tool: {input.tool_name}")
        if not os.path.exists(input.file_path):
            return ValidationResult(is_valid=False, message=f"Path not found: {input.file_path}")
        return ValidationResult(is_valid=True)

    async def call(self, input: LintInput, ctx: ToolContext) -> ToolResult[LintOutput]:
        cwd = ctx.workspace_root or os.getcwd()

        try:
            if input.tool_name == "ruff":
                process = await asyncio.create_subprocess_exec(
                    sys.executable, "-m", "ruff", "check", input.file_path,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=cwd,
                )
            else:
                process = await asyncio.create_subprocess_exec(
                    sys.executable, "-m", "mypy", input.file_path,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=cwd,
                )

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    process.communicate(), timeout=60
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                return ToolResult(
                    data=LintOutput(
                        tool_name=input.tool_name,
                        exit_code=-1,
                        stdout="",
                        stderr="Timed out after 60s",
                        passed=False,
                    )
                )

            stdout = stdout_bytes.decode("utf-8", errors="replace")
            stderr = stderr_bytes.decode("utf-8", errors="replace")

            return ToolResult(
                data=LintOutput(
                    tool_name=input.tool_name,
                    exit_code=process.returncode or 0,
                    stdout=stdout,
                    stderr=stderr,
                    passed=(process.returncode == 0),
                )
            )
        except Exception as e:
            return ToolResult(
                data=LintOutput(
                    tool_name=input.tool_name,
                    exit_code=-1,
                    stdout="",
                    stderr=str(e),
                    passed=False,
                )
            )
