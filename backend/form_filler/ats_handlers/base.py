"""
Base ATS handler — abstract interface for platform-specific form adapters.
"""

import logging
from abc import ABC, abstractmethod
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class BaseATSHandler(ABC):
    """
    Abstract base class for ATS form handlers.

    Each ATS handler must implement:
    - extract_fields: Parse form fields from the page
    - fill_field: Fill a single field using Playwright
    - detect_submit_button: Locate the submit button
    - get_platform_name: Return the ATS platform name
    """

    @abstractmethod
    def get_platform_name(self) -> str:
        """Return the name of this ATS platform."""
        ...

    @abstractmethod
    def extract_fields(self, page) -> List[Dict]:
        """
        Extract form fields from a Playwright page.

        Returns a list of dicts with keys:
            - locator: CSS selector or Playwright locator string
            - label: The field's label text
            - type: input type (text, textarea, select, checkbox, file, etc.)
            - options: list of option strings (for select/dropdown fields)
            - required: whether the field is marked required
            - context: surrounding text for classification
        """
        ...

    @abstractmethod
    def fill_field(self, page, locator: str, value: str, field_type: str) -> bool:
        """
        Fill a single form field.

        Args:
            page: Playwright Page object.
            locator: CSS selector or locator for the field.
            value: Value to fill.
            field_type: The field's input type.

        Returns:
            True if field was filled successfully.
        """
        ...

    @abstractmethod
    def detect_submit_button(self, page) -> Optional[str]:
        """
        Locate the form's submit button.

        Returns:
            CSS selector for the submit button, or None if not found.
        """
        ...

    def navigate_multi_page(self, page) -> bool:
        """
        Handle multi-page forms (click 'Next' to advance).

        Override in subclasses that have multi-step forms.
        Returns True if there's a next page, False if on the last page.
        """
        return False

    def upload_resume(self, page, file_path: str) -> bool:
        """
        Upload a resume file if the form has a file upload field.

        Override in subclasses if the upload mechanism differs.
        """
        try:
            file_input = page.locator("input[type='file']")
            if file_input.count() > 0:
                file_input.first.set_input_files(file_path)
                logger.info("Uploaded resume: %s", file_path)
                return True
        except Exception as e:
            logger.warning("Failed to upload resume: %s", e)
        return False
