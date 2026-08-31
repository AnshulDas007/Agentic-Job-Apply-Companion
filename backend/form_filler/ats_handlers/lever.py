"""
Lever ATS handler.

Lever forms are typically at: jobs.lever.co/<company>/<id>/apply
They use a clean, single-page form layout.
"""

import logging
from typing import Dict, List, Optional

from backend.form_filler.ats_handlers.base import BaseATSHandler

logger = logging.getLogger(__name__)


class LeverHandler(BaseATSHandler):
    """Handler for Lever ATS application forms."""

    def get_platform_name(self) -> str:
        return "lever"

    def extract_fields(self, page) -> List[Dict]:
        """
        Extract fields from a Lever application form.

        Lever forms use .application-question containers with
        label + input/textarea/select elements.
        """
        fields = []
        try:
            # Lever uses .application-question for each field group
            containers = page.locator(
                ".application-question, .application-field, .custom-question"
            )
            count = containers.count()

            for i in range(count):
                container = containers.nth(i)
                label_el = container.locator("label, .question-label").first
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
                    or "required" in (container.get_attribute("class") or "")
                )

                fields.append({
                    "locator": f".application-question:nth-of-type({i + 1}) input, .application-question:nth-of-type({i + 1}) textarea",
                    "label": label_text.strip().rstrip("*").strip(),
                    "type": input_type,
                    "options": options,
                    "required": required,
                    "context": container.inner_text()[:200] if container.count() > 0 else "",
                })

        except Exception as e:
            logger.error("Failed to extract Lever fields: %s", e)

        return fields

    def fill_field(self, page, locator: str, value: str, field_type: str) -> bool:
        """Fill a single Lever form field."""
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
            logger.warning("Failed to fill Lever field %s: %s", locator, e)
            return False

    def detect_submit_button(self, page) -> Optional[str]:
        """Locate the Lever submit button."""
        selectors = [
            "button[type='submit']",
            "button:has-text('Submit application')",
            "button:has-text('Apply')",
            ".postings-btn-wrapper button",
        ]
        for selector in selectors:
            if page.locator(selector).count() > 0:
                return selector
        return None
