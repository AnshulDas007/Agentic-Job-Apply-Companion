"""
Legal clause extraction and review module.

Extracts and summarizes legally binding clauses from job application forms
and documents. Enforces the non-negotiable guardrail: NEVER auto-accept
or auto-check any legally binding consent, agreement, or checkbox.

Key rules (from Section 10 of the build spec):
  - Never auto-accept: arbitration, non-compete, IP assignment, background check auth
  - Extract and summarize unusual clauses in plain language
  - Hard stop on any legally binding checkbox or agreement toggle
  - Typed-name e-signature may be auto-filled ONLY when standalone
  - If typed-name is adjacent to a consent checkbox, treat entire block as legal
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional, Tuple

from backend.model_router import ModelRouter

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Classification types
# ---------------------------------------------------------------------------

class ClauseType(str, Enum):
    """Types of legal clauses that can be detected."""
    ARBITRATION = "arbitration"
    NON_COMPETE = "non_compete"
    NON_SOLICIT = "non_solicit"
    IP_ASSIGNMENT = "ip_assignment"
    BACKGROUND_CHECK = "background_check"
    NDA = "nda"
    AT_WILL = "at_will"
    SEVERANCE = "severance"
    CONSENT_CHECKBOX = "consent_checkbox"
    ESIGNATURE = "esignature"
    DATA_PRIVACY = "data_privacy"
    RELOCATION = "relocation"
    OTHER = "other"


class ConsentElementType(str, Enum):
    """Types of consent elements on forms."""
    CHECKBOX = "checkbox"           # Always requires human action
    TOGGLE = "toggle"               # Always requires human action
    TYPED_NAME = "typed_name"       # May be auto-filled if standalone
    DRAWN_SIGNATURE = "drawn_sig"   # Always requires human action
    UPLOADED_SIGNATURE = "upload_sig"  # Always requires human action
    AGREEMENT_LINK = "agree_link"   # Always requires human action


class ReviewAction(str, Enum):
    """What action should be taken for a detected element."""
    HARD_STOP = "hard_stop"         # Cannot proceed without human review
    AUTO_FILL_OK = "auto_fill_ok"   # Safe to auto-fill (standalone typed-name only)
    FLAG_FOR_REVIEW = "flag"        # Bring to user's attention but not blocking


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class DetectedClause:
    """A single detected legal clause."""
    clause_type: ClauseType
    original_text: str
    plain_language_summary: str
    severity: str = "medium"  # low, medium, high, critical
    action: ReviewAction = ReviewAction.FLAG_FOR_REVIEW
    location: str = ""  # Where on the form this was found

    @property
    def is_blocking(self) -> bool:
        return self.action == ReviewAction.HARD_STOP


@dataclass
class ConsentElement:
    """A detected consent/signature element on a form."""
    element_type: ConsentElementType
    label_text: str
    action: ReviewAction
    reason: str = ""
    is_adjacent_to_consent: bool = False

    @property
    def is_blocking(self) -> bool:
        return self.action == ReviewAction.HARD_STOP


@dataclass
class LegalReviewResult:
    """Complete result of a legal review of a form or document."""
    clauses: List[DetectedClause] = field(default_factory=list)
    consent_elements: List[ConsentElement] = field(default_factory=list)
    can_proceed: bool = True
    blocking_reasons: List[str] = field(default_factory=list)
    model_used: str = ""
    provider_used: str = ""
    reviewed_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @property
    def has_blocking_clauses(self) -> bool:
        return any(c.is_blocking for c in self.clauses)

    @property
    def has_blocking_consent(self) -> bool:
        return any(e.is_blocking for e in self.consent_elements)

    @property
    def summary(self) -> str:
        parts = []
        if not self.can_proceed:
            parts.append(f"⛔ BLOCKED — {len(self.blocking_reasons)} issue(s) require human review")
        else:
            parts.append("✅ CLEAR — no blocking legal elements detected")

        if self.clauses:
            parts.append(f"  Clauses found: {len(self.clauses)}")
            for c in self.clauses:
                prefix = "⛔" if c.is_blocking else "⚠️"
                parts.append(f"    {prefix} [{c.clause_type.value}] {c.plain_language_summary[:80]}")

        if self.consent_elements:
            parts.append(f"  Consent elements: {len(self.consent_elements)}")
            for e in self.consent_elements:
                prefix = "⛔" if e.is_blocking else "✅"
                parts.append(f"    {prefix} [{e.element_type.value}] {e.label_text[:60]}")

        return "\n".join(parts)


# ---------------------------------------------------------------------------
# Rule-based clause detection (fast, no LLM needed)
# ---------------------------------------------------------------------------

# Patterns that indicate specific clause types
CLAUSE_PATTERNS: Dict[ClauseType, List[str]] = {
    ClauseType.ARBITRATION: [
        r"binding\s+arbitration",
        r"arbitration\s+agreement",
        r"waive\s+(?:your\s+)?right\s+to\s+(?:a\s+)?(?:jury\s+)?trial",
        r"dispute\s+resolution\s+(?:through|via)\s+arbitration",
        r"mandatory\s+arbitration",
    ],
    ClauseType.NON_COMPETE: [
        r"non[\-\s]?compete",
        r"non[\-\s]?competition",
        r"not\s+(?:directly\s+)?compete\s+with",
        r"restrictive\s+covenant",
        r"covenant\s+not\s+to\s+compete",
    ],
    ClauseType.NON_SOLICIT: [
        r"non[\-\s]?solicit",
        r"not\s+solicit\s+(?:any\s+)?(?:employees|clients|customers)",
    ],
    ClauseType.IP_ASSIGNMENT: [
        r"assign\s+(?:all\s+)?(?:intellectual\s+property|ip)\s+rights",
        r"work\s+(?:product|for\s+hire)",
        r"(?:all|any)\s+inventions\s+(?:created|developed|made)\s+(?:during|while)",
        r"assign\s+(?:to\s+the\s+company\s+)?(?:all\s+)?(?:rights|ownership)",
        r"intellectual\s+property\s+(?:belongs|assigned)\s+to",
    ],
    ClauseType.BACKGROUND_CHECK: [
        r"background\s+(?:check|screening|investigation)",
        r"authorize\s+(?:a\s+)?(?:background|criminal|credit)\s+(?:check|screening)",
        r"consent\s+to\s+(?:a\s+)?(?:background|criminal)\s+(?:check|investigation)",
    ],
    ClauseType.NDA: [
        r"non[\-\s]?disclosure\s+agreement",
        r"confidentiality\s+agreement",
        r"nda",
        r"proprietary\s+information\s+agreement",
    ],
}

SEVERITY_BY_TYPE: Dict[ClauseType, str] = {
    ClauseType.ARBITRATION: "critical",
    ClauseType.NON_COMPETE: "critical",
    ClauseType.NON_SOLICIT: "high",
    ClauseType.IP_ASSIGNMENT: "critical",
    ClauseType.BACKGROUND_CHECK: "high",
    ClauseType.NDA: "medium",
    ClauseType.AT_WILL: "low",
    ClauseType.DATA_PRIVACY: "low",
}


def detect_clauses_rule_based(text: str) -> List[DetectedClause]:
    """
    Detect legal clauses using regex patterns (fast, no LLM needed).

    This is the first-pass detection. The LLM-based detection runs
    after this for more nuanced analysis.

    Args:
        text: The text to scan for legal clauses.

    Returns:
        List of detected clauses.
    """
    detected = []
    text_lower = text.lower()

    for clause_type, patterns in CLAUSE_PATTERNS.items():
        for pattern in patterns:
            matches = list(re.finditer(pattern, text_lower))
            if matches:
                # Extract surrounding context for the first match
                match = matches[0]
                start = max(0, match.start() - 100)
                end = min(len(text), match.end() + 100)
                context = text[start:end].strip()

                detected.append(DetectedClause(
                    clause_type=clause_type,
                    original_text=context,
                    plain_language_summary=_rule_based_summary(clause_type),
                    severity=SEVERITY_BY_TYPE.get(clause_type, "medium"),
                    action=ReviewAction.HARD_STOP,
                ))
                break  # One detection per clause type is enough

    return detected


def _rule_based_summary(clause_type: ClauseType) -> str:
    """Generate a plain-language summary for a clause type."""
    summaries = {
        ClauseType.ARBITRATION: (
            "This agreement requires disputes to be resolved through binding "
            "arbitration instead of a court/jury trial."
        ),
        ClauseType.NON_COMPETE: (
            "This includes a non-compete clause that may restrict where you "
            "can work after leaving this company."
        ),
        ClauseType.NON_SOLICIT: (
            "This includes a non-solicitation clause restricting you from "
            "recruiting employees or clients of this company."
        ),
        ClauseType.IP_ASSIGNMENT: (
            "This clause assigns intellectual property rights for work created "
            "during employment to the company."
        ),
        ClauseType.BACKGROUND_CHECK: (
            "This requires authorization for a background check or screening."
        ),
        ClauseType.NDA: (
            "This includes a non-disclosure or confidentiality agreement."
        ),
    }
    return summaries.get(clause_type, f"Legal clause detected: {clause_type.value}")


# ---------------------------------------------------------------------------
# Consent element classification
# ---------------------------------------------------------------------------

def classify_consent_element(
    element_type: ConsentElementType,
    label_text: str,
    is_adjacent_to_consent: bool = False,
) -> ConsentElement:
    """
    Classify a consent element and determine the required action.

    Rules from Section 10:
    - Checkboxes and toggles: ALWAYS require human action
    - Typed-name e-signature: May auto-fill ONLY if standalone
    - If typed-name is adjacent to consent checkbox: treat as HARD_STOP
    - Drawn/uploaded signatures: ALWAYS require human action

    Args:
        element_type: The type of form element.
        label_text: The text label near the element.
        is_adjacent_to_consent: Whether a consent checkbox is nearby.

    Returns:
        ConsentElement with the determined action.
    """
    # Checkboxes and toggles — ALWAYS block
    if element_type in (ConsentElementType.CHECKBOX, ConsentElementType.TOGGLE):
        return ConsentElement(
            element_type=element_type,
            label_text=label_text,
            action=ReviewAction.HARD_STOP,
            reason="Consent checkbox/toggle requires explicit human action",
            is_adjacent_to_consent=is_adjacent_to_consent,
        )

    # Drawn or uploaded signatures — ALWAYS block
    if element_type in (ConsentElementType.DRAWN_SIGNATURE, ConsentElementType.UPLOADED_SIGNATURE):
        return ConsentElement(
            element_type=element_type,
            label_text=label_text,
            action=ReviewAction.HARD_STOP,
            reason="Signature upload/drawing requires human action",
            is_adjacent_to_consent=is_adjacent_to_consent,
        )

    # Agreement links — ALWAYS block
    if element_type == ConsentElementType.AGREEMENT_LINK:
        return ConsentElement(
            element_type=element_type,
            label_text=label_text,
            action=ReviewAction.HARD_STOP,
            reason="Agreement acknowledgment requires human review",
            is_adjacent_to_consent=is_adjacent_to_consent,
        )

    # Typed-name e-signature — the narrow exception
    if element_type == ConsentElementType.TYPED_NAME:
        if is_adjacent_to_consent:
            return ConsentElement(
                element_type=element_type,
                label_text=label_text,
                action=ReviewAction.HARD_STOP,
                reason=(
                    "Typed-name field is adjacent to a consent checkbox — "
                    "treating entire block as legal acceptance requiring human review"
                ),
                is_adjacent_to_consent=True,
            )
        else:
            # Standalone typed-name — safe to auto-fill with candidate name
            return ConsentElement(
                element_type=element_type,
                label_text=label_text,
                action=ReviewAction.AUTO_FILL_OK,
                reason="Standalone typed-name e-signature — safe to auto-fill with legal name",
                is_adjacent_to_consent=False,
            )

    # Default: flag for review
    return ConsentElement(
        element_type=element_type,
        label_text=label_text,
        action=ReviewAction.FLAG_FOR_REVIEW,
        reason="Unknown consent element type — flagging for review",
        is_adjacent_to_consent=is_adjacent_to_consent,
    )


# ---------------------------------------------------------------------------
# LLM-based clause analysis (for nuanced/ambiguous cases)
# ---------------------------------------------------------------------------

def _build_legal_system_prompt() -> str:
    """Build the system prompt for LLM-based legal analysis."""
    return """You are a legal clause analyzer for job applications. Your job is to
