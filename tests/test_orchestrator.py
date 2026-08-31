"""
Tests for the Application Orchestrator Module.
"""

import pytest
from unittest.mock import MagicMock, patch

from backend.orchestrator import (
    ApplicationOrchestrator, 
    PlatformTier, 
    _get_platform_tier,
    generate_daily_digest
)
from backend.scrapers.job_schema import RawJobListing

@pytest.fixture
def mock_dependencies():
    return {
        "profile": MagicMock(),
        "registry": MagicMock(),
        "fraud_filter": MagicMock(),
        "scorer": MagicMock(),
        "form_filler": MagicMock(),
    }

def test_get_platform_tier():
    assert _get_platform_tier("LinkedIn") == PlatformTier.TIER_2
    assert _get_platform_tier("indeed") == PlatformTier.TIER_2
    assert _get_platform_tier("naukri") == PlatformTier.TIER_2
    assert _get_platform_tier("Greenhouse") == PlatformTier.TIER_1
    assert _get_platform_tier("Lever") == PlatformTier.TIER_1

def test_orchestrator_fraud_filter_rejection(mock_dependencies):
    job = RawJobListing(title="Engineer", company="ScamCo", url="http://scam", source="greenhouse", location="", description="")
    mock_dependencies["registry"].scrape_all.return_value = [job]
    
    fraud_result = MagicMock()
    fraud_result.passed = False
    fraud_result.summary = "Payment required"
    mock_dependencies["fraud_filter"].check_listing.return_value = fraud_result
    
    orchestrator = ApplicationOrchestrator(**mock_dependencies)
    report = orchestrator.run_pipeline()
    
    assert len(report) == 1
    assert report[0]["status"] == "rejected"
    assert "Payment required" in report[0]["reason"]
    mock_dependencies["scorer"].score_job.assert_not_called()

def test_orchestrator_low_score_rejection(mock_dependencies):
    job = RawJobListing(title="Engineer", company="Tech", url="http://tech", source="greenhouse", location="", description="")
    mock_dependencies["registry"].scrape_all.return_value = [job]
    
    fraud_result = MagicMock()
    fraud_result.passed = True
    mock_dependencies["fraud_filter"].check_listing.return_value = fraud_result
    
    score_result = MagicMock()
    score_result.relevance_score = 0.50
    mock_dependencies["scorer"].score_job.return_value = score_result
    
    orchestrator = ApplicationOrchestrator(min_relevance_score=0.65, **mock_dependencies)
    report = orchestrator.run_pipeline()
    
    assert len(report) == 1
    assert report[0]["status"] == "rejected"
    assert "Low Relevance Score" in report[0]["reason"]
    mock_dependencies["form_filler"].fill_form.assert_not_called()

def test_orchestrator_form_filler_blocked(mock_dependencies):
    job = RawJobListing(title="Engineer", company="Tech", url="http://tech", source="greenhouse", location="", description="")
    mock_dependencies["registry"].scrape_all.return_value = [job]
    
    fraud_result = MagicMock()
    fraud_result.passed = True
    mock_dependencies["fraud_filter"].check_listing.return_value = fraud_result
    
    score_result = MagicMock()
    score_result.relevance_score = 0.80
    mock_dependencies["scorer"].score_job.return_value = score_result
    
    # Form filler fails (e.g., blocked by legal clause)
    mock_dependencies["form_filler"].fill_form.return_value = False
    
    orchestrator = ApplicationOrchestrator(min_relevance_score=0.65, **mock_dependencies)
    report = orchestrator.run_pipeline()
    
    assert len(report) == 1
    assert report[0]["status"] == "review_required"
    assert "blocked by legal clause" in report[0]["reason"]

def test_orchestrator_tier2_held(mock_dependencies):
    job = RawJobListing(title="Engineer", company="Tech", url="http://tech", source="linkedin", location="", description="")
    mock_dependencies["registry"].scrape_all.return_value = [job]
    
    fraud_result = MagicMock()
    fraud_result.passed = True
    mock_dependencies["fraud_filter"].check_listing.return_value = fraud_result
    
    score_result = MagicMock()
    score_result.relevance_score = 0.80
    mock_dependencies["scorer"].score_job.return_value = score_result
    
    mock_dependencies["form_filler"].fill_form.return_value = True
    
    orchestrator = ApplicationOrchestrator(min_relevance_score=0.65, burn_in_mode=False, **mock_dependencies)
    report = orchestrator.run_pipeline()
    
    assert len(report) == 1
    assert report[0]["status"] == "held_for_human"
    assert "Tier 2" in report[0]["reason"]

def test_orchestrator_burn_in_held(mock_dependencies):
    job = RawJobListing(title="Engineer", company="Tech", url="http://tech", source="greenhouse", location="", description="")
    mock_dependencies["registry"].scrape_all.return_value = [job]
    
    fraud_result = MagicMock()
    fraud_result.passed = True
    mock_dependencies["fraud_filter"].check_listing.return_value = fraud_result
    
    score_result = MagicMock()
    score_result.relevance_score = 0.80
    mock_dependencies["scorer"].score_job.return_value = score_result
    
    mock_dependencies["form_filler"].fill_form.return_value = True
    
    # Burn in is True by default, Tier 1 is Greenhouse
    orchestrator = ApplicationOrchestrator(min_relevance_score=0.65, burn_in_mode=True, **mock_dependencies)
    report = orchestrator.run_pipeline()
    
    assert len(report) == 1
    assert report[0]["status"] == "held_for_human"
    assert "Burn-in mode" in report[0]["reason"]

def test_orchestrator_tier1_submitted(mock_dependencies):
    job = RawJobListing(title="Engineer", company="Tech", url="http://tech", source="greenhouse", location="", description="")
    mock_dependencies["registry"].scrape_all.return_value = [job]
    
    fraud_result = MagicMock()
    fraud_result.passed = True
    mock_dependencies["fraud_filter"].check_listing.return_value = fraud_result
    
    score_result = MagicMock()
    score_result.relevance_score = 0.80
    mock_dependencies["scorer"].score_job.return_value = score_result
    
    mock_dependencies["form_filler"].fill_form.return_value = True
    
    orchestrator = ApplicationOrchestrator(min_relevance_score=0.65, burn_in_mode=False, **mock_dependencies)
    
    with patch.object(orchestrator, "_submit_application") as mock_submit:
        report = orchestrator.run_pipeline()
        
        assert len(report) == 1
        assert report[0]["status"] == "submitted"
        assert "Tier 1 unattended" in report[0]["reason"]
        mock_submit.assert_called_once()

def test_generate_daily_digest():
    report = [
        {"job_title": "A", "company": "C1", "url": "U", "status": "submitted", "reason": ""},
        {"job_title": "B", "company": "C2", "url": "U", "status": "held_for_human", "reason": "Burn-in"},
        {"job_title": "C", "company": "C3", "url": "U", "status": "rejected", "reason": "Low Match"},
    ]
    digest = generate_daily_digest(report)
    
    assert "Total Jobs Processed: 3" in digest
    assert "Automatically Submitted: 1" in digest
    assert "Held for Human Review: 1" in digest
    assert "Rejected (Fraud/Low Match): 1" in digest
    assert "- A at C1 (U)" in digest
    assert "- B at C2: Burn-in" in digest
