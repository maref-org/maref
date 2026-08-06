"""
MAREF Knowledge Graph — backward-compatible re-exports.

All core logic has been moved to maref.knowledge.graph.
This module re-exports for existing importers.
"""

import maref.knowledge.graph as _kg

GraphSnapshot = _kg.GraphSnapshot
KnowledgeGraph = _kg.KnowledgeGraph
KnowledgeNode = _kg.KnowledgeNode
RelationEdge = _kg.RelationEdge

__all__ = [
    'GraphSnapshot',
    'KnowledgeGraph',
    'KnowledgeNode',
    'RelationEdge',
]
