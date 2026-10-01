"""
GitHub Issues integration for job application review.

Provides the review interface: scrape-and-score opens Issues for candidates,
users approve/reject via labels, and apply-tier1 reads approved Issues.
"""

from backend.issues_review.github_issues import GitHubIssuesManager

__all__ = ["GitHubIssuesManager"]
