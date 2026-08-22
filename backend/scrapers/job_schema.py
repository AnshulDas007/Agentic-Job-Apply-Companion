"""
Job listing data schemas.

Strict Pydantic models for raw and processed job listings.
"""

from datetime import datetime, timezone
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class RawJobListing(BaseModel):
    """Raw job listing as scraped from a source — minimal processing."""

    title: str
    company: str
    url: str
    source: Literal[
        "linkedin", "indeed", "naukri", "wellfound", "ziprecruiter",
        "yc_jobs", "greenhouse", "lever", "workday", "ashby", "direct"
    ]
    location: str = ""
    salary_text: Optional[str] = None
    description: str = ""
    company_url: Optional[str] = None
    company_email: Optional[str] = None
    posted_date: Optional[str] = None
    scraped_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    # Raw metadata from the source (platform-specific fields)
    raw_metadata: dict = Field(default_factory=dict)


class ProcessedJobListing(BaseModel):
    """
    Job listing after fraud filtering and relevance scoring.

    This is the canonical representation used by the rest of the pipeline.
    """

    # Identity
    id: str = Field(description="Unique ID: hash of url + company + title")
    title: str
    company: str
    url: str
    source: str
    location: str = ""

    # Salary
    salary_text: Optional[str] = None
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None

    # Description
    description: str = ""
    required_skills: List[str] = Field(default_factory=list)
    experience_required: Optional[str] = None

    # Company info
    company_url: Optional[str] = None
    company_email: Optional[str] = None
    company_linkedin: Optional[str] = None
    has_glassdoor: bool = False

    # Fraud filter results
    legitimacy_score: float = 0.0
    fraud_hard_block: bool = False
    fraud_reasons: List[str] = Field(default_factory=list)

    # Relevance scoring
    relevance_score: float = 0.0
    relevance_breakdown: dict = Field(default_factory=dict)

    # Status tracking
    status: Literal["new", "filtered", "scored", "queued", "applied", "rejected", "held"] = "new"
    posted_date: Optional[str] = None
    scraped_at: str = ""
    processed_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    # Automation tier
    tier: Literal["tier1_ats", "tier2_platform"] = "tier1_ats"
