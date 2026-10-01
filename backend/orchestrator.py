"""
Orchestrator Module.

Two-phase pipeline architecture for GitHub Actions execution:
  Phase 1 (scrape-and-score): Scrape → Fraud Filter → Score → Dedupe → open Issues
  Phase 2 (apply-tier1): Read approved Issues → Playwright apply → close Issues

State persists between runs via data/jobs_seen.json, committed back to the
repo by the GitHub Actions workflow after each run.
"""

import hashlib
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional
from enum import Enum

from backend.parsing.profile_schema import CandidateProfile
from backend.scrapers.job_schema import RawJobListing
from backend.scrapers.scraper_registry import ScraperRegistry
from backend.fraud_filter.filter import FraudFilter
from backend.matching.scorer import RelevanceScorer
from backend.form_filler.filler import FormFiller

logger = logging.getLogger(__name__)

JOBS_SEEN_PATH = Path("data/jobs_seen.json")


class PlatformTier(str, Enum):
    TIER_1 = "tier_1"  # ATS sites: Greenhouse, Lever, Ashby, YC, direct career pages
    TIER_2 = "tier_2"  # Job boards: LinkedIn, Indeed, Naukri, Wellfound (require human click)


def _get_platform_tier(platform: str) -> PlatformTier:
    tier_2_platforms = {"linkedin", "indeed", "naukri", "wellfound"}
    if platform.lower() in tier_2_platforms:
        return PlatformTier.TIER_2
    return PlatformTier.TIER_1


def _generate_job_id(job: RawJobListing) -> str:
    """Generate a stable unique ID for a job listing."""
    raw = f"{job.url}|{job.company}|{job.title}".lower()
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Deduplication via jobs_seen.json
# ---------------------------------------------------------------------------

def load_jobs_seen(path: Path = None) -> Dict[str, dict]:
    """Load the dedupe log from disk. Returns {job_id: {first_seen, last_seen, status}}."""
    if path is None:
        path = JOBS_SEEN_PATH
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        logger.warning("Failed to load jobs_seen.json, starting fresh")
        return {}


def save_jobs_seen(data: Dict[str, dict], path: Path = None) -> None:
    """Persist the dedupe log to disk (will be committed by Actions)."""
    if path is None:
        path = JOBS_SEEN_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
    logger.info("Saved %d entries to %s", len(data), path)


# ---------------------------------------------------------------------------
# Phase 1: Scrape and Score
# ---------------------------------------------------------------------------

class ScrapeAndScoreResult:
    """Result of the scrape-and-score phase."""

    def __init__(self):
        self.total_scraped: int = 0
        self.duplicates_skipped: int = 0
        self.fraud_rejected: int = 0
        self.low_score_rejected: int = 0
        self.candidates: List[Dict] = []  # jobs that cleared all filters
        self.errors: List[str] = []

    @property
    def tier1_count(self) -> int:
        return sum(1 for c in self.candidates if c["tier"] == "tier1")

    @property
    def tier2_count(self) -> int:
        return sum(1 for c in self.candidates if c["tier"] == "tier2")


def run_scrape_and_score(
    profile: CandidateProfile,
    registry: ScraperRegistry,
    fraud_filter: FraudFilter,
    scorer: RelevanceScorer,
    platforms: Optional[List[str]] = None,
    min_relevance_score: float = 0.65,
) -> ScrapeAndScoreResult:
    """
    Phase 1: Scrape jobs, run fraud filter and scoring, return candidates.

    This does NOT apply to any jobs — it produces a list of candidates
    that the scrape-and-score workflow will open as GitHub Issues.
    """
    result = ScrapeAndScoreResult()

    # Load dedupe log
    jobs_seen = load_jobs_seen()

    # Scrape
    logger.info("Scraping platforms: %s", platforms if platforms else "all")
    try:
        jobs = registry.scrape_all(platform_filter=platforms)
    except Exception as e:
        logger.error("Scraping failed: %s", e)
        result.errors.append(f"Scraping failed: {e}")
        return result

    result.total_scraped = len(jobs)
    logger.info("Scraped %d jobs total", len(jobs))

    from datetime import datetime, timezone
    now_iso = datetime.now(timezone.utc).isoformat()

    for job in jobs:
        job_id = _generate_job_id(job)

        # Dedupe
        if job_id in jobs_seen:
            result.duplicates_skipped += 1
            jobs_seen[job_id]["last_seen"] = now_iso
            continue

        # Fraud filter
        fraud_result = fraud_filter.check_listing(job)
        if not fraud_result.passed:
            result.fraud_rejected += 1
            jobs_seen[job_id] = {
                "first_seen": now_iso,
                "last_seen": now_iso,
                "status": "fraud_rejected",
            }
            logger.info("Fraud rejected: %s at %s — %s", job.title, job.company, fraud_result.summary)
            continue

        # Matching / scoring
        score_result = scorer.score_job(profile, job)
        if score_result.relevance_score < min_relevance_score:
            result.low_score_rejected += 1
            jobs_seen[job_id] = {
                "first_seen": now_iso,
                "last_seen": now_iso,
                "status": "low_score",
            }
            logger.info(
                "Low score: %s at %s — %.2f < %.2f",
                job.title, job.company, score_result.relevance_score, min_relevance_score,
            )
            continue

        # Determine tier
        tier = _get_platform_tier(job.source)
        tier_str = "tier1" if tier == PlatformTier.TIER_1 else "tier2"

        # This job is a candidate — will become a GitHub Issue
        candidate = {
            "job_id": job_id,
            "title": job.title,
            "company": job.company,
            "url": job.url,
            "source": job.source,
            "location": job.location,
            "description": job.description,
            "match_score": score_result.relevance_score,
            "fraud_summary": fraud_result.summary,
            "legitimacy_score": fraud_result.legitimacy_score,
            "tier": tier_str,
            "score_breakdown": score_result.breakdown if hasattr(score_result, "breakdown") else {},
        }
        result.candidates.append(candidate)

        jobs_seen[job_id] = {
            "first_seen": now_iso,
            "last_seen": now_iso,
            "status": "issue_opened",
        }

        logger.info(
            "✅ Candidate: %s at %s (score=%.2f, tier=%s)",
            job.title, job.company, score_result.relevance_score, tier_str,
        )

    # Persist dedupe log — Actions will commit this back
    save_jobs_seen(jobs_seen)

    logger.info(
        "Phase 1 complete: %d scraped, %d dupes, %d fraud, %d low-score, %d candidates",
        result.total_scraped, result.duplicates_skipped,
        result.fraud_rejected, result.low_score_rejected, len(result.candidates),
    )

    return result


