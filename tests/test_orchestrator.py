"""
Tests for the orchestrator module.

Tests the two-phase pipeline (scrape-and-score and apply-tier1),
platform tier classification, and daily digest generation.

Note: The orchestrator was refactored from a monolithic ApplicationOrchestrator
class to separate functions (run_scrape_and_score, run_apply_tier1) for the
GitHub Actions architecture. Comprehensive tests for the new API are in
test_run_pipeline.py. This file retains backward-compatible smoke tests.
"""

import pytest
from unittest.mock import MagicMock, patch

from backend.orchestrator import (
    PlatformTier,
    ScrapeAndScoreResult,
    _get_platform_tier,
    generate_daily_digest,
    run_scrape_and_score,
    run_apply_tier1,
)
from backend.scrapers.job_schema import RawJobListing


def test_get_platform_tier():
    assert _get_platform_tier("LinkedIn") == PlatformTier.TIER_2
    assert _get_platform_tier("indeed") == PlatformTier.TIER_2
    assert _get_platform_tier("naukri") == PlatformTier.TIER_2
    assert _get_platform_tier("Greenhouse") == PlatformTier.TIER_1
    assert _get_platform_tier("Lever") == PlatformTier.TIER_1


def test_scrape_and_score_fraud_rejection(tmp_path):
    """A job blocked by fraud filter should not become a candidate."""
    jobs_seen_path = tmp_path / "jobs_seen.json"

    job = RawJobListing(
        title="Engineer", company="ScamCo",
        url="http://scam", source="greenhouse",
    )
    registry = MagicMock()
    registry.scrape_all.return_value = [job]

    fraud_result = MagicMock()
    fraud_result.passed = False
    fraud_result.summary = "Payment required"
    fraud_filter = MagicMock()
    fraud_filter.check_listing.return_value = fraud_result

    scorer = MagicMock()
    profile = MagicMock()

    with patch("backend.orchestrator.JOBS_SEEN_PATH", jobs_seen_path):
        result = run_scrape_and_score(
            profile=profile,
            registry=registry,
            fraud_filter=fraud_filter,
            scorer=scorer,
        )

    assert result.fraud_rejected == 1
    assert len(result.candidates) == 0
    scorer.score_job.assert_not_called()


def test_scrape_and_score_low_score_rejection(tmp_path):
    """A job with low relevance score should not become a candidate."""
    jobs_seen_path = tmp_path / "jobs_seen.json"

    job = RawJobListing(
        title="Engineer", company="Tech",
        url="http://tech", source="greenhouse",
    )
    registry = MagicMock()
    registry.scrape_all.return_value = [job]

    fraud_result = MagicMock()
    fraud_result.passed = True
    fraud_result.summary = "PASSED"
    fraud_result.legitimacy_score = 0.85
    fraud_filter = MagicMock()
    fraud_filter.check_listing.return_value = fraud_result

    score_result = MagicMock()
    score_result.relevance_score = 0.50
    scorer = MagicMock()
    scorer.score_job.return_value = score_result

    profile = MagicMock()

    with patch("backend.orchestrator.JOBS_SEEN_PATH", jobs_seen_path):
        result = run_scrape_and_score(
            profile=profile,
            registry=registry,
            fraud_filter=fraud_filter,
            scorer=scorer,
            min_relevance_score=0.65,
        )

    assert result.low_score_rejected == 1
    assert len(result.candidates) == 0


def test_apply_tier1_burn_in(tmp_path):
    """Burn-in mode should prevent actual submissions."""
    from backend.orchestrator import save_jobs_seen

    jobs_seen_path = tmp_path / "jobs_seen.json"
    save_jobs_seen({"abc": {"first_seen": "2026-01-01", "status": "issue_opened"}}, jobs_seen_path)

    profile = MagicMock()
    form_filler = MagicMock()
    approved = [{"issue_number": 1, "job_id": "abc", "title": "Eng", "company": "Co", "url": "u", "source": "greenhouse"}]

    with patch("backend.orchestrator.JOBS_SEEN_PATH", jobs_seen_path):
        outcomes = run_apply_tier1(profile, approved, form_filler, burn_in_mode=True)

    assert outcomes[0]["outcome"] == "dry_run"
    form_filler.fill_form.assert_not_called()


def test_generate_daily_digest():
    result = ScrapeAndScoreResult()
    result.total_scraped = 3
    result.fraud_rejected = 1
    result.low_score_rejected = 1
    result.candidates = [
        {"title": "A", "company": "C1", "match_score": 0.80, "tier": "tier1"},
    ]

    digest = generate_daily_digest(result)

    assert "Total Jobs Scraped: 3" in digest
    assert "Fraud Rejected: 1" in digest
    assert "Low Score Rejected: 1" in digest
    assert "A at C1" in digest
