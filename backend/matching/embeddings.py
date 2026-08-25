"""
Embedding manager for profile and job description vectorization.

Uses sentence-transformers for generating dense embeddings used in
similarity-based relevance scoring. Model is loaded lazily on first use
and cached for subsequent calls.
"""

import logging
from pathlib import Path
from typing import List, Optional, Union

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


class EmbeddingManager:
    """
    Manages text embedding generation via sentence-transformers.

    Lazily loads the model on first use to avoid startup overhead.
    All embeddings are L2-normalized by default (suitable for cosine similarity).

    Usage:
        em = EmbeddingManager()
        vec = em.embed_text("Software Engineer with Python experience")
        vecs = em.embed_texts(["text1", "text2"])
    """

    def __init__(self, config_path: Path = MATCHING_CONFIG_PATH):
        config = _load_matching_config(config_path)
        embedding_config = config.get("embedding", {})
        self._model_name: str = embedding_config.get("model_name", "all-MiniLM-L6-v2")
        self._cache_dir: str = embedding_config.get("cache_dir", "data/models")
        self._model = None  # Lazy-loaded

    @property
    def model_name(self) -> str:
        return self._model_name

    def _load_model(self):
        """Load the sentence-transformers model (lazy, one-time)."""
        if self._model is not None:
            return

        from sentence_transformers import SentenceTransformer

        cache_path = Path(self._cache_dir)
        cache_path.mkdir(parents=True, exist_ok=True)

        logger.info("Loading embedding model '%s' (cache: %s)", self._model_name, self._cache_dir)
        self._model = SentenceTransformer(self._model_name, cache_folder=str(cache_path))
        logger.info("Embedding model loaded — dimension: %d", self.dimension)

    @property
    def dimension(self) -> int:
        """Return the embedding dimensionality."""
        self._load_model()
        return self._model.get_embedding_dimension()

    def embed_text(self, text: str) -> List[float]:
        """
        Generate a single embedding vector from text.

        Args:
            text: Input text to embed.

        Returns:
            List of floats representing the normalized embedding vector.
        """
        self._load_model()
        embedding = self._model.encode(text, normalize_embeddings=True)
        return embedding.tolist()

    def embed_texts(self, texts: List[str], batch_size: int = 32) -> List[List[float]]:
        """
        Generate embeddings for multiple texts in batch.

        Args:
            texts: List of input texts.
            batch_size: Batch size for encoding.

        Returns:
            List of embedding vectors (each a list of floats).
        """
        if not texts:
            return []

        self._load_model()
        embeddings = self._model.encode(
            texts, normalize_embeddings=True, batch_size=batch_size, show_progress_bar=False,
        )
        return [emb.tolist() for emb in embeddings]

    def profile_to_text(self, profile) -> str:
        """
        Convert a CandidateProfile into a single text string for embedding.

        Combines skills, experience descriptions, and project descriptions
        into a unified representation.

        Args:
            profile: A CandidateProfile object.

        Returns:
            Combined text suitable for embedding.
        """
        parts = []

        # Skills
        if profile.skills:
            parts.append("Skills: " + ", ".join(profile.skills))

        # Experience
        for exp in profile.experience:
            parts.append(
                f"{exp.type} at {exp.company}: {exp.title}. {exp.description}"
            )

        # Projects
        for proj in profile.projects:
            tech = ", ".join(proj.tech_stack) if proj.tech_stack else ""
            parts.append(
                f"Project {proj.name}: {proj.description}"
                + (f" ({tech})" if tech else "")
            )

        # Education
        for edu in profile.education:
            parts.append(f"{edu.degree} in {edu.field_of_study} from {edu.institution}")

        return " | ".join(parts) if parts else ""

    def job_to_text(self, job) -> str:
        """
        Convert a job listing (RawJobListing or ProcessedJobListing) into
        a single text string for embedding.

        Args:
            job: A job listing object.

        Returns:
            Combined text suitable for embedding.
        """
        parts = [
            f"Title: {job.title}",
            f"Company: {job.company}",
        ]

        if getattr(job, "description", ""):
            parts.append(f"Description: {job.description}")

        required_skills = getattr(job, "required_skills", [])
        if required_skills:
            parts.append("Required skills: " + ", ".join(required_skills))

        experience_required = getattr(job, "experience_required", None)
        if experience_required:
            parts.append(f"Experience required: {experience_required}")

        location = getattr(job, "location", "")
        if location:
            parts.append(f"Location: {location}")

        return " | ".join(parts)
