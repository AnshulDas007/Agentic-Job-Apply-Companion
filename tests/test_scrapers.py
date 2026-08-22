"""
Tests for the scraping layer — schemas, registry, and scraper logic.
"""

import json
import pytest
from unittest.mock import MagicMock, patch

from backend.scrapers.job_schema import RawJobListing, ProcessedJobListing
from backend.scrapers.base_scraper import BaseScraper, ScraperError
from backend.scrapers.apify_scraper import ApifyScraper, _normalize_apify_result
from backend.scrapers.ats_scraper import GreenhouseScraper, LeverScraper, AshbyScraper
from backend.scrapers.yc_scraper import YCScraper
from backend.scrapers.scraper_registry import ScraperRegistry


# ---------------------------------------------------------------------------
# Job Schema
# ---------------------------------------------------------------------------

class TestJobSchema:
    def test_raw_listing_creation(self):
        listing = RawJobListing(
            title="Software Engineer",
            company="Acme Corp",
            url="https://acme.com/jobs/123",
            source="greenhouse",
        )
        assert listing.title == "Software Engineer"
        assert listing.source == "greenhouse"
        assert listing.scraped_at  # auto-populated

    def test_raw_listing_invalid_source(self):
        with pytest.raises(Exception):
            RawJobListing(
                title="Test",
                company="Test",
                url="https://test.com",
                source="invalid_platform",
            )

    def test_processed_listing_defaults(self):
        listing = ProcessedJobListing(
            id="test-123",
            title="Engineer",
            company="Corp",
            url="https://test.com",
            source="greenhouse",
        )
        assert listing.status == "new"
        assert listing.legitimacy_score == 0.0
        assert listing.relevance_score == 0.0
        assert listing.tier == "tier1_ats"


# ---------------------------------------------------------------------------
# Apify normalizer
# ---------------------------------------------------------------------------

class TestApifyNormalizer:
    def test_normalize_standard_result(self):
        item = {
            "title": "Backend Engineer",
            "company": "Startup Inc",
            "url": "https://linkedin.com/jobs/123",
            "location": "San Francisco, CA",
            "description": "Build cool stuff",
            "salary": "$100k - $150k",
        }
        listing = _normalize_apify_result(item, "linkedin")
        assert listing is not None
        assert listing.title == "Backend Engineer"
        assert listing.company == "Startup Inc"
        assert listing.source == "linkedin"

    def test_normalize_alternate_keys(self):
        item = {
            "jobTitle": "Frontend Dev",
            "companyName": "WebCo",
            "jobUrl": "https://indeed.com/jobs/456",
            "jobLocation": "Remote",
        }
        listing = _normalize_apify_result(item, "indeed")
        assert listing is not None
        assert listing.title == "Frontend Dev"
        assert listing.company == "WebCo"

    def test_normalize_missing_title_returns_none(self):
        item = {"company": "NoTitle Corp", "url": "https://test.com"}
        listing = _normalize_apify_result(item, "linkedin")
        assert listing is None

    def test_normalize_missing_url_returns_none(self):
        item = {"title": "Good Job", "company": "NoURL Corp"}
        listing = _normalize_apify_result(item, "linkedin")
        assert listing is None


# ---------------------------------------------------------------------------
# Apify scraper (no token = graceful skip)
# ---------------------------------------------------------------------------

class TestApifyScraper:
    def test_invalid_platform_raises(self):
        with pytest.raises(ValueError, match="Unsupported Apify platform"):
            ApifyScraper(platform="fakebook")

    def test_valid_platforms(self):
        for platform in ["linkedin", "indeed", "naukri", "wellfound", "ziprecruiter"]:
            scraper = ApifyScraper(platform=platform)
            assert scraper.platform == platform

    @patch.dict("os.environ", {"APIFY_TOKEN": ""})
    def test_no_token_returns_empty(self):
        scraper = ApifyScraper(platform="linkedin")
        result = scraper.scrape("software engineer")
        assert result == []


# ---------------------------------------------------------------------------
# ATS scrapers
# ---------------------------------------------------------------------------