identify and summarize any legally binding clauses in plain language.

For each clause found, output in this exact format (one per line):
CLAUSE|<type>|<severity>|<plain_language_summary>

Types: arbitration, non_compete, non_solicit, ip_assignment, background_check,
       nda, at_will, severance, data_privacy, relocation, other

Severity: low, medium, high, critical

Rules:
- Be conservative: if something MIGHT be legally binding, flag it.
- Use plain, simple language in summaries.
- Focus on what the clause MEANS for the applicant, not legal jargon.
- If no clauses are found, output: NO_CLAUSES_FOUND

Example output:
CLAUSE|arbitration|critical|Disputes must go through binding arbitration, waiving your right to a jury trial.
CLAUSE|ip_assignment|critical|All work you create during employment belongs to the company, including side projects."""


def _build_legal_user_prompt(text: str) -> str:
    """Build the user prompt for legal analysis."""
    # Truncate very long texts
    truncated = text[:4000] if len(text) > 4000 else text
    return (
        "Analyze the following text from a job application form for any "
        "legally binding clauses. Identify ALL clauses that an applicant "
        "should review before agreeing.\n\n"
        f"TEXT:\n{truncated}"
    )


def parse_llm_clauses(response: str) -> List[DetectedClause]:
    """
    Parse the LLM response into DetectedClause objects.

    Expected format per line: CLAUSE|<type>|<severity>|<summary>
    """
    clauses = []
    for line in response.strip().split("\n"):
        line = line.strip()
        if line.startswith("NO_CLAUSES_FOUND"):
            return []
        if not line.startswith("CLAUSE|"):
            continue

        parts = line.split("|", 3)
        if len(parts) < 4:
            continue

        _, type_str, severity, summary = parts

        # Map type string to ClauseType
        try:
            clause_type = ClauseType(type_str.strip().lower())
        except ValueError:
            clause_type = ClauseType.OTHER

        severity = severity.strip().lower()
        if severity not in ("low", "medium", "high", "critical"):
            severity = "medium"

        clauses.append(DetectedClause(
            clause_type=clause_type,
            original_text="",  # LLM doesn't return original text
            plain_language_summary=summary.strip(),
            severity=severity,
            action=ReviewAction.HARD_STOP if severity in ("high", "critical") else ReviewAction.FLAG_FOR_REVIEW,
        ))

    return clauses


# ---------------------------------------------------------------------------
# Legal Reviewer
# ---------------------------------------------------------------------------

class LegalReviewer:
    """
    Reviews job application forms and documents for legal clauses.

    Two-stage pipeline:
    1. Rule-based detection (fast regex patterns)
    2. LLM-based analysis (for nuanced/ambiguous cases)

    Always errs on the side of caution — if anything MIGHT be
    legally binding, it blocks and requires human review.

    Usage:
        reviewer = LegalReviewer()

        # Review form text
        result = reviewer.review_text(form_text)
        if not result.can_proceed:
            # Show blocking reasons to user
            print(result.summary)

        # Check a specific consent element
        element = reviewer.check_consent_element(
            element_type=ConsentElementType.CHECKBOX,
            label_text="I agree to the terms",
        )
        if element.is_blocking:
            # Must wait for human action
    """

    def __init__(self, model_router: Optional[ModelRouter] = None):
        self._router = model_router or ModelRouter()

    def review_text(
        self,
        text: str,
        use_llm: bool = True,
    ) -> LegalReviewResult:
        """
        Review text for legal clauses.

        Args:
            text: The text to review (form content, terms, etc.)
            use_llm: Whether to also run LLM-based analysis.

        Returns:
            LegalReviewResult with all detected clauses and blocking status.
        """
        if not text or not text.strip():
            return LegalReviewResult(can_proceed=True)

        # Stage 1: Rule-based detection
        rule_clauses = detect_clauses_rule_based(text)

        # Stage 2: LLM-based analysis (optional)
        llm_clauses = []
        model_used = ""
        provider_used = ""

        if use_llm:
            try:
                system_prompt = _build_legal_system_prompt()
                user_prompt = _build_legal_user_prompt(text)

                result = self._router.complete(
                    tier="legal_review",
                    prompt=user_prompt,
                    system_prompt=system_prompt,
                )
                llm_clauses = parse_llm_clauses(result.get("content", ""))
                model_used = result.get("model", "")
                provider_used = result.get("provider", "")

            except RuntimeError as e:
                logger.warning("LLM legal analysis failed: %s — using rule-based only", e)

        # Merge results (deduplicate by clause type)
        all_clauses = list(rule_clauses)
        seen_types = {c.clause_type for c in rule_clauses}
        for c in llm_clauses:
            if c.clause_type not in seen_types:
                all_clauses.append(c)
                seen_types.add(c.clause_type)

        # Determine blocking status
        blocking_reasons = []
        for clause in all_clauses:
            if clause.is_blocking:
                blocking_reasons.append(
                    f"[{clause.clause_type.value}] {clause.plain_language_summary}"
                )

        return LegalReviewResult(
            clauses=all_clauses,
            can_proceed=len(blocking_reasons) == 0,
            blocking_reasons=blocking_reasons,
            model_used=model_used,
            provider_used=provider_used,
        )

    def check_consent_element(
        self,
        element_type: ConsentElementType,
        label_text: str,
        is_adjacent_to_consent: bool = False,
    ) -> ConsentElement:
        """
        Check a single consent/signature element.

        Args:
            element_type: The type of form element.
            label_text: The text label near the element.
            is_adjacent_to_consent: Whether a consent checkbox is nearby.

        Returns:
            ConsentElement with the determined action.
        """
        return classify_consent_element(element_type, label_text, is_adjacent_to_consent)

    def review_form_elements(
        self,
        elements: List[Dict],
        form_text: str = "",
    ) -> LegalReviewResult:
        """
        Review a set of form elements for legal/consent issues.

        Args:
            elements: List of dicts with keys:
                - type: str (checkbox, toggle, typed_name, etc.)
                - label: str
                - adjacent_to_consent: bool (optional)
            form_text: Optional full form text for clause analysis.

        Returns:
            LegalReviewResult with clauses and consent elements.
        """
        # Review text if provided
        text_result = self.review_text(form_text) if form_text else LegalReviewResult()

        # Check consent elements
        consent_elements = []
        for elem in elements:
            try:
                etype = ConsentElementType(elem.get("type", ""))
            except ValueError:
                continue

            ce = self.check_consent_element(
                element_type=etype,
                label_text=elem.get("label", ""),
                is_adjacent_to_consent=elem.get("adjacent_to_consent", False),
            )
            consent_elements.append(ce)

        # Combine results
        blocking_reasons = list(text_result.blocking_reasons)
        for ce in consent_elements:
            if ce.is_blocking:
                blocking_reasons.append(
                    f"[{ce.element_type.value}] {ce.reason}"
                )

        return LegalReviewResult(
            clauses=text_result.clauses,
            consent_elements=consent_elements,
            can_proceed=len(blocking_reasons) == 0,
            blocking_reasons=blocking_reasons,
            model_used=text_result.model_used,
            provider_used=text_result.provider_used,
        )
