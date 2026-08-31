"""
Legal clause detection patterns.

Centralizes regex patterns and keyword lists for identifying
legally binding clauses in job application forms and documents.
Used by the LegalReviewer for rule-based (fast, no LLM) detection.
"""

import re
from enum import Enum
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Clause types (mirrors legal_review/reviewer.py ClauseType)
# ---------------------------------------------------------------------------

class ClauseCategory(str, Enum):
    """Categories of legal clauses that can be detected."""
    ARBITRATION = "arbitration"
    NON_COMPETE = "non_compete"
    NON_SOLICIT = "non_solicit"
    IP_ASSIGNMENT = "ip_assignment"
    BACKGROUND_CHECK = "background_check"
    NDA = "nda"
    AT_WILL = "at_will"
    DATA_PRIVACY = "data_privacy"
    RELOCATION = "relocation"


# ---------------------------------------------------------------------------
# Pattern definitions
# ---------------------------------------------------------------------------

CLAUSE_PATTERNS: Dict[ClauseCategory, List[str]] = {
    ClauseCategory.ARBITRATION: [
        r"binding\s+arbitration",
        r"arbitration\s+agreement",
        r"waive\s+(?:your\s+)?right\s+to\s+(?:a\s+)?(?:jury\s+)?trial",
        r"dispute\s+resolution\s+(?:through|via)\s+arbitration",
        r"mandatory\s+arbitration",
        r"individual\s+arbitration",
        r"class\s+action\s+waiver",
    ],
    ClauseCategory.NON_COMPETE: [
        r"non[\-\s]?compete",
        r"non[\-\s]?competition",
        r"not\s+(?:directly\s+)?compete\s+with",
        r"restrictive\s+covenant",
        r"covenant\s+not\s+to\s+compete",
        r"prohibited\s+from\s+(?:working|engaging)",
    ],
    ClauseCategory.NON_SOLICIT: [
        r"non[\-\s]?solicit",
        r"not\s+solicit\s+(?:any\s+)?(?:employees|clients|customers)",
        r"no[\-\s]?hire\s+(?:agreement|clause)",
    ],
    ClauseCategory.IP_ASSIGNMENT: [
        r"assign\s+(?:all\s+)?(?:intellectual\s+property|ip)\s+rights",
        r"work\s+(?:product|for\s+hire)",
        r"(?:all|any)\s+inventions\s+(?:created|developed|made)\s+(?:during|while)",
        r"assign\s+(?:to\s+the\s+company\s+)?(?:all\s+)?(?:rights|ownership)",
        r"intellectual\s+property\s+(?:belongs|assigned)\s+to",
        r"prior\s+inventions?\s+(?:disclosure|agreement)",
    ],
    ClauseCategory.BACKGROUND_CHECK: [
        r"background\s+(?:check|screening|investigation)",
        r"authorize\s+(?:a\s+)?(?:background|criminal|credit)\s+(?:check|screening)",
        r"consent\s+to\s+(?:a\s+)?(?:background|criminal)\s+(?:check|investigation)",
        r"drug\s+(?:test|screening)",
    ],
    ClauseCategory.NDA: [
        r"non[\-\s]?disclosure\s+agreement",
        r"confidentiality\s+agreement",
        r"\bnda\b",
        r"proprietary\s+information\s+agreement",
    ],
    ClauseCategory.AT_WILL: [
        r"at[\-\s]?will\s+employ",
        r"employment\s+is\s+at[\-\s]?will",
        r"either\s+party\s+may\s+terminate",
    ],
    ClauseCategory.DATA_PRIVACY: [
        r"data\s+(?:privacy|protection)\s+(?:policy|notice|agreement)",
        r"gdpr\s+(?:consent|compliance)",
        r"personal\s+data\s+(?:processing|collection)",
        r"consent\s+to\s+(?:the\s+)?(?:processing|collection)\s+of",
    ],
}

# Severity levels for each clause category
SEVERITY_MAP: Dict[ClauseCategory, str] = {
    ClauseCategory.ARBITRATION: "critical",
    ClauseCategory.NON_COMPETE: "critical",
    ClauseCategory.NON_SOLICIT: "high",
    ClauseCategory.IP_ASSIGNMENT: "critical",
    ClauseCategory.BACKGROUND_CHECK: "high",
    ClauseCategory.NDA: "medium",
    ClauseCategory.AT_WILL: "low",
    ClauseCategory.DATA_PRIVACY: "low",
    ClauseCategory.RELOCATION: "low",
}

# Plain-language summaries for each category
SUMMARIES: Dict[ClauseCategory, str] = {
    ClauseCategory.ARBITRATION: (
        "This agreement requires disputes to be resolved through binding "
        "arbitration instead of a court/jury trial."
    ),
    ClauseCategory.NON_COMPETE: (
        "This includes a non-compete clause that may restrict where you "
        "can work after leaving this company."
    ),
    ClauseCategory.NON_SOLICIT: (
        "This includes a non-solicitation clause restricting you from "
        "recruiting employees or clients of this company."
    ),
    ClauseCategory.IP_ASSIGNMENT: (
        "This requires you to assign intellectual property rights for "
        "work created during employment to the company."
    ),
    ClauseCategory.BACKGROUND_CHECK: (
        "This authorizes the company to conduct a background check on you."
    ),
    ClauseCategory.NDA: (
        "This is a non-disclosure agreement requiring you to keep "
        "company information confidential."
    ),
    ClauseCategory.AT_WILL: (
        "This states that employment is at-will and can be terminated "
        "by either party at any time."
    ),
    ClauseCategory.DATA_PRIVACY: (
        "This describes how your personal data will be collected, "
        "processed, and stored."
    ),
}


# ---------------------------------------------------------------------------
# Consent element patterns
# ---------------------------------------------------------------------------

CONSENT_KEYWORDS: List[str] = [
    "i agree",
    "i accept",
    "i acknowledge",
    "i consent",
    "i authorize",
    "i certify",
    "by checking this box",
    "by signing below",
    "i have read and agree",
    "terms and conditions",
    "terms of service",
    "privacy policy",
]


# ---------------------------------------------------------------------------
# Detection functions
# ---------------------------------------------------------------------------

def scan_for_clauses(
    text: str,
) -> List[Tuple[ClauseCategory, str, str, str]]:
    """
    Scan text for legal clause patterns.

    Args:
        text: The text to scan.

    Returns:
        List of tuples: (category, matched_text, context, severity)
    """
    results = []
    text_lower = text.lower()

    for category, patterns in CLAUSE_PATTERNS.items():
        for pattern in patterns:
            matches = list(re.finditer(pattern, text_lower))
            if matches:
                match = matches[0]
                start = max(0, match.start() - 100)
                end = min(len(text), match.end() + 100)
                context = text[start:end].strip()
                severity = SEVERITY_MAP.get(category, "medium")

                results.append((category, match.group(), context, severity))
                break  # One detection per category is sufficient

    return results


def has_consent_language(text: str) -> bool:
    """Check if text contains consent/agreement language."""
    text_lower = text.lower()
    return any(kw in text_lower for kw in CONSENT_KEYWORDS)


def get_summary(category: ClauseCategory) -> str:
    """Get the plain-language summary for a clause category."""
    return SUMMARIES.get(category, "Legal clause detected — review required.")
