"""
Resume parser module.

Extracts raw text from PDF and DOCX resumes, then uses the Model Router
(small-tier LLM) to produce a structured CandidateProfile. Integrated
with the profile store for one-time gap-check intake.

Supported formats:
  - PDF  (via pdfplumber)
  - DOCX (via python-docx)
"""

import json
import logging
from pathlib import Path
from typing import Optional

from backend.model_router import ModelRouter
from backend.parsing.profile_schema import (
    CandidateProfile,
    ContactInfo,
    Education,
    Experience,
    Project,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------

def extract_text_from_pdf(file_path: Path) -> str:
    """Extract all text from a PDF file using pdfplumber."""
    import pdfplumber

    text_parts: list[str] = []
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)

    return "\n\n".join(text_parts)


def extract_text_from_docx(file_path: Path) -> str:
    """Extract all text from a DOCX file using python-docx."""
    from docx import Document

    doc = Document(str(file_path))
    return "\n".join(para.text for para in doc.paragraphs if para.text.strip())


def extract_text(file_path: Path) -> str:
    """
    Extract text from a resume file (PDF or DOCX).

    Args:
        file_path: Path to the resume file.

    Returns:
        Extracted text as a string.

    Raises:
        ValueError: If the file extension is not supported.
        FileNotFoundError: If the file does not exist.
    """
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"Resume file not found: {path}")

    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return extract_text_from_pdf(path)
    elif suffix in (".docx", ".doc"):
        return extract_text_from_docx(path)
    else:
        raise ValueError(
            f"Unsupported resume format: '{suffix}'. "
            f"Supported: .pdf, .docx"
        )


# ---------------------------------------------------------------------------
# LLM-based structured extraction
# ---------------------------------------------------------------------------

EXTRACTION_SYSTEM_PROMPT = """You are a resume parser. Extract structured data from the resume text.

Return ONLY valid JSON matching this schema exactly — no markdown, no explanation:

{
  "name": "string",
  "contact": {
    "address": "string",
    "github_url": "string",
    "linkedin_url": "string",
    "email": "string",
    "phone": "string"
  },
  "experience": [
    {
      "type": "internship|full_time|part_time|contract",
      "title": "string",
      "company": "string",
      "duration_months": integer,
      "start_date": "YYYY-MM",
      "end_date": "YYYY-MM or Present",
      "description": "string",
      "is_fresher_relevant": boolean
    }
  ],
  "projects": [
    {
      "name": "string",
      "description": "string",
      "github_url": "string or null",
      "tech_stack": ["string"]
    }
  ],
  "skills": ["string"],
  "education": [
    {
      "institution": "string",
      "degree": "string",
      "field_of_study": "string",
      "start_date": "YYYY-MM",
      "end_date": "YYYY-MM",
      "gpa": "string or null"
    }
  ]
}

STRICT RULES:
1. Experience = ONLY real work/internship history. Never put personal projects here.
2. Projects = ONLY personal/academic projects. Never put work experience here.
3. duration_months must be exact (e.g. 6 for a 6-month internship) — never rounded.
4. is_fresher_relevant = true ONLY for internships relevant to the candidate's career.
5. For any missing field, use empty string "" or empty list [] — never null for required fields.
6. Skills should be individual, specific items (e.g. "Python", "React") — not paragraphs.
7. Return ONLY the JSON object — no wrapping text, no markdown code fences."""


def _build_extraction_prompt(resume_text: str) -> str:
    """Build the user prompt for structured extraction."""
    # Truncate very long resumes to avoid token limits
    truncated = resume_text[:8000] if len(resume_text) > 8000 else resume_text
    return f"Parse the following resume into the required JSON schema:\n\n{truncated}"


def _clean_llm_json(raw: str) -> str:
    """Strip markdown code fences and surrounding text from LLM output."""
    text = raw.strip()

    # Remove ```json ... ``` or ``` ... ```
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first line (```json) and last line (```)
        start = 1
        end = len(lines)
        for i in range(len(lines) - 1, -1, -1):
            if lines[i].strip() == "```":
                end = i
                break
        text = "\n".join(lines[start:end])

    return text.strip()


def parse_resume_with_llm(
    resume_text: str,
    router: Optional[ModelRouter] = None,
) -> CandidateProfile:
    """
    Use the Model Router to extract structured profile data from resume text.

    Args:
        resume_text: Raw text extracted from the resume.
        router: Optional ModelRouter instance (created if not provided).

    Returns:
        A validated CandidateProfile.

    Raises:
        RuntimeError: If LLM call fails or output cannot be parsed.
        ValueError: If the LLM output doesn't match the schema.
    """
    if not router:
        router = ModelRouter()

    prompt = _build_extraction_prompt(resume_text)

    result = router.complete(
        tier="parsing",
        prompt=prompt,
        system_prompt=EXTRACTION_SYSTEM_PROMPT,
    )

    raw_content = result.get("content", "")
    if not raw_content or not raw_content.strip():
        raise RuntimeError("LLM returned empty response for resume parsing")

    cleaned = _clean_llm_json(raw_content)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"LLM output is not valid JSON: {e}\n"
            f"Raw output (first 500 chars): {raw_content[:500]}"
        )

    try:
        profile = CandidateProfile(**data)
    except Exception as e:
        raise ValueError(f"LLM output doesn't match CandidateProfile schema: {e}")

    logger.info(
        "Parsed resume: name=%s, %d experience(s), %d project(s), %d skill(s)",
        profile.name,
        len(profile.experience),
        len(profile.projects),
        len(profile.skills),
    )

    return profile


# ---------------------------------------------------------------------------
# Full intake pipeline
# ---------------------------------------------------------------------------

def parse_resume(
    file_path: str | Path,
    router: Optional[ModelRouter] = None,
) -> CandidateProfile:
    """
    End-to-end resume parsing: extract text → LLM extraction → validated profile.

    Args:
        file_path: Path to the resume file (PDF or DOCX).
        router: Optional ModelRouter instance.

    Returns:
        A validated CandidateProfile.
    """
    path = Path(file_path)
    logger.info("Parsing resume: %s", path)

    text = extract_text(path)
    if not text.strip():
        raise RuntimeError(f"No text could be extracted from {path}")

    logger.info("Extracted %d characters from resume", len(text))

    profile = parse_resume_with_llm(text, router=router)
    return profile
