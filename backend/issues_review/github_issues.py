"""
GitHub Issues manager for the review interface.

Opens Issues for job candidates that clear scraping + fraud + scoring,
reads Issue labels (approve/reject) for the apply step, and closes
Issues with outcome comments after applications are submitted.

This is the only review interface — no custom web app. Users interact
via the GitHub web UI or mobile app.
"""

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from github import Auth, Github
from github.GithubException import GithubException
from github.Issue import Issue
from github.Repository import Repository

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Label constants
# ---------------------------------------------------------------------------

LABEL_TIER1 = "tier1-ats"
LABEL_TIER2 = "tier2-manual"
LABEL_REVIEW = "review-required"
LABEL_APPROVE = "approve"
LABEL_REJECT = "reject"
LABEL_APPLIED = "applied"
LABEL_FAILED = "failed"

ALL_LABELS = {
    LABEL_TIER1: "0E8A16",       # green
    LABEL_TIER2: "FBCA04",       # yellow
    LABEL_REVIEW: "1D76DB",      # blue
    LABEL_APPROVE: "0E8A16",     # green
    LABEL_REJECT: "D93F0B",      # red
    LABEL_APPLIED: "6F42C1",     # purple
    LABEL_FAILED: "B60205",      # dark red
}


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class JobCandidate:
    """A job that passed scraping + fraud filter + scoring and is ready for review."""

    job_id: str
    title: str
    company: str
    url: str
    source: str
    location: str = ""
    match_score: float = 0.0
    fraud_summary: str = ""
    legitimacy_score: float = 0.0
    cover_letter: str = ""
    legal_flags: List[str] = field(default_factory=list)
    tier: str = "tier1"  # "tier1" or "tier2"
    description: str = ""


@dataclass
class ApprovedJob:
    """A job that the user approved via Issue label."""

    issue_number: int
    job_id: str
    title: str
    company: str
    url: str
    source: str
    tier: str = "tier1"
    cover_letter: str = ""


# ---------------------------------------------------------------------------
# Issue body builder
# ---------------------------------------------------------------------------

def _build_issue_body(candidate: JobCandidate) -> str:
    """Build the Issue body with structured job details for review."""
    tier_label = "🟢 Tier 1 — ATS (auto-apply eligible)" if candidate.tier == "tier1" else \
                 "🟡 Tier 2 — Platform (manual apply required)"

    sections = [
        f"## {candidate.title} at {candidate.company}\n",
        f"**URL:** {candidate.url}",
        f"**Source:** `{candidate.source}`",
        f"**Location:** {candidate.location or 'Not specified'}",
        f"**Tier:** {tier_label}\n",
        "---\n",
        "### Scores\n",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Match Score | **{candidate.match_score:.2f}** |",
        f"| Legitimacy Score | **{candidate.legitimacy_score:.2f}** |",
        f"| Fraud Filter | {candidate.fraud_summary} |\n",
    ]

    # Legal flags
    if candidate.legal_flags:
        sections.append("### ⚠️ Legal Flags\n")
        for flag in candidate.legal_flags:
            sections.append(f"- {flag}")
        sections.append("")

    # Cover letter draft
    if candidate.cover_letter:
        sections.append("### 📝 Cover Letter Draft\n")
        sections.append("<details>")
        sections.append("<summary>Click to expand</summary>\n")
        sections.append(candidate.cover_letter)
        sections.append("\n</details>\n")

    # Job description snippet
    if candidate.description:
        desc_preview = candidate.description[:1500]
        if len(candidate.description) > 1500:
            desc_preview += "\n\n*(truncated)*"
        sections.append("### 📋 Job Description\n")
        sections.append("<details>")
        sections.append("<summary>Click to expand</summary>\n")
        sections.append(desc_preview)
        sections.append("\n</details>\n")

    # Action instructions
    sections.extend([
        "---\n",
        "### Actions\n",
    ])

    if candidate.tier == "tier1":
        sections.append(
            "- **To approve for auto-apply:** add the `approve` label\n"
            "- **To reject:** add the `reject` label or close this issue\n"
        )
    else:
        sections.append(
            "- **Manual apply required** — use the details above to apply yourself\n"
            "- **Mark done:** add the `applied` label and close this issue\n"
            "- **Skip:** add the `reject` label and close this issue\n"
        )

    # Metadata (hidden, machine-readable)
    metadata = {
        "job_id": candidate.job_id,
        "source": candidate.source,
        "tier": candidate.tier,
        "match_score": candidate.match_score,
    }
    sections.append(f"\n<!-- job_metadata: {json.dumps(metadata)} -->")

    return "\n".join(sections)


def _extract_metadata_from_body(body: str) -> Dict[str, Any]:
    """Extract the hidden job_metadata JSON from an Issue body."""
    marker = "<!-- job_metadata: "
    idx = body.find(marker)
    if idx == -1:
        return {}
    start = idx + len(marker)
    end = body.find(" -->", start)
    if end == -1:
        return {}
    try:
        return json.loads(body[start:end])
    except json.JSONDecodeError:
        logger.warning("Failed to parse job_metadata from Issue body")
        return {}


