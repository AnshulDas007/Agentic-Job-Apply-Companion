"""
Tests for Phase 13: Form filler enhancements.

Tests verification module, dropdown handler, and ATS handler detection.
"""

import pytest

from backend.parsing.profile_schema import (
    CandidateProfile,
    ContactInfo,
    Education,
    Experience,
    Project,
)
from backend.form_filler.verification import verify_fill_plan
from backend.form_filler.dropdown_handler import (
    months_to_years,
    select_year_bucket,
    select_experience_value,
    _parse_option_range,
)
from backend.form_filler.ats_handlers import get_handler_for_url


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_profile():
    return CandidateProfile(
        name="Anshul Das",
        contact=ContactInfo(
            address="Bangalore, India",
            github_url="https://github.com/AnshulDas007",
            linkedin_url="https://linkedin.com/in/anshuldas",
            email="anshuldas42@gmail.com",
            phone="+91-1234567890",
        ),
        experience=[
            Experience(
                type="internship",
                title="Software Engineering Intern",
                company="Tech Corp",
                duration_months=6,
                start_date="2024-01",
                end_date="2024-06",
                description="Built backend services.",
                is_fresher_relevant=True,
            )
        ],
        projects=[
            Project(
                name="Deep Research Copilot",
                description="AI assistant using LLMs.",
                tech_stack=["Python", "LangChain"],
            )
        ],
        skills=["Python"],
        education=[],
    )


# ---------------------------------------------------------------------------
# Tests: Verification
# ---------------------------------------------------------------------------

class TestVerification:
    def test_clean_plan_passes(self, sample_profile):
        plan = [
            {"category": "experience", "field_label": "Work History", "value": "Intern at Tech Corp"},
            {"category": "project", "field_label": "Projects", "value": "Deep Research Copilot"},
        ]
        result = verify_fill_plan(plan, sample_profile)
        assert result.passed

    def test_project_in_experience_fails(self, sample_profile):
        plan = [
            {"category": "experience", "field_label": "Work History",
             "value": "Deep Research Copilot - Built AI tools"},
        ]
        result = verify_fill_plan(plan, sample_profile)
        assert not result.passed
        assert any("project name" in e.issue.lower() for e in result.errors)

    def test_company_in_project_fails(self, sample_profile):
        plan = [
            {"category": "project", "field_label": "Projects",
             "value": "Tech Corp internal tool for data analysis"},
        ]
        result = verify_fill_plan(plan, sample_profile)
        assert not result.passed
        assert any("company name" in e.issue.lower() for e in result.errors)

    def test_url_in_address_fails(self, sample_profile):
        plan = [
            {"category": "address", "field_label": "Address",
             "value": "https://github.com/AnshulDas007"},
        ]
        result = verify_fill_plan(plan, sample_profile)
        assert not result.passed

    def test_empty_values_pass(self, sample_profile):
        plan = [
            {"category": "experience", "field_label": "Work", "value": ""},
            {"category": "project", "field_label": "Projects", "value": None},
        ]
        result = verify_fill_plan(plan, sample_profile)
        assert result.passed

    def test_summary_output(self, sample_profile):
        plan = [
            {"category": "experience", "field_label": "Work",
             "value": "Deep Research Copilot project"},
        ]
        result = verify_fill_plan(plan, sample_profile)
        assert "FAILED" in result.summary


# ---------------------------------------------------------------------------
# Tests: Dropdown Handler
# ---------------------------------------------------------------------------

class TestDropdownHandler:
    def test_months_to_years(self):
        assert months_to_years(0) == 0.0
        assert months_to_years(6) == 0.5
        assert months_to_years(12) == 1.0
        assert months_to_years(18) == 1.5
        assert months_to_years(36) == 3.0

    def test_select_year_bucket_standard(self):
        assert select_year_bucket(6) == "0-1 years"  # 0.5 years → 0-1
        assert select_year_bucket(12) == "1-3 years"  # 1 year → 1-3
        assert select_year_bucket(0) == "0-1 years"  # 0 → 0-1
        assert select_year_bucket(36) == "3-5 years"  # 3 years → 3-5
        assert select_year_bucket(120) == "10-15 years"  # 10 years → 10-15

    def test_select_year_bucket_never_rounds_up(self):
        """6 months = 0.5 years, should go in 0-1, not 1-3."""
        result = select_year_bucket(6)
        assert result == "0-1 years"

    def test_select_with_form_options(self):
        options = ["Less than 1 year", "1-3 years", "3-5 years", "5+ years"]
        assert select_year_bucket(6, options) == "Less than 1 year"
        assert select_year_bucket(24, options) == "1-3 years"

    def test_parse_option_range_hyphen(self):
        assert _parse_option_range("0-1 years") == (0.0, 1.0)
        assert _parse_option_range("1 - 3 yrs") == (1.0, 3.0)

    def test_parse_option_range_plus(self):
        assert _parse_option_range("5+ years") == (5.0, float("inf"))
        assert _parse_option_range("10+") == (10.0, float("inf"))

    def test_parse_option_range_less_than(self):
        assert _parse_option_range("Less than 1 year") == (0.0, 1.0)
        assert _parse_option_range("Under 2 years") == (0.0, 2.0)

    def test_parse_option_range_more_than(self):
        assert _parse_option_range("More than 10 years") == (10.0, float("inf"))

    def test_parse_option_range_single(self):
        assert _parse_option_range("3 years") == (3.0, 3.0)

    def test_parse_option_range_unknown(self):
        assert _parse_option_range("Not applicable") is None


class TestSelectExperienceValue:
    def test_number_field(self):
        assert select_experience_value(6, "number") == "6"

    def test_text_field_months(self):
        result = select_experience_value(6, "text")
        assert "6 months" in result

    def test_text_field_years(self):
        result = select_experience_value(24, "text")
        assert "2 year" in result

    def test_dropdown_field(self):
        options = ["0-1 years", "1-3 years", "3-5 years"]
        result = select_experience_value(6, "dropdown", options)
        assert result == "0-1 years"


# ---------------------------------------------------------------------------
# Tests: ATS Handler Detection
# ---------------------------------------------------------------------------

class TestATSHandlerDetection:
    def test_greenhouse_url(self):
        handler = get_handler_for_url("https://boards.greenhouse.io/company/jobs/123")
        assert handler.get_platform_name() == "greenhouse"

    def test_lever_url(self):
        handler = get_handler_for_url("https://jobs.lever.co/company/abc-123/apply")
        assert handler.get_platform_name() == "lever"

    def test_workday_url(self):
        handler = get_handler_for_url("https://company.myworkdayjobs.com/en-US/External/job/123")
        assert handler.get_platform_name() == "workday"

    def test_ashby_url(self):
        handler = get_handler_for_url("https://jobs.ashbyhq.com/company/abc-123")
        assert handler.get_platform_name() == "ashby"

    def test_unknown_url_returns_generic(self):
        handler = get_handler_for_url("https://company.com/careers/apply")
        assert handler.get_platform_name() == "generic"
