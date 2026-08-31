"""
Tests for Phase 15: CLI entry point and scheduling.

Tests the Click CLI commands (using CliRunner) and scheduling utilities.
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from click.testing import CliRunner

from main import cli
from schedule import (
    DEFAULT_CRON_SCHEDULE,
    generate_crontab_entry,
    generate_github_actions_workflow,
)


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
        assert "run" in result.output
        assert "status" in result.output
        assert "review" in result.output
        assert "profile" in result.output

    def test_intake_help(self, runner):
        result = runner.invoke(cli, ["intake", "--help"])
        assert result.exit_code == 0
        assert "--resume" in result.output

    def test_run_help(self, runner):
        result = runner.invoke(cli, ["run", "--help"])
        assert result.exit_code == 0
        assert "--platforms" in result.output
        assert "--burn-in" in result.output
        assert "--min-score" in result.output

    def test_status_help(self, runner):
        result = runner.invoke(cli, ["status", "--help"])
        assert result.exit_code == 0
        assert "--limit" in result.output


# ---------------------------------------------------------------------------
# Tests: CLI status command
# ---------------------------------------------------------------------------

class TestStatusCommand:
    def test_status_with_empty_db(self, runner, tmp_path):
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
# Tests: CLI review command
# ---------------------------------------------------------------------------

class TestReviewCommand:
    def test_review_no_pending(self, runner):
        with patch("backend.database.Database") as MockDB:
            mock_db = MagicMock()
            mock_db.get_applications.return_value = []
            MockDB.return_value = mock_db

            result = runner.invoke(cli, ["review"])
            assert result.exit_code == 0
            assert "No applications pending review" in result.output


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


# ---------------------------------------------------------------------------
# Tests: Scheduling - Crontab
# ---------------------------------------------------------------------------

class TestCrontabGeneration:
    def test_default_entry(self):
        entry = generate_crontab_entry(project_dir="/opt/jobapply")
        assert DEFAULT_CRON_SCHEDULE in entry
        assert "main.py run" in entry
        assert "/opt/jobapply" in entry

    def test_custom_schedule(self):
        entry = generate_crontab_entry(
            schedule="30 10 * * *",
            project_dir="/home/user/project",
        )
        assert "30 10 * * *" in entry

    def test_with_platforms(self):
        entry = generate_crontab_entry(
            project_dir="/opt/app",
            platforms=["greenhouse", "lever"],
        )
        assert "-p greenhouse" in entry
        assert "-p lever" in entry

    def test_burn_in_off(self):
        entry = generate_crontab_entry(
            project_dir="/opt/app",
            burn_in=False,
        )
        assert "--no-burn-in" in entry

    def test_burn_in_on(self):
        entry = generate_crontab_entry(
            project_dir="/opt/app",
            burn_in=True,
        )
        assert "--no-burn-in" not in entry

    def test_log_file(self):
        entry = generate_crontab_entry(
            project_dir="/opt/app",
            log_file="logs/run.log",
        )
        assert "logs/run.log" in entry


# ---------------------------------------------------------------------------
# Tests: Scheduling - GitHub Actions
# ---------------------------------------------------------------------------

class TestGitHubActionsGeneration:
    def test_generates_valid_yaml(self):
        yaml = generate_github_actions_workflow()
        assert "name: Auto-Apply Pipeline" in yaml
        assert "cron:" in yaml
        assert "python main.py run" in yaml

    def test_schedule_in_yaml(self):
        yaml = generate_github_actions_workflow(schedule="0 8 * * 1-5")
        assert "0 8 * * 1-5" in yaml

    def test_secrets_referenced(self):
        yaml = generate_github_actions_workflow()
        assert "GROQ_API_KEY" in yaml
        assert "APIFY_TOKEN" in yaml

    def test_platforms_in_command(self):
        yaml = generate_github_actions_workflow(platforms=["greenhouse"])
        assert "-p greenhouse" in yaml

    def test_burn_in_off_in_command(self):
        yaml = generate_github_actions_workflow(burn_in=False)
        assert "--no-burn-in" in yaml
