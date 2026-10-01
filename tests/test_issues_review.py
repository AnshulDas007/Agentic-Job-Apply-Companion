"""
Tests for the GitHub Issues review module.

Tests the Issue body builder, metadata extraction, and helper functions.
GitHub API calls are mocked — no actual API requests are made.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from backend.issues_review.github_issues import (
    ALL_LABELS,
    GitHubIssuesManager,
    JobCandidate,
    _build_issue_body,
    _extract_company_from_issue,
    _extract_cover_letter,
    _extract_metadata_from_body,
    _extract_title_from_issue,
    _extract_url_from_body,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_candidate():
    """A sample Tier 1 job candidate."""
    return JobCandidate(
        job_id="abc123",
        title="Backend Engineer",
        company="Acme Corp",
        url="https://boards.greenhouse.io/acme/123",
        source="greenhouse",
        location="Remote",
        match_score=0.82,
        fraud_summary="PASSED: legitimacy score 0.90",
        legitimacy_score=0.90,
        cover_letter="Dear Acme team,\n\nI built backend services...\n\nBest,\nAnshul",
        legal_flags=["Non-compete clause detected"],
        tier="tier1",
        description="We're looking for a backend engineer...",
    )


@pytest.fixture
def sample_tier2_candidate():
    """A sample Tier 2 job candidate."""
    return JobCandidate(
        job_id="def456",
        title="Software Engineer",
        company="Big Corp",
        url="https://linkedin.com/jobs/view/456",
        source="linkedin",
        location="Bangalore, India",
        match_score=0.75,
        fraud_summary="PASSED: legitimacy score 0.85",
        legitimacy_score=0.85,
        tier="tier2",
    )


# ---------------------------------------------------------------------------
# Issue body builder tests
# ---------------------------------------------------------------------------

class TestBuildIssueBody:
    """Tests for _build_issue_body."""

    def test_tier1_body_contains_key_sections(self, sample_candidate):
        body = _build_issue_body(sample_candidate)

        assert "Backend Engineer" in body
        assert "Acme Corp" in body
        assert "https://boards.greenhouse.io/acme/123" in body
        assert "greenhouse" in body
        assert "Remote" in body
        assert "0.82" in body
        assert "0.90" in body
        assert "Tier 1" in body
        assert "auto-apply eligible" in body

    def test_tier2_body_shows_manual_apply(self, sample_tier2_candidate):
        body = _build_issue_body(sample_tier2_candidate)

        assert "Tier 2" in body
        assert "manual apply required" in body.lower()

    def test_cover_letter_in_details_block(self, sample_candidate):
        body = _build_issue_body(sample_candidate)

        assert "Cover Letter Draft" in body
        assert "<details>" in body
        assert "Dear Acme team" in body

    def test_legal_flags_shown(self, sample_candidate):
        body = _build_issue_body(sample_candidate)

        assert "Legal Flags" in body
        assert "Non-compete clause detected" in body

    def test_no_cover_letter_section_when_empty(self, sample_tier2_candidate):
        body = _build_issue_body(sample_tier2_candidate)

        assert "Cover Letter Draft" not in body

    def test_metadata_embedded(self, sample_candidate):
        body = _build_issue_body(sample_candidate)

        assert "<!-- job_metadata:" in body
        metadata = _extract_metadata_from_body(body)
        assert metadata["job_id"] == "abc123"
        assert metadata["source"] == "greenhouse"
        assert metadata["tier"] == "tier1"
        assert metadata["match_score"] == 0.82

    def test_job_description_truncated(self, sample_candidate):
        sample_candidate.description = "x" * 2000
        body = _build_issue_body(sample_candidate)

        assert "Job Description" in body
        # Should include the content (up to 1500 chars)
        assert "x" * 1500 in body

    def test_tier1_approve_instructions(self, sample_candidate):
        body = _build_issue_body(sample_candidate)

        assert "`approve`" in body
        assert "`reject`" in body

    def test_tier2_manual_instructions(self, sample_tier2_candidate):
        body = _build_issue_body(sample_tier2_candidate)

        assert "Manual apply required" in body
        assert "`applied`" in body


# ---------------------------------------------------------------------------
# Metadata extraction tests
# ---------------------------------------------------------------------------

class TestMetadataExtraction:
    """Tests for _extract_metadata_from_body."""

    def test_valid_metadata(self):
        body = 'some text\n<!-- job_metadata: {"job_id": "x", "tier": "tier1"} -->\n'
        meta = _extract_metadata_from_body(body)
        assert meta["job_id"] == "x"
        assert meta["tier"] == "tier1"

    def test_no_metadata(self):
        body = "just a plain body with no metadata"
        assert _extract_metadata_from_body(body) == {}

    def test_malformed_json(self):
        body = '<!-- job_metadata: {not valid json} -->'
        assert _extract_metadata_from_body(body) == {}


# ---------------------------------------------------------------------------
# Title/Company extraction tests
# ---------------------------------------------------------------------------

class TestTitleCompanyExtraction:
    """Tests for extracting title and company from Issue titles."""

    def test_standard_format(self):
        title = "[Job] Backend Engineer — Acme Corp"
        assert _extract_title_from_issue(title) == "Backend Engineer"
        assert _extract_company_from_issue(title) == "Acme Corp"

    def test_no_company(self):
        title = "[Job] Backend Engineer"
        assert _extract_title_from_issue(title) == "Backend Engineer"
        assert _extract_company_from_issue(title) == ""

    def test_no_prefix(self):
        title = "Backend Engineer — Acme Corp"
        assert _extract_title_from_issue(title) == "Backend Engineer"
        assert _extract_company_from_issue(title) == "Acme Corp"


# ---------------------------------------------------------------------------
# URL extraction tests
# ---------------------------------------------------------------------------

class TestUrlExtraction:
    """Tests for extracting URL from Issue body."""

    def test_url_present(self):
        body = "Some text\n**URL:** https://example.com/job/123\nMore text"
        assert _extract_url_from_body(body) == "https://example.com/job/123"

    def test_url_missing(self):
        body = "Some text without a URL line"
        assert _extract_url_from_body(body) == ""


# ---------------------------------------------------------------------------
# Cover letter extraction tests
# ---------------------------------------------------------------------------

class TestCoverLetterExtraction:
    """Tests for extracting cover letter from Issue body."""

    def test_cover_letter_present(self):
        body = (
            "### 📝 Cover Letter Draft\n\n"
            "<details>\n"
            "<summary>Click to expand</summary>\n\n"
            "Dear team,\n\nI am writing...\n\nBest,\nAnshul"
            "\n\n</details>\n"
        )
        result = _extract_cover_letter(body)
        assert "Dear team" in result
        assert "Best,\nAnshul" in result

    def test_no_cover_letter(self):
        body = "Just a regular body without cover letter"
        assert _extract_cover_letter(body) == ""


# ---------------------------------------------------------------------------
# GitHubIssuesManager tests (mocked API)
# ---------------------------------------------------------------------------

class TestGitHubIssuesManager:
    """Tests for GitHubIssuesManager with mocked GitHub API."""

    @patch.dict("os.environ", {"GITHUB_TOKEN": "test-token", "GITHUB_REPOSITORY": "user/repo"})
    @patch("backend.issues_review.github_issues.Github")
    def test_init_creates_missing_labels(self, mock_github_class):
        """Manager should create any missing labels on init."""
        mock_repo = MagicMock()
        mock_repo.get_labels.return_value = []  # no existing labels
        mock_github_class.return_value.get_repo.return_value = mock_repo

        manager = GitHubIssuesManager()

        # Should have called create_label for each label in ALL_LABELS
        assert mock_repo.create_label.call_count == len(ALL_LABELS)

    @patch.dict("os.environ", {"GITHUB_TOKEN": "test-token", "GITHUB_REPOSITORY": "user/repo"})
    @patch("backend.issues_review.github_issues.Github")
    def test_open_job_issue(self, mock_github_class, sample_candidate):
        """open_job_issue should create an Issue with correct title and labels."""
        mock_repo = MagicMock()
        mock_repo.get_labels.return_value = []
        mock_issue = MagicMock()
        mock_issue.number = 42
        mock_repo.create_issue.return_value = mock_issue
        mock_github_class.return_value.get_repo.return_value = mock_repo

        manager = GitHubIssuesManager()
        issue_num = manager.open_job_issue(sample_candidate)

        assert issue_num == 42
        call_kwargs = mock_repo.create_issue.call_args
        assert "Backend Engineer" in call_kwargs.kwargs["title"]
        assert "Acme Corp" in call_kwargs.kwargs["title"]
        assert "review-required" in call_kwargs.kwargs["labels"]
        assert "tier1-ats" in call_kwargs.kwargs["labels"]

    @patch.dict("os.environ", {"GITHUB_TOKEN": "test-token", "GITHUB_REPOSITORY": "user/repo"})
    @patch("backend.issues_review.github_issues.Github")
    def test_close_issue_with_success(self, mock_github_class):
        """close_issue_with_outcome should comment, relabel, and close."""
        mock_repo = MagicMock()
        mock_repo.get_labels.return_value = []
        mock_issue = MagicMock()
        mock_repo.get_issue.return_value = mock_issue
        mock_github_class.return_value.get_repo.return_value = mock_repo

        manager = GitHubIssuesManager()
        manager.close_issue_with_outcome(42, "success", "Applied via Greenhouse")

        mock_issue.create_comment.assert_called_once()
        comment_text = mock_issue.create_comment.call_args[0][0]
        assert "✅" in comment_text
        assert "Success" in comment_text

        mock_issue.add_to_labels.assert_called_with("applied")
        mock_issue.edit.assert_called_with(state="closed")

    @patch.dict("os.environ", {"GITHUB_TOKEN": "", "GITHUB_REPOSITORY": "user/repo"})
    def test_init_raises_without_token(self):
        """Should raise ValueError when no token is provided."""
        with pytest.raises(ValueError, match="GitHub token not found"):
            GitHubIssuesManager()

    @patch.dict("os.environ", {"GITHUB_TOKEN": "test-token", "GITHUB_REPOSITORY": ""})
    def test_init_raises_without_repo(self):
        """Should raise ValueError when no repo name is provided."""
        with pytest.raises(ValueError, match="Repository name not found"):
            GitHubIssuesManager()
