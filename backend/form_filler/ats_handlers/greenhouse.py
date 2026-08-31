"""
Greenhouse ATS handler.

Greenhouse forms use a structured layout with labeled sections.
Application pages are at: boards.greenhouse.io/<company>/jobs/<id>
"""

import logging
from typing import Dict, List, Optional

from backend.form_filler.ats_handlers.base import BaseATSHandler

logger = logging.getLogger(__name__)


class GreenhouseHandler(BaseATSHandler):
    """Handler for Greenhouse ATS application forms."""

    def get_platform_name(self) -> str:
        return "greenhouse"

    def extract_fields(self, page) -> List[Dict]:
        """
        Extract fields from a Greenhouse application form.

        Greenhouse forms typically use:
        - .field CSS class for each form field
        - label elements associated with inputs
        - select elements for dropdowns
        - textarea for long-form fields
        """
        fields = []
        try:
            field_containers = page.locator(".field, .application-field")
            count = field_containers.count()

            for i in range(count):
                container = field_containers.nth(i)
                label_el = container.locator("label").first
                label_text = label_el.inner_text() if label_el.count() > 0 else ""

                # Detect input type
                input_el = container.locator("input, textarea, select").first
                if input_el.count() == 0:
                    continue

                tag = input_el.evaluate("el => el.tagName.toLowerCase()")
                input_type = input_el.get_attribute("type") or tag

                # Get options for select fields
                options = []
                if tag == "select":
                    option_els = input_el.locator("option")
                    for j in range(option_els.count()):
                        opt_text = option_els.nth(j).inner_text()
                        if opt_text.strip():
                            options.append(opt_text.strip())

                # Check if required
                required = (
                    input_el.get_attribute("required") is not None
                    or input_el.get_attribute("aria-required") == "true"
                    or "*" in label_text
                )

                fields.append({
                    "locator": f".field:nth-of-type({i + 1}) input, .field:nth-of-type({i + 1}) textarea, .field:nth-of-type({i + 1}) select",
                    "label": label_text.strip().rstrip("*").strip(),
                    "type": input_type,
                    "options": options,
                    "required": required,
                    "context": container.inner_text()[:200] if container.count() > 0 else "",
                })

        except Exception as e:
            logger.error("Failed to extract Greenhouse fields: %s", e)

        return fields

    def fill_field(self, page, locator: str, value: str, field_type: str) -> bool:
        """Fill a single Greenhouse form field."""
        try:
            element = page.locator(locator).first
            if element.count() == 0:
                return False

            if field_type in ("text", "email", "tel", "url", "number"):
                element.fill(value)
            elif field_type == "textarea":
                element.fill(value)
            elif field_type == "select":
                element.select_option(label=value)
            elif field_type == "checkbox":
                # Never auto-check — handled by legal review
                return False
            elif field_type == "file":
                element.set_input_files(value)
            else:
                element.fill(value)

            return True

        except Exception as e:
            logger.warning("Failed to fill field %s: %s", locator, e)
            return False

    def detect_submit_button(self, page) -> Optional[str]:
        """Locate the Greenhouse submit button."""
        selectors = [
            "#submit_app",
            "button[type='submit']",
            "input[type='submit']",
            "button:has-text('Submit Application')",
            "button:has-text('Apply')",
        ]
        for selector in selectors:
            if page.locator(selector).count() > 0:
                return selector
        return None
