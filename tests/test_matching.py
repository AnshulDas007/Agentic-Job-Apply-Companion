"""
Tests for the matching/relevance scoring layer.

Tests the scoring components, embedding manager, vector store, and
the full RelevanceScorer integration.
"""

import pytest

from backend.parsing.profile_schema import (
    CandidateProfile,
    ContactInfo,
    Education,
    Experience,
    Project,
)
from backend.matching.scorer import (
    MatchResult,
    RelevanceScorer,
    score_experience_relevance,
    score_location_fit,
    score_skill_match,
    _normalize_skill,
)
from backend.matching.embeddings import EmbeddingManager
from backend.matching.vector_store import VectorStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_profile():
    """A realistic candidate profile for testing."""
    return CandidateProfile(
        name="Anshul Das",
        contact=ContactInfo(
            address="Bangalore, India",
            github_url="https://github.com/AnshulDas007",
            linkedin_url="https://linkedin.com/in/anshuldas",
            email="anshuldas42@gmail.com",
            phone="+91-9876543210",
        ),
        experience=[
            Experience(
                type="internship",
                title="Software Engineering Intern",
                company="TechCorp",
                duration_months=6,
                start_date="2025-01",
                end_date="2025-06",
                description="Built backend APIs in Python and FastAPI. "
                            "Worked on CI/CD pipelines and cloud deployments.",
                is_fresher_relevant=True,
            ),
        ],
        projects=[
            Project(
                name="Deep Research Copilot",
                description="An AI-powered research assistant using LLMs "
                            "for document analysis and knowledge extraction.",
                github_url="https://github.com/AnshulDas007/deep-research-copilot",
                tech_stack=["Python", "LangChain", "FastAPI", "ChromaDB"],
            ),
            Project(
                name="Job Application Bot",
                description="Automated job application system with "
                            "fraud detection and form filling.",
                tech_stack=["Python", "Playwright", "Pydantic"],
            ),
        ],
        skills=[
            "Python", "JavaScript", "FastAPI", "React",
            "Docker", "Git", "PostgreSQL", "LangChain",
            "Machine Learning", "Playwright",
        ],
        education=[
            Education(
                institution="IIT Bangalore",
                degree="B.Tech",
                field_of_study="Computer Science",
                start_date="2022-08",
                end_date="2026-05",
            ),
        ],
    )


@pytest.fixture
def no_experience_profile():
    """A fresher profile with no work experience."""
    return CandidateProfile(
        name="Fresh Grad",
        contact=ContactInfo(
            address="Mumbai, India",
            github_url="https://github.com/freshgrad",
            linkedin_url="https://linkedin.com/in/freshgrad",
            email="fresh@example.com",
            phone="+91-1234567890",
        ),
        experience=[],
        projects=[
            Project(
                name="Todo App",
                description="A simple todo application.",
                tech_stack=["React", "Node.js"],
            ),
        ],
        skills=["JavaScript", "React", "Node.js", "HTML", "CSS"],
        education=[],
    )


class MockJob:
    """Minimal mock job listing for testing."""

    def __init__(self, **kwargs):
        self.id = kwargs.get("id", "test-job-001")
        self.title = kwargs.get("title", "Software Engineer")
        self.company = kwargs.get("company", "Acme Corp")
        self.url = kwargs.get("url", "https://acme.com/jobs/se")
        self.source = kwargs.get("source", "greenhouse")
        self.location = kwargs.get("location", "Remote")
        self.description = kwargs.get("description", "")
        self.required_skills = kwargs.get("required_skills", [])
        self.experience_required = kwargs.get("experience_required", None)
        self.salary_text = kwargs.get("salary_text", None)


# ---------------------------------------------------------------------------
# Skill normalization tests
# ---------------------------------------------------------------------------

class TestSkillNormalization:
    def test_lowercase(self):
        assert _normalize_skill("Python") == "python"

    def test_alias_js(self):
        assert _normalize_skill("JS") == "javascript"

    def test_alias_react_js(self):
        assert _normalize_skill("React.js") == "react"

    def test_alias_node(self):
        assert _normalize_skill("Node") == "nodejs"

    def test_alias_cpp(self):
        assert _normalize_skill("C++") == "cpp"

    def test_alias_k8s(self):
        assert _normalize_skill("k8s") == "kubernetes"

    def test_no_alias(self):
        assert _normalize_skill("FastAPI") == "fastapi"

    def test_whitespace_stripped(self):
        assert _normalize_skill("  Python  ") == "python"


