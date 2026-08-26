"""
Tests for the legal review module.

Tests clause detection (rule-based and LLM-parsed), consent element
classification, and the full LegalReviewer integration.
"""

import pytest
from unittest.mock import MagicMock

from backend.legal_review.reviewer import (
    ClauseType,
    ConsentElement,
    ConsentElementType,
    DetectedClause,
    LegalReviewResult,
    LegalReviewer,
    ReviewAction,
    classify_consent_element,
    detect_clauses_rule_based,
    parse_llm_clauses,
)


# ---------------------------------------------------------------------------
# Rule-based clause detection tests
# ---------------------------------------------------------------------------

class TestRuleBasedDetection:
    def test_detects_arbitration(self):
        text = "By signing, you agree to binding arbitration for all disputes."
        clauses = detect_clauses_rule_based(text)
        types = [c.clause_type for c in clauses]
        assert ClauseType.ARBITRATION in types

    def test_detects_non_compete(self):
        text = "Employee agrees to a non-compete clause for 12 months after termination."
        clauses = detect_clauses_rule_based(text)
        types = [c.clause_type for c in clauses]
        assert ClauseType.NON_COMPETE in types

    def test_detects_non_solicit(self):
        text = "You agree to not solicit any employees or clients for 2 years."
        clauses = detect_clauses_rule_based(text)
        types = [c.clause_type for c in clauses]
        assert ClauseType.NON_SOLICIT in types

    def test_detects_ip_assignment(self):
        text = "All inventions created during employment shall be assigned to the company."
        clauses = detect_clauses_rule_based(text)
        types = [c.clause_type for c in clauses]
        assert ClauseType.IP_ASSIGNMENT in types

    def test_detects_background_check(self):
        text = "By proceeding, you authorize a background check and screening."
        clauses = detect_clauses_rule_based(text)
        types = [c.clause_type for c in clauses]
        assert ClauseType.BACKGROUND_CHECK in types

    def test_detects_nda(self):
        text = "You must sign a non-disclosure agreement before your start date."
        clauses = detect_clauses_rule_based(text)
        types = [c.clause_type for c in clauses]
        assert ClauseType.NDA in types

    def test_detects_jury_waiver(self):
        text = "You hereby waive your right to a jury trial."
        clauses = detect_clauses_rule_based(text)
        types = [c.clause_type for c in clauses]
        assert ClauseType.ARBITRATION in types

    def test_clean_text_no_clauses(self):
        text = (
            "We are looking for a talented software engineer to join our team. "
            "Competitive salary and great benefits. Apply on our website."
        )
        clauses = detect_clauses_rule_based(text)
        assert len(clauses) == 0

    def test_multiple_clauses(self):
        text = (
            "By accepting this offer, you agree to binding arbitration "
            "and a non-compete clause for 1 year. You also authorize "
            "a background check and consent to a non-disclosure agreement."
        )
        clauses = detect_clauses_rule_based(text)
        assert len(clauses) >= 3

    def test_all_detected_clauses_are_blocking(self):
        text = "You agree to binding arbitration and a non-compete for 2 years."
        clauses = detect_clauses_rule_based(text)
        for clause in clauses:
            assert clause.is_blocking
            assert clause.action == ReviewAction.HARD_STOP

    def test_clauses_have_summaries(self):
        text = "The company requires binding arbitration for all disputes."
        clauses = detect_clauses_rule_based(text)
        for clause in clauses:
            assert clause.plain_language_summary
            assert len(clause.plain_language_summary) > 10


# ---------------------------------------------------------------------------
# LLM response parsing tests
# ---------------------------------------------------------------------------

