"""
Tests for the orchestrator's two-phase pipeline and run_pipeline.py.

Tests the scrape-and-score phase (dedupe, filtering, scoring) and
the apply-tier1 phase (with mocked form filler).
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from backend.orchestrator import (
    PlatformTier,
    ScrapeAndScoreResult,
    _generate_job_id,
    _get_platform_tier,
    generate_daily_digest,
    load_jobs_seen,
    run_apply_tier1,
    run_scrape_and_score,
    save_jobs_seen,
)
from backend.scrapers.job_schema import RawJobListing


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_job():
    """A sample Greenhouse job listing."""
    return RawJobListing(
        title="Backend Engineer",
        company="Acme Corp",
        url="https://boards.greenhouse.io/acme/123",
        source="greenhouse",
        description="Build backend services in Python.",
        company_url="https://acme.com",
        location="Remote",
    )


@pytest.fixture
def sample_linkedin_job():
    """A sample LinkedIn job listing (Tier 2)."""
    return RawJobListing(
        title="Software Engineer",
        company="Big Corp",
        url="https://linkedin.com/jobs/view/456",
        source="linkedin",
        description="Standard software engineering role.",
        company_url="https://bigcorp.com",
    )


@pytest.fixture
def mock_profile():
    """A mock CandidateProfile."""
    profile = MagicMock()
    profile.name = "Test User"
    profile.experience = [MagicMock()]
    profile.projects = [MagicMock()]
    profile.skills = ["Python", "SQL"]
    return profile


@pytest.fixture
def tmp_jobs_seen(tmp_path):
    """A temporary jobs_seen.json file path."""
    return tmp_path / "jobs_seen.json"


# ---------------------------------------------------------------------------
# Platform tier tests
# ---------------------------------------------------------------------------

class TestPlatformTier:
    """Tests for platform tier classification."""

    def test_greenhouse_is_tier1(self):
        assert _get_platform_tier("greenhouse") == PlatformTier.TIER_1

    def test_lever_is_tier1(self):
        assert _get_platform_tier("lever") == PlatformTier.TIER_1

    def test_linkedin_is_tier2(self):
        assert _get_platform_tier("linkedin") == PlatformTier.TIER_2

    def test_indeed_is_tier2(self):
        assert _get_platform_tier("indeed") == PlatformTier.TIER_2

    def test_naukri_is_tier2(self):
        assert _get_platform_tier("naukri") == PlatformTier.TIER_2

    def test_case_insensitive(self):
        assert _get_platform_tier("LinkedIn") == PlatformTier.TIER_2


# ---------------------------------------------------------------------------
# Job ID generation tests
# ---------------------------------------------------------------------------

class TestJobIdGeneration:
    """Tests for _generate_job_id."""

    def test_deterministic(self, sample_job):
        id1 = _generate_job_id(sample_job)
        id2 = _generate_job_id(sample_job)
        assert id1 == id2

    def test_different_jobs_different_ids(self, sample_job, sample_linkedin_job):
        assert _generate_job_id(sample_job) != _generate_job_id(sample_linkedin_job)

    def test_id_is_16_chars(self, sample_job):
        assert len(_generate_job_id(sample_job)) == 16


# ---------------------------------------------------------------------------
# Jobs seen persistence tests
# ---------------------------------------------------------------------------

class TestJobsSeen:
    """Tests for load/save jobs_seen.json."""

    def test_load_empty(self, tmp_jobs_seen):
        assert load_jobs_seen(tmp_jobs_seen) == {}

    def test_save_and_load(self, tmp_jobs_seen):
        data = {"abc123": {"first_seen": "2026-01-01", "status": "new"}}
        save_jobs_seen(data, tmp_jobs_seen)
        loaded = load_jobs_seen(tmp_jobs_seen)
        assert loaded == data

    def test_load_corrupted_json(self, tmp_jobs_seen):
        tmp_jobs_seen.write_text("not valid json")
        assert load_jobs_seen(tmp_jobs_seen) == {}


# ---------------------------------------------------------------------------
# Scrape and score tests
# ---------------------------------------------------------------------------

class TestScrapeAndScore:
    """Tests for run_scrape_and_score."""

    def test_basic_pipeline(self, mock_profile, sample_job, tmp_jobs_seen):
        """A job that passes fraud + scoring should appear as a candidate."""
        registry = MagicMock()
        registry.scrape_all.return_value = [sample_job]

        fraud_filter = MagicMock()
        fraud_result = MagicMock()
        fraud_result.passed = True
        fraud_result.summary = "PASSED"
        fraud_result.legitimacy_score = 0.90
        fraud_filter.check_listing.return_value = fraud_result

        scorer = MagicMock()
        score_result = MagicMock()
        score_result.relevance_score = 0.80
        score_result.breakdown = {}
        scorer.score_job.return_value = score_result

        with patch("backend.orchestrator.JOBS_SEEN_PATH", tmp_jobs_seen):
            result = run_scrape_and_score(
                profile=mock_profile,
                registry=registry,
                fraud_filter=fraud_filter,
                scorer=scorer,
                min_relevance_score=0.65,
            )

        assert result.total_scraped == 1
        assert len(result.candidates) == 1
        assert result.candidates[0]["title"] == "Backend Engineer"
        assert result.candidates[0]["tier"] == "tier1"

    def test_fraud_rejected(self, mock_profile, sample_job, tmp_jobs_seen):
        """A job that fails fraud filter should not be a candidate."""
        registry = MagicMock()
        registry.scrape_all.return_value = [sample_job]

        fraud_filter = MagicMock()
        fraud_result = MagicMock()
        fraud_result.passed = False
        fraud_result.summary = "BLOCKED: scam detected"
        fraud_filter.check_listing.return_value = fraud_result

        scorer = MagicMock()

        with patch("backend.orchestrator.JOBS_SEEN_PATH", tmp_jobs_seen):
            result = run_scrape_and_score(
                profile=mock_profile,
                registry=registry,
                fraud_filter=fraud_filter,
                scorer=scorer,
            )

        assert result.fraud_rejected == 1
        assert len(result.candidates) == 0

    def test_low_score_rejected(self, mock_profile, sample_job, tmp_jobs_seen):
        """A job with low relevance score should not be a candidate."""
        registry = MagicMock()
        registry.scrape_all.return_value = [sample_job]

        fraud_filter = MagicMock()
        fraud_result = MagicMock()
        fraud_result.passed = True
        fraud_result.summary = "PASSED"
        fraud_filter.check_listing.return_value = fraud_result

        scorer = MagicMock()
        score_result = MagicMock()
        score_result.relevance_score = 0.30  # below threshold
        scorer.score_job.return_value = score_result

        with patch("backend.orchestrator.JOBS_SEEN_PATH", tmp_jobs_seen):
            result = run_scrape_and_score(
                profile=mock_profile,
                registry=registry,
                fraud_filter=fraud_filter,
                scorer=scorer,
                min_relevance_score=0.65,
            )

        assert result.low_score_rejected == 1
        assert len(result.candidates) == 0

    def test_dedupe_skips_seen_jobs(self, mock_profile, sample_job, tmp_jobs_seen):
        """Jobs already in jobs_seen.json should be skipped."""
        job_id = _generate_job_id(sample_job)
        save_jobs_seen({job_id: {"first_seen": "2026-01-01", "status": "seen"}}, tmp_jobs_seen)

        registry = MagicMock()
        registry.scrape_all.return_value = [sample_job]

        fraud_filter = MagicMock()
        scorer = MagicMock()

        with patch("backend.orchestrator.JOBS_SEEN_PATH", tmp_jobs_seen):
            result = run_scrape_and_score(
                profile=mock_profile,
                registry=registry,
                fraud_filter=fraud_filter,
                scorer=scorer,
            )

        assert result.duplicates_skipped == 1
        assert len(result.candidates) == 0
        # Fraud filter should NOT have been called for a deduplicated job
        fraud_filter.check_listing.assert_not_called()

    def test_linkedin_job_is_tier2(self, mock_profile, sample_linkedin_job, tmp_jobs_seen):
        """LinkedIn jobs should be classified as Tier 2."""
        registry = MagicMock()
        registry.scrape_all.return_value = [sample_linkedin_job]

        fraud_filter = MagicMock()
        fraud_result = MagicMock()
        fraud_result.passed = True
        fraud_result.summary = "PASSED"
        fraud_result.legitimacy_score = 0.85
        fraud_filter.check_listing.return_value = fraud_result

        scorer = MagicMock()
        score_result = MagicMock()
        score_result.relevance_score = 0.80
        score_result.breakdown = {}
        scorer.score_job.return_value = score_result

        with patch("backend.orchestrator.JOBS_SEEN_PATH", tmp_jobs_seen):
            result = run_scrape_and_score(
                profile=mock_profile,
                registry=registry,
                fraud_filter=fraud_filter,
                scorer=scorer,
            )

        assert len(result.candidates) == 1
        assert result.candidates[0]["tier"] == "tier2"

    def test_state_persisted_after_run(self, mock_profile, sample_job, tmp_jobs_seen):
        """jobs_seen.json should be updated after a run."""
        registry = MagicMock()
        registry.scrape_all.return_value = [sample_job]

        fraud_filter = MagicMock()
        fraud_result = MagicMock()
        fraud_result.passed = True
        fraud_result.summary = "PASSED"
        fraud_result.legitimacy_score = 0.90
        fraud_filter.check_listing.return_value = fraud_result

        scorer = MagicMock()
        score_result = MagicMock()
        score_result.relevance_score = 0.80
        score_result.breakdown = {}
        scorer.score_job.return_value = score_result

        with patch("backend.orchestrator.JOBS_SEEN_PATH", tmp_jobs_seen):
            run_scrape_and_score(
                profile=mock_profile,
                registry=registry,
                fraud_filter=fraud_filter,
                scorer=scorer,
            )

        # File should now contain the job
        saved = load_jobs_seen(tmp_jobs_seen)
        assert len(saved) == 1
        job_id = _generate_job_id(sample_job)
        assert job_id in saved
        assert saved[job_id]["status"] == "issue_opened"


# ---------------------------------------------------------------------------
# Apply tier 1 tests
# ---------------------------------------------------------------------------

class TestApplyTier1:
    """Tests for run_apply_tier1."""

    def test_burn_in_mode_skips_submission(self, mock_profile, tmp_jobs_seen):
        """In burn-in mode, all jobs should get dry_run outcome."""
        approved = [{
            "issue_number": 42,
            "job_id": "abc123",
            "title": "Backend Engineer",
            "company": "Acme Corp",
            "url": "https://example.com",
            "source": "greenhouse",
        }]
        form_filler = MagicMock()

        # Pre-seed jobs_seen so the update path works
        save_jobs_seen({"abc123": {"first_seen": "2026-01-01", "status": "issue_opened"}}, tmp_jobs_seen)

        with patch("backend.orchestrator.JOBS_SEEN_PATH", tmp_jobs_seen):
            outcomes = run_apply_tier1(
                profile=mock_profile,
                approved_jobs=approved,
                form_filler=form_filler,
                burn_in_mode=True,
            )

        assert len(outcomes) == 1
        assert outcomes[0]["outcome"] == "dry_run"
        assert "Burn-in" in outcomes[0]["details"]
        # Form filler should NOT have been called
        form_filler.fill_form.assert_not_called()


# ---------------------------------------------------------------------------
# Daily digest tests
# ---------------------------------------------------------------------------

class TestDailyDigest:
    """Tests for generate_daily_digest."""

    def test_digest_format(self):
        result = ScrapeAndScoreResult()
        result.total_scraped = 10
        result.fraud_rejected = 2
        result.low_score_rejected = 3
        result.candidates = [
            {"title": "Engineer", "company": "Co", "match_score": 0.80, "tier": "tier1"},
        ]

        digest = generate_daily_digest(result)
        assert "Total Jobs Scraped: 10" in digest
        assert "Fraud Rejected: 2" in digest
        assert "Low Score Rejected: 3" in digest
        assert "Engineer at Co" in digest

    def test_empty_digest(self):
        result = ScrapeAndScoreResult()
        digest = generate_daily_digest(result)
        assert "Total Jobs Scraped: 0" in digest
