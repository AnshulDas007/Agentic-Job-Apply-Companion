"""
Field Classification Module for Form Filling.

Classifies form fields into strongly typed categories using an LLM.
This ensures strict separation between work experience, projects, and personal info.
"""

import json
import logging
from enum import Enum
from typing import Dict, List, Optional

from backend.model_router import ModelRouter

logger = logging.getLogger(__name__)

class FieldCategory(str, Enum):
    """Categories of form fields that can be filled."""
    # Personal Info
    FIRST_NAME = "first_name"
    LAST_NAME = "last_name"
    FULL_NAME = "full_name"
    EMAIL = "email"
    PHONE = "phone"
    ADDRESS = "address"
    
    # Links
    GITHUB_URL = "github_url"
    LINKEDIN_URL = "linkedin_url"
    PORTFOLIO_URL = "portfolio_url"
    
    # Experience & Projects (Strictly separated)
    WORK_EXPERIENCE = "work_experience"
    YEARS_OF_EXPERIENCE = "years_of_experience"
    PROJECT = "project"
    
    # Education
    EDUCATION = "education"
    
    # Other specific ATS fields
    SKILLS = "skills"
    RESUME_UPLOAD = "resume_upload"
    COVER_LETTER = "cover_letter"
    
    # Legal & Consent (Handled by LegalReviewer, but classified here)
    CONSENT_CHECKBOX = "consent_checkbox"
    SIGNATURE = "signature"
    
    # Catch-all
    OTHER = "other"
    UNKNOWN = "unknown"

def _build_classifier_prompt(field_label: str, context: str, input_type: str, options: Optional[List[str]] = None) -> str:
    """Build the prompt for classifying a single field."""
    prompt = f"""You are an expert form field classifier for job applications.
Your task is to classify a given form field into exactly ONE of the following strict categories:

CATEGORIES:
{', '.join([c.value for c in FieldCategory])}

RULES:
1. Differentiate between general "work_experience" and "project". If it asks for personal projects, academic projects, or side projects, it is "project". If it asks for past employment, internships, or jobs, it is "work_experience".
2. "years_of_experience" is for numeric fields or dropdowns asking for duration of experience (e.g., "How many years of Python experience?").
3. Links: Separate github_url, linkedin_url, portfolio_url.
4. "signature" is for e-signatures or typing name to sign.
5. "consent_checkbox" is for agreeing to terms, arbitration, background checks, etc.
6. Return ONLY the category string exactly as it appears in the list above. Do not include any other text.

FIELD TO CLASSIFY:
Label: "{field_label}"
Nearby Text/Context: "{context}"
Input Type: "{input_type}"
"""
    if options:
        prompt += f"Dropdown Options: {', '.join(options)}\n"
        
    prompt += "\nCATEGORY:"
    return prompt

class FieldClassifier:
    """Classifies form fields to determine what data should be placed in them."""
    
    def __init__(self, model_router: Optional[ModelRouter] = None):
        self._router = model_router or ModelRouter()
        
    def classify_field(
        self, 
        field_label: str, 
        context: str = "", 
        input_type: str = "text",
        options: Optional[List[str]] = None
    ) -> FieldCategory:
        """
        Classifies a single form field using a fast/small LLM tier.
        
        Args:
            field_label: The visible label of the field (e.g., "Years of Python")
            context: Surrounding text or section header (e.g., "Work History")
            input_type: HTML input type (e.g., "text", "select", "checkbox")
            options: Dropdown options if applicable.
            
        Returns:
            The classified FieldCategory.
        """
        prompt = _build_classifier_prompt(field_label, context, input_type, options)
        
        try:
            # Use a fast, small model for this narrow classification task
            result = self._router.complete(
                tier="classification",
                prompt=prompt,
                system_prompt="You are a precise classification system. Output only the category string.",
            )
            raw_category = result.get("content", "").strip().lower()
            
            # Extract just the category if the LLM was verbose
            for cat in FieldCategory:
                if cat.value in raw_category:
                    return cat
                    
            logger.warning("Unrecognized category returned by LLM: %s. Defaulting to OTHER.", raw_category)
            return FieldCategory.OTHER
            
        except Exception as e:
            logger.error("Failed to classify field '%s': %s", field_label, e)
            return FieldCategory.UNKNOWN
