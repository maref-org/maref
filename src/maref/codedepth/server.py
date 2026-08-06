"""CodeDepth MCP Server — 代码深度探索工具集。

支持两种运行模式：
  1. MAREF MCPServer 集成 — 通过 create_code_depth_server() 工厂函数
  2. 独立 stdio 子进程 — python -m maref.codedepth.server

用法 (独立模式):
    from maref.codedepth.server import create_code_depth_server
    server = create_code_depth_server(repo_path="/path/to/repo")
    transport = server.get_inprocess_transport()
"""

from __future__ import annotations

import json
import sys
from typing import Any

from maref.codedepth.indexer import CodeIndexer
from maref.integration.mcp_server import SUPPORTED_PROTOCOL_VERSIONS, MCPServer


def create_code_depth_server(
    name: str = "maref-codedepth",
    version: str = "0.1.0",
    repo_path: str | None = None,
) -> MCPServer:
    """创建 CodeDepth MCP 服务器实例。

    Args:
        name: 服务器名称
        version: 服务器版本
        repo_path: 仓库路径（默认使用 CWD）

    Returns:
        配置好的 MCPServer 实例
    """
    indexer = CodeIndexer(repo_path)
    server = MCPServer(name=name, version=version)

    def _rebuild(args: dict[str, Any]) -> dict[str, Any]:
        return indexer.build()

    def _stats(args: dict[str, Any]) -> dict[str, Any]:
        return indexer.get_stats()

    def _search(args: dict[str, Any]) -> dict[str, Any]:
        query = (args.get("query") or "").strip()
        if not query:
            return {"results": [], "error": "query is required"}
        return {
            "results": indexer.search_symbols(
                query=query,
                kind=args.get("kind"),
                limit=args.get("limit", 50),
            ),
        }

    def _outline(args: dict[str, Any]) -> dict[str, Any]:
        fp = (args.get("file_path") or "").strip()
        if not fp:
            return {"error": "file_path is required", "symbols": []}
        return indexer.get_file_outline(fp)

    def _call_graph(args: dict[str, Any]) -> dict[str, Any]:
        sym = (args.get("symbol_name") or "").strip()
        if not sym:
            return {"error": "symbol_name is required", "symbol": "", "callers": [], "callees": []}
        return indexer.get_call_graph(sym)

    def _imports(args: dict[str, Any]) -> dict[str, Any]:
        fp = (args.get("file_path") or "").strip()
        if not fp:
            return {"error": "file_path is required", "file": "", "imports": [], "imported_by": []}
        return indexer.get_imports(fp)

    def _references(args: dict[str, Any]) -> dict[str, Any]:
        sym = (args.get("symbol_name") or "").strip()
        if not sym:
            return {"error": "symbol_name is required", "symbol": "", "calls": [], "imports": [], "definitions": [], "total": 0}
        return indexer.get_references(sym)

    server.register_tool(
        "depth_rebuild",
        "全量重建代码索引",
        {"type": "object", "properties": {}},
        _rebuild,
    )
    server.register_tool(
        "depth_stats",
        "索引统计信息（文件数、符号数、调用边数）",
        {"type": "object", "properties": {}},
        _stats,
    )
    server.register_tool(
        "depth_symbol_search",
        "按名称模糊搜索符号（函数、类、方法等）",
        {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "符号名称搜索关键词"},
                "kind": {"type": "string", "description": "过滤类型: function, class, method, import", "enum": ["function", "class", "method", "import", ""]},
                "limit": {"type": "integer", "description": "最大返回数"},
            },
            "required": ["query"],
        },
        _search,
    )
    server.register_tool(
        "depth_file_outline",
        "获取文件中定义的所有符号（函数、类、方法）的结构化大纲",
        {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "文件路径（相对于仓库根或绝对路径）"},
            },
            "required": ["file_path"],
        },
        _outline,
    )
    server.register_tool(
        "depth_call_graph",
        "查看某个符号的调用者与被调用者",
        {
            "type": "object",
            "properties": {
                "symbol_name": {"type": "string", "description": "符号名称（函数/方法名）"},
            },
            "required": ["symbol_name"],
        },
        _call_graph,
    )
    server.register_tool(
        "depth_imports",
        "查看文件导入了哪些模块，以及哪些文件导入了该模块",
        {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "文件路径"},
            },
            "required": ["file_path"],
        },
        _imports,
    )
    server.register_tool(
        "depth_references",
        "跨文件查找符号的所有引用（调用、导入、定义）",
        {
            "type": "object",
            "properties": {
                "symbol_name": {"type": "string", "description": "符号名称"},
            },
            "required": ["symbol_name"],
        },
        _references,
    )

    return server