# ---------------------------------------------------------------------------
# Skill match scoring tests
# ---------------------------------------------------------------------------

class TestSkillMatchScoring:
    def test_perfect_match(self):
        score = score_skill_match(
            candidate_skills=["Python", "React", "Docker"],
            required_skills=["Python", "React", "Docker"],
        )
        assert score == 1.0

    def test_partial_match(self):
        score = score_skill_match(
            candidate_skills=["Python", "React"],
            required_skills=["Python", "React", "Kubernetes", "Go"],
        )
        assert 0.4 <= score <= 0.6  # 2/4 = 0.5

    def test_no_match(self):
        score = score_skill_match(
            candidate_skills=["Python", "React"],
            required_skills=["Java", "Spring", "Scala"],
        )
        assert score == 0.0

    def test_alias_matching(self):
        """JS alias should match JavaScript."""
        score = score_skill_match(
            candidate_skills=["JavaScript"],
            required_skills=["JS"],
        )
        assert score == 1.0

    def test_empty_candidate_skills(self):
        score = score_skill_match(
            candidate_skills=[],
            required_skills=["Python"],
        )
        assert score == 0.0

    def test_empty_required_skills_with_description(self):
        """When no explicit skills, extract from description."""
        score = score_skill_match(
            candidate_skills=["Python", "Docker", "FastAPI"],
            required_skills=[],
            job_description="We need someone proficient in Python and Docker.",
        )
        assert score > 0.5  # Should find Python and Docker

    def test_empty_required_skills_no_description(self):
        """Neutral score when we can't determine requirements."""
        score = score_skill_match(
            candidate_skills=["Python"],
            required_skills=[],
            job_description="",
        )
        assert score == 0.5


# ---------------------------------------------------------------------------
# Experience relevance tests
# ---------------------------------------------------------------------------

class TestExperienceRelevance:
    def test_matching_title(self, sample_profile):
        score = score_experience_relevance(
            profile=sample_profile,
            job_title="Software Engineering Intern",
            job_description="Python backend development.",
        )
        assert score > 0.5

    def test_years_requirement_met(self, sample_profile):
        """6 months internship vs 0+ years requirement."""
        score = score_experience_relevance(
            profile=sample_profile,
            job_title="Backend Developer",
            experience_required="0+ years",
        )
        assert score >= 0.5

    def test_years_requirement_not_met(self, sample_profile):
        """6 months internship vs 5+ years requirement."""
        score = score_experience_relevance(
            profile=sample_profile,
            job_title="Senior Backend Developer",
            experience_required="5+ years",
        )
        assert score < 0.5

    def test_no_experience_entry_level(self, no_experience_profile):
        score = score_experience_relevance(
            profile=no_experience_profile,
            job_title="Junior Developer Intern",
            job_description="Entry level position for fresh graduates.",
        )
        assert score >= 0.5

    def test_no_experience_senior_role(self, no_experience_profile):
        score = score_experience_relevance(
            profile=no_experience_profile,
            job_title="Senior Staff Engineer",
            job_description="Lead a team of engineers.",
        )
        assert score < 0.4


# ---------------------------------------------------------------------------
# Location fit tests
# ---------------------------------------------------------------------------

class TestLocationFit:
    def test_remote_perfect_fit(self, sample_profile):
        score = score_location_fit(sample_profile, "Remote")
        assert score == 1.0

    def test_wfh(self, sample_profile):
        score = score_location_fit(sample_profile, "Work From Home")
        assert score == 1.0

    def test_hybrid(self, sample_profile):
        score = score_location_fit(sample_profile, "Hybrid - Bangalore")
        assert score == 0.8

    def test_same_city(self, sample_profile):
        score = score_location_fit(sample_profile, "Bangalore, India")
        assert score >= 0.8

    def test_different_city(self, sample_profile):
        score = score_location_fit(sample_profile, "San Francisco, CA, USA")
        assert score <= 0.6

    def test_no_location(self, sample_profile):
        score = score_location_fit(sample_profile, "")
        assert score == 0.7  # Slightly positive default

    def test_anywhere(self, sample_profile):
        score = score_location_fit(sample_profile, "Anywhere")
        assert score == 1.0


