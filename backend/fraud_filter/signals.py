"""
Fraud signal checkers.

Individual functions that check specific legitimacy signals for a job listing.
These are composed by the main filter to produce a final legitimacy score.
"""

import logging
import re
from typing import List, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Hard blockers — any one of these disqualifies a listing immediately
# ---------------------------------------------------------------------------

# Patterns indicating the listing asks for money from applicants
FEE_PATTERNS = [
    r"registration\s+fee",
    r"training\s+fee",
    r"training\s+deposit",
    r"security\s+deposit",
    r"buy\s+(your\s+own\s+)?equipment",
    r"purchase\s+(your\s+own\s+)?equipment",
    r"pay\s+(?:for\s+)?(?:training|certification|background\s+check)",
    r"application\s+fee",
    r"processing\s+fee",
    r"enrollment\s+fee",
    r"upfront\s+(?:cost|payment|investment)",
    r"invest\s+(?:\$|₹|USD|INR)",
    r"(?:send|transfer|deposit)\s+(?:\$|₹|USD|INR)\s*\d+",
]

# Patterns indicating they want financial info at application stage
FINANCIAL_INFO_PATTERNS = [
    r"bank\s+(?:account|details|information)",
    r"credit\s+card\s+(?:number|details|information)",
    r"debit\s+card",
    r"\bSSN\b",
    r"\bsocial\s+security\s+number\b",
    r"\bAadhaar\b",
    r"\bPAN\s+(?:card|number|details)\b",
    r"routing\s+number",
    r"wire\s+transfer",
]

# Patterns for WhatsApp/Telegram-only communication
INFORMAL_ONLY_PATTERNS = [
    r"(?:contact|reach|message|apply)\s+(?:us\s+)?(?:on|via|through)\s+(?:WhatsApp|Telegram)",
    r"WhatsApp\s+(?:only|us\s+at|on)\s*[:\s]*[\+\d]",
    r"Telegram\s+(?:only|us\s+at|on|@)",
    r"send\s+(?:your\s+)?(?:resume|CV)\s+(?:on|via|to)\s+WhatsApp",
]

# Generic email domains (no company domain)
GENERIC_EMAIL_DOMAINS = {
    "gmail.com", "yahoo.com", "yahoo.co.in", "hotmail.com", "outlook.com",
    "aol.com", "mail.com", "protonmail.com", "yandex.com", "rediffmail.com",
    "live.com", "icloud.com",
}


def check_fee_requirement(text: str) -> Tuple[bool, str]:
    """Check if the listing mentions any fees or payments required from applicants."""
    text_lower = text.lower()
    for pattern in FEE_PATTERNS:
        match = re.search(pattern, text_lower)
        if match:
            return True, f"Fee/payment detected: '{match.group()}'"
    return False, ""


def check_financial_info_request(text: str) -> Tuple[bool, str]:
    """Check if the listing asks for bank details, SSN, etc. at application stage."""
    text_lower = text.lower()
    for pattern in FINANCIAL_INFO_PATTERNS:
        match = re.search(pattern, text_lower, re.IGNORECASE)
        if match:
            return True, f"Financial info request detected: '{match.group()}'"
    return False, ""


def check_informal_only_communication(text: str) -> Tuple[bool, str]:
    """Check if the entire hiring process is via WhatsApp/Telegram only."""
    text_lower = text.lower()
    for pattern in INFORMAL_ONLY_PATTERNS:
        match = re.search(pattern, text_lower, re.IGNORECASE)
        if match:
            # Only flag if there's NO professional email/website mentioned alongside
            has_company_email = bool(re.search(r'\b[\w.-]+@(?!gmail|yahoo|hotmail|outlook)\w+\.\w+', text))
            has_company_website = bool(re.search(r'https?://(?!wa\.me|t\.me|telegram)', text))
            if not has_company_email and not has_company_website:
                return True, f"Informal-only communication: '{match.group()}'"
    return False, ""