class TestParseLLMClauses:
    def test_parses_valid_response(self):
        response = (
            "CLAUSE|arbitration|critical|Disputes must go through binding arbitration.\n"
            "CLAUSE|ip_assignment|high|All work belongs to the company."
        )
        clauses = parse_llm_clauses(response)
        assert len(clauses) == 2
        assert clauses[0].clause_type == ClauseType.ARBITRATION
        assert clauses[0].severity == "critical"
        assert clauses[1].clause_type == ClauseType.IP_ASSIGNMENT

    def test_parses_no_clauses(self):
        response = "NO_CLAUSES_FOUND"
        clauses = parse_llm_clauses(response)
        assert len(clauses) == 0

    def test_handles_unknown_type(self):
        response = "CLAUSE|unknown_type|medium|Some unusual clause."
        clauses = parse_llm_clauses(response)
        assert len(clauses) == 1
        assert clauses[0].clause_type == ClauseType.OTHER

    def test_handles_malformed_lines(self):
        response = (
            "Some preamble text\n"
            "CLAUSE|arbitration|critical|Valid clause.\n"
            "Not a clause line\n"
            "CLAUSE|bad format\n"  # Missing fields
        )
        clauses = parse_llm_clauses(response)
        assert len(clauses) == 1  # Only the valid one

    def test_critical_clauses_are_blocking(self):
        response = "CLAUSE|arbitration|critical|Must use arbitration."
        clauses = parse_llm_clauses(response)
        assert clauses[0].is_blocking

    def test_low_clauses_not_blocking(self):
        response = "CLAUSE|at_will|low|Employment is at-will."
        clauses = parse_llm_clauses(response)
        assert not clauses[0].is_blocking
        assert clauses[0].action == ReviewAction.FLAG_FOR_REVIEW


# ---------------------------------------------------------------------------
# Consent element classification tests
# ---------------------------------------------------------------------------

class TestConsentElementClassification:
    def test_checkbox_always_blocks(self):
        result = classify_consent_element(
            ConsentElementType.CHECKBOX,
            "I agree to the terms and conditions",
        )
        assert result.is_blocking
        assert result.action == ReviewAction.HARD_STOP

    def test_toggle_always_blocks(self):
        result = classify_consent_element(
            ConsentElementType.TOGGLE,
            "Accept privacy policy",
        )
        assert result.is_blocking

    def test_drawn_signature_blocks(self):
        result = classify_consent_element(
            ConsentElementType.DRAWN_SIGNATURE,
            "Draw your signature",
        )
        assert result.is_blocking

    def test_uploaded_signature_blocks(self):
        result = classify_consent_element(
            ConsentElementType.UPLOADED_SIGNATURE,
            "Upload your signature",
        )
        assert result.is_blocking

    def test_agreement_link_blocks(self):
        result = classify_consent_element(
            ConsentElementType.AGREEMENT_LINK,
            "Click to acknowledge agreement",
        )
        assert result.is_blocking

    def test_standalone_typed_name_auto_fills(self):
        """The narrow e-signature exception: standalone typed-name is OK."""
        result = classify_consent_element(
            ConsentElementType.TYPED_NAME,
            "Type your full legal name",
            is_adjacent_to_consent=False,
        )
        assert not result.is_blocking
        assert result.action == ReviewAction.AUTO_FILL_OK

    def test_typed_name_adjacent_to_consent_blocks(self):
        """Typed-name next to a consent checkbox must block."""
        result = classify_consent_element(
            ConsentElementType.TYPED_NAME,
            "Type your name to sign",
            is_adjacent_to_consent=True,
        )
        assert result.is_blocking
        assert result.action == ReviewAction.HARD_STOP

    def test_consent_element_preserves_label(self):
        result = classify_consent_element(
            ConsentElementType.CHECKBOX,
            "I agree to the arbitration clause",
        )
        assert result.label_text == "I agree to the arbitration clause"


# ---------------------------------------------------------------------------
# LegalReviewResult tests
# ---------------------------------------------------------------------------

class TestLegalReviewResult:
    def test_empty_result_can_proceed(self):
        result = LegalReviewResult()
        assert result.can_proceed
        assert not result.has_blocking_clauses
        assert not result.has_blocking_consent

    def test_blocking_clause_prevents_proceed(self):
        result = LegalReviewResult(
            clauses=[
                DetectedClause(
                    clause_type=ClauseType.ARBITRATION,
                    original_text="",
                    plain_language_summary="Binding arbitration required",
                    action=ReviewAction.HARD_STOP,
                ),
            ],
            can_proceed=False,
            blocking_reasons=["Arbitration clause found"],
        )
        assert not result.can_proceed
        assert result.has_blocking_clauses

    def test_summary_shows_blocked(self):
        result = LegalReviewResult(
            can_proceed=False,
            blocking_reasons=["Test reason"],
        )
        assert "BLOCKED" in result.summary

    def test_summary_shows_clear(self):
        result = LegalReviewResult(can_proceed=True)
        assert "CLEAR" in result.summary


