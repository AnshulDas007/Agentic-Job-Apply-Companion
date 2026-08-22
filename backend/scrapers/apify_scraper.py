"""
Apify-based scraper for major job platforms.

Uses Apify marketplace actors to scrape:
- LinkedIn, Indeed, Naukri, Wellfound, ZipRecruiter

These platforms actively block direct scraping, so we use Apify's
managed actors (within free-tier credits: $5/month, non-rolling).
"""

import logging
import os
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

from backend.scrapers.base_scraper import BaseScraper, ScraperError
from backend.scrapers.job_schema import RawJobListing

load_dotenv()
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Apify actor IDs (marketplace actors for each platform)
# ---------------------------------------------------------------------------
# These are well-known actor IDs from the Apify marketplace.
# Users can swap them in config if better actors become available.

PLATFORM_ACTORS: Dict[str, Dict[str, Any]] = {
    "linkedin": {
        "actor_id": "anchor/linkedin-jobs-scraper",
        "tier": "tier2_platform",  # Requires human click for application
    },
    "indeed": {
        "actor_id": "misceres/indeed-scraper",
        "tier": "tier2_platform",
    },
    "naukri": {
        "actor_id": "curious_coder/naukri-scraper",
        "tier": "tier2_platform",
    },
    "wellfound": {
        "actor_id": "dainty_screw/wellfound-scraper",
        "tier": "tier1_ats",
    },
    "ziprecruiter": {
        "actor_id": "misceres/ziprecruiter-scraper",
        "tier": "tier1_ats",
    },
}


def _normalize_apify_result(item: dict, platform: str) -> Optional[RawJobListing]:
    """
    Normalize an Apify result item into a RawJobListing.

    Each actor returns slightly different schemas, so we do
    best-effort extraction with sensible defaults.
    """
    try:
        title = (
            item.get("title")
            or item.get("jobTitle")
            or item.get("position")
            or ""
        )
        company = (
            item.get("company")
            or item.get("companyName")
            or item.get("organization")
            or ""
        )
        url = (
            item.get("url")
            or item.get("jobUrl")
            or item.get("link")
            or ""
        )
        location = (
            item.get("location")
            or item.get("jobLocation")
            or item.get("place")
            or ""
        )
        description = (
            item.get("description")
            or item.get("jobDescription")
            or item.get("descriptionText")
            or ""
        )
        salary = (
            item.get("salary")
            or item.get("salaryText")
            or item.get("compensation")
        )
        posted = (
            item.get("postedDate")
            or item.get("postedAt")
            or item.get("publishedAt")
        )
        company_url = item.get("companyUrl") or item.get("companyWebsite")

        if not title or not url:
            logger.debug("Skipping Apify result with missing title or url: %s", item)
            return None

        return RawJobListing(
            title=title.strip(),
            company=company.strip(),
            url=url.strip(),
            source=platform,
            location=location.strip(),
            salary_text=salary,
            description=description,
            company_url=company_url,
            posted_date=posted,
            raw_metadata=item,
        )
    except Exception as e:
        logger.warning("Failed to normalize Apify result for %s: %s", platform, e)
        return None


class ApifyScraper(BaseScraper):
    """
    Scrapes job listings via Apify marketplace actors.

    Requires APIFY_TOKEN in environment.
    Gracefully skips if token is not set (logs a warning).
    """

    def __init__(self, platform: str, **kwargs):
        if platform not in PLATFORM_ACTORS:
            raise ValueError(
                f"Unsupported Apify platform: '{platform}'. "
                f"Available: {list(PLATFORM_ACTORS.keys())}"
            )

        self.platform = platform
        self.actor_config = PLATFORM_ACTORS[platform]
        self.tier = self.actor_config["tier"]
        super().__init__(name=f"apify-{platform}", **kwargs)

    def _get_apify_client(self):
        """Get or create an Apify client."""
        token = os.getenv("APIFY_TOKEN", "")
        if not token:
            return None

        try:
            from apify_client import ApifyClient
            return ApifyClient(token)
        except ImportError:
            logger.error("apify-client not installed. Run: pip install apify-client")
            return None

    def _build_actor_input(self, query: str, location: str, max_results: int) -> dict:
        """
        Build platform-specific actor input.

        Each Apify actor expects slightly different input schemas.
        """
        base_input = {
            "maxItems": max_results,
        }

        if self.platform == "linkedin":
            base_input.update({
                "searchTerms": [query],
                "location": location,
                "scrapeJobDetails": True,
            })
        elif self.platform == "indeed":
            base_input.update({
                "queries": [query],
                "location": location,
            })
        elif self.platform == "naukri":
            base_input.update({
                "keyword": query,
                "location": location,
            })
        elif self.platform == "wellfound":
            base_input.update({
                "searchTerms": [query],
                "location": location,
            })
        elif self.platform == "ziprecruiter":
            base_input.update({
                "search": query,
                "location": location,
            })

        return base_input

    def scrape(self, query: str, location: str = "", max_results: int = 50) -> List[RawJobListing]:
        """
        Run the Apify actor and return normalized job listings.

        Returns an empty list (with warning) if APIFY_TOKEN is not set.
        """
        client = self._get_apify_client()
        if client is None:
            logger.warning(
                "%s: APIFY_TOKEN not set or apify-client not installed. "
                "Skipping scrape for %s.",
                self.name, self.platform,
            )
            return []

        actor_id = self.actor_config["actor_id"]
        actor_input = self._build_actor_input(query, location, max_results)

        logger.info(
            "%s: running actor %s with query=%r, location=%r, max=%d",
            self.name, actor_id, query, location, max_results,
        )

        try:
            run = client.actor(actor_id).call(run_input=actor_input)
            dataset_items = client.dataset(run["defaultDatasetId"]).list_items().items

            listings = []
            for item in dataset_items:
                listing = _normalize_apify_result(item, self.platform)
                if listing:
                    listings.append(listing)

            logger.info("%s: scraped %d listings from %s", self.name, len(listings), self.platform)
            return listings[:max_results]

        except Exception as e:
            logger.error("%s: Apify actor failed: %s", self.name, e)
            raise ScraperError(f"{self.name}: Apify actor {actor_id} failed: {e}") from e
