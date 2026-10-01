"""
run_pipeline.py — Entry point for GitHub Actions workflows.

Subcommands:
  scrape-and-score  - Scrape jobs, filter, score, open GitHub Issues
  apply-tier1       - Apply to jobs approved via Issue labels

This runs on GitHub Actions runners (stateless). State persists via
data/jobs_seen.json committed back to the repo after each run.
"""

import logging
import os
import sys
from pathlib import Path

import click
from dotenv import load_dotenv

load_dotenv()


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )


# ---------------------------------------------------------------------------
# CLI group
# ---------------------------------------------------------------------------

@click.group()
def cli() -> None:
    """Agentic-JobApply-Companion — GitHub Actions pipeline runner."""
    _setup_logging()


# ---------------------------------------------------------------------------
# scrape-and-score
# ---------------------------------------------------------------------------

@cli.command("scrape-and-score")
@click.option(
    "--platforms", "-p",
    multiple=True,
    help="Platforms to scrape (e.g., greenhouse, linkedin). Omit for all.",
)
@click.option(
    "--min-score",
    type=float,
    default=0.65,
    help="Minimum relevance score threshold.",
)
def scrape_and_score(platforms: tuple, min_score: float) -> None:
    """Scrape jobs → fraud filter → score → open GitHub Issues."""
    from backend.fraud_filter.filter import FraudFilter
    from backend.matching.scorer import RelevanceScorer
    from backend.orchestrator import run_scrape_and_score, generate_daily_digest
    from backend.parsing.profile_store import load_profile
    from backend.scrapers.scraper_registry import ScraperRegistry
    from backend.cover_letter.generator import CoverLetterGenerator
    from backend.legal_review.reviewer import LegalReviewer
    from backend.issues_review.github_issues import GitHubIssuesManager, JobCandidate

    logger = logging.getLogger("pipeline.scrape-and-score")

    # Load profile
    profile = load_profile()
    if not profile:
        logger.error("No candidate profile found at data/candidate_profile.json")
        sys.exit(1)

    logger.info("Loaded profile: %s", profile.name)

    # Initialize modules
    registry = ScraperRegistry()
    fraud_filter = FraudFilter()
    scorer = RelevanceScorer()

    # Run Phase 1
    platform_list = list(platforms) if platforms else None
    result = run_scrape_and_score(
        profile=profile,
        registry=registry,
        fraud_filter=fraud_filter,
        scorer=scorer,
        platforms=platform_list,
        min_relevance_score=min_score,
    )

    # Print digest
    digest = generate_daily_digest(result)
    logger.info("\n%s", digest)

    if not result.candidates:
        logger.info("No candidates to open Issues for. Done.")
        return

    # Generate cover letters and run legal review for each candidate
    cover_gen = CoverLetterGenerator()
    legal_reviewer = LegalReviewer()
    candidates_for_issues: list[JobCandidate] = []

    for c in result.candidates:
        # Cover letter (only for Tier 1 where forms may require it)
        cover_letter_text = ""
        if c["tier"] == "tier1":
            try:
                cl_result = cover_gen.generate(
                    profile=profile,
                    job_title=c["title"],
                    company=c["company"],
                    job_description=c.get("description", ""),
                    is_mandatory=True,
                )
                if cl_result.generated:
                    cover_letter_text = cl_result.content
            except Exception as e:
                logger.warning("Cover letter generation failed for %s: %s", c["title"], e)

        # Legal review
        legal_flags: list[str] = []
        try:
            legal_result = legal_reviewer.review_text(c.get("description", ""))
            if legal_result.has_concerns:
                legal_flags = [clause.summary for clause in legal_result.clauses]
        except Exception as e:
            logger.warning("Legal review failed for %s: %s", c["title"], e)

        candidates_for_issues.append(JobCandidate(
            job_id=c["job_id"],
            title=c["title"],
            company=c["company"],
            url=c["url"],
            source=c["source"],
            location=c.get("location", ""),
            match_score=c["match_score"],
            fraud_summary=c["fraud_summary"],
            legitimacy_score=c.get("legitimacy_score", 0.0),
            cover_letter=cover_letter_text,
            legal_flags=legal_flags,
            tier=c["tier"],
            description=c.get("description", ""),
        ))

    # Open GitHub Issues
    try:
        issues_manager = GitHubIssuesManager()
        issue_numbers = issues_manager.open_batch_issues(candidates_for_issues)
        logger.info("Opened %d GitHub Issues", len(issue_numbers))

        # Post run summary
        issues_manager.post_run_summary(
            total_scraped=result.total_scraped,
            fraud_rejected=result.fraud_rejected,
            low_score_rejected=result.low_score_rejected,
            issues_opened=len(issue_numbers),
            tier1_count=result.tier1_count,
            tier2_count=result.tier2_count,
        )
    except Exception as e:
        logger.error("Failed to open GitHub Issues: %s", e)
        logger.info("Candidates were still saved to jobs_seen.json for next run.")
        sys.exit(1)


# ---------------------------------------------------------------------------
# apply-tier1
# ---------------------------------------------------------------------------

@cli.command("apply-tier1")
@click.option(
    "--burn-in/--no-burn-in",
    default=True,
    help="Enable burn-in mode (log but don't submit).",
)
def apply_tier1(burn_in: bool) -> None:
    """Read approved GitHub Issues and apply to Tier 1 jobs."""
    from backend.form_filler.filler import FormFiller
    from backend.orchestrator import run_apply_tier1
    from backend.parsing.profile_store import load_profile
    from backend.issues_review.github_issues import GitHubIssuesManager

    logger = logging.getLogger("pipeline.apply-tier1")

    # Load profile
    profile = load_profile()
    if not profile:
        logger.error("No candidate profile found at data/candidate_profile.json")
        sys.exit(1)

    logger.info("Loaded profile: %s", profile.name)
    logger.info("Burn-in mode: %s", "ON" if burn_in else "OFF")

    # Fetch approved issues
    try:
        issues_manager = GitHubIssuesManager()
        approved = issues_manager.get_approved_issues()
    except Exception as e:
        logger.error("Failed to fetch approved Issues: %s", e)
        sys.exit(1)

    if not approved:
        logger.info("No approved Issues found. Nothing to apply to.")
        return

    logger.info("Found %d approved jobs to apply to", len(approved))

    # Convert to dicts for the orchestrator
    approved_dicts = [
        {
            "issue_number": a.issue_number,
            "job_id": a.job_id,
            "title": a.title,
            "company": a.company,
            "url": a.url,
            "source": a.source,
            "tier": a.tier,
            "cover_letter": a.cover_letter,
        }
        for a in approved
    ]

    # Run Phase 2
    form_filler = FormFiller()
    outcomes = run_apply_tier1(
        profile=profile,
        approved_jobs=approved_dicts,
        form_filler=form_filler,
        burn_in_mode=burn_in,
    )

    # Close Issues with outcomes
    for outcome in outcomes:
        issue_num = outcome.get("issue_number")
        if issue_num is None:
            continue

        try:
            issues_manager.close_issue_with_outcome(
                issue_number=issue_num,
                outcome=outcome["outcome"],
                details=outcome.get("details", ""),
            )
        except Exception as e:
            logger.error("Failed to close Issue #%s: %s", issue_num, e)

    # Summary
    success = sum(1 for o in outcomes if o["outcome"] == "success")
    failed = sum(1 for o in outcomes if o["outcome"] == "failed")
    dry_run = sum(1 for o in outcomes if o["outcome"] == "dry_run")

    logger.info(
        "Apply phase complete: %d success, %d failed, %d dry-run",
        success, failed, dry_run,
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    cli()
