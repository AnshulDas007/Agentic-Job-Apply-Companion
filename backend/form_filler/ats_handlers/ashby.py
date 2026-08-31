"""
Ashby ATS handler.

Ashby forms are relatively clean, single-page applications.
URLs: jobs.ashbyhq.com/<company>/application/<id>
"""

import logging
from typing import Dict, List, Optional

from backend.form_filler.ats_handlers.base import BaseATSHandler

logger = logging.getLogger(__name__)


class AshbyHandler(BaseATSHandler):
    """Handler for Ashby ATS application forms."""

    def get_platform_name(self) -> str:
        return "ashby"

    def extract_fields(self, page) -> List[Dict]:
        """
        Extract fields from an Ashby application form.

        Ashby uses a modern React-based form with aria attributes
        and data-testid attributes.
        """
        fields = []
        try:
            # Ashby uses .ashby-application-form-field-entry containers
            containers = page.locator(
                ".ashby-application-form-field-entry, [data-testid*='field']"
            )
            count = containers.count()

            for i in range(count):
                container = containers.nth(i)
                label_el = container.locator("label").first
                label_text = label_el.inner_text() if label_el.count() > 0 else ""

                input_el = container.locator("input, textarea, select").first
                if input_el.count() == 0:
                    continue

                tag = input_el.evaluate("el => el.tagName.toLowerCase()")
                input_type = input_el.get_attribute("type") or tag

                options = []
                if tag == "select":
                    option_els = input_el.locator("option")
                    for j in range(option_els.count()):
                        opt_text = option_els.nth(j).inner_text()
                        if opt_text.strip():
                            options.append(opt_text.strip())

                required = (
                    input_el.get_attribute("required") is not None
                    or input_el.get_attribute("aria-required") == "true"
                )

                fields.append({
                    "locator": f".ashby-application-form-field-entry:nth-of-type({i + 1}) input",
                    "label": label_text.strip().rstrip("*").strip(),
                    "type": input_type,
                    "options": options,
                    "required": required,
                    "context": container.inner_text()[:200] if container.count() > 0 else "",
                })

        except Exception as e:
            logger.error("Failed to extract Ashby fields: %s", e)

        return fields

    def fill_field(self, page, locator: str, value: str, field_type: str) -> bool:
        """Fill a single Ashby form field."""
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
                return False  # Never auto-check
            elif field_type == "file":
                element.set_input_files(value)
            else:
                element.fill(value)

            return True

        except Exception as e:
            logger.warning("Failed to fill Ashby field %s: %s", locator, e)
            return False

    def detect_submit_button(self, page) -> Optional[str]:
        """Locate the Ashby submit button."""
        selectors = [
            "button[type='submit']",
            "button:has-text('Submit Application')",
            "button:has-text('Apply')",
            "[data-testid='submit-application']",
        ]
        for selector in selectors:
            if page.locator(selector).count() > 0:
                return selector
        return None
