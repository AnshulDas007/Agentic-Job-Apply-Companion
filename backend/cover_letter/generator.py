"""
Cover letter generator.

Generates cover letters ONLY when a form explicitly marks them as mandatory.
Uses the best available LLM model tier for natural, specific writing.

Key rules enforced:
  - Only generate when mandatory — skip otherwise
  - Draw exclusively from real CandidateProfile data (experience + projects)
  - No stock AI phrases (banned phrase list enforced in post-processing)
  - Vary sentence length and structure naturally
  - Plain, natural language — no jargon
  - Every letter goes to a review queue before submission
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from backend.model_router import ModelRouter
from backend.parsing.profile_schema import CandidateProfile

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Banned phrase list — stock AI phrases that make letters sound generic
# ---------------------------------------------------------------------------

BANNED_PHRASES = [
    "in today's fast-paced world",
    "i am excited to leverage my skills",
    "passionate about",
    "dynamic environment",
    "results-driven",
    "detail-oriented",
    "proven track record",
    "strong communicator",
    "team player",
    "self-starter",
    "go-getter",
    "synergy",
    "paradigm shift",
    "think outside the box",
    "value-add",
    "best-in-class",
    "cutting-edge",
    "seasoned professional",
    "highly motivated individual",
    "i believe i would be a great fit",
    "as a passionate professional",
    "i am confident that",
    "unique opportunity",
    "to whom it may concern",
    "i am writing to express my interest",
    "please find attached",
    "dear hiring manager",  # We use the actual company name instead
    "i look forward to discussing",
    "please do not hesitate to contact",
    "leveraging my expertise",
    "i am eager to contribute",
]


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class CoverLetterResult:
    """Result of a cover letter generation attempt."""

    generated: bool
    content: str = ""
    job_title: str = ""
    company: str = ""
    reason_skipped: str = ""
    banned_phrases_found: List[str] = field(default_factory=list)
    model_used: str = ""
    provider_used: str = ""
    tokens_used: int = 0
    generated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @property
    def needs_review(self) -> bool:
        """All generated letters need human review."""
        return self.generated

    @property
    def summary(self) -> str:
        if not self.generated:
            return f"SKIPPED ({self.reason_skipped}): {self.job_title} @ {self.company}"
        status = "REVIEW" if self.banned_phrases_found else "READY"
        return f"[{status}] {self.job_title} @ {self.company} ({len(self.content)} chars)"


# ---------------------------------------------------------------------------
# System prompt builder
# ---------------------------------------------------------------------------

def _build_system_prompt() -> str:
    """Build the system prompt for cover letter generation."""
    return """You are a professional cover letter writer. Your job is to write
a concise, specific, and natural-sounding cover letter.

CRITICAL RULES:
1. Write in first person from the candidate's perspective.
2. Use ONLY the real experience, projects, and skills provided — never invent or embellish.
3. Be SPECIFIC: reference concrete project names, technologies used, and actual outcomes.
4. Keep it concise: 3-4 short paragraphs maximum, under 300 words total.
5. Vary your sentence length — mix short punchy sentences with longer ones.
6. Use plain, natural language. No jargon, no buzzwords.
7. NEVER use any of these stock AI phrases:
   - "passionate about", "dynamic environment", "proven track record"
   - "results-driven", "detail-oriented", "leveraging my expertise"
   - "in today's fast-paced world", "I am excited to leverage"
   - "I believe I would be a great fit", "as a passionate professional"
   - "Dear Hiring Manager" (use the company name instead)
   - "I look forward to discussing", "please do not hesitate"
8. Start with something specific about the company or role — not a generic opener.
9. End naturally — no formulaic closings.
10. The letter should sound like a real person wrote it, not an AI.

FORMAT:
- No subject line or headers — just the letter body.
- Use paragraph breaks, not bullet points.
- Sign off with the candidate's name."""


def _build_user_prompt(
    profile: CandidateProfile,
    job_title: str,
    company: str,
    job_description: str,
) -> str:
    """Build the user prompt with candidate data and job details."""
    parts = [f"Write a cover letter for the following position:\n"]
    parts.append(f"POSITION: {job_title} at {company}\n")

    if job_description:
        # Truncate very long descriptions to save tokens
        desc = job_description[:2000] if len(job_description) > 2000 else job_description
        parts.append(f"JOB DESCRIPTION:\n{desc}\n")

    parts.append("CANDIDATE INFORMATION:")
    parts.append(f"Name: {profile.name}")

    # Experience — real work history only
    if profile.experience:
        parts.append("\nWORK EXPERIENCE:")
        for exp in profile.experience:
            parts.append(
                f"- {exp.title} at {exp.company} ({exp.type}, "
                f"{exp.duration_months} months): {exp.description}"
            )
    else:
        parts.append("\nWORK EXPERIENCE: None (recent graduate)")

    # Projects — real projects only
    if profile.projects:
        parts.append("\nPROJECTS:")
        for proj in profile.projects:
            tech = ", ".join(proj.tech_stack) if proj.tech_stack else "various"
            parts.append(f"- {proj.name} ({tech}): {proj.description}")

    # Skills
    if profile.skills:
        parts.append(f"\nSKILLS: {', '.join(profile.skills)}")

    # Education
    if profile.education:
        parts.append("\nEDUCATION:")
        for edu in profile.education:
            parts.append(f"- {edu.degree} in {edu.field_of_study} from {edu.institution}")

    parts.append(
        "\nRemember: Use ONLY the information above. Be specific. "
        "Reference actual project names and technologies. "
        "Keep it under 300 words. Sound human, not AI."
    )

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Post-processing
# ---------------------------------------------------------------------------

