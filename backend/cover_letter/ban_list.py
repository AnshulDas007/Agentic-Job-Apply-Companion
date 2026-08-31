"""
Banned phrase list for cover letter generation.

Centralizes the list of stock AI phrases that make cover letters
detectable as AI-generated. These phrases are checked in post-processing
and flagged for regeneration.

The actual fix for "AI-detectability" is specificity, not evasion.
Letters built from real, concrete details read as human because they
substantively are.
"""

from typing import List


# ---------------------------------------------------------------------------
# Banned phrases — stock AI filler that must never appear
# ---------------------------------------------------------------------------

BANNED_PHRASES: List[str] = [
    # Generic openers
    "in today's fast-paced world",
    "i am writing to express my interest",
    "to whom it may concern",
    "dear hiring manager",

    # Self-description filler
    "i am excited to leverage my skills",
    "passionate about",
    "as a passionate professional",
    "i believe i would be a great fit",
    "i am confident that",
    "highly motivated individual",
    "i am eager to contribute",
    "leveraging my expertise",

    # Buzzwords and jargon
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

    # Generic closings
    "i look forward to discussing",
    "please do not hesitate to contact",
    "please find attached",
    "unique opportunity",
]


def check_banned_phrases(text: str) -> List[str]:
    """
    Check text for banned stock AI phrases.

    Args:
        text: The generated cover letter text.

    Returns:
        List of banned phrases found in the text.
    """
    found = []
    text_lower = text.lower()
    for phrase in BANNED_PHRASES:
        if phrase in text_lower:
            found.append(phrase)
    return found


def is_clean(text: str) -> bool:
    """Return True if the text contains no banned phrases."""
    return len(check_banned_phrases(text)) == 0
