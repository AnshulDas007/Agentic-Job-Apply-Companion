"""
Y Combinator "Work at a Startup" board scraper.

Scrapes https://www.workatastartup.com — a free, public job board
aggregating open roles at YC-backed startups.

Uses their public API endpoint rather than HTML scraping for reliability.
"""

import json
import logging
from typing import List

import httpx

from backend.scrapers.base_scraper import BaseScraper, ScraperError
from backend.scrapers.job_schema import RawJobListing

logger = logging.getLogger(__name__)

# YC's Work at a Startup uses an Algolia-powered search API
YC_SEARCH_URL = "https://www.workatastartup.com/companies/fetch"
YC_BASE_URL = "https://www.workatastartup.com"


class YCScraper(BaseScraper):
    """
    Scrapes Y Combinator's Work at a Startup job board.

    Uses the public fetch API to get company listings with their jobs.
    """

    def __init__(self, **kwargs):
        super().__init__(name="yc-jobs", **kwargs)

    def scrape(self, query: str, location: str = "", max_results: int = 50) -> List[RawJobListing]:
        """
        Scrape YC Work at a Startup listings.

        Args:
            query: Job title or keyword to search for
            location: Location filter (optional)
            max_results: Maximum results to return

        Returns:
            List of RawJobListing objects from YC startups
        """
        listings = []

        try:
            with self._get_http_client() as client:
                # YC's search endpoint accepts POST with filters
                payload = {
                    "query": query,
                    "page": 1,
                    "batch_size": min(max_results * 2, 100),  # Overfetch since we filter
                }

                if location:
                    payload["location"] = location

                self._rate_limit()
                response = client.post(
                    YC_SEARCH_URL,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )
                response.raise_for_status()
                data = response.json()

                # The API returns companies with nested jobs
                companies = data if isinstance(data, list) else data.get("companies", [])

                for company in companies:
                    company_name = company.get("name", "")
                    company_url = company.get("website", "")
                    company_slug = company.get("slug", "")

                    jobs = company.get("jobs", [])
                    for job in jobs:
                        title = job.get("title", "")
                        job_location = job.get("location", "") or location
                        job_id = job.get("id", "")
                        salary_min = job.get("salary_min")
                        salary_max = job.get("salary_max")
                        description = job.get("description", "")
                        created_at = job.get("created_at", "")

                        # Build the job URL
                        job_url = f"{YC_BASE_URL}/companies/{company_slug}/jobs/{job_id}" if company_slug and job_id else ""

                        # Build salary text
                        salary_text = None
                        if salary_min and salary_max:
                            salary_text = f"${salary_min:,} - ${salary_max:,}"
                        elif salary_min:
                            salary_text = f"${salary_min:,}+"

                        if title and (job_url or company_name):
                            listings.append(RawJobListing(
                                title=title.strip(),
                                company=company_name.strip(),
                                url=job_url or f"{YC_BASE_URL}/companies/{company_slug}",
                                source="yc_jobs",
                                location=job_location,
                                salary_text=salary_text,
                                description=description,
                                company_url=company_url,
                                posted_date=created_at,
                                raw_metadata={
                                    "yc_company_slug": company_slug,
                                    "yc_job_id": job_id,
                                    "batch": company.get("batch", ""),
                                    "team_size": company.get("team_size"),
                                },
                            ))

                            if len(listings) >= max_results:
                                break

                    if len(listings) >= max_results:
                        break

        except httpx.HTTPError as e:
            logger.error("YC scraper HTTP error: %s", e)
            raise ScraperError(f"YC scraper failed: {e}") from e
        except Exception as e:
            logger.error("YC scraper error: %s", e)
            raise ScraperError(f"YC scraper failed: {e}") from e

        logger.info("YC Jobs: scraped %d listings", len(listings))
        return listings[:max_results]