# ---------------------------------------------------------------------------
# MatchResult tests
# ---------------------------------------------------------------------------

class TestMatchResult:
    def test_strong_match_summary(self):
        result = MatchResult(
            job_id="test-1",
            title="Python Dev",
            company="Acme",
            relevance_score=0.85,
            is_strong_match=True,
            meets_threshold=True,
        )
        assert "STRONG" in result.summary
        assert "Python Dev" in result.summary

    def test_pass_summary(self):
        result = MatchResult(
            job_id="test-2",
            title="React Dev",
            company="Foo Inc",
            relevance_score=0.70,
            is_strong_match=False,
            meets_threshold=True,
        )
        assert "PASS" in result.summary

    def test_skip_summary(self):
        result = MatchResult(
            job_id="test-3",
            title="Java Dev",
            company="Bar LLC",
            relevance_score=0.30,
            is_strong_match=False,
            meets_threshold=False,
        )
        assert "SKIP" in result.summary

    def test_breakdown_in_summary(self):
        result = MatchResult(
            job_id="test-4",
            title="Dev",
            company="Co",
            relevance_score=0.75,
            breakdown={"skill_match": 0.80, "embedding_similarity": 0.70},
            meets_threshold=True,
        )
        assert "skill_match" in result.summary


# ---------------------------------------------------------------------------
# EmbeddingManager tests
# ---------------------------------------------------------------------------

class TestEmbeddingManager:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.em = EmbeddingManager()

    def test_embed_text_returns_list(self):
        vec = self.em.embed_text("Hello world")
        assert isinstance(vec, list)
        assert len(vec) > 0
        assert all(isinstance(v, float) for v in vec)

    def test_embed_texts_batch(self):
        vecs = self.em.embed_texts(["Hello", "World", "Python"])
        assert len(vecs) == 3
        assert all(len(v) == len(vecs[0]) for v in vecs)

    def test_embed_empty_list(self):
        vecs = self.em.embed_texts([])
        assert vecs == []

    def test_similar_texts_high_similarity(self):
        v1 = self.em.embed_text("Python backend developer with FastAPI experience")
        v2 = self.em.embed_text("Python backend engineer experienced with FastAPI")
        sim = sum(a * b for a, b in zip(v1, v2))
        assert sim > 0.8  # Very similar texts

    def test_dissimilar_texts_low_similarity(self):
        v1 = self.em.embed_text("Python backend developer with FastAPI experience")
        v2 = self.em.embed_text("Experienced chef specializing in Italian cuisine")
        sim = sum(a * b for a, b in zip(v1, v2))
        assert sim < 0.5  # Dissimilar texts

    def test_profile_to_text(self, sample_profile):
        text = self.em.profile_to_text(sample_profile)
        assert "Python" in text
        assert "TechCorp" in text
        assert "Deep Research Copilot" in text
        assert "IIT Bangalore" in text

    def test_job_to_text(self):
        job = MockJob(
            title="Backend Developer",
            company="Stripe",
            description="Build payment APIs",
            required_skills=["Python", "PostgreSQL"],
            location="Remote",
        )
        text = self.em.job_to_text(job)
        assert "Backend Developer" in text
        assert "Stripe" in text
        assert "Python" in text
        assert "Remote" in text

    def test_dimension_positive(self):
        assert self.em.dimension > 0


# ---------------------------------------------------------------------------
# VectorStore tests
# ---------------------------------------------------------------------------