class TestGreenhouseScraper:
    def test_no_tokens_returns_empty(self):
        scraper = GreenhouseScraper(board_tokens=[])
        result = scraper.scrape("engineer")
        assert result == []

    @patch.object(GreenhouseScraper, "_fetch_with_retry")
    def test_parse_api_response(self, mock_fetch):
        mock_fetch.return_value = json.dumps({
            "jobs": [
                {
                    "title": "Software Engineer",
                    "location": {"name": "NYC"},
                    "absolute_url": "https://boards.greenhouse.io/acme/jobs/1",
                    "content": "<p>Build things</p>",
                    "id": 1,
                    "updated_at": "2025-01-01",
                },
            ]
        })

        scraper = GreenhouseScraper(board_tokens=["acme"])
        listings = scraper.scrape("engineer")
        assert len(listings) == 1
        assert listings[0].title == "Software Engineer"
        assert listings[0].source == "greenhouse"


class TestLeverScraper:
    def test_no_slugs_returns_empty(self):
        scraper = LeverScraper(company_slugs=[])
        result = scraper.scrape("engineer")
        assert result == []

    @patch.object(LeverScraper, "_fetch_with_retry")
    def test_parse_api_response(self, mock_fetch):
        mock_fetch.return_value = json.dumps([
            {
                "text": "Product Manager",
                "categories": {"location": "Remote"},
                "hostedUrl": "https://jobs.lever.co/testco/abc",
                "createdAt": 1700000000000,
                "id": "abc",
                "lists": [],
            }
        ])

        scraper = LeverScraper(company_slugs=["testco"])
        listings = scraper.scrape("product")
        assert len(listings) == 1
        assert listings[0].title == "Product Manager"
        assert listings[0].source == "lever"


class TestAshbyScraper:
    def test_no_slugs_returns_empty(self):
        scraper = AshbyScraper(org_slugs=[])
        result = scraper.scrape("engineer")
        assert result == []


# ---------------------------------------------------------------------------
# YC Scraper
# ---------------------------------------------------------------------------

class TestYCScraper:
    def test_init(self):
        scraper = YCScraper()
        assert scraper.name == "yc-jobs"


# ---------------------------------------------------------------------------
# Scraper Registry
# ---------------------------------------------------------------------------

class TestScraperRegistry:
    def test_register_and_list(self):
        registry = ScraperRegistry()
        mock_scraper = MagicMock(spec=BaseScraper)
        registry.register("test_platform", mock_scraper)
        assert "test_platform" in registry.list_platforms()

    def test_unregister(self):
        registry = ScraperRegistry()
        mock_scraper = MagicMock(spec=BaseScraper)
        registry.register("test", mock_scraper)
        registry.unregister("test")
        assert "test" not in registry.list_platforms()

    def test_scrape_unregistered_raises(self):
        registry = ScraperRegistry()
        with pytest.raises(KeyError, match="No scraper registered"):
            registry.scrape("nonexistent", "query")

    def test_scrape_calls_scraper(self):
        registry = ScraperRegistry()
        mock_scraper = MagicMock(spec=BaseScraper)
        mock_scraper.scrape.return_value = [
            RawJobListing(
                title="Test Job",
                company="Test Co",
                url="https://test.com/job/1",
                source="greenhouse",
            )
        ]

        registry.register("test", mock_scraper)
        results = registry.scrape("test", "engineer")
        assert len(results) == 1
        mock_scraper.scrape.assert_called_once_with("engineer", "", 50)

    def test_scrape_all(self):
        registry = ScraperRegistry()
        for name in ["platform_a", "platform_b"]:
            mock = MagicMock(spec=BaseScraper)
            mock.scrape.return_value = [
                RawJobListing(
                    title=f"Job from {name}",
                    company="Co",
                    url=f"https://test.com/{name}/1",
                    source="greenhouse",
                )
            ]
            registry.register(name, mock)

        results = registry.scrape_all("query")
        assert len(results) == 2
        assert len(results["platform_a"]) == 1
        assert len(results["platform_b"]) == 1

    def test_scrape_all_with_platform_filter(self):
        registry = ScraperRegistry()
        for name in ["a", "b", "c"]:
            mock = MagicMock(spec=BaseScraper)
            mock.scrape.return_value = []
            registry.register(name, mock)

        results = registry.scrape_all("query", platforms=["a", "c"])
        assert "a" in results
        assert "c" in results
        assert "b" not in results

    def test_scrape_failure_returns_empty(self):
        registry = ScraperRegistry()
        mock_scraper = MagicMock(spec=BaseScraper)
        mock_scraper.scrape.side_effect = Exception("Boom")

        registry.register("failing", mock_scraper)
        results = registry.scrape("failing", "query")
        assert results == []
