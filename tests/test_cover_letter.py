"""
Tests for the cover letter generation module.

Tests the generation rules, banned phrase checking, post-processing,
and the full generator with mocked LLM responses.
"""

import pytest
from unittest.mock import MagicMock, patch

from backend.parsing.profile_schema import (
    CandidateProfile,
    ContactInfo,
    Education,
    Experience,
    Project,
)
from backend.cover_letter.generator import (
    BANNED_PHRASES,
    CoverLetterGenerator,
    CoverLetterResult,
    _build_system_prompt,
    _build_user_prompt,
    check_banned_phrases,
    clean_cover_letter,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_profile():
    """A realistic candidate profile for testing."""
    return CandidateProfile(
        name="Anshul Das",
        contact=ContactInfo(
            address="Bangalore, India",
            github_url="https://github.com/AnshulDas007",
            linkedin_url="https://linkedin.com/in/anshuldas",
            email="anshuldas42@gmail.com",
            phone="+91-9876543210",
        ),
        experience=[
            Experience(
                type="internship",
                title="Software Engineering Intern",
                company="TechCorp",
                duration_months=6,
                start_date="2025-01",
                end_date="2025-06",
                description="Built backend APIs in Python and FastAPI. "
                            "Reduced API response time by 40% through caching.",
                is_fresher_relevant=True,
            ),
        ],
        projects=[
            Project(
                name="Deep Research Copilot",
                description="An AI-powered research assistant using LLMs "
                            "for document analysis and knowledge extraction.",
                github_url="https://github.com/AnshulDas007/deep-research-copilot",
                tech_stack=["Python", "LangChain", "FastAPI", "ChromaDB"],
            ),
        ],
        skills=["Python", "JavaScript", "FastAPI", "React", "Docker", "Git"],
        education=[
            Education(
                institution="IIT Bangalore",
                degree="B.Tech",
                field_of_study="Computer Science",
                start_date="2022-08",
                end_date="2026-05",
            ),
        ],
    )


@pytest.fixture
def empty_profile():
    """Profile with no experience or projects."""
    return CandidateProfile(
        name="Empty User",
        contact=ContactInfo(
            address="",
            github_url="",
            linkedin_url="",
            email="empty@example.com",
            phone="",
        ),
        experience=[],
        projects=[],
        skills=[],
        education=[],
    )


@pytest.fixture
def mock_router():
    """A mocked ModelRouter that returns a realistic cover letter."""
    router = MagicMock()
    router.complete.return_value = {
        "content": (
            "The backend engineering role at Stripe caught my attention because "
            "of your focus on building reliable payment APIs at scale.\n\n"
            "During my internship at TechCorp, I built backend APIs in Python "
            "and FastAPI, reducing API response time by 40% through caching. "
            "That experience taught me how small architectural decisions compound "
            "into real performance gains.\n\n"
            "I also built Deep Research Copilot, an AI-powered research assistant "
            "using LangChain and ChromaDB. The project involved designing a RAG "
            "pipeline that handles document analysis and knowledge extraction.\n\n"
            "I'd welcome the chance to talk about how these experiences connect "
            "to what you're building.\n\n"
            "Anshul Das"
        ),
        "tokens_in": 500,
        "tokens_out": 200,
        "model": "openai/gpt-oss-120b",
        "provider": "groq",
    }
    return router


# ---------------------------------------------------------------------------
# Banned phrase tests
# ---------------------------------------------------------------------------

class TestBannedPhrases:
    def test_clean_text_no_banned(self):
        text = "I built a REST API in Python that handles 10k requests per second."
        found = check_banned_phrases(text)
        assert found == []

    def test_detects_passionate_about(self):
        text = "I am passionate about building software."
        found = check_banned_phrases(text)
        assert "passionate about" in found

    def test_detects_dynamic_environment(self):
        text = "I thrive in a dynamic environment."
        found = check_banned_phrases(text)
        assert "dynamic environment" in found

    def test_detects_multiple_banned(self):
        text = (
            "I am passionate about working in a dynamic environment. "
            "As a detail-oriented team player, I believe I would be a great fit."
        )
        found = check_banned_phrases(text)
        assert len(found) >= 3

    def test_case_insensitive(self):
        text = "I am PASSIONATE ABOUT software."
        found = check_banned_phrases(text)
        assert "passionate about" in found

    def test_banned_list_not_empty(self):
        assert len(BANNED_PHRASES) > 20  # We should have a good list


# ---------------------------------------------------------------------------
# Post-processing tests
# ---------------------------------------------------------------------------

class TestCleanCoverLetter:
    def test_strips_whitespace(self):
        text = "  \n\n  Hello World.  \n\n  "
        cleaned = clean_cover_letter(text)
        assert cleaned == "Hello World."

    def test_removes_subject_line(self):
        text = "Subject: Application for Software Engineer\n\nI built APIs."
        cleaned = clean_cover_letter(text)
        assert "Subject:" not in cleaned
        assert "I built APIs." in cleaned

    def test_removes_re_line(self):
        text = "Re: Software Engineer Position\n\nI built APIs."
        cleaned = clean_cover_letter(text)
        assert "Re:" not in cleaned

    def test_collapses_excess_newlines(self):
        text = "Para one.\n\n\n\n\nPara two."
        cleaned = clean_cover_letter(text)
        assert "\n\n\n" not in cleaned
        assert "Para one.\n\nPara two." == cleaned

    def test_preserves_double_newlines(self):
        text = "Para one.\n\nPara two."
        cleaned = clean_cover_letter(text)
        assert cleaned == "Para one.\n\nPara two."


# ---------------------------------------------------------------------------
# Prompt builder tests
# ---------------------------------------------------------------------------

class TestPromptBuilders:
    def test_system_prompt_contains_rules(self):
        prompt = _build_system_prompt()
        assert "CRITICAL RULES" in prompt
        assert "passionate about" in prompt
        assert "300 words" in prompt

    def test_user_prompt_contains_profile_data(self, sample_profile):
        prompt = _build_user_prompt(sample_profile, "Backend Dev", "Stripe", "Build APIs")
        assert "Backend Dev" in prompt
        assert "Stripe" in prompt
        assert "TechCorp" in prompt
        assert "Deep Research Copilot" in prompt
        assert "Python" in prompt
        assert "IIT Bangalore" in prompt
        assert "Build APIs" in prompt

    def test_user_prompt_handles_empty_experience(self, empty_profile):
        prompt = _build_user_prompt(empty_profile, "Dev", "Co", "")
        assert "recent graduate" in prompt.lower()

    def test_user_prompt_truncates_long_description(self, sample_profile):
        long_desc = "A" * 5000
        prompt = _build_user_prompt(sample_profile, "Dev", "Co", long_desc)
        # Should be truncated to ~2000 chars
        assert len(prompt) < 5000


# ---------------------------------------------------------------------------
# CoverLetterResult tests
# ---------------------------------------------------------------------------

class TestCoverLetterResult:
    def test_generated_needs_review(self):
        result = CoverLetterResult(generated=True, content="Some letter.")
        assert result.needs_review

    def test_skipped_no_review(self):
        result = CoverLetterResult(generated=False, reason_skipped="Not mandatory")
        assert not result.needs_review

    def test_summary_skipped(self):
        result = CoverLetterResult(
            generated=False,
            job_title="Dev",
            company="Co",
            reason_skipped="Not mandatory",
        )
        assert "SKIPPED" in result.summary

    def test_summary_ready(self):
        result = CoverLetterResult(
            generated=True,
            content="Some letter content here.",
            job_title="Dev",
            company="Co",
            banned_phrases_found=[],
        )
        assert "READY" in result.summary

    def test_summary_review_with_banned(self):
        result = CoverLetterResult(
            generated=True,
            content="I am passionate about coding.",
            job_title="Dev",
            company="Co",
            banned_phrases_found=["passionate about"],
        )
        assert "REVIEW" in result.summary


# ---------------------------------------------------------------------------
# Generator tests (with mocked LLM)
# ---------------------------------------------------------------------------

class TestCoverLetterGenerator:
    def test_skips_when_not_mandatory(self, sample_profile, mock_router):
        gen = CoverLetterGenerator(model_router=mock_router)
        result = gen.generate(
            profile=sample_profile,
            job_title="Backend Dev",
            company="Stripe",
            is_mandatory=False,
        )
        assert not result.generated
        assert "mandatory" in result.reason_skipped.lower()
        mock_router.complete.assert_not_called()

    def test_skips_empty_profile(self, empty_profile, mock_router):
        gen = CoverLetterGenerator(model_router=mock_router)
        result = gen.generate(
            profile=empty_profile,
            job_title="Dev",
            company="Co",
            is_mandatory=True,
        )
        assert not result.generated
        assert "no experience or projects" in result.reason_skipped.lower()
        mock_router.complete.assert_not_called()

    def test_generates_when_mandatory(self, sample_profile, mock_router):
        gen = CoverLetterGenerator(model_router=mock_router)
        result = gen.generate(
            profile=sample_profile,
            job_title="Backend Engineer",
            company="Stripe",
            job_description="Build payment APIs at scale.",
            is_mandatory=True,
        )
        assert result.generated
        assert result.content  # Non-empty
        assert result.needs_review  # Always needs review
        assert result.model_used == "openai/gpt-oss-120b"
        assert result.provider_used == "groq"
        assert result.tokens_used == 700  # 500 in + 200 out
        mock_router.complete.assert_called_once()

    def test_uses_cover_letter_tier(self, sample_profile, mock_router):
        gen = CoverLetterGenerator(model_router=mock_router)
        gen.generate(
            profile=sample_profile,
            job_title="Dev",
            company="Co",
            is_mandatory=True,
        )
        call_args = mock_router.complete.call_args
        assert call_args.kwargs.get("tier") or call_args.args[0] == "cover_letter"

    def test_content_contains_real_data(self, sample_profile, mock_router):
        """The mock response references real profile data (TechCorp, Deep Research Copilot)."""
        gen = CoverLetterGenerator(model_router=mock_router)
        result = gen.generate(
            profile=sample_profile,
            job_title="Backend Engineer",
            company="Stripe",
            is_mandatory=True,
        )
        assert "TechCorp" in result.content
        assert "Deep Research Copilot" in result.content

    def test_detects_banned_phrases_in_output(self, sample_profile):
        """If LLM returns banned phrases, they should be flagged."""
        router = MagicMock()
        router.complete.return_value = {
            "content": "I am passionate about building software in a dynamic environment.",
            "tokens_in": 100,
            "tokens_out": 50,
            "model": "test-model",
            "provider": "test",
        }
        gen = CoverLetterGenerator(model_router=router)
        result = gen.generate(
            profile=sample_profile,
            job_title="Dev",
            company="Co",
            is_mandatory=True,
        )
        assert result.generated
        assert len(result.banned_phrases_found) >= 2
        assert "passionate about" in result.banned_phrases_found

    def test_handles_llm_failure(self, sample_profile):
        router = MagicMock()
        router.complete.side_effect = RuntimeError("All providers failed")
        gen = CoverLetterGenerator(model_router=router)
        result = gen.generate(
            profile=sample_profile,
            job_title="Dev",
            company="Co",
            is_mandatory=True,
        )
        assert not result.generated
        assert "failed" in result.reason_skipped.lower()

    def test_handles_empty_llm_response(self, sample_profile):
        router = MagicMock()
        router.complete.return_value = {
            "content": "",
            "tokens_in": 100,
            "tokens_out": 0,
            "model": "test",
            "provider": "test",
        }
        gen = CoverLetterGenerator(model_router=router)
        result = gen.generate(
            profile=sample_profile,
            job_title="Dev",
            company="Co",
            is_mandatory=True,
        )
        assert not result.generated
        assert "empty" in result.reason_skipped.lower()

    def test_cleans_subject_line_from_output(self, sample_profile):
        router = MagicMock()
        router.complete.return_value = {
            "content": "Subject: Application for Dev\n\nI built APIs at TechCorp.",
            "tokens_in": 100,
            "tokens_out": 50,
            "model": "test",
            "provider": "test",
        }
        gen = CoverLetterGenerator(model_router=router)
        result = gen.generate(
            profile=sample_profile,
            job_title="Dev",
            company="Co",
            is_mandatory=True,
        )
        assert result.generated
        assert "Subject:" not in result.content

    def test_skip_convenience_method(self):
        gen = CoverLetterGenerator(model_router=MagicMock())
        result = gen.skip("Dev", "Co", "Field not present")
        assert not result.generated
        assert result.reason_skipped == "Field not present"