class TestVectorStore:
    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        """Use a temporary directory for ChromaDB storage."""
        # Create a temporary config
        config = {
            "vector_store": {
                "collection_name": "test_jobs",
                "persist_directory": str(tmp_path / "chroma_test"),
            },
            "deduplication": {
                "method": "url_hash",
                "similarity_threshold": 0.95,
            },
        }
        import yaml as _yaml
        config_path = tmp_path / "test_matching_config.yaml"
        with open(config_path, "w") as f:
            _yaml.dump(config, f)

        self.store = VectorStore(config_path=config_path)
        self.em = EmbeddingManager()

    def test_add_and_count(self):
        emb = self.em.embed_text("Python developer role")
        added = self.store.add_job("job-1", emb, {"title": "Python Dev"})
        assert added
        assert self.store.count == 1

    def test_duplicate_rejected(self):
        emb = self.em.embed_text("Python developer role")
        self.store.add_job("job-1", emb)
        added = self.store.add_job("job-1", emb)
        assert not added
        assert self.store.count == 1

    def test_batch_add(self):
        texts = ["Python dev", "Java dev", "React dev"]
        embs = self.em.embed_texts(texts)
        count = self.store.add_jobs_batch(
            job_ids=["j1", "j2", "j3"],
            embeddings=embs,
            metadatas=[{"title": t} for t in texts],
        )
        assert count == 3
        assert self.store.count == 3

    def test_batch_add_with_duplicates(self):
        emb = self.em.embed_text("Python dev")
        self.store.add_job("j1", emb)

        texts = ["Python dev", "Java dev"]
        embs = self.em.embed_texts(texts)
        count = self.store.add_jobs_batch(
            job_ids=["j1", "j2"],  # j1 is duplicate
            embeddings=embs,
        )
        assert count == 1  # Only j2 added
        assert self.store.count == 2

    def test_query_returns_results(self):
        texts = ["Python backend developer", "Java enterprise architect", "React frontend developer"]
        embs = self.em.embed_texts(texts)
        self.store.add_jobs_batch(
            job_ids=["j1", "j2", "j3"],
            embeddings=embs,
            metadatas=[{"title": t} for t in texts],
        )

        query_emb = self.em.embed_text("Python backend engineer")
        results = self.store.query(query_emb, top_k=2)
        assert len(results) == 2
        # Python backend dev should be the top result
        assert results[0]["metadata"]["title"] == "Python backend developer"
        assert results[0]["score"] > 0.5

    def test_query_empty_store(self):
        query_emb = self.em.embed_text("Python dev")
        results = self.store.query(query_emb)
        assert results == []

    def test_get_by_id(self):
        emb = self.em.embed_text("Test job")
        self.store.add_job("j1", emb, {"title": "Test"}, "Test job listing")
        result = self.store.get_by_id("j1")
        assert result is not None
        assert result["id"] == "j1"
        assert result["metadata"]["title"] == "Test"
        assert result["document"] == "Test job listing"

    def test_get_by_id_missing(self):
        result = self.store.get_by_id("nonexistent")
        assert result is None

    def test_delete_job(self):
        emb = self.em.embed_text("Test job")
        self.store.add_job("j1", emb)
        assert self.store.count == 1
        self.store.delete_job("j1")
        assert self.store.count == 0

    def test_clear(self):
        embs = self.em.embed_texts(["a", "b", "c"])
        self.store.add_jobs_batch(["j1", "j2", "j3"], embs)
        assert self.store.count == 3
        self.store.clear()
        assert self.store.count == 0

    def test_generate_job_id_deterministic(self):
        id1 = VectorStore.generate_job_id("https://acme.com/1", "Acme", "Dev")
        id2 = VectorStore.generate_job_id("https://acme.com/1", "Acme", "Dev")
        assert id1 == id2

    def test_generate_job_id_unique(self):
        id1 = VectorStore.generate_job_id("https://acme.com/1", "Acme", "Dev")
        id2 = VectorStore.generate_job_id("https://acme.com/2", "Acme", "Dev")
        assert id1 != id2


# ---------------------------------------------------------------------------
# Full RelevanceScorer integration tests
# ---------------------------------------------------------------------------

