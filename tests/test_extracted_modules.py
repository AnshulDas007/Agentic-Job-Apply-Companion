"""
Tests for Phase 14: Extracted modules (ban_list and clause_patterns).
"""

import pytest

from backend.cover_letter.ban_list import (
    BANNED_PHRASES,
    check_banned_phrases,
    is_clean,
)
from backend.legal_review.clause_patterns import (
    ClauseCategory,
    CONSENT_KEYWORDS,
    get_summary,
    has_consent_language,
    scan_for_clauses,
)


# ---------------------------------------------------------------------------
# Tests: Ban List
# ---------------------------------------------------------------------------

class TestBanList:
    def test_banned_phrases_not_empty(self):
        assert len(BANNED_PHRASES) > 20

    def test_detects_single_phrase(self):
        text = "I am passionate about building great products."
        found = check_banned_phrases(text)
        assert "passionate about" in found

    def test_detects_multiple_phrases(self):
        text = (
            "In today's fast-paced world, I am a results-driven "
            "professional with a proven track record."
        )
        found = check_banned_phrases(text)
        assert len(found) >= 3
        assert "in today's fast-paced world" in found
        assert "results-driven" in found
        assert "proven track record" in found

    def test_clean_text_returns_empty(self):
        text = (
            "While building the Deep Research Copilot, I implemented "
            "a multi-agent architecture using LangChain that reduced "
            "query latency by 40%."
        )
        assert check_banned_phrases(text) == []

    def test_is_clean_true(self):
        assert is_clean("Built a RAG pipeline with 95% retrieval accuracy.")

    def test_is_clean_false(self):
        assert not is_clean("I am a highly motivated individual.")

    def test_case_insensitive(self):
        text = "PASSIONATE ABOUT technology"
        found = check_banned_phrases(text)
        assert "passionate about" in found

    def test_dear_hiring_manager_detected(self):
        text = "Dear Hiring Manager, I am writing to apply..."
        found = check_banned_phrases(text)
        assert "dear hiring manager" in found


# ---------------------------------------------------------------------------
# Tests: Clause Patterns
# ---------------------------------------------------------------------------

class TestClausePatterns:
    def test_detects_arbitration(self):
        text = "By accepting this offer, you agree to binding arbitration for all disputes."
        results = scan_for_clauses(text)
        categories = [r[0] for r in results]
        assert ClauseCategory.ARBITRATION in categories

    def test_detects_non_compete(self):
        text = "Employee agrees to a non-compete agreement for 12 months after termination."
        results = scan_for_clauses(text)
        categories = [r[0] for r in results]
        assert ClauseCategory.NON_COMPETE in categories

    def test_detects_ip_assignment(self):
        text = "You agree to assign all intellectual property rights to the company."
        results = scan_for_clauses(text)
        categories = [r[0] for r in results]
        assert ClauseCategory.IP_ASSIGNMENT in categories

    def test_detects_background_check(self):
        text = "I authorize a background check and criminal screening."
        results = scan_for_clauses(text)
        categories = [r[0] for r in results]
        assert ClauseCategory.BACKGROUND_CHECK in categories

    def test_detects_nda(self):
        text = "You must sign a non-disclosure agreement before starting."
        results = scan_for_clauses(text)
        categories = [r[0] for r in results]
        assert ClauseCategory.NDA in categories

    def test_clean_text_no_clauses(self):
        text = "We are looking for a skilled Python developer to join our team."
        results = scan_for_clauses(text)
        assert len(results) == 0

    def test_severity_levels(self):
        text = "binding arbitration"
        results = scan_for_clauses(text)
        # Arbitration should be critical severity
        assert results[0][3] == "critical"

    def test_context_extraction(self):
        prefix = "A" * 150
        text = f"{prefix} binding arbitration clause here"
        results = scan_for_clauses(text)
        assert len(results) > 0
        # Context should include surrounding text
        context = results[0][2]
        assert "arbitration" in context.lower()

    def test_multiple_clause_types(self):
        text = (
            "You agree to binding arbitration. You also agree to a "
            "non-compete for 1 year. Additionally, consent to a background check."
        )
        results = scan_for_clauses(text)
        categories = {r[0] for r in results}
        assert ClauseCategory.ARBITRATION in categories
        assert ClauseCategory.NON_COMPETE in categories
        assert ClauseCategory.BACKGROUND_CHECK in categories


class TestConsentLanguage:
    def test_detects_i_agree(self):
        assert has_consent_language("I agree to the terms and conditions.")

    def test_detects_checkbox_language(self):
        assert has_consent_language("By checking this box, you consent...")

    def test_clean_text(self):
        assert not has_consent_language("Please enter your full name.")

    def test_detects_authorize(self):
        assert has_consent_language("I authorize the company to verify.")


class TestGetSummary:
    def test_known_category(self):
        summary = get_summary(ClauseCategory.ARBITRATION)
        assert "arbitration" in summary.lower()
        assert len(summary) > 20

    def test_all_categories_have_summaries(self):
        for cat in [
            ClauseCategory.ARBITRATION,
            ClauseCategory.NON_COMPETE,
            ClauseCategory.IP_ASSIGNMENT,
            ClauseCategory.BACKGROUND_CHECK,
            ClauseCategory.NDA,
        ]:
            summary = get_summary(cat)
            assert len(summary) > 0
