"""CodeDepth — 零外部依赖的 Python 代码深度索引器。

为 Agent 提供跨文件符号搜索、调用图、导入链等认知增强能力。
"""

from maref.codedepth.indexer import CallEdge, CodeIndexer, SymbolInfo

__all__ = ["CodeIndexer", "SymbolInfo", "CallEdge"]
