"""
Matching package — job relevance scoring and vector similarity.

Public API:
    - RelevanceScorer: Multi-signal relevance scorer
    - MatchResult: Scoring result dataclass
    - EmbeddingManager: Text embedding generation
    - VectorStore: ChromaDB-backed embedding store
"""

from backend.matching.scorer import RelevanceScorer, MatchResult
from backend.matching.embeddings import EmbeddingManager
from backend.matching.vector_store import VectorStore

__all__ = [
    "RelevanceScorer",
    "MatchResult",
    "EmbeddingManager",
    "VectorStore",
]
