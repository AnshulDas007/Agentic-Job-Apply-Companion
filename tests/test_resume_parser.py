"""
Tests for the resume parser module.

Tests text extraction, LLM JSON cleaning, and the structured extraction
pipeline. LLM calls are mocked — no real API keys needed.
"""

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from backend.parsing.resume_parser import (
    _build_extraction_prompt,
    _clean_llm_json,
    extract_text,
    parse_resume_with_llm,
)
from backend.parsing.profile_schema import CandidateProfile


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_PROFILE_JSON = json.dumps({
    "name": "Anshul Das",
    "contact": {
        "address": "Bangalore, India",
        "github_url": "https://github.com/AnshulDas007",
        "linkedin_url": "https://linkedin.com/in/anshuldas",
        "email": "anshuldas42@gmail.com",
        "phone": "+91-1234567890",
    },
    "experience": [
        {
            "type": "internship",
            "title": "Software Engineering Intern",
            "company": "Tech Corp",
            "duration_months": 6,
            "start_date": "2024-01",
            "end_date": "2024-06",
            "description": "Built backend services in Python.",
            "is_fresher_relevant": True,
        }
    ],
    "projects": [
        {
            "name": "Deep Research Copilot",
            "description": "AI research assistant using LLMs.",
            "github_url": "https://github.com/AnshulDas007/copilot",
            "tech_stack": ["Python", "LangChain", "FastAPI"],
        }
    ],
    "skills": ["Python", "FastAPI", "LLMs"],
    "education": [
        {
            "institution": "XYZ University",
            "degree": "B.Tech",
            "field_of_study": "Computer Science",
            "start_date": "2020-08",
            "end_date": "2024-05",
            "gpa": "8.5",
        }
    ],
})


# ---------------------------------------------------------------------------
# Tests: JSON cleaning
# ---------------------------------------------------------------------------

class TestCleanLLMJson:
    def test_plain_json(self):
        raw = '{"name": "Test"}'
        assert _clean_llm_json(raw) == '{"name": "Test"}'

    def test_markdown_code_fence(self):
        raw = '```json\n{"name": "Test"}\n```'
        assert _clean_llm_json(raw) == '{"name": "Test"}'

    def test_plain_code_fence(self):
        raw = '```\n{"name": "Test"}\n```'
        assert _clean_llm_json(raw) == '{"name": "Test"}'

    def test_whitespace_padding(self):
        raw = '  \n  {"name": "Test"}  \n  '
        assert _clean_llm_json(raw) == '{"name": "Test"}'


# ---------------------------------------------------------------------------
# Tests: Prompt building
# ---------------------------------------------------------------------------

class TestPromptBuilding:
    def test_builds_prompt_with_text(self):
        prompt = _build_extraction_prompt("Some resume text here")
        assert "Some resume text here" in prompt

    def test_truncates_long_text(self):
        long_text = "x" * 10000
        prompt = _build_extraction_prompt(long_text)
        # Prompt should contain truncated text (8000 chars max)
        assert len(prompt) < 10000


# ---------------------------------------------------------------------------
# Tests: LLM-based parsing (mocked)
# ---------------------------------------------------------------------------

class TestParseResumeWithLLM:
    def test_successful_parse(self):
        mock_router = MagicMock()
        mock_router.complete.return_value = {
            "content": SAMPLE_PROFILE_JSON,
            "tokens_in": 500,
            "tokens_out": 300,
            "model": "test-model",
            "provider": "test",
        }

        profile = parse_resume_with_llm("Some resume text", router=mock_router)

        assert isinstance(profile, CandidateProfile)
        assert profile.name == "Anshul Das"
        assert len(profile.experience) == 1
        assert profile.experience[0].type == "internship"
        assert profile.experience[0].duration_months == 6
        assert len(profile.projects) == 1
        assert profile.projects[0].name == "Deep Research Copilot"

    def test_parse_with_markdown_fences(self):
        """LLM wraps JSON in markdown code fences."""
        mock_router = MagicMock()
        mock_router.complete.return_value = {
            "content": f"```json\n{SAMPLE_PROFILE_JSON}\n```",
            "tokens_in": 500,
            "tokens_out": 300,
        }

        profile = parse_resume_with_llm("Resume text", router=mock_router)
        assert profile.name == "Anshul Das"

    def test_empty_response_raises(self):
        mock_router = MagicMock()
        mock_router.complete.return_value = {"content": ""}

        with pytest.raises(RuntimeError, match="empty response"):
            parse_resume_with_llm("Resume text", router=mock_router)

    def test_invalid_json_raises(self):
        mock_router = MagicMock()
        mock_router.complete.return_value = {
            "content": "This is not JSON at all.",
        }

        with pytest.raises(RuntimeError, match="not valid JSON"):
            parse_resume_with_llm("Resume text", router=mock_router)

    def test_schema_mismatch_raises(self):
        mock_router = MagicMock()
        # Missing required fields
        mock_router.complete.return_value = {
            "content": json.dumps({"name": "Test"}),
        }

        with pytest.raises(ValueError, match="CandidateProfile schema"):
            parse_resume_with_llm("Resume text", router=mock_router)


# ---------------------------------------------------------------------------
# Tests: Text extraction (file format detection)
# ---------------------------------------------------------------------------

class TestExtractText:
    def test_unsupported_format_raises(self, tmp_path):
        fake_file = tmp_path / "resume.txt"
        fake_file.write_text("hello")
        with pytest.raises(ValueError, match="Unsupported resume format"):
            extract_text(fake_file)

    def test_missing_file_raises(self):
        with pytest.raises(FileNotFoundError):
            extract_text(Path("/nonexistent/resume.pdf"))

    def test_pdf_extraction(self, tmp_path):
        """Test PDF extraction if pdfplumber is available."""
        try:
            import pdfplumber
        except ImportError:
            pytest.skip("pdfplumber not installed")

        # Mock pdfplumber since we don't have a real PDF
        with patch("backend.parsing.resume_parser.extract_text_from_pdf") as mock_pdf:
            mock_pdf.return_value = "Extracted PDF text"
            fake_pdf = tmp_path / "resume.pdf"
            fake_pdf.write_bytes(b"fake pdf content")
            result = extract_text(fake_pdf)
            assert result == "Extracted PDF text"

    def test_docx_extraction(self, tmp_path):
        """Test DOCX extraction path."""
        with patch("backend.parsing.resume_parser.extract_text_from_docx") as mock_docx:
            mock_docx.return_value = "Extracted DOCX text"
            fake_docx = tmp_path / "resume.docx"
            fake_docx.write_bytes(b"fake docx content")
            result = extract_text(fake_docx)
            assert result == "Extracted DOCX text"


# ---------------------------------------------------------------------------
# Tests: Experience/Project separation enforcement
# ---------------------------------------------------------------------------

class TestSchemaEnforcement:
    def test_experience_stays_separate(self):
        """Verify a parsed profile maintains strict Experience/Project separation."""
        mock_router = MagicMock()
        mock_router.complete.return_value = {
            "content": SAMPLE_PROFILE_JSON,
            "tokens_in": 100,
            "tokens_out": 200,
        }

        profile = parse_resume_with_llm("Resume", router=mock_router)

        # Experience should only have work entries
        for exp in profile.experience:
            assert exp.company  # Must have a company
            assert exp.duration_months >= 0  # Must have duration
            assert not hasattr(exp, "tech_stack")  # Should not have project fields

        # Projects should only have project entries
        for proj in profile.projects:
            assert proj.name  # Must have a name
            assert not hasattr(proj, "company")  # Should not have experience fields
