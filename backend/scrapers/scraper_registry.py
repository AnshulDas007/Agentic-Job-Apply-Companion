"""
Scraper registry — register and run scrapers by platform name.

Provides a single entry point to run scraping across all configured platforms.
"""

import logging
from typing import Dict, List, Optional, Type

from backend.scrapers.base_scraper import BaseScraper
from backend.scrapers.job_schema import RawJobListing

logger = logging.getLogger(__name__)


class ScraperRegistry:
    """
    Registry for managing and running job scrapers.

    Usage:
        registry = ScraperRegistry()
        registry.register("greenhouse", GreenhouseScraper(board_tokens=["stripe"]))
        registry.register("yc_jobs", YCScraper())

        # Run all scrapers
        all_listings = registry.scrape_all("software engineer", location="remote")

        # Run a specific platform
        yc_listings = registry.scrape("yc_jobs", "software engineer")
    """

    def __init__(self):
        self._scrapers: Dict[str, BaseScraper] = {}

    def register(self, platform: str, scraper: BaseScraper) -> None:
        """Register a scraper for a platform."""
        self._scrapers[platform] = scraper
        logger.info("Registered scraper for platform: %s", platform)

    def unregister(self, platform: str) -> None:
        """Remove a scraper registration."""
        if platform in self._scrapers:
            del self._scrapers[platform]

    def get(self, platform: str) -> Optional[BaseScraper]:
        """Get a scraper by platform name."""
        return self._scrapers.get(platform)

    def list_platforms(self) -> List[str]:
        """List all registered platform names."""
        return list(self._scrapers.keys())

    def scrape(
        self,
        platform: str,
        query: str,
        location: str = "",
        max_results: int = 50,
    ) -> List[RawJobListing]:
        """
        Run a specific platform's scraper.

        Raises KeyError if platform is not registered.
        """
        scraper = self._scrapers.get(platform)
        if not scraper:
            raise KeyError(f"No scraper registered for platform: '{platform}'")

        try:
            return scraper.scrape(query, location, max_results)
        except Exception as e:
            logger.error("Scraper '%s' failed: %s", platform, e)
            return []

    def scrape_all(
        self,
        query: str,
        location: str = "",
        max_results_per_platform: int = 50,
        platforms: Optional[List[str]] = None,
    ) -> Dict[str, List[RawJobListing]]:
        """
        Run all registered scrapers (or a subset).

        Args:
            query: Search query
            location: Location filter
            max_results_per_platform: Max results per platform
            platforms: Optional list of platform names to scrape.
                       If None, scrapes all registered platforms.

        Returns:
            Dict mapping platform name → list of RawJobListing
        """
        target_platforms = platforms or self.list_platforms()
        results: Dict[str, List[RawJobListing]] = {}

        for platform in target_platforms:
            if platform not in self._scrapers:
                logger.warning("Platform '%s' not registered, skipping", platform)
                continue

            logger.info("Scraping platform: %s", platform)
            try:
                listings = self.scrape(platform, query, location, max_results_per_platform)
                results[platform] = listings
                logger.info("  → %d listings from %s", len(listings), platform)
            except Exception as e:
                logger.error("  → Failed for %s: %s", platform, e)
                results[platform] = []

        total = sum(len(v) for v in results.values())
        logger.info("Total scraped: %d listings across %d platforms", total, len(results))
        return results


def build_default_registry(
    enabled_platforms: Optional[Dict[str, bool]] = None,
    greenhouse_tokens: Optional[List[str]] = None,
    lever_slugs: Optional[List[str]] = None,
    ashby_slugs: Optional[List[str]] = None,
) -> ScraperRegistry:
    """
    Build a ScraperRegistry with all default scrapers.

    Args:
        enabled_platforms: Dict of platform_name → enabled (from app_config.yaml)
        greenhouse_tokens: List of Greenhouse board tokens
        lever_slugs: List of Lever company slugs
        ashby_slugs: List of Ashby org slugs

    Returns:
        Configured ScraperRegistry
    """
    from backend.scrapers.apify_scraper import ApifyScraper, PLATFORM_ACTORS
    from backend.scrapers.ats_scraper import GreenhouseScraper, LeverScraper, AshbyScraper
    from backend.scrapers.yc_scraper import YCScraper

    enabled = enabled_platforms or {}
    registry = ScraperRegistry()

    # Apify-based scrapers (LinkedIn, Indeed, Naukri, Wellfound, ZipRecruiter)
    for platform in PLATFORM_ACTORS:
        if enabled.get(platform, True):
            try:
                registry.register(platform, ApifyScraper(platform=platform))
            except Exception as e:
                logger.warning("Failed to register Apify scraper for %s: %s", platform, e)

    # Direct ATS scrapers
    if enabled.get("greenhouse", True):
        registry.register("greenhouse", GreenhouseScraper(board_tokens=greenhouse_tokens or []))

    if enabled.get("lever", True):
        registry.register("lever", LeverScraper(company_slugs=lever_slugs or []))

    if enabled.get("ashby", True):
        registry.register("ashby", AshbyScraper(org_slugs=ashby_slugs or []))

    # YC Jobs
    if enabled.get("yc_jobs", True):
        registry.register("yc_jobs", YCScraper())

    return registry
