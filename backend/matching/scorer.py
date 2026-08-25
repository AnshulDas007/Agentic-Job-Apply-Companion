"""
Multi-signal relevance scorer for matching job listings against a candidate profile.

Combines four scoring components (config-driven weights):
  1. Embedding similarity — cosine similarity of profile vs job embeddings
  2. Skill match — percentage of required skills the candidate has
  3. Experience relevance — how well the candidate's experience fits
  4. Location fit — remote, relocation, or geographic match

Uses a two-stage pipeline:
  - Stage 1: Embedding pre-filter (fast, removes obvious mismatches)
  - Stage 2: Full multi-signal scoring on survivors

Only listings that pass both the fraud filter AND meet the minimum
match score are eligible for application.
"""

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yaml

from backend.matching.embeddings import EmbeddingManager
from backend.matching.vector_store import VectorStore
from backend.parsing.profile_schema import CandidateProfile

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


# ---------------------------------------------------------------------------
# Scoring result
# ---------------------------------------------------------------------------

@dataclass
class MatchResult:
    """Result of scoring a job listing against the candidate profile."""

    job_id: str
    title: str = ""
    company: str = ""
    relevance_score: float = 0.0
    breakdown: Dict[str, float] = field(default_factory=dict)
    passed_prefilter: bool = True
    meets_threshold: bool = False
    is_strong_match: bool = False
    threshold_used: float = 0.65

    @property
    def summary(self) -> str:
        """Human-readable match summary."""
        status = "STRONG" if self.is_strong_match else ("PASS" if self.meets_threshold else "SKIP")
        parts = [f"[{status}] {self.title} @ {self.company}: {self.relevance_score:.2f}"]
        if self.breakdown:
            details = ", ".join(f"{k}={v:.2f}" for k, v in self.breakdown.items())
            parts.append(f"  ({details})")
        return " ".join(parts)


# ---------------------------------------------------------------------------
# Individual scoring components
# ---------------------------------------------------------------------------

def _normalize_skill(skill: str) -> str:
    """Normalize a skill string for comparison."""
    s = skill.lower().strip()
    # Common aliases
    aliases = {
        "js": "javascript",
        "ts": "typescript",
        "py": "python",
        "react.js": "react",
        "reactjs": "react",
        "node.js": "nodejs",
        "node": "nodejs",
        "vue.js": "vue",
        "vuejs": "vue",
        "next.js": "nextjs",
        "c++": "cpp",
        "c#": "csharp",
        "golang": "go",
        "ml": "machine learning",
        "dl": "deep learning",
        "ai": "artificial intelligence",
        "k8s": "kubernetes",
        "tf": "terraform",
        "aws": "amazon web services",
        "gcp": "google cloud platform",
        "azure": "microsoft azure",
        "postgres": "postgresql",
        "mongo": "mongodb",
    }
    return aliases.get(s, s)


def score_skill_match(
    candidate_skills: List[str],
    required_skills: List[str],
    job_description: str = "",
) -> float:
    """
    Calculate skill overlap between candidate and job requirements.

    If required_skills is empty, attempts to extract skills from
    the job description text.

    Args:
        candidate_skills: The candidate's skills list.
        required_skills: Explicitly listed required skills from the job.
        job_description: Full job description text (fallback skill extraction).

    Returns:
        Float between 0.0 and 1.0 representing the match ratio.
    """
    if not candidate_skills:
        return 0.0

    normalized_candidate = {_normalize_skill(s) for s in candidate_skills}

    # If no explicit required_skills, try basic extraction from description
    job_skills = set()
    if required_skills:
        job_skills = {_normalize_skill(s) for s in required_skills}
    elif job_description:
        # Basic keyword extraction: look for candidate skills mentioned in description
        desc_lower = job_description.lower()
        for skill in normalized_candidate:
            # Use word boundary matching to avoid false positives
            pattern = r'\b' + re.escape(skill) + r'\b'
            if re.search(pattern, desc_lower):
                job_skills.add(skill)

    if not job_skills:
        # Can't determine required skills — return a neutral score
        return 0.5

    matched = normalized_candidate & job_skills
    score = len(matched) / len(job_skills) if job_skills else 0.0
    return min(score, 1.0)