# ── 独立 stdio 入口 ────────────────────────────────────────

def _stdio_handle(server: MCPServer, raw: str) -> str | None:
    """处理单个 JSON-RPC 请求，返回响应 JSON 字符串（或 None 表示通知）。"""
    try:
        msg = json.loads(raw)
    except json.JSONDecodeError:
        return json.dumps({"jsonrpc": "2.0", "error": {"code": -32700, "message": "Parse error"}, "id": None})

    req_id = msg.get("id", 0)
    method = msg.get("method", "")

    if method == "initialize":
        client_version = (msg.get("params") or {}).get("protocolVersion", "2024-11-05")
        protocol_version = (
            client_version if client_version in SUPPORTED_PROTOCOL_VERSIONS else SUPPORTED_PROTOCOL_VERSIONS[0]
        )
        return json.dumps({
            "jsonrpc": "2.0", "id": req_id,
            "result": {"protocolVersion": protocol_version, "serverInfo": {"name": "maref-codedepth", "version": "0.1.0"}},
        })
    if method == "server/discover":
        return json.dumps({
            "jsonrpc": "2.0", "id": req_id,
            "result": {"protocolVersions": SUPPORTED_PROTOCOL_VERSIONS, "capabilities": {"tools": {}}, "serverInfo": {"name": "maref-codedepth", "version": "0.1.0"}},
        })
    if method == "tools/list":
        tools = [{"name": t.name, "description": t.description, "inputSchema": t.input_schema}
                 for t in server._tools.values()]
        return json.dumps({"jsonrpc": "2.0", "id": req_id, "result": {"tools": tools}})
    if method == "tools/call":
        params = msg.get("params", {})
        tool_name = params.get("name", "")
        args = params.get("arguments", {})
        tool = server._tools.get(tool_name)
        if not tool:
            return json.dumps({
                "jsonrpc": "2.0", "id": req_id,
                "error": {"code": -32601, "message": f"Tool not found: {tool_name}"},
            })
        try:
            result = tool.handler(args)
            return json.dumps({"jsonrpc": "2.0", "id": req_id, "result": result})
        except RuntimeError as e:
            return json.dumps({
                "jsonrpc": "2.0", "id": req_id,
                "error": {"code": -32000, "message": str(e)},
            })
    # 通知 / 其他方法 — 静默忽略
    return None


def stdio_main() -> None:
    """在 stdin/stdout 上运行 JSON-RPC MCP 服务器。

    启动时自动检测并构建索引（仅在首次或索引缺失时）。
    """
    server = create_code_depth_server()
    idx = server._tools.get("depth_stats")
    if idx:
        stats = idx.handler({})
        if stats.get("files", 0) == 0:
            print("[codedepth] No index found — auto-building...", file=sys.stderr)
            rebuild = server._tools.get("depth_rebuild")
            if rebuild:
                result = rebuild.handler({})
                print(f"[codedepth] {result}", file=sys.stderr)

    buff = ""
    while True:
        try:
            chunk = sys.stdin.read(4096)
            if not chunk:
                break
            buff += chunk
            while "\n" in buff:
                line, buff = buff.split("\n", 1)
                line = line.strip()
                if not line:
                    continue
                resp = _stdio_handle(server, line)
                if resp is not None:
                    sys.stdout.write(resp + "\n")
                    sys.stdout.flush()
        except (EOFError, KeyboardInterrupt):
            break


if __name__ == "__main__":
    stdio_main()