# ---------------------------------------------------------------------------
# GitHub Issues Manager
# ---------------------------------------------------------------------------

class GitHubIssuesManager:
    """
    Manages GitHub Issues as the review interface for the pipeline.

    Usage:
        manager = GitHubIssuesManager()
        manager.open_job_issue(candidate)           # scrape-and-score
        approved = manager.get_approved_issues()     # apply-tier1
        manager.close_issue_with_outcome(42, "success", "Applied via Greenhouse")
    """

    def __init__(
        self,
        token: Optional[str] = None,
        repo_name: Optional[str] = None,
    ):
        """
        Initialize the GitHub Issues manager.

        Args:
            token: GitHub personal access token or GITHUB_TOKEN from Actions.
                   Defaults to GITHUB_TOKEN env var.
            repo_name: Full repo name (owner/repo). Defaults to GITHUB_REPOSITORY env var.
        """
        self._token = token or os.environ.get("GITHUB_TOKEN", "")
        self._repo_name = repo_name or os.environ.get("GITHUB_REPOSITORY", "")

        if not self._token:
            raise ValueError(
                "GitHub token not found. Set GITHUB_TOKEN env var or pass token= argument."
            )
        if not self._repo_name:
            raise ValueError(
                "Repository name not found. Set GITHUB_REPOSITORY env var or pass repo_name= argument."
            )

        auth = Auth.Token(self._token)
        self._github = Github(auth=auth)
        self._repo: Repository = self._github.get_repo(self._repo_name)

        # Ensure our labels exist
        self._ensure_labels()

    def _ensure_labels(self) -> None:
        """Create pipeline labels if they don't exist yet."""
        existing = {label.name for label in self._repo.get_labels()}

        for name, color in ALL_LABELS.items():
            if name not in existing:
                try:
                    self._repo.create_label(name=name, color=color)
                    logger.info("Created label: %s", name)
                except GithubException as e:
                    # Label might have been created by another concurrent run
                    if e.status != 422:  # 422 = already exists
                        logger.warning("Failed to create label %s: %s", name, e)

    # -------------------------------------------------------------------
    # Open Issues (scrape-and-score)
    # -------------------------------------------------------------------

    def open_job_issue(self, candidate: JobCandidate) -> int:
        """
        Open a GitHub Issue for a job candidate.

        Args:
            candidate: The job candidate data to create an Issue for.

        Returns:
            The Issue number.
        """
        title = f"[Job] {candidate.title} — {candidate.company}"

        # Determine labels
        labels = [LABEL_REVIEW]
        if candidate.tier == "tier1":
            labels.append(LABEL_TIER1)
        else:
            labels.append(LABEL_TIER2)

        body = _build_issue_body(candidate)

        try:
            issue = self._repo.create_issue(
                title=title,
                body=body,
                labels=labels,
            )
            logger.info(
                "Opened Issue #%d for %s at %s",
                issue.number, candidate.title, candidate.company,
            )
            return issue.number

        except GithubException as e:
            logger.error("Failed to create Issue: %s", e)
            raise

    def open_batch_issues(self, candidates: List[JobCandidate]) -> List[int]:
        """
        Open Issues for a batch of candidates.

        Returns:
            List of Issue numbers created.
        """
        issue_numbers = []
        for candidate in candidates:
            try:
                num = self.open_job_issue(candidate)
                issue_numbers.append(num)
            except GithubException:
                logger.error(
                    "Skipping Issue for %s at %s due to API error",
                    candidate.title, candidate.company,
                )
        return issue_numbers

    # -------------------------------------------------------------------
    # Read approved Issues (apply-tier1)
    # -------------------------------------------------------------------

    def get_approved_issues(self) -> List[ApprovedJob]:
        """
        Fetch all open Issues labeled 'approve' (ready for auto-apply).

        Returns:
            List of ApprovedJob with data extracted from Issue bodies.
        """
        approved = []

        try:
            issues = self._repo.get_issues(
                state="open",
                labels=[LABEL_APPROVE, LABEL_TIER1],
            )
        except GithubException as e:
            logger.error("Failed to fetch approved Issues: %s", e)
            return []

        for issue in issues:
            metadata = _extract_metadata_from_body(issue.body or "")
            if not metadata:
                logger.warning("Issue #%d has no parseable metadata — skipping", issue.number)
                continue

            # Extract cover letter from body
            cover_letter = _extract_cover_letter(issue.body or "")

            approved.append(ApprovedJob(
                issue_number=issue.number,
                job_id=metadata.get("job_id", ""),
                title=_extract_title_from_issue(issue.title),
                company=_extract_company_from_issue(issue.title),
                url=_extract_url_from_body(issue.body or ""),
                source=metadata.get("source", ""),
                tier=metadata.get("tier", "tier1"),
                cover_letter=cover_letter,
            ))

        logger.info("Found %d approved Issues for auto-apply", len(approved))
        return approved

    # -------------------------------------------------------------------
    # Close Issues with outcome (apply-tier1)
    # -------------------------------------------------------------------

    def close_issue_with_outcome(
        self,
        issue_number: int,
        outcome: str,
        details: str = "",
    ) -> None:
        """
        Close an Issue after application attempt, adding outcome as a comment.

        Args:
            issue_number: The Issue number to close.
            outcome: "success" or "failed".
            details: Additional details about the outcome.
        """
        try:
            issue = self._repo.get_issue(issue_number)
        except GithubException as e:
            logger.error("Failed to get Issue #%d: %s", issue_number, e)
            return

        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        if outcome == "success":
            emoji = "✅"
            label = LABEL_APPLIED
        else:
            emoji = "❌"
            label = LABEL_FAILED

        comment = f"{emoji} **Application {outcome.title()}** — {now}\n\n{details}"

        try:
            issue.create_comment(comment)

            # Replace approve label with outcome label
            try:
                issue.remove_from_labels(LABEL_APPROVE)
            except GithubException:
                pass  # label might already be removed

            issue.add_to_labels(label)
            issue.edit(state="closed")

            logger.info("Closed Issue #%d with outcome: %s", issue_number, outcome)

        except GithubException as e:
            logger.error("Failed to close Issue #%d: %s", issue_number, e)

    # -------------------------------------------------------------------
    # Daily summary
    # -------------------------------------------------------------------

    def post_run_summary(
        self,
        total_scraped: int,
        fraud_rejected: int,
        low_score_rejected: int,
        issues_opened: int,
        tier1_count: int,
        tier2_count: int,
    ) -> None:
        """
        Post a summary of the scrape-and-score run as a comment on a
        pinned 'Pipeline Run Log' issue.
        """
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        summary = (
            f"## 📊 Pipeline Run — {now}\n\n"
            f"| Metric | Count |\n"
            f"|--------|-------|\n"
            f"| Jobs Scraped | {total_scraped} |\n"
            f"| Fraud Rejected | {fraud_rejected} |\n"
            f"| Low Score Rejected | {low_score_rejected} |\n"
            f"| Issues Opened | {issues_opened} |\n"
            f"| Tier 1 (auto-apply eligible) | {tier1_count} |\n"
            f"| Tier 2 (manual apply) | {tier2_count} |\n"
        )

        log_issue = self._get_or_create_run_log_issue()
        try:
            log_issue.create_comment(summary)
            logger.info("Posted run summary to Issue #%d", log_issue.number)
        except GithubException as e:
            logger.error("Failed to post run summary: %s", e)

    def _get_or_create_run_log_issue(self) -> Issue:
        """Get or create the pinned 'Pipeline Run Log' issue."""
        # Search for existing run log issue
        issues = self._repo.get_issues(
            state="open",
            labels=["run-log"],
        )

        for issue in issues:
            if issue.title == "[Pipeline] Run Log":
                return issue

        # Create it with a run-log label
        if "run-log" not in ALL_LABELS:
            try:
                self._repo.create_label(name="run-log", color="EDEDED")
            except GithubException:
                pass  # may already exist

        issue = self._repo.create_issue(
            title="[Pipeline] Run Log",
            body=(
                "This issue collects daily pipeline run summaries.\n\n"
                "Each comment below is an automated summary from a "
                "`scrape-and-score` workflow run.\n\n"
                "**Do not close this issue.**"
            ),
            labels=["run-log"],
        )
        logger.info("Created Pipeline Run Log Issue #%d", issue.number)
        return issue