def score_experience_relevance(
    profile: CandidateProfile,
    job_title: str,
    job_description: str = "",
    experience_required: Optional[str] = None,
) -> float:
    """
    Score how relevant the candidate's experience is to the job.

    Considers:
    - Title similarity (keyword overlap)
    - Total months of experience vs. stated requirements
    - Type of experience (full_time weighs more than internship)

    Args:
        profile: The candidate's profile.
        job_title: The job listing title.
        job_description: Full job description text.
        experience_required: Experience requirement string (e.g., "2+ years").

    Returns:
        Float between 0.0 and 1.0.
    """
    if not profile.experience:
        # No experience — base score on whether the job looks entry-level
        entry_level_keywords = {
            "intern", "fresher", "entry", "junior", "graduate",
            "trainee", "associate", "new grad",
        }
        combined = f"{job_title} {job_description}".lower()
        if any(kw in combined for kw in entry_level_keywords):
            return 0.6  # Entry-level job, no experience is OK
        return 0.2  # Non-entry job, no experience is a weak signal

    # Calculate total experience months
    total_months = sum(exp.duration_months for exp in profile.experience)
    total_years = total_months / 12.0

    # Check against stated requirement
    years_score = 1.0
    if experience_required:
        required_match = re.search(r'(\d+)\+?\s*(?:years?|yrs?)', experience_required.lower())
        if required_match:
            required_years = int(required_match.group(1))
            if total_years >= required_years:
                years_score = 1.0
            elif total_years >= required_years * 0.5:
                years_score = 0.6  # Have at least half the required
            else:
                years_score = 0.3  # Significantly under-qualified

    # Title relevance: keyword overlap between experience titles and job title
    job_title_words = set(job_title.lower().split())
    title_matches = 0
    for exp in profile.experience:
        exp_words = set(exp.title.lower().split())
        if job_title_words & exp_words:
            title_matches += 1

    title_score = min(title_matches / max(len(profile.experience), 1), 1.0) if profile.experience else 0.0

    # Weighted combination
    return 0.5 * years_score + 0.5 * title_score


def score_location_fit(
    profile: CandidateProfile,
    job_location: str,
) -> float:
    """
    Score how well the job location matches the candidate's location/preferences.

    Args:
        profile: The candidate's profile.
        job_location: The job's location string.

    Returns:
        Float between 0.0 and 1.0.
    """
    if not job_location:
        return 0.7  # No location info — slightly positive default

    loc_lower = job_location.lower().strip()

    # Remote is always a perfect fit
    remote_keywords = {"remote", "work from home", "wfh", "anywhere", "distributed"}
    if any(kw in loc_lower for kw in remote_keywords):
        return 1.0

    # Hybrid is a good fit
    if "hybrid" in loc_lower:
        return 0.8

    # Check if candidate's address/location overlaps with job location
    candidate_location = profile.contact.address.lower() if profile.contact.address else ""
    if candidate_location:
        # Check for city/state/country overlap
        candidate_parts = set(re.split(r'[,\s]+', candidate_location))
        job_parts = set(re.split(r'[,\s]+', loc_lower))

        # Remove noise words
        noise = {"", "st", "rd", "ave", "blvd", "street", "road", "apt", "suite", "floor"}
        candidate_parts -= noise
        job_parts -= noise

        overlap = candidate_parts & job_parts
        if overlap:
            return 0.9  # Good location match

    # Unknown or different location — moderate score (candidate might relocate)
    return 0.5


# ---------------------------------------------------------------------------
# Main scorer
# ---------------------------------------------------------------------------

