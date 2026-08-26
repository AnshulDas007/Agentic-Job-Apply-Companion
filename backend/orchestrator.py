"""
Orchestrator Module.

Coordinates the entire job application pipeline:
1. Scrape jobs from configured platforms.
2. Filter through Fraud Filter.
3. Score against CandidateProfile using Matching logic.
4. Auto-fill application form (with Legal Review & Cover Letter generation).
5. Enforce Tier 1 (unattended) vs Tier 2 (human click required) rules.
"""

import logging
from typing import List, Dict
from enum import Enum

from backend.parsing.profile_schema import CandidateProfile
from backend.scrapers.job_schema import RawJobListing
from backend.scrapers.scraper_registry import ScraperRegistry
from backend.fraud_filter.filter import FraudFilter
from backend.matching.scorer import RelevanceScorer
from backend.form_filler.filler import FormFiller

logger = logging.getLogger(__name__)

class PlatformTier(str, Enum):
    TIER_1 = "tier_1" # ATS sites: Greenhouse, Lever, Ashby, YC, direct career pages
    TIER_2 = "tier_2" # Job boards: LinkedIn, Indeed, Naukri, Wellfound (require human click)

def _get_platform_tier(platform: str) -> PlatformTier:
    tier_2_platforms = {"linkedin", "indeed", "naukri", "wellfound"}
    if platform.lower() in tier_2_platforms:
        return PlatformTier.TIER_2
    return PlatformTier.TIER_1

class ApplicationOrchestrator:
    """
    Main orchestrator for the job application pipeline.
    """
    
    def __init__(
        self,
        profile: CandidateProfile,
        registry: ScraperRegistry,
        fraud_filter: FraudFilter,
        scorer: RelevanceScorer,
        form_filler: FormFiller,
        min_relevance_score: float = 0.65,
        burn_in_mode: bool = True
    ):
        self.profile = profile
        self.registry = registry
        self.fraud_filter = fraud_filter
        self.scorer = scorer
        self.form_filler = form_filler
        self.min_relevance_score = min_relevance_score
        
        # Burn-in mode forces even Tier 1 applications to wait for a human click
        self.burn_in_mode = burn_in_mode 

    def run_pipeline(self, platforms: List[str] = None) -> List[Dict]:
        """
        Runs the end-to-end pipeline.
        Returns a summary report of actions taken.
        """
        logger.info("Starting Application Orchestrator Pipeline")
        report = []
        
        # 1. Scrape Jobs
        logger.info(f"Scraping platforms: {platforms if platforms else 'all'}")
        jobs = self.registry.scrape_all(platform_filter=platforms)
        logger.info(f"Scraped {len(jobs)} jobs total.")
        
        for job in jobs:
            job_report = {
                "job_title": job.title,
                "company": job.company,
                "url": job.url,
                "status": "pending",
                "reason": ""
            }
            
            # 2. Fraud Filter
            fraud_result = self.fraud_filter.evaluate_job(job.description, job.company, job.url)
            if not fraud_result.is_legitimate:
                job_report["status"] = "rejected"
                job_report["reason"] = f"Fraud Filter Failed: {fraud_result.hard_blocker_reason}"
                report.append(job_report)
                continue
                
            # 3. Matching
            score_result = self.scorer.score_job(job, self.profile)
            if score_result.total_score < self.min_relevance_score:
                job_report["status"] = "rejected"
                job_report["reason"] = f"Low Relevance Score: {score_result.total_score:.2f}"
                report.append(job_report)
                continue
                
            # 4. Determine Automation Tier
            tier = _get_platform_tier(job.source)
            
            # 5. Execute Application (Form Filling)
            # In a real implementation, we would launch a browser context here.
            # We mock the page object for the structure.
            mock_page = None 
            
            fill_success = self.form_filler.fill_form(
                page=mock_page,
                profile=self.profile,
                job_title=job.title,
                company=job.company,
                job_description=job.description
            )
            
            if not fill_success:
                job_report["status"] = "review_required"
                job_report["reason"] = "Form filling blocked by legal clause or verification mismatch."
                report.append(job_report)
                continue
                
            # 6. Submission Decision
            if tier == PlatformTier.TIER_2:
                job_report["status"] = "held_for_human"
                job_report["reason"] = "Tier 2 platform (LinkedIn/Indeed/Naukri) requires human click."
            elif self.burn_in_mode:
                job_report["status"] = "held_for_human"
                job_report["reason"] = "Burn-in mode active. Verify output before unattended submission."
            else:
                # Unattended Submission
                self._submit_application(mock_page)
                job_report["status"] = "submitted"
                job_report["reason"] = "Tier 1 unattended submission successful."
                
            report.append(job_report)
            
        logger.info("Pipeline run complete.")
        return report
        
    def _submit_application(self, page):
        """Clicks the final submit button."""
        # page.locator("button[type='submit']").click()
        pass

def generate_daily_digest(report: List[Dict]) -> str:
    """Generates a text summary of the orchestrator run for logging/email."""
    submitted = [r for r in report if r["status"] == "submitted"]
    held = [r for r in report if r["status"] == "held_for_human" or r["status"] == "review_required"]
    rejected = [r for r in report if r["status"] == "rejected"]
    
    digest = [
        "--- Daily Job Application Digest ---",
        f"Total Jobs Processed: {len(report)}",
        f"Automatically Submitted: {len(submitted)}",
        f"Held for Human Review: {len(held)}",
        f"Rejected (Fraud/Low Match): {len(rejected)}",
        "\n--- Submitted ---"
    ]
    
    for r in submitted:
        digest.append(f"- {r['job_title']} at {r['company']} ({r['url']})")
        
    digest.append("\n--- Held for Human Review ---")
    for r in held:
        digest.append(f"- {r['job_title']} at {r['company']}: {r['reason']}")
        
    return "\n".join(digest)
