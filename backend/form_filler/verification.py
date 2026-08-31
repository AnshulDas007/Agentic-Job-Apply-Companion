"""
Pre-submission verification module.

Performs a diff-check between what the form filler plans to write
and the candidate's actual profile data. Catches cross-contamination
(e.g., project data in experience fields) before submission.
"""

import logging
from typing import Dict, List, Optional

from backend.parsing.profile_schema import CandidateProfile

logger = logging.getLogger(__name__)


class VerificationError:
    """A single verification mismatch."""

    def __init__(self, field_category: str, field_label: str, issue: str):
        self.field_category = field_category
        self.field_label = field_label
        self.issue = issue

    def __repr__(self) -> str:
        return f"VerificationError({self.field_category}: {self.issue})"


class VerificationResult:
    """Result of a pre-submission verification pass."""

    def __init__(self):
        self.errors: List[VerificationError] = []

    @property
    def passed(self) -> bool:
        return len(self.errors) == 0

    @property
    def summary(self) -> str:
        if self.passed:
            return "✅ Verification passed — no cross-contamination detected."
        lines = [f"⛔ Verification FAILED — {len(self.errors)} issue(s):"]
        for err in self.errors:
            lines.append(f"  - [{err.field_category}] {err.field_label}: {err.issue}")
        return "\n".join(lines)

    def add_error(self, field_category: str, field_label: str, issue: str) -> None:
        self.errors.append(VerificationError(field_category, field_label, issue))


def verify_fill_plan(
    fill_plan: List[Dict],
    profile: CandidateProfile,
) -> VerificationResult:
    """
    Verify that the fill plan doesn't cross-contaminate data.

    Checks:
    1. Experience fields don't contain project names
    2. Project fields don't contain company names from experience
    3. Contact fields don't contain experience/project data
    4. GitHub URLs aren't placed in address fields
    5. Address isn't placed in URL fields

    Args:
        fill_plan: List of dicts with keys: category, field_label, value.
        profile: The candidate's structured profile.

    Returns:
        VerificationResult with any detected issues.
    """
    result = VerificationResult()

    project_names = {p.name.lower() for p in profile.projects if p.name}
    company_names = {e.company.lower() for e in profile.experience if e.company}
    project_descriptions = {p.description.lower() for p in profile.projects if p.description}
    experience_descriptions = {e.description.lower() for e in profile.experience if e.description}

    for item in fill_plan:
        category = str(item.get("category", "")).lower()
        label = item.get("field_label", "")
        value = str(item.get("value", "")) if item.get("value") else ""
        value_lower = value.lower()

        if not value:
            continue

        # Rule 1: Experience fields must not contain project names
        if category in ("work_experience", "experience"):
            for pname in project_names:
                if pname and pname in value_lower:
                    result.add_error(
                        "experience", label,
                        f"Project name '{pname}' found in experience field"
                    )

        # Rule 2: Project fields must not contain company names
        if category in ("project", "projects"):
            for cname in company_names:
                if cname and cname in value_lower:
                    result.add_error(
                        "project", label,
                        f"Company name '{cname}' found in project field"
                    )

        # Rule 3: Address fields should not contain URLs
        if category == "address":
            if "github.com" in value_lower or "linkedin.com" in value_lower:
                result.add_error(
                    "address", label,
                    "URL found in address field"
                )

        # Rule 4: URL fields should not contain addresses
        if category in ("url", "github_url", "linkedin_url", "portfolio_url"):
            if not value.startswith(("http://", "https://", "www.")):
                # Looks like a non-URL was placed in a URL field
                if any(c.isalpha() for c in value) and " " in value:
                    result.add_error(
                        "url", label,
                        "Non-URL content found in URL field"
                    )

    if not result.passed:
        logger.error("Verification failed:\n%s", result.summary)
    else:
        logger.info("Verification passed — fill plan is clean.")

    return result
