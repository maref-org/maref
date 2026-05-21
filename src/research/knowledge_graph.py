"""
MAREF Knowledge Graph — backward-compatible re-exports.

All core logic has been moved to maref.knowledge.graph.
This module re-exports for existing importers.
"""

from maref.knowledge.graph import GraphSnapshot, KnowledgeGraph, KnowledgeNode, RelationEdge

__all__ = ["KnowledgeGraph", "KnowledgeNode", "RelationEdge", "GraphSnapshot"]
