"""
Legal review package — clause extraction, summarization, and consent detection.

Public API:
    - LegalReviewer: Reviews forms/text for legal clauses and consent elements
    - LegalReviewResult: Complete review result
    - DetectedClause: A single detected clause
    - ConsentElement: A detected consent/signature form element
    - ClauseType: Enum of clause types
    - ConsentElementType: Enum of consent element types
    - ReviewAction: Enum of required actions
"""

from backend.legal_review.reviewer import (
    LegalReviewer,
    LegalReviewResult,
    DetectedClause,
    ConsentElement,
    ClauseType,
    ConsentElementType,
    ReviewAction,
    detect_clauses_rule_based,
    classify_consent_element,
    parse_llm_clauses,
)

__all__ = [
    "LegalReviewer",
    "LegalReviewResult",
    "DetectedClause",
    "ConsentElement",
    "ClauseType",
    "ConsentElementType",
    "ReviewAction",
    "detect_clauses_rule_based",
    "classify_consent_element",
    "parse_llm_clauses",
]
