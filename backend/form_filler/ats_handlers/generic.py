"""
Generic ATS handler.

Fallback handler for unknown or custom career pages. Uses standard
HTML form patterns to extract and fill fields.
"""

import logging
from typing import Dict, List, Optional

from backend.form_filler.ats_handlers.base import BaseATSHandler

logger = logging.getLogger(__name__)


class GenericHandler(BaseATSHandler):
    """
    Generic fallback handler for any career page or unknown ATS.

    Uses standard HTML patterns (form, input, label, select) to
    extract and fill fields.
    """

    def get_platform_name(self) -> str:
        return "generic"

    def extract_fields(self, page) -> List[Dict]:
        """
        Extract fields using generic HTML form patterns.

        Scans for standard form elements: input, textarea, select.
        Associates labels via for/id attributes or parent containers.
        """
        fields = []
        try:
            # Find all visible form inputs
            inputs = page.locator(
                "form input:visible, form textarea:visible, form select:visible"
            )
            count = inputs.count()

            for i in range(count):
                el = inputs.nth(i)
                input_id = el.get_attribute("id") or ""
                name = el.get_attribute("name") or ""
                tag = el.evaluate("el => el.tagName.toLowerCase()")
                input_type = el.get_attribute("type") or tag

                # Skip hidden and submit inputs
                if input_type in ("hidden", "submit", "button"):
                    continue

                # Try to find associated label
                label_text = ""
                if input_id:
                    label_el = page.locator(f"label[for='{input_id}']")
                    if label_el.count() > 0:
                        label_text = label_el.first.inner_text()

                if not label_text:
                    # Try aria-label or placeholder
                    label_text = (
                        el.get_attribute("aria-label")
                        or el.get_attribute("placeholder")
                        or name
                        or input_id
                    )

                options = []
                if tag == "select":
                    option_els = el.locator("option")
                    for j in range(option_els.count()):
                        opt_text = option_els.nth(j).inner_text()
                        if opt_text.strip():
                            options.append(opt_text.strip())

                required = (
                    el.get_attribute("required") is not None
                    or el.get_attribute("aria-required") == "true"
                )

                locator = f"#{input_id}" if input_id else f"[name='{name}']"

                fields.append({
                    "locator": locator,
                    "label": label_text.strip().rstrip("*").strip(),
                    "type": input_type,
                    "options": options,
                    "required": required,
                    "context": label_text,
                })

        except Exception as e:
            logger.error("Failed to extract generic form fields: %s", e)

        return fields

    def fill_field(self, page, locator: str, value: str, field_type: str) -> bool:
        """Fill a single generic form field."""
        try:
            element = page.locator(locator).first
            if element.count() == 0:
                return False

            if field_type in ("text", "email", "tel", "url", "number", "password"):
                element.fill(value)
            elif field_type == "textarea":
                element.fill(value)
            elif field_type == "select":
                element.select_option(label=value)
            elif field_type == "checkbox":
                return False  # Never auto-check
            elif field_type == "radio":
                # Find the radio with the matching value
                radio = page.locator(f"{locator}[value='{value}']")
                if radio.count() > 0:
                    radio.check()
                else:
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
        """Locate any submit button using common patterns."""
        selectors = [
            "button[type='submit']",
            "input[type='submit']",
            "button:has-text('Submit')",
            "button:has-text('Apply')",
            "button:has-text('Send Application')",
            "input[value='Submit']",
            "input[value='Apply']",
        ]
        for selector in selectors:
            if page.locator(selector).count() > 0:
                return selector
        return None