class RelevanceScorer:
    """
    Multi-signal relevance scorer for job listings.

    Orchestrates:
    1. Embedding pre-filter (fast cosine similarity check)
    2. Full multi-signal scoring with configurable weights

    Usage:
        scorer = RelevanceScorer()
        # Score a single listing
        result = scorer.score_job(profile, job_listing)

        # Score a batch (uses pre-filter)
        results = scorer.score_batch(profile, job_listings)
    """

    def __init__(
        self,
        config_path: Path = MATCHING_CONFIG_PATH,
        embedding_manager: Optional[EmbeddingManager] = None,
        vector_store: Optional[VectorStore] = None,
    ):
        config = _load_matching_config(config_path)

        # Scoring weights
        weights = config.get("weights", {})
        self.w_embedding: float = weights.get("embedding_similarity", 0.40)
        self.w_skill: float = weights.get("skill_match", 0.30)
        self.w_experience: float = weights.get("experience_relevance", 0.20)
        self.w_location: float = weights.get("location_fit", 0.10)

        # Thresholds
        thresholds = config.get("thresholds", {})
        self.prefilter_threshold: float = thresholds.get("embedding_prefilter", 0.35)
        self.min_match_score: float = thresholds.get("minimum_match_score", 0.65)
        self.strong_match_score: float = thresholds.get("strong_match_score", 0.80)

        # Components (injectable for testing)
        self._embeddings = embedding_manager or EmbeddingManager(config_path)
        self._vector_store = vector_store or VectorStore(config_path)

        # Cached profile embedding
        self._profile_embedding: Optional[List[float]] = None
        self._profile_text: Optional[str] = None

    def _get_profile_embedding(self, profile: CandidateProfile) -> List[float]:
        """Get or compute the profile embedding (cached per profile text)."""
        text = self._embeddings.profile_to_text(profile)
        if self._profile_text != text or self._profile_embedding is None:
            self._profile_text = text
            self._profile_embedding = self._embeddings.embed_text(text)
        return self._profile_embedding

    def score_job(self, profile: CandidateProfile, job) -> MatchResult:
        """
        Score a single job listing against the candidate profile.

        Args:
            profile: The candidate's profile.
            job: A job listing object (RawJobListing or ProcessedJobListing).

        Returns:
            MatchResult with score, breakdown, and pass/fail status.
        """
        job_id = getattr(job, "id", "") or VectorStore.generate_job_id(
            getattr(job, "url", ""),
            getattr(job, "company", ""),
            getattr(job, "title", ""),
        )

        # 1. Embedding similarity
        profile_emb = self._get_profile_embedding(profile)
        job_text = self._embeddings.job_to_text(job)
        job_emb = self._embeddings.embed_text(job_text)

        # Cosine similarity (embeddings are normalized)
        embedding_sim = sum(a * b for a, b in zip(profile_emb, job_emb))
        embedding_sim = max(0.0, min(1.0, embedding_sim))  # Clamp

        # 2. Skill match
        required_skills = getattr(job, "required_skills", [])
        description = getattr(job, "description", "")
        skill_score = score_skill_match(profile.skills, required_skills, description)

        # 3. Experience relevance
        exp_score = score_experience_relevance(
            profile,
            getattr(job, "title", ""),
            description,
            getattr(job, "experience_required", None),
        )

        # 4. Location fit
        loc_score = score_location_fit(profile, getattr(job, "location", ""))

        # Weighted combination
        total_weight = self.w_embedding + self.w_skill + self.w_experience + self.w_location
        if total_weight > 0:
            relevance_score = (
                self.w_embedding * embedding_sim
                + self.w_skill * skill_score
                + self.w_experience * exp_score
                + self.w_location * loc_score
            ) / total_weight
        else:
            relevance_score = 0.0

        relevance_score = round(relevance_score, 4)

        breakdown = {
            "embedding_similarity": round(embedding_sim, 4),
            "skill_match": round(skill_score, 4),
            "experience_relevance": round(exp_score, 4),
            "location_fit": round(loc_score, 4),
        }

        result = MatchResult(
            job_id=job_id,
            title=getattr(job, "title", ""),
            company=getattr(job, "company", ""),
            relevance_score=relevance_score,
            breakdown=breakdown,
            passed_prefilter=True,
            meets_threshold=relevance_score >= self.min_match_score,
            is_strong_match=relevance_score >= self.strong_match_score,
            threshold_used=self.min_match_score,
        )

        logger.info("Match: %s", result.summary)
        return result

    def prefilter(
        self,
        profile: CandidateProfile,
        jobs: list,
    ) -> Tuple[List, List]:
        """
        Fast embedding pre-filter to remove obvious mismatches.

        Args:
            profile: The candidate's profile.
            jobs: List of job listing objects.

        Returns:
            Tuple of (passed_jobs, filtered_out_jobs).
        """
        if not jobs:
            return [], []

        profile_emb = self._get_profile_embedding(profile)

        # Embed all jobs
        job_texts = [self._embeddings.job_to_text(j) for j in jobs]
        job_embs = self._embeddings.embed_texts(job_texts)

        passed = []
        filtered = []

        for job, job_emb in zip(jobs, job_embs):
            similarity = sum(a * b for a, b in zip(profile_emb, job_emb))
            if similarity >= self.prefilter_threshold:
                passed.append(job)
            else:
                filtered.append(job)

        logger.info(
            "Pre-filter: %d/%d jobs passed (threshold=%.2f)",
            len(passed), len(jobs), self.prefilter_threshold,
        )
        return passed, filtered

    def score_batch(
        self,
        profile: CandidateProfile,
        jobs: list,
        use_prefilter: bool = True,
    ) -> List[MatchResult]:
        """
        Score a batch of job listings, optionally with pre-filtering.

        Args:
            profile: The candidate's profile.
            jobs: List of job listing objects.
            use_prefilter: If True, apply embedding pre-filter first.

        Returns:
            List of MatchResult, sorted by relevance_score descending.
            Includes results for pre-filtered jobs (with passed_prefilter=False).
        """
        results = []

        if use_prefilter:
            passed_jobs, filtered_jobs = self.prefilter(profile, jobs)

            # Mark filtered jobs
            for job in filtered_jobs:
                job_id = getattr(job, "id", "") or VectorStore.generate_job_id(
                    getattr(job, "url", ""),
                    getattr(job, "company", ""),
                    getattr(job, "title", ""),
                )
                results.append(MatchResult(
                    job_id=job_id,
                    title=getattr(job, "title", ""),
                    company=getattr(job, "company", ""),
                    relevance_score=0.0,
                    passed_prefilter=False,
                    meets_threshold=False,
                    is_strong_match=False,
                    threshold_used=self.min_match_score,
                ))
        else:
            passed_jobs = jobs

        # Full scoring on passed jobs
        for job in passed_jobs:
            result = self.score_job(profile, job)
            results.append(result)

        # Sort by score descending
        results.sort(key=lambda r: r.relevance_score, reverse=True)
        return results

    def store_job_embeddings(self, jobs: list) -> int:
        """
        Compute and store embeddings for a batch of jobs in the vector store.

        Useful for building up the embedding database from scraped listings.

        Args:
            jobs: List of job listing objects.

        Returns:
            Number of new jobs added (excluding duplicates).
        """
        if not jobs:
            return 0

        job_texts = [self._embeddings.job_to_text(j) for j in jobs]
        job_embs = self._embeddings.embed_texts(job_texts)

        job_ids = []
        metadatas = []
        documents = []

        for job, text in zip(jobs, job_texts):
            jid = getattr(job, "id", "") or VectorStore.generate_job_id(
                getattr(job, "url", ""),
                getattr(job, "company", ""),
                getattr(job, "title", ""),
            )
            job_ids.append(jid)
            metadatas.append({
                "title": getattr(job, "title", ""),
                "company": getattr(job, "company", ""),
                "url": getattr(job, "url", ""),
                "source": getattr(job, "source", ""),
                "location": getattr(job, "location", ""),
            })
            documents.append(text)

        return self._vector_store.add_jobs_batch(
            job_ids=job_ids,
            embeddings=job_embs,
            metadatas=metadatas,
            documents=documents,
        )

    def find_similar_jobs(
        self,
        profile: CandidateProfile,
        top_k: int = 20,
    ) -> List[Dict]:
        """
        Find the most similar stored jobs to the candidate profile.

        Searches the vector store using the profile embedding.

        Args:
            profile: The candidate's profile.
            top_k: Maximum number of results.

        Returns:
            List of dicts with id, score, metadata, document.
        """
        profile_emb = self._get_profile_embedding(profile)
        return self._vector_store.query(query_embedding=profile_emb, top_k=top_k)
