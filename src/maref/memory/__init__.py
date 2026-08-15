"""Memory Layer for MAREF.

Three-tier memory architecture:
- Working Memory (Hot): Runtime state, TTL minutes, Pub/Sub sync
- Episodic Memory (Warm): Historical task records, SQL query
- Semantic Memory (Cold): Knowledge ontology, semantic retrieval

Key components:
- MemoryManager: Unified interface for all memory operations
- WorkingMemoryStore: Hot-tier in-memory with checkpointing
- EpisodicMemoryStore: Warm-tier structured task history
- SemanticMemoryStore: Cold-tier knowledge graph + vector search
"""

from maref.memory.episodic_store import EpisodicStore
from maref.memory.memory_manager import (
    ConfidenceLabel,
    EpisodicMemoryStore,
    MemoryManager,
    MemoryQuery,
    MemoryRecord,
    SemanticMemoryStore,
    SourceAnnotation,
    UserIsolationTag,
    WorkingMemoryStore,
)
from maref.memory.persona_learning import PersonaLearningLoop
from maref.memory.persona_tools import (
    PERSONA_TOOLS,
    CreateHandoffTool,
    GetHandoffTool,
    GetPersonaContextTool,
    GetUserProfileTool,
    PersonaMemoryTool,
    RecordFeedbackTool,
    ResolveHandoffTool,
    SearchMemoryTool,
    WriteMemoryTool,
    quick_sentiment,
    register_persona_tools,
)
from maref.memory.style_learner import StyleLearner
from maref.memory.user_profile_graph import DEFAULT_DB_PATH, Preference, UserProfileGraph

__all__ = [
    "ConfidenceLabel",
    "CreateHandoffTool",
    "DEFAULT_DB_PATH",
    "EpisodicMemoryStore",
    "EpisodicStore",
    "GetHandoffTool",
    "GetPersonaContextTool",
    "GetUserProfileTool",
    "MemoryManager",
    "MemoryQuery",
    "MemoryRecord",
    "PERSONA_TOOLS",
    "PersonaLearningLoop",
    "PersonaMemoryTool",
    "Preference",
    "RecordFeedbackTool",
    "ResolveHandoffTool",
    "SearchMemoryTool",
    "SemanticMemoryStore",
    "SourceAnnotation",
    "StyleLearner",
    "UserIsolationTag",
    "UserProfileGraph",
    "WorkingMemoryStore",
    "WriteMemoryTool",
    "quick_sentiment",
    "register_persona_tools",
]
