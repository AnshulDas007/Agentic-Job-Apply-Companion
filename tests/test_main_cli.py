"""
Tests for the main CLI entry point.

Tests the Click CLI commands (using CliRunner). Only tests the local-use
commands (intake, status, profile). Pipeline execution (run) and review
have moved to run_pipeline.py + GitHub Issues.
"""

import pytest
from unittest.mock import MagicMock, patch
from click.testing import CliRunner

from main import cli


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def runner():
    return CliRunner()


# ---------------------------------------------------------------------------
# Tests: CLI help and structure
# ---------------------------------------------------------------------------

class TestCLIStructure:
    def test_main_help(self, runner):
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "Agentic-JobApply-Companion" in result.output
        assert "intake" in result.output
        assert "status" in result.output
        assert "profile" in result.output

    def test_run_command_removed(self, runner):
        """The 'run' command was moved to run_pipeline.py."""
        result = runner.invoke(cli, ["run", "--help"])
        assert result.exit_code != 0

    def test_review_command_removed(self, runner):
        """The 'review' command was moved to GitHub Issues."""
        result = runner.invoke(cli, ["review", "--help"])
        assert result.exit_code != 0

    def test_intake_help(self, runner):
        result = runner.invoke(cli, ["intake", "--help"])
        assert result.exit_code == 0
        assert "--resume" in result.output

    def test_status_help(self, runner):
        result = runner.invoke(cli, ["status", "--help"])
        assert result.exit_code == 0
        assert "--limit" in result.output


# ---------------------------------------------------------------------------
# Tests: CLI status command
# ---------------------------------------------------------------------------

class TestStatusCommand:
    def test_status_with_empty_db(self, runner):
        with patch("backend.database.Database") as MockDB:
            mock_db = MagicMock()
            mock_db.get_stats.return_value = {
                "jobs": {},
                "applications": {},
                "usage": {},
            }
            mock_db.get_audit_trail.return_value = []
            MockDB.return_value = mock_db

            result = runner.invoke(cli, ["status"])
            assert result.exit_code == 0
            assert "Pipeline Statistics" in result.output


# ---------------------------------------------------------------------------
# Tests: CLI profile command
# ---------------------------------------------------------------------------

class TestProfileCommand:
    def test_profile_no_profile(self, runner):
        with patch("backend.parsing.profile_store.load_profile", return_value=None):
            result = runner.invoke(cli, ["profile"])
            assert result.exit_code != 0
            assert "No profile found" in result.output

    def test_profile_shows_data(self, runner):
        from backend.parsing.profile_schema import (
            CandidateProfile,
            ContactInfo,
        )

        mock_profile = CandidateProfile(
            name="Test User",
            contact=ContactInfo(
                address="Test City",
                github_url="https://github.com/test",
                linkedin_url="https://linkedin.com/in/test",
                email="test@example.com",
                phone="+1-555-0000",
            ),
            skills=["Python", "Testing"],
            experience=[],
            projects=[],
            education=[],
        )

        with patch("backend.parsing.profile_store.load_profile", return_value=mock_profile):
            result = runner.invoke(cli, ["profile"])
            assert result.exit_code == 0
            assert "Test User" in result.output
            assert "test@example.com" in result.output
            assert "Python" in result.output