def check_no_company_domain(company_email: str) -> Tuple[bool, str]:
    """Check if the company uses only a generic email domain (no company email)."""
    if not company_email:
        return False, ""  # Absence of email is not a hard blocker by itself

    email_lower = company_email.strip().lower()
    domain = email_lower.split("@")[-1] if "@" in email_lower else ""

    if domain in GENERIC_EMAIL_DOMAINS:
        return True, f"Generic email domain: '{domain}' — no verifiable company domain"
    return False, ""


# ---------------------------------------------------------------------------
# Soft signals — scored and weighted
# ---------------------------------------------------------------------------

# Urgency-pressure language
URGENCY_PATTERNS = [
    r"apply\s+(?:within\s+)?\d+\s*(?:hour|hr|min)",
    r"immediate\s+(?:joining|start|hire|openings?)",
    r"no\s+interview\s+(?:required|needed|necessary)",
    r"guaranteed\s+(?:job|placement|hire|offer)",
    r"limited\s+(?:spots|positions|seats|openings?)\s+(?:available|left|remaining)",
    r"hurry",
    r"(?:last|final)\s+(?:date|chance)\s+(?:to\s+)?apply",
    r"don'?t\s+miss\s+(?:this|out)",
    r"walk[- ]?in\s+interview\s+(?:today|tomorrow|now)",
]

# Unrealistic salary indicators for fresher/entry-level roles
UNREALISTIC_SALARY_PATTERNS = [
    # These detect implausibly high figures for entry-level
    r"(?:\$|₹)\s*(?:\d{2,3})\s*(?:LPA|lpa|Lakh)",  # ₹ 50 LPA for fresher
    r"(?:\$)\s*(?:2[5-9]0|[3-9]\d{2})\s*[kK]",       # $250k+ for entry-level
]


def score_urgency_language(text: str) -> float:
    """
    Score urgency/pressure language.

    Returns 0.0 (no urgency) to 1.0 (extreme pressure).
    """
    text_lower = text.lower()
    matches = 0
    for pattern in URGENCY_PATTERNS:
        if re.search(pattern, text_lower):
            matches += 1

    if matches == 0:
        return 1.0   # No urgency = good signal
    elif matches == 1:
        return 0.5   # Minor urgency = neutral
    else:
        return 0.0   # Multiple urgency patterns = red flag


def score_salary_reasonableness(salary_text: str, experience_level: str = "fresher") -> float:
    """
    Score whether the salary is reasonable for the experience level.

    Returns 0.0 (unrealistic) to 1.0 (reasonable).
    """
    if not salary_text:
        return 0.7  # No salary info = slightly below neutral

    salary_lower = salary_text.lower()

    # Check for unrealistic patterns
    for pattern in UNREALISTIC_SALARY_PATTERNS:
        if re.search(pattern, salary_lower):
            return 0.1  # Very likely unrealistic

    # Zero pay / unpaid is suspicious for non-internship
    if "unpaid" in salary_lower and experience_level != "intern":
        return 0.3

    return 0.9  # Salary looks reasonable


def score_company_presence(
    has_linkedin: bool = False,
    has_glassdoor: bool = False,
    has_company_website: bool = False,
) -> float:
    """
    Score company's online presence.

    Returns 0.0 (no presence) to 1.0 (strong presence).
    """
    score = 0.0
    if has_company_website:
        score += 0.4
    if has_linkedin:
        score += 0.35
    if has_glassdoor:
        score += 0.25
    return min(score, 1.0)


def extract_hard_blockers(text: str, company_email: str = "") -> List[str]:
    """
    Run all hard-blocker checks and return list of reasons.

    Returns empty list if no hard blockers found.
    """
    blockers = []

    blocked, reason = check_fee_requirement(text)
    if blocked:
        blockers.append(reason)

    blocked, reason = check_financial_info_request(text)
    if blocked:
        blockers.append(reason)

    blocked, reason = check_informal_only_communication(text)
    if blocked:
        blockers.append(reason)

    blocked, reason = check_no_company_domain(company_email)
    if blocked:
        blockers.append(reason)

    return blockers