def check_banned_phrases(text: str) -> List[str]:
    """Check the generated text for banned stock AI phrases."""
    found = []
    text_lower = text.lower()
    for phrase in BANNED_PHRASES:
        if phrase in text_lower:
            found.append(phrase)
    return found


def clean_cover_letter(text: str) -> str:
    """
    Clean up generated cover letter text.

    Removes common artifacts:
    - Leading/trailing whitespace
    - "Subject:" or "Re:" lines
    - Duplicate newlines
    """
    # Remove subject/re lines
    lines = text.strip().split("\n")
    cleaned_lines = []
    for line in lines:
        stripped = line.strip().lower()
        if stripped.startswith("subject:") or stripped.startswith("re:"):
            continue
        cleaned_lines.append(line)

    text = "\n".join(cleaned_lines).strip()

    # Collapse triple+ newlines to double
    text = re.sub(r'\n{3,}', '\n\n', text)

    return text


# ---------------------------------------------------------------------------
# Cover Letter Generator
# ---------------------------------------------------------------------------

class CoverLetterGenerator:
    """
    Generates cover letters using the best available LLM model.

    Enforces all cover letter rules from the build specification:
    - Only generates when explicitly told to (mandatory field)
    - Uses real profile data only
    - Checks for and flags banned AI phrases
    - All letters go through a review queue

    Usage:
        generator = CoverLetterGenerator()

        # Check if generation is needed
        if form_requires_cover_letter:
            result = generator.generate(
                profile=profile,
                job_title="Software Engineer",
                company="Stripe",
                job_description="Build payment APIs...",
            )
            if result.generated and result.needs_review:
                # Present to user for review before submission
                print(result.content)
    """

    def __init__(self, model_router: Optional[ModelRouter] = None):
        self._router = model_router or ModelRouter()

    def generate(
        self,
        profile: CandidateProfile,
        job_title: str,
        company: str,
        job_description: str = "",
        is_mandatory: bool = True,
    ) -> CoverLetterResult:
        """
        Generate a cover letter for a specific job application.

        Args:
            profile: The candidate's profile (source of truth for all content).
            job_title: Title of the position.
            company: Company name.
            job_description: Full job description text.
            is_mandatory: Whether the cover letter is mandatory on the form.
                          Only generates if True.

        Returns:
            CoverLetterResult with the generated letter or skip reason.
        """
        # Rule: Only generate when form marks it mandatory
        if not is_mandatory:
            logger.info("Cover letter not mandatory for %s @ %s — skipping", job_title, company)
            return CoverLetterResult(
                generated=False,
                job_title=job_title,
                company=company,
                reason_skipped="Cover letter not marked as mandatory on the form",
            )

        # Validate we have enough profile data to write something meaningful
        if not profile.experience and not profile.projects:
            logger.warning(
                "No experience or projects in profile — cover letter would be generic"
            )
            return CoverLetterResult(
                generated=False,
                job_title=job_title,
                company=company,
                reason_skipped="Profile has no experience or projects to draw from",
            )

        # Build prompts
        system_prompt = _build_system_prompt()
        user_prompt = _build_user_prompt(profile, job_title, company, job_description)

        # Call LLM via model router — use "cover_letter" tier (best model)
        try:
            result = self._router.complete(
                tier="cover_letter",
                prompt=user_prompt,
                system_prompt=system_prompt,
            )
        except RuntimeError as e:
            logger.error("Cover letter generation failed: %s", e)
            return CoverLetterResult(
                generated=False,
                job_title=job_title,
                company=company,
                reason_skipped=f"LLM generation failed: {e}",
            )

        raw_content = result.get("content", "")
        if not raw_content or not raw_content.strip():
            return CoverLetterResult(
                generated=False,
                job_title=job_title,
                company=company,
                reason_skipped="LLM returned empty response",
            )

        # Post-process
        cleaned = clean_cover_letter(raw_content)
        banned_found = check_banned_phrases(cleaned)

        if banned_found:
            logger.warning(
                "Cover letter contains %d banned phrases: %s",
                len(banned_found), banned_found,
            )

        tokens_total = result.get("tokens_in", 0) + result.get("tokens_out", 0)

        return CoverLetterResult(
            generated=True,
            content=cleaned,
            job_title=job_title,
            company=company,
            banned_phrases_found=banned_found,
            model_used=result.get("model", ""),
            provider_used=result.get("provider", ""),
            tokens_used=tokens_total,
        )

    def skip(self, job_title: str, company: str, reason: str = "") -> CoverLetterResult:
        """
        Explicitly skip cover letter generation.

        Use when the form doesn't require a cover letter.
        """
        return CoverLetterResult(
            generated=False,
            job_title=job_title,
            company=company,
            reason_skipped=reason or "Cover letter not required",
        )
