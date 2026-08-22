"""
Fraud/legitimacy filter.

Runs every listing through hard-blocker checks and soft-signal scoring
before it is eligible for application. This is a non-negotiable guardrail:
the agent never applies to a listing that failed the fraud filter.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import yaml

from backend.fraud_filter.signals import (
    extract_hard_blockers,
    score_company_presence,
    score_salary_reasonableness,
    score_urgency_language,
)

logger = logging.getLogger(__name__)

APP_CONFIG_PATH = Path("config/app_config.yaml")


@dataclass
class FraudResult:
    """Result of a fraud/legitimacy check on a job listing."""

    passed: bool
    hard_blocked: bool = False
    hard_block_reasons: List[str] = field(default_factory=list)
    legitimacy_score: float = 0.0
    signal_scores: Dict[str, float] = field(default_factory=dict)
    minimum_threshold: float = 0.50

    @property
    def summary(self) -> str:
        """Human-readable summary of the fraud check result."""
        if self.hard_blocked:
            return f"BLOCKED: {'; '.join(self.hard_block_reasons)}"
        elif not self.passed:
            return (
                f"FAILED: legitimacy score {self.legitimacy_score:.2f} "
                f"below threshold {self.minimum_threshold:.2f}"
            )
        else:
            return f"PASSED: legitimacy score {self.legitimacy_score:.2f}"


class FraudFilter:
    """
    Fraud/legitimacy filter for job listings.

    Two-stage check:
    1. Hard blockers — any one disqualifies immediately
    2. Soft-signal scoring — weighted score must meet minimum threshold

    Usage:
        fraud_filter = FraudFilter()
        result = fraud_filter.check(
            description="...",
            company_email="hr@acme.com",
            salary_text="$80k - $100k",
            has_linkedin=True,
            has_glassdoor=True,
            has_company_website=True,
        )
        if result.passed:
            # Proceed with this listing
        else:
            # Log and skip
    """

    def __init__(self, config_path: Path = APP_CONFIG_PATH):
        self.config = self._load_config(config_path)
        fraud_config = self.config.get("fraud_filter", {})
        self.minimum_score = fraud_config.get("minimum_legitimacy_score", 0.50)
        self.signal_weights = fraud_config.get("signal_weights", {
            "linkedin_presence": 0.30,
            "glassdoor_presence": 0.20,
            "salary_reasonableness": 0.25,
            "urgency_language": 0.25,
        })

    @staticmethod
    def _load_config(path: Path) -> dict:
        """Load application config."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except FileNotFoundError:
            logger.warning("Config not found at %s, using defaults", path)
            return {}

    def check(
        self,
        description: str,
        company_email: str = "",
        salary_text: Optional[str] = None,
        has_linkedin: bool = False,
        has_glassdoor: bool = False,
        has_company_website: bool = False,
        experience_level: str = "fresher",
    ) -> FraudResult:
        """
        Run the full fraud/legitimacy check on a listing.

        Args:
            description: Full text of the job listing
            company_email: Contact email from the listing
            salary_text: Salary information if available
            has_linkedin: Whether the company has a LinkedIn page
            has_glassdoor: Whether the company is on Glassdoor/AmbitionBox
            has_company_website: Whether the company has a real website
            experience_level: "fresher", "mid", "senior" — affects salary checks

        Returns:
            FraudResult with pass/fail, score, and reasons
        """
        # Stage 1: Hard blockers
        hard_block_reasons = extract_hard_blockers(description, company_email)

        if hard_block_reasons:
            logger.info("Listing hard-blocked: %s", hard_block_reasons)
            return FraudResult(
                passed=False,
                hard_blocked=True,
                hard_block_reasons=hard_block_reasons,
                legitimacy_score=0.0,
                minimum_threshold=self.minimum_score,
            )

        # Stage 2: Soft-signal scoring
        signal_scores = {}

        # Company online presence
        presence_score = score_company_presence(
            has_linkedin=has_linkedin,
            has_glassdoor=has_glassdoor,
            has_company_website=has_company_website,
        )
        signal_scores["company_presence"] = presence_score

        # Salary reasonableness
        salary_score = score_salary_reasonableness(salary_text or "", experience_level)
        signal_scores["salary_reasonableness"] = salary_score

        # Urgency language
        urgency_score = score_urgency_language(description)
        signal_scores["urgency_language"] = urgency_score

        # Calculate weighted legitimacy score
        # We combine presence signals into one component
        w_linkedin = self.signal_weights.get("linkedin_presence", 0.30)
        w_glassdoor = self.signal_weights.get("glassdoor_presence", 0.20)
        w_salary = self.signal_weights.get("salary_reasonableness", 0.25)
        w_urgency = self.signal_weights.get("urgency_language", 0.25)

        # Presence weight is linkedin + glassdoor combined
        w_presence = w_linkedin + w_glassdoor
        total_weight = w_presence + w_salary + w_urgency

        if total_weight > 0:
            legitimacy_score = (
                (w_presence * presence_score)
                + (w_salary * salary_score)
                + (w_urgency * urgency_score)
            ) / total_weight
        else:
            legitimacy_score = 0.5  # Default neutral

        passed = legitimacy_score >= self.minimum_score

        logger.info(
            "Fraud check: score=%.2f threshold=%.2f passed=%s signals=%s",
            legitimacy_score, self.minimum_score, passed, signal_scores,
        )

        return FraudResult(
            passed=passed,
            hard_blocked=False,
            legitimacy_score=legitimacy_score,
            signal_scores=signal_scores,
            minimum_threshold=self.minimum_score,
        )

    def check_listing(self, listing) -> FraudResult:
        """
        Convenience method to check a RawJobListing or ProcessedJobListing.

        Extracts relevant fields from the listing object.
        """
        description = getattr(listing, "description", "")
        company_email = getattr(listing, "company_email", "") or ""
        salary_text = getattr(listing, "salary_text", None)
        company_url = getattr(listing, "company_url", None)

        return self.check(
            description=description,
            company_email=company_email,
            salary_text=salary_text,
            has_company_website=bool(company_url),
        )
