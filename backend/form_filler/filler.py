"""
Form Filler Module.

Orchestrates the process of filling job application forms using Playwright.
It extracts form fields, classifies them, maps values from CandidateProfile,
and uses LegalReviewer to ensure no unauthorized consents are submitted.
"""

import logging
from typing import Dict, List, Optional

from backend.parsing.profile_schema import CandidateProfile
from backend.form_filler.classifier import FieldClassifier, FieldCategory
from backend.form_filler.field_mapper import map_field_value
from backend.legal_review.reviewer import LegalReviewer, ConsentElementType
from backend.cover_letter.generator import CoverLetterGenerator

logger = logging.getLogger(__name__)

class FormFiller:
    """
    Handles the automation of filling job application forms.
    """
    
    def __init__(
        self,
        classifier: Optional[FieldClassifier] = None,
        legal_reviewer: Optional[LegalReviewer] = None,
        cover_letter_gen: Optional[CoverLetterGenerator] = None,
    ):
        self.classifier = classifier or FieldClassifier()
        self.legal_reviewer = legal_reviewer or LegalReviewer()
        self.cover_letter_gen = cover_letter_gen or CoverLetterGenerator()
        
    def fill_form(
        self, 
        page, 
        profile: CandidateProfile, 
        job_title: str,
        company: str,
        job_description: str = ""
    ) -> bool:
        """
        Takes a Playwright `page` object, analyzes its fields, fills them with
        CandidateProfile data, and performs verification.
        
        Args:
            page: Playwright Page object.
            profile: The candidate's structured profile.
            job_title: Job title (for cover letter).
            company: Company name (for cover letter).
            job_description: Full job description text (for cover letter).
            
        Returns:
            True if the form was filled successfully and is ready for submission (or review).
            False if blocked by legal clauses or validation mismatches.
        """
        # Note: In a real implementation, we would extract fields via Playwright locator evaluation.
        # This is a structural skeleton representing the required logic.
        
        logger.info(f"Starting form fill for {job_title} at {company}")
        
        # 1. Extract all page text and run Legal Review
        page_text = self._extract_page_text(page)
        legal_result = self.legal_reviewer.review_text(page_text)
        
        if not legal_result.can_proceed:
            logger.error(f"Form blocked by legal clauses: {legal_result.summary}")
            return False
            
        # 2. Extract fields (locators, labels, types, options)
        fields = self._extract_fields(page)
        
        # 3. Classify and map fields
        fill_plan = []
        for field in fields:
            category = self.classifier.classify_field(
                field_label=field["label"],
                context=field.get("context", ""),
                input_type=field["type"],
                options=field.get("options")
            )
            
            # Specific Legal Check for Consent Fields
            if category == FieldCategory.CONSENT_CHECKBOX:
                consent = self.legal_reviewer.check_consent_element(
                    element_type=ConsentElementType.CHECKBOX,
                    label_text=field["label"],
                )
                if consent.is_blocking:
                    logger.error(f"Blocked by consent checkbox: {field['label']}")
                    return False
                    
            elif category == FieldCategory.SIGNATURE:
                is_adjacent = self._check_adjacent_to_consent(page, field)
                consent = self.legal_reviewer.check_consent_element(
                    element_type=ConsentElementType.TYPED_NAME,
                    label_text=field["label"],
                    is_adjacent_to_consent=is_adjacent
                )
                if consent.is_blocking:
                    logger.error(f"Blocked by signature field: {field['label']}")
                    return False
            
            # Map Value
            value = map_field_value(
                profile=profile,
                category=category,
                field_label=field["label"],
                options=field.get("options")
            )
            
            # Cover Letter specific handling
            if category == FieldCategory.COVER_LETTER:
                # Is it mandatory? 
                is_mandatory = field.get("required", False)
                cl_result = self.cover_letter_gen.generate(
                    profile=profile,
                    job_title=job_title,
                    company=company,
                    job_description=job_description,
                    is_mandatory=is_mandatory
                )
                if cl_result.generated:
                    value = cl_result.content
                else:
                    value = "" # Skip
                    
            fill_plan.append({
                "locator": field["locator"],
                "category": category,
                "value": value
            })
            
        # 4. Verification Pass (Diff Check) before executing fill
        if not self._verify_fill_plan(fill_plan, profile):
            logger.error("Verification failed: Project data mapped to Experience field or vice-versa.")
            return False
            
        # 5. Execute Fill Plan
        self._execute_fill_plan(page, fill_plan)
        
        logger.info("Form filled successfully. Ready for submission review.")
        return True
        
    def _extract_page_text(self, page) -> str:
        """Extract text from the entire page for legal analysis."""
        # return page.evaluate("document.body.innerText")
        return ""
        
    def _extract_fields(self, page) -> List[Dict]:
        """
        Extract interactive fields from the page.
        Returns a list of dicts: {"locator": ..., "label": ..., "type": ..., "options": ...}
        """
        return []
        
    def _check_adjacent_to_consent(self, page, field) -> bool:
        """Check if a signature field is adjacent to a consent checkbox."""
        return False
        
    def _verify_fill_plan(self, fill_plan: List[Dict], profile: CandidateProfile) -> bool:
        """
        Verify that experience values didn't end up in project fields and vice versa.
        """
        for item in fill_plan:
            val = str(item["value"]) if item["value"] else ""
            cat = item["category"]
            
            if cat == FieldCategory.WORK_EXPERIENCE:
                # Ensure no project names are in the work experience output
                for proj in profile.projects:
                    if proj.name and proj.name in val:
                        return False
            
            elif cat == FieldCategory.PROJECT:
                # Ensure no company names are in the project output
                for exp in profile.experience:
                    if exp.company and exp.company in val:
                        return False
                        
        return True
        
    def _execute_fill_plan(self, page, fill_plan: List[Dict]):
        """Execute Playwright commands to fill the fields."""
        # for item in fill_plan:
        #     if item["value"] is not None:
        #         page.locator(item["locator"]).fill(str(item["value"]))
        pass
