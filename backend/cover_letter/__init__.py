"""
Cover letter package — conditional generation with specificity enforcement.

Public API:
    - CoverLetterGenerator: Generates cover letters using LLM
    - CoverLetterResult: Generation result dataclass
    - check_banned_phrases: Scans text for stock AI phrases
    - BANNED_PHRASES: List of disallowed generic phrases
"""

from backend.cover_letter.generator import (
    CoverLetterGenerator,
    CoverLetterResult,
    check_banned_phrases,
    BANNED_PHRASES,
)

__all__ = [
    "CoverLetterGenerator",
    "CoverLetterResult",
    "check_banned_phrases",
    "BANNED_PHRASES",
]
