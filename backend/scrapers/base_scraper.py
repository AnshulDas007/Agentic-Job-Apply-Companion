"""
Abstract base scraper with retry, rate-limiting, and error handling.

All scrapers inherit from BaseScraper and implement the `scrape()` method.
"""

import abc
import logging
import time
from typing import List, Optional

import httpx

from backend.scrapers.job_schema import RawJobListing

logger = logging.getLogger(__name__)


class ScraperError(Exception):
    """Raised when a scraper encounters an unrecoverable error."""
    pass


class BaseScraper(abc.ABC):
    """
    Abstract base class for all job scrapers.

    Provides:
    - Configurable retry with exponential backoff
    - Rate limiting between requests
    - Shared HTTP client with sensible defaults
    - Structured error handling and logging
    """

    def __init__(
        self,
        name: str,
        max_retries: int = 3,
        request_delay: float = 2.0,
        timeout: float = 30.0,
    ):
        self.name = name
        self.max_retries = max_retries
        self.request_delay = request_delay
        self.timeout = timeout
        self._last_request_time: float = 0.0

    def _get_http_client(self) -> httpx.Client:
        """Create an HTTP client with sensible defaults."""
        return httpx.Client(
            timeout=self.timeout,
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/128.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            },
        )

    def _rate_limit(self) -> None:
        """Enforce minimum delay between requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.request_delay:
            sleep_time = self.request_delay - elapsed
            logger.debug("%s: rate limiting, sleeping %.1fs", self.name, sleep_time)
            time.sleep(sleep_time)
        self._last_request_time = time.time()

    def _fetch_with_retry(self, url: str, client: Optional[httpx.Client] = None) -> str:
        """
        Fetch a URL with retry and exponential backoff.

        Returns the response text.
        Raises ScraperError after all retries are exhausted.
        """
        own_client = client is None
        if own_client:
            client = self._get_http_client()

        try:
            for attempt in range(self.max_retries):
                try:
                    self._rate_limit()
                    response = client.get(url)
                    response.raise_for_status()
                    return response.text
                except httpx.HTTPStatusError as e:
                    if e.response.status_code in (429, 503):
                        delay = min(2 ** attempt * 2, 30)
                        logger.warning(
                            "%s: %d on attempt %d, retrying in %.0fs",
                            self.name, e.response.status_code, attempt + 1, delay,
                        )
                        time.sleep(delay)
                    else:
                        raise ScraperError(
                            f"{self.name}: HTTP {e.response.status_code} for {url}"
                        ) from e
                except httpx.RequestError as e:
                    delay = min(2 ** attempt * 2, 30)
                    logger.warning(
                        "%s: request error on attempt %d: %s, retrying in %.0fs",
                        self.name, attempt + 1, e, delay,
                    )
                    time.sleep(delay)

            raise ScraperError(f"{self.name}: all {self.max_retries} retries exhausted for {url}")
        finally:
            if own_client:
                client.close()

    @abc.abstractmethod
    def scrape(self, query: str, location: str = "", max_results: int = 50) -> List[RawJobListing]:
        """
        Scrape job listings matching the query.

        Args:
            query: Job search query (title, keywords)
            location: Location filter
            max_results: Maximum number of results to return

        Returns:
            List of RawJobListing objects
        """
        ...

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name!r}>"