# ---------------------------------------------------------------------------
# Full LegalReviewer integration tests (mocked LLM)
# ---------------------------------------------------------------------------

class TestLegalReviewer:
    @pytest.fixture
    def mock_router(self):
        router = MagicMock()
        router.complete.return_value = {
            "content": "NO_CLAUSES_FOUND",
            "tokens_in": 100,
            "tokens_out": 10,
            "model": "openai/gpt-oss-120b",
            "provider": "groq",
        }
        return router

    def test_clean_text_passes(self, mock_router):
        reviewer = LegalReviewer(model_router=mock_router)
        result = reviewer.review_text(
            "We are hiring a software engineer. Great benefits and salary.",
        )
        assert result.can_proceed

    def test_text_with_arbitration_blocks(self, mock_router):
        mock_router.complete.return_value = {
            "content": "CLAUSE|arbitration|critical|Must use binding arbitration.",
            "tokens_in": 200,
            "tokens_out": 50,
            "model": "test",
            "provider": "test",
        }
        reviewer = LegalReviewer(model_router=mock_router)
        result = reviewer.review_text(
            "By applying, you agree to binding arbitration for all disputes."
        )
        assert not result.can_proceed
        assert len(result.clauses) >= 1

    def test_rule_based_only_no_llm(self, mock_router):
        reviewer = LegalReviewer(model_router=mock_router)
        result = reviewer.review_text(
            "You agree to a non-compete clause for 12 months.",
            use_llm=False,
        )
        assert not result.can_proceed
        mock_router.complete.assert_not_called()

    def test_llm_failure_falls_back_to_rules(self):
        router = MagicMock()
        router.complete.side_effect = RuntimeError("Provider down")
        reviewer = LegalReviewer(model_router=router)
        result = reviewer.review_text(
            "You authorize a background check and screening."
        )
        # Rule-based should still detect it
        assert len(result.clauses) >= 1
        types = [c.clause_type for c in result.clauses]
        assert ClauseType.BACKGROUND_CHECK in types

    def test_empty_text_passes(self, mock_router):
        reviewer = LegalReviewer(model_router=mock_router)
        result = reviewer.review_text("")
        assert result.can_proceed
        mock_router.complete.assert_not_called()

    def test_check_consent_element(self, mock_router):
        reviewer = LegalReviewer(model_router=mock_router)
        elem = reviewer.check_consent_element(
            ConsentElementType.CHECKBOX,
            "I agree to the terms",
        )
        assert elem.is_blocking

    def test_review_form_elements(self, mock_router):
        reviewer = LegalReviewer(model_router=mock_router)
        result = reviewer.review_form_elements(
            elements=[
                {"type": "checkbox", "label": "I agree to the terms"},
                {"type": "typed_name", "label": "Sign here", "adjacent_to_consent": False},
            ],
            form_text="Standard application form with no unusual clauses.",
        )
        # Checkbox should block
        assert not result.can_proceed
        assert len(result.consent_elements) == 2
        # Checkbox blocks, standalone typed-name is OK
        assert result.consent_elements[0].is_blocking
        assert not result.consent_elements[1].is_blocking

    def test_review_form_elements_typed_name_adjacent(self, mock_router):
        """Typed-name adjacent to consent checkbox should block."""
        reviewer = LegalReviewer(model_router=mock_router)
        result = reviewer.review_form_elements(
            elements=[
                {"type": "checkbox", "label": "I agree to the terms"},
                {"type": "typed_name", "label": "Sign here", "adjacent_to_consent": True},
            ],
        )
        # Both should block
        assert not result.can_proceed
        assert all(e.is_blocking for e in result.consent_elements)

    def test_deduplicates_clause_types(self, mock_router):
        """Rule-based and LLM should not double-count the same clause type."""
        mock_router.complete.return_value = {
            "content": "CLAUSE|arbitration|critical|Arbitration required.",
            "tokens_in": 100,
            "tokens_out": 20,
            "model": "test",
            "provider": "test",
        }
        reviewer = LegalReviewer(model_router=mock_router)
        result = reviewer.review_text(
            "You agree to binding arbitration for all employment disputes."
        )
        # Should have arbitration detected once (not duplicated)
        arb_clauses = [c for c in result.clauses if c.clause_type == ClauseType.ARBITRATION]
        assert len(arb_clauses) == 1
