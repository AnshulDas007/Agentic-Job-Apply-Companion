"""
Tests for the fraud/legitimacy filter.
"""

import pytest

from backend.fraud_filter.signals import (
    check_fee_requirement,
    check_financial_info_request,
    check_informal_only_communication,
    check_no_company_domain,
    extract_hard_blockers,
    score_company_presence,
    score_salary_reasonableness,
    score_urgency_language,
)
from backend.fraud_filter.filter import FraudFilter, FraudResult


# ---------------------------------------------------------------------------
# Hard blocker tests
# ---------------------------------------------------------------------------

class TestFeeDetection:
    def test_registration_fee(self):
        blocked, reason = check_fee_requirement("Pay a registration fee of ₹500 to proceed")
        assert blocked
        assert "fee" in reason.lower()

    def test_training_deposit(self):
        blocked, _ = check_fee_requirement("A training deposit of $200 is required")
        assert blocked

    def test_buy_equipment(self):
        blocked, _ = check_fee_requirement("You need to buy your own equipment before starting")
        assert blocked

    def test_normal_listing_no_fee(self):
        blocked, _ = check_fee_requirement(
            "We offer competitive salary and comprehensive training program"
        )
        assert not blocked

    def test_upfront_investment(self):
        blocked, _ = check_fee_requirement("Invest $1000 upfront to get started")
        assert blocked


class TestFinancialInfoDetection:
    def test_bank_details(self):
        blocked, _ = check_financial_info_request("Please provide your bank account details")
        assert blocked

    def test_credit_card(self):
        blocked, _ = check_financial_info_request("Enter your credit card number for verification")
        assert blocked

    def test_aadhaar(self):
        blocked, _ = check_financial_info_request("Submit your Aadhaar card for KYC")
        assert blocked

    def test_pan_card(self):
        blocked, _ = check_financial_info_request("PAN card number required before interview")
        assert blocked

    def test_normal_listing_no_financial(self):
        blocked, _ = check_financial_info_request(
            "Background check will be conducted after offer acceptance"
        )
        assert not blocked


class TestInformalCommunication:
    def test_whatsapp_only(self):
        blocked, _ = check_informal_only_communication(
            "Apply via WhatsApp on +91-9876543210. Send your resume to this number."
        )
        assert blocked

    def test_telegram_only(self):
        blocked, _ = check_informal_only_communication(
            "Contact us on Telegram @jobs_hiring for immediate placement"
        )
        assert blocked

    def test_whatsapp_with_company_email_ok(self):
        """WhatsApp mentioned but company email also present — not a hard block."""
        blocked, _ = check_informal_only_communication(
            "Apply via WhatsApp on +91-123 or email hr@acmetech.com"
        )
        assert not blocked

    def test_normal_communication(self):
        blocked, _ = check_informal_only_communication(
            "Apply through our careers page at https://acme.com/careers"
        )
        assert not blocked


class TestGenericEmailDomain:
    def test_gmail_blocked(self):
        blocked, _ = check_no_company_domain("hr.jobs@gmail.com")
        assert blocked

    def test_yahoo_blocked(self):
        blocked, _ = check_no_company_domain("recruitment@yahoo.com")
        assert blocked

    def test_company_email_ok(self):
        blocked, _ = check_no_company_domain("careers@stripe.com")
        assert not blocked

    def test_empty_email_not_blocked(self):
        """Absence of email is NOT a hard blocker."""
        blocked, _ = check_no_company_domain("")
        assert not blocked


class TestExtractHardBlockers:
    def test_multiple_blockers(self):
        text = (
            "Pay registration fee of $500 via WhatsApp. "
            "Send your bank account details for processing."
        )
        blockers = extract_hard_blockers(text, "jobs@gmail.com")
        assert len(blockers) >= 2  # Fee + financial info at minimum

    def test_clean_listing(self):
        text = (
            "We are looking for a Software Engineer with 2+ years of experience. "
            "Competitive salary and benefits. Apply at careers@stripe.com"
        )
        blockers = extract_hard_blockers(text, "careers@stripe.com")
        assert len(blockers) == 0