class TestRelevanceScorer:
    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        """Set up scorer with temp vector store."""
        import yaml as _yaml

        config = {
            "embedding": {
                "model_name": "all-MiniLM-L6-v2",
                "cache_dir": str(tmp_path / "models"),
            },
            "weights": {
                "embedding_similarity": 0.40,
                "skill_match": 0.30,
                "experience_relevance": 0.20,
                "location_fit": 0.10,
            },
            "thresholds": {
                "embedding_prefilter": 0.35,
                "minimum_match_score": 0.65,
                "strong_match_score": 0.80,
            },
            "vector_store": {
                "collection_name": "test_scoring",
                "persist_directory": str(tmp_path / "chroma_scoring"),
            },
            "deduplication": {
                "method": "url_hash",
            },
        }
        config_path = tmp_path / "scoring_config.yaml"
        with open(config_path, "w") as f:
            _yaml.dump(config, f)

        self.scorer = RelevanceScorer(config_path=config_path)

    def test_good_match(self, sample_profile):
        """A Python backend job should score well for a Python-skilled candidate."""
        job = MockJob(
            title="Python Backend Developer",
            company="TechStartup",
            description="Build APIs with Python and FastAPI. "
                        "Experience with Docker and PostgreSQL preferred.",
            required_skills=["Python", "FastAPI", "Docker", "PostgreSQL"],
            location="Remote",
            experience_required="0-1 years",
        )
        result = self.scorer.score_job(sample_profile, job)
        assert result.relevance_score > 0.5
        assert result.meets_threshold or result.relevance_score >= 0.5
        assert result.breakdown["skill_match"] > 0.5
        assert result.breakdown["location_fit"] == 1.0  # Remote

    def test_poor_match(self, sample_profile):
        """A Java enterprise job should score poorly for a Python-focused candidate."""
        job = MockJob(
            title="Senior Java Enterprise Architect",
            company="BigBank",
            description="Design and implement enterprise Java solutions. "
                        "10+ years of Java/Spring required. "
                        "Lead a team of 20 engineers.",
            required_skills=["Java", "Spring Boot", "Oracle", "Microservices"],
            location="New York, NY",
            experience_required="10+ years",
        )
        result = self.scorer.score_job(sample_profile, job)
        assert result.relevance_score < 0.6
        assert result.breakdown["skill_match"] < 0.3
        assert result.breakdown["experience_relevance"] < 0.5

    def test_score_batch(self, sample_profile):
        """Batch scoring should return sorted results."""
        jobs = [
            MockJob(
                id="good-1",
                title="Python Developer",
                description="Python and FastAPI",
                required_skills=["Python", "FastAPI"],
                location="Remote",
            ),
            MockJob(
                id="bad-1",
                title="Chef Manager",
                description="Manage a restaurant kitchen. Culinary degree required.",
                required_skills=["Culinary Arts", "Food Safety"],
                location="Chicago, IL",
            ),
            MockJob(
                id="ok-1",
                title="Full Stack Developer",
                description="React and Node.js development",
                required_skills=["React", "JavaScript", "Node.js"],
                location="Remote",
            ),
        ]
        results = self.scorer.score_batch(sample_profile, jobs, use_prefilter=False)
        assert len(results) == 3
        # Results should be sorted descending
        scores = [r.relevance_score for r in results]
        assert scores == sorted(scores, reverse=True)
        # Chef job should be last
        assert results[-1].title == "Chef Manager"

    def test_score_batch_with_prefilter(self, sample_profile):
        """Pre-filter should remove obvious mismatches before full scoring."""
        jobs = [
            MockJob(
                id="match-1",
                title="Python Backend Developer",
                description="Build APIs with Python and FastAPI.",
                required_skills=["Python", "FastAPI"],
                location="Remote",
            ),
            MockJob(
                id="mismatch-1",
                title="Executive Chef",
                description="Lead a 5-star restaurant kitchen team. "
                            "Michelin-star experience required.",
                required_skills=["Culinary Management", "Haute Cuisine"],
                location="Paris, France",
            ),
        ]
        results = self.scorer.score_batch(sample_profile, jobs, use_prefilter=True)
        assert len(results) == 2
        # Both should appear, but mismatch may have passed_prefilter=False
        mismatch = [r for r in results if r.title == "Executive Chef"]
        match = [r for r in results if r.title == "Python Backend Developer"]
        assert len(match) == 1
        assert match[0].relevance_score > mismatch[0].relevance_score

    def test_store_and_find_similar(self, sample_profile):
        """Store embeddings and find similar jobs."""
        jobs = [
            MockJob(id="s1", title="Python Dev", description="Python backend"),
            MockJob(id="s2", title="Java Dev", description="Java enterprise"),
        ]
        stored = self.scorer.store_job_embeddings(jobs)
        assert stored == 2

        similar = self.scorer.find_similar_jobs(sample_profile, top_k=5)
        assert len(similar) == 2
        # Python dev should rank higher
        assert similar[0]["metadata"]["title"] == "Python Dev"