# ---------------------------------------------------------------------------
# Phase 2: Apply Tier 1
# ---------------------------------------------------------------------------

def run_apply_tier1(
    profile: CandidateProfile,
    approved_jobs: List[Dict],
    form_filler: FormFiller,
    burn_in_mode: bool = True,
) -> List[Dict]:
    """
    Phase 2: Apply to approved Tier 1 jobs.

    Args:
        profile: Candidate profile for form filling.
        approved_jobs: List of approved job dicts (from GitHub Issues).
        form_filler: Form filler instance.
        burn_in_mode: If True, skip actual submission (dry run).

    Returns:
        List of outcome dicts [{issue_number, outcome, details}].
    """
    outcomes = []

    for job in approved_jobs:
        issue_number = job.get("issue_number")
        outcome = {
            "issue_number": issue_number,
            "job_title": job.get("title", ""),
            "company": job.get("company", ""),
            "outcome": "failed",
            "details": "",
        }

        if burn_in_mode:
            outcome["outcome"] = "dry_run"
            outcome["details"] = (
                "Burn-in mode active — application not submitted. "
                "Review the Issue details and manually verify the pipeline "
                "is producing correct outputs before disabling burn-in."
            )
            outcomes.append(outcome)
            logger.info(
                "Burn-in: skipped submission for %s at %s (Issue #%s)",
                job.get("title"), job.get("company"), issue_number,
            )
            continue

        # In production mode, launch Playwright and apply
        # This is where ATS-specific handlers would run
        try:
            mock_page = None  # Placeholder for actual Playwright page
            fill_success = form_filler.fill_form(
                page=mock_page,
                profile=profile,
                job_title=job.get("title", ""),
                company=job.get("company", ""),
                job_description=job.get("description", ""),
            )

            if fill_success:
                outcome["outcome"] = "success"
                outcome["details"] = f"Application submitted via {job.get('source', 'ATS')}"
            else:
                outcome["outcome"] = "failed"
                outcome["details"] = "Form filling was blocked (legal clause or verification mismatch)"

        except Exception as e:
            outcome["outcome"] = "failed"
            outcome["details"] = f"Application failed with error: {e}"
            logger.error("Apply failed for Issue #%s: %s", issue_number, e)

        outcomes.append(outcome)

    # Update jobs_seen with outcomes
    jobs_seen = load_jobs_seen()
    from datetime import datetime, timezone
    now_iso = datetime.now(timezone.utc).isoformat()

    for o in outcomes:
        job_id = None
        for j in approved_jobs:
            if j.get("issue_number") == o["issue_number"]:
                job_id = j.get("job_id")
                break
        if job_id and job_id in jobs_seen:
            jobs_seen[job_id]["status"] = o["outcome"]
            jobs_seen[job_id]["last_seen"] = now_iso

    save_jobs_seen(jobs_seen)

    return outcomes


# ---------------------------------------------------------------------------
# Daily digest (text format, for logging)
# ---------------------------------------------------------------------------

def generate_daily_digest(result: ScrapeAndScoreResult) -> str:
    """Generates a text summary of the scrape-and-score run."""
    lines = [
        "--- Daily Job Application Digest ---",
        f"Total Jobs Scraped: {result.total_scraped}",
        f"Duplicates Skipped: {result.duplicates_skipped}",
        f"Fraud Rejected: {result.fraud_rejected}",
        f"Low Score Rejected: {result.low_score_rejected}",
        f"Issues to Open: {len(result.candidates)}",
        f"  Tier 1 (auto-apply): {result.tier1_count}",
        f"  Tier 2 (manual):     {result.tier2_count}",
    ]

    if result.candidates:
        lines.append("\n--- Candidates ---")
        for c in result.candidates:
            lines.append(
                f"- {c['title']} at {c['company']} "
                f"(score={c['match_score']:.2f}, tier={c['tier']})"
            )

    if result.errors:
        lines.append("\n--- Errors ---")
        for err in result.errors:
            lines.append(f"- {err}")

    return "\n".join(lines)