# ---------------------------------------------------------------------------
# Soft signal tests
# ---------------------------------------------------------------------------

class TestUrgencyLanguage:
    def test_no_urgency(self):
        score = score_urgency_language(
            "We're building something amazing. Apply when ready."
        )
        assert score == 1.0

    def test_mild_urgency(self):
        score = score_urgency_language("Immediate joining required")
        assert 0.0 < score <= 0.5

    def test_extreme_urgency(self):
        score = score_urgency_language(
            "Apply within 2 hours! Immediate joining, no interview needed. "
            "Guaranteed job offer! Limited spots available. Hurry!"
        )
        assert score == 0.0


class TestSalaryReasonableness:
    def test_reasonable_salary(self):
        score = score_salary_reasonableness("$80,000 - $120,000")
        assert score > 0.5

    def test_no_salary(self):
        score = score_salary_reasonableness("")
        assert 0.5 <= score <= 0.8  # Slightly below neutral

    def test_unrealistic_high(self):
        score = score_salary_reasonableness("$300k for entry level")
        assert score < 0.3


class TestCompanyPresence:
    def test_full_presence(self):
        score = score_company_presence(
            has_linkedin=True,
            has_glassdoor=True,
            has_company_website=True,
        )
        assert score == 1.0

    def test_no_presence(self):
        score = score_company_presence(
            has_linkedin=False,
            has_glassdoor=False,
            has_company_website=False,
        )
        assert score == 0.0

    def test_partial_presence(self):
        score = score_company_presence(
            has_linkedin=True,
            has_glassdoor=False,
            has_company_website=True,
        )
        assert 0.5 < score < 1.0


# ---------------------------------------------------------------------------
# Full filter integration tests
# ---------------------------------------------------------------------------

class TestFraudFilter:
    def test_clean_listing_passes(self):
        ff = FraudFilter()
        result = ff.check(
            description="Software Engineer role at a well-funded startup. "
                        "Competitive salary. Apply through our website.",
            company_email="hr@startup.com",
            salary_text="$100k - $140k",
            has_linkedin=True,
            has_glassdoor=True,
            has_company_website=True,
        )
        assert result.passed
        assert not result.hard_blocked
        assert result.legitimacy_score > 0.5

    def test_scam_listing_blocked(self):
        ff = FraudFilter()
        result = ff.check(
            description="Pay ₹500 registration fee via WhatsApp +91-9876543210. "
                        "Immediate joining! No interview! Guaranteed placement! "
                        "Send bank details for salary setup.",
            company_email="jobs@gmail.com",
            salary_text="₹50 LPA for fresher",
            has_linkedin=False,
            has_glassdoor=False,
            has_company_website=False,
        )
        assert not result.passed
        assert result.hard_blocked
        assert len(result.hard_block_reasons) > 0

    def test_borderline_listing(self):
        """Listing with no hard blockers but weak signals — may or may not pass."""
        ff = FraudFilter()
        result = ff.check(
            description="We are hiring developers. Good package offered.",
            company_email="",
            salary_text=None,
            has_linkedin=False,
            has_glassdoor=False,
            has_company_website=False,
        )
        assert not result.hard_blocked
        # With no presence and no salary info, score should be low
        assert result.legitimacy_score < 0.8

    def test_fraud_result_summary(self):
        result = FraudResult(
            passed=False,
            hard_blocked=True,
            hard_block_reasons=["Fee detected", "Generic email"],
        )
        assert "BLOCKED" in result.summary
        assert "Fee detected" in result.summary

    def test_check_listing_method(self):
        """Test the convenience method that takes a listing object."""
        ff = FraudFilter()

        class MockListing:
            description = "Great engineering role at a top company"
            company_email = "hr@topcompany.com"
            salary_text = "$120k"
            company_url = "https://topcompany.com"

        result = ff.check_listing(MockListing())
        assert not result.hard_blocked
