"""
ChromaDB-backed vector store for job listing embeddings.

Stores job description embeddings and provides similarity search
for finding relevant matches against the candidate profile.
Persists to disk for cross-session use.
"""

import hashlib
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yaml

logger = logging.getLogger(__name__)

MATCHING_CONFIG_PATH = Path("config/matching_config.yaml")


def _load_matching_config(path: Path = MATCHING_CONFIG_PATH) -> dict:
    """Load matching configuration from YAML."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        logger.warning("Matching config not found at %s, using defaults", path)
        return {}


def _job_id(url: str, company: str, title: str) -> str:
    """Generate a deterministic ID for a job listing."""
    raw = f"{url}|{company}|{title}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


class VectorStore:
    """
    ChromaDB-backed vector store for job listing embeddings.

    Stores embeddings with metadata and supports:
    - Adding individual or batch job embeddings
    - Querying by embedding similarity
    - Deduplication via URL hash
    - Persistent storage across sessions

    Usage:
        store = VectorStore()
        store.add_job(job_id="abc123", embedding=[0.1, ...], metadata={...})
        results = store.query(query_embedding=[0.1, ...], top_k=20)
    """

    def __init__(self, config_path: Path = MATCHING_CONFIG_PATH):
        config = _load_matching_config(config_path)
        vs_config = config.get("vector_store", {})
        dedup_config = config.get("deduplication", {})

        self._collection_name: str = vs_config.get("collection_name", "job_listings")
        self._persist_dir: str = vs_config.get("persist_directory", "data/chroma_db")
        self._dedup_method: str = dedup_config.get("method", "url_hash")
        self._dedup_threshold: float = dedup_config.get("similarity_threshold", 0.95)

        self._client = None
        self._collection = None

    def _ensure_initialized(self):
        """Lazily initialize ChromaDB client and collection."""
        if self._client is not None:
            return

        import chromadb

        persist_path = Path(self._persist_dir)
        persist_path.mkdir(parents=True, exist_ok=True)

        self._client = chromadb.PersistentClient(path=str(persist_path))
        self._collection = self._client.get_or_create_collection(
            name=self._collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(
            "VectorStore initialized: collection='%s', persist='%s', count=%d",
            self._collection_name,
            self._persist_dir,
            self._collection.count(),
        )

    @property
    def count(self) -> int:
        """Number of embeddings currently stored."""
        self._ensure_initialized()
        return self._collection.count()

    def add_job(
        self,
        job_id: str,
        embedding: List[float],
        metadata: Optional[Dict] = None,
        document: str = "",
    ) -> bool:
        """
        Add a single job embedding to the store.

        Args:
            job_id: Unique identifier for the job listing.
            embedding: Embedding vector (list of floats).
            metadata: Optional metadata dict (title, company, url, etc.).
            document: Optional raw text of the job listing.

        Returns:
            True if added, False if duplicate detected and skipped.
        """
        self._ensure_initialized()

        # Deduplication check
        if self._is_duplicate(job_id):
            logger.debug("Duplicate job_id '%s' — skipping", job_id)
            return False

        # ChromaDB requires metadata to be a non-empty dict if provided
        resolved_metadata = metadata if metadata else {"_placeholder": True}

        add_kwargs = {
            "ids": [job_id],
            "embeddings": [embedding],
            "metadatas": [resolved_metadata],
        }
        if document:
            add_kwargs["documents"] = [document]

        self._collection.add(**add_kwargs)
        logger.debug("Added job '%s' to vector store", job_id)
        return True

    def add_jobs_batch(
        self,
        job_ids: List[str],
        embeddings: List[List[float]],
        metadatas: Optional[List[Dict]] = None,
        documents: Optional[List[str]] = None,
    ) -> int:
        """
        Add multiple job embeddings in batch.

        Args:
            job_ids: List of unique job IDs.
            embeddings: List of embedding vectors.
            metadatas: Optional list of metadata dicts.
            documents: Optional list of raw text documents.

        Returns:
            Number of jobs actually added (excluding duplicates).
        """
        self._ensure_initialized()

        if not job_ids:
            return 0

        # Filter out duplicates
        new_indices = []
        for i, jid in enumerate(job_ids):
            if not self._is_duplicate(jid):
                new_indices.append(i)

        if not new_indices:
            logger.debug("All %d jobs are duplicates — skipping batch", len(job_ids))
            return 0

        filtered_ids = [job_ids[i] for i in new_indices]
        filtered_embeddings = [embeddings[i] for i in new_indices]
        filtered_metadatas = (
            [metadatas[i] for i in new_indices] if metadatas else None
        )
        filtered_documents = (
            [documents[i] for i in new_indices] if documents else None
        )

        # Ensure all metadata dicts are non-empty (ChromaDB 1.0+ requirement)
        if filtered_metadatas:
            filtered_metadatas = [
                m if m else {"_placeholder": True} for m in filtered_metadatas
            ]

        add_kwargs = {
            "ids": filtered_ids,
            "embeddings": filtered_embeddings,
        }
        if filtered_metadatas:
            add_kwargs["metadatas"] = filtered_metadatas
        if filtered_documents:
            add_kwargs["documents"] = filtered_documents

        self._collection.add(**add_kwargs)
        logger.info("Added %d/%d jobs to vector store (batch)", len(filtered_ids), len(job_ids))
        return len(filtered_ids)

    def query(
        self,
        query_embedding: List[float],
        top_k: int = 20,
        where: Optional[Dict] = None,
    ) -> List[Dict]:
        """
        Find the most similar jobs to a query embedding.

        Args:
            query_embedding: The embedding to search against.
            top_k: Maximum number of results to return.
            where: Optional ChromaDB where filter for metadata.

        Returns:
            List of dicts with keys: id, score (cosine similarity),
            metadata, document.
        """
        self._ensure_initialized()

        if self._collection.count() == 0:
            return []

        # Clamp top_k to available items
        actual_k = min(top_k, self._collection.count())

        query_kwargs = {
            "query_embeddings": [query_embedding],
            "n_results": actual_k,
            "include": ["embeddings", "metadatas", "documents", "distances"],
        }
        if where:
            query_kwargs["where"] = where

        results = self._collection.query(**query_kwargs)

        # ChromaDB returns distances; for cosine space, distance = 1 - similarity
        output = []
        ids = results.get("ids", [[]])[0]
        distances = results.get("distances", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        documents = results.get("documents", [[]])[0]

        for i, jid in enumerate(ids):
            similarity = 1.0 - distances[i]  # Convert cosine distance to similarity
            output.append({
                "id": jid,
                "score": round(similarity, 4),
                "metadata": metadatas[i] if metadatas else {},
                "document": documents[i] if documents else "",
            })

        return output

    def get_by_id(self, job_id: str) -> Optional[Dict]:
        """Retrieve a stored job by its ID."""
        self._ensure_initialized()
        try:
            result = self._collection.get(
                ids=[job_id],
                include=["metadatas", "documents"],
            )
            if result and result.get("ids"):
                metadatas = result.get("metadatas")
                documents = result.get("documents")
                return {
                    "id": result["ids"][0],
                    "metadata": metadatas[0] if metadatas else {},
                    "document": documents[0] if documents else "",
                }
        except Exception as e:
            logger.warning("Failed to get job '%s' from vector store: %s", job_id, e)
        return None

    def delete_job(self, job_id: str) -> None:
        """Remove a job from the store by ID."""
        self._ensure_initialized()
        self._collection.delete(ids=[job_id])
        logger.debug("Deleted job '%s' from vector store", job_id)

    def clear(self) -> None:
        """Remove all jobs from the collection."""
        self._ensure_initialized()
        self._client.delete_collection(self._collection_name)
        self._collection = self._client.get_or_create_collection(
            name=self._collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info("Vector store cleared")

    def _is_duplicate(self, job_id: str) -> bool:
        """Check if a job ID already exists in the store."""
        try:
            result = self._collection.get(ids=[job_id])
            return bool(result["ids"])
        except Exception:
            return False

    @staticmethod
    def generate_job_id(url: str, company: str, title: str) -> str:
        """Generate a deterministic ID for a job listing."""
        return _job_id(url, company, title)
