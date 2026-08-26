"""
Form Filler Layer.

Handles Playwright automation for navigating and filling out job application forms.
Includes LLM-based field classification, data mapping from CandidateProfile,
and integration with Cover Letter and Legal Review modules.
"""

from backend.form_filler.classifier import FieldClassifier, FieldCategory
from backend.form_filler.field_mapper import map_field_value
from backend.form_filler.filler import FormFiller

__all__ = [
    "FieldClassifier",
    "FieldCategory",
    "map_field_value",
    "FormFiller",
]