# ---------------------------------------------------------------------------
# Body parsing helpers
# ---------------------------------------------------------------------------

def _extract_title_from_issue(issue_title: str) -> str:
    """Extract job title from Issue title format '[Job] Title — Company'."""
    clean = issue_title.replace("[Job] ", "")
    parts = clean.split(" — ", 1)
    return parts[0].strip() if parts else clean


def _extract_company_from_issue(issue_title: str) -> str:
    """Extract company from Issue title format '[Job] Title — Company'."""
    clean = issue_title.replace("[Job] ", "")
    parts = clean.split(" — ", 1)
    return parts[1].strip() if len(parts) > 1 else ""


def _extract_url_from_body(body: str) -> str:
    """Extract job URL from Issue body."""
    for line in body.split("\n"):
        if line.startswith("**URL:**"):
            return line.replace("**URL:**", "").strip()
    return ""


def _extract_cover_letter(body: str) -> str:
    """Extract cover letter from the collapsible details block."""
    marker_start = "### 📝 Cover Letter Draft"
    marker_end = "</details>"

    idx_start = body.find(marker_start)
    if idx_start == -1:
        return ""

    # Find the content between <summary>...</summary> and </details>
    summary_end = body.find("</summary>", idx_start)
    if summary_end == -1:
        return ""

    content_start = summary_end + len("</summary>")
    idx_end = body.find(marker_end, content_start)
    if idx_end == -1:
        return ""

    return body[content_start:idx_end].strip()
