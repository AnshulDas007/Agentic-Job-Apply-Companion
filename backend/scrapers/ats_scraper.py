"""
Direct scraper for ATS career pages.

Handles Greenhouse, Lever, and Ashby career pages via their public APIs/pages.
These ATS platforms have structured, scrapable career pages that don't require
Apify credits — we can scrape them directly with httpx + BeautifulSoup.
"""

import hashlib
import json
import logging
import re
from typing import List, Optional
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from backend.scrapers.base_scraper import BaseScraper, ScraperError
from backend.scrapers.job_schema import RawJobListing

logger = logging.getLogger(__name__)


class GreenhouseScraper(BaseScraper):
    """
    Scrapes Greenhouse job boards.

    Greenhouse exposes a JSON API at:
        https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs

    Also supports HTML scraping for boards without API access:
        https://boards.greenhouse.io/{board_token}
    """

    def __init__(self, board_tokens: Optional[List[str]] = None, **kwargs):
        """
        Args:
            board_tokens: List of Greenhouse board tokens to scrape.
                          e.g., ["stripe", "airbnb", "figma"]
        """
        self.board_tokens = board_tokens or []
        super().__init__(name="greenhouse", **kwargs)

    def _scrape_board_api(self, token: str, max_results: int) -> List[RawJobListing]:
        """Scrape a single Greenhouse board via JSON API."""
        api_url = f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs"
        listings = []

        try:
            response_text = self._fetch_with_retry(api_url)
            data = json.loads(response_text)
            jobs = data.get("jobs", [])

            for job in jobs[:max_results]:
                title = job.get("title", "")
                location = job.get("location", {}).get("name", "")
                job_url = job.get("absolute_url", "")
                updated_at = job.get("updated_at", "")

                # Fetch detailed description if available
                description = ""
                content = job.get("content", "")
                if content:
                    soup = BeautifulSoup(content, "html.parser")
                    description = soup.get_text(separator="\n", strip=True)

                if title and job_url:
                    listings.append(RawJobListing(
                        title=title.strip(),
                        company=token,  # Will be enriched later
                        url=job_url,
                        source="greenhouse",
                        location=location,
                        description=description,
                        posted_date=updated_at,
                        raw_metadata={"board_token": token, "greenhouse_id": job.get("id")},
                    ))

        except Exception as e:
            logger.warning("Greenhouse API scrape failed for board '%s': %s", token, e)

        return listings

    def scrape(self, query: str, location: str = "", max_results: int = 50) -> List[RawJobListing]:
        """Scrape all configured Greenhouse boards."""
        if not self.board_tokens:
            logger.info("No Greenhouse board tokens configured. Skipping.")
            return []

        all_listings = []
        per_board_max = max(max_results // len(self.board_tokens), 10)

        for token in self.board_tokens:
            logger.info("Scraping Greenhouse board: %s", token)
            board_listings = self._scrape_board_api(token, per_board_max)
            all_listings.extend(board_listings)

        # Filter by query if provided
        if query:
            query_lower = query.lower()
            all_listings = [
                listing for listing in all_listings
                if query_lower in listing.title.lower()
                or query_lower in listing.description.lower()
            ]

        logger.info("Greenhouse: scraped %d total listings", len(all_listings))
        return all_listings[:max_results]


class LeverScraper(BaseScraper):
    """
    Scrapes Lever job boards.

    Lever exposes a JSON API at:
        https://api.lever.co/v0/postings/{company}

    HTML fallback:
        https://jobs.lever.co/{company}
    """

    def __init__(self, company_slugs: Optional[List[str]] = None, **kwargs):
        """
        Args:
            company_slugs: List of Lever company slugs.
                           e.g., ["netflix", "twitch"]
        """
        self.company_slugs = company_slugs or []
        super().__init__(name="lever", **kwargs)

    def _scrape_company_api(self, slug: str, max_results: int) -> List[RawJobListing]:
        """Scrape a single Lever company via JSON API."""
        api_url = f"https://api.lever.co/v0/postings/{slug}"
        listings = []

        try:
            response_text = self._fetch_with_retry(api_url)
            jobs = json.loads(response_text)

            if not isinstance(jobs, list):
                logger.warning("Unexpected Lever API response for '%s'", slug)
                return []

            for job in jobs[:max_results]:
                title = job.get("text", "")
                location = job.get("categories", {}).get("location", "")
                job_url = job.get("hostedUrl", "") or job.get("applyUrl", "")
                created_at = job.get("createdAt")

                # Description from lists
                desc_parts = []
                for desc_list in job.get("lists", []):
                    list_text = desc_list.get("text", "")
                    list_content = desc_list.get("content", "")
                    if list_text:
                        desc_parts.append(list_text)
                    if list_content:
                        soup = BeautifulSoup(list_content, "html.parser")
                        desc_parts.append(soup.get_text(separator="\n", strip=True))

                description = "\n".join(desc_parts)

                if title and job_url:
                    listings.append(RawJobListing(
                        title=title.strip(),
                        company=slug,
                        url=job_url,
                        source="lever",
                        location=location if isinstance(location, str) else "",
                        description=description,
                        posted_date=str(created_at) if created_at else None,
                        raw_metadata={"company_slug": slug, "lever_id": job.get("id")},
                    ))

        except Exception as e:
            logger.warning("Lever API scrape failed for '%s': %s", slug, e)

        return listings

    def scrape(self, query: str, location: str = "", max_results: int = 50) -> List[RawJobListing]:
        """Scrape all configured Lever company boards."""
        if not self.company_slugs:
            logger.info("No Lever company slugs configured. Skipping.")
            return []

        all_listings = []
        per_company_max = max(max_results // len(self.company_slugs), 10)

        for slug in self.company_slugs:
            logger.info("Scraping Lever board: %s", slug)
            company_listings = self._scrape_company_api(slug, per_company_max)
            all_listings.extend(company_listings)

        if query:
            query_lower = query.lower()
            all_listings = [
                listing for listing in all_listings
                if query_lower in listing.title.lower()
                or query_lower in listing.description.lower()
            ]

        logger.info("Lever: scraped %d total listings", len(all_listings))
        return all_listings[:max_results]


class AshbyScraper(BaseScraper):
    """
    Scrapes Ashby job boards.

    Ashby exposes a GraphQL-like API at:
        https://api.ashbyhq.com/posting-api/job-board/{org}

    HTML boards at:
        https://jobs.ashbyhq.com/{org}
    """

    def __init__(self, org_slugs: Optional[List[str]] = None, **kwargs):
        """
        Args:
            org_slugs: List of Ashby org slugs.
                       e.g., ["ramp", "notion"]
        """
        self.org_slugs = org_slugs or []
        super().__init__(name="ashby", **kwargs)

    def _scrape_org_api(self, slug: str, max_results: int) -> List[RawJobListing]:
        """Scrape a single Ashby org via their posting API."""
        api_url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
        listings = []

        try:
            response_text = self._fetch_with_retry(api_url)
            data = json.loads(response_text)
            jobs = data.get("jobs", [])

            for job in jobs[:max_results]:
                title = job.get("title", "")
                location = job.get("location", "")
                job_id = job.get("id", "")
                job_url = f"https://jobs.ashbyhq.com/{slug}/{job_id}"
                published_at = job.get("publishedAt", "")

                # Description might be in descriptionHtml or descriptionPlain
                description = job.get("descriptionPlain", "")
                if not description:
                    desc_html = job.get("descriptionHtml", "")
                    if desc_html:
                        soup = BeautifulSoup(desc_html, "html.parser")
                        description = soup.get_text(separator="\n", strip=True)

                if title:
                    listings.append(RawJobListing(
                        title=title.strip(),
                        company=slug,
                        url=job_url,
                        source="ashby",
                        location=location if isinstance(location, str) else "",
                        description=description,
                        posted_date=published_at,
                        raw_metadata={"org_slug": slug, "ashby_id": job_id},
                    ))

        except Exception as e:
            logger.warning("Ashby API scrape failed for '%s': %s", slug, e)

        return listings

    def scrape(self, query: str, location: str = "", max_results: int = 50) -> List[RawJobListing]:
        """Scrape all configured Ashby org boards."""
        if not self.org_slugs:
            logger.info("No Ashby org slugs configured. Skipping.")
            return []

        all_listings = []
        per_org_max = max(max_results // len(self.org_slugs), 10)

        for slug in self.org_slugs:
            logger.info("Scraping Ashby board: %s", slug)
            org_listings = self._scrape_org_api(slug, per_org_max)
            all_listings.extend(org_listings)

        if query:
            query_lower = query.lower()
            all_listings = [
                listing for listing in all_listings
                if query_lower in listing.title.lower()
                or query_lower in listing.description.lower()
            ]

        logger.info("Ashby: scraped %d total listings", len(all_listings))
        return all_listings[:max_results]
