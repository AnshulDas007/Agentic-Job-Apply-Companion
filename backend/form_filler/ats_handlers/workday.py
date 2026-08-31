"""
Workday ATS handler.

Workday forms are complex, multi-page, JavaScript-heavy applications.
URLs typically contain: myworkday.com or wd5.myworkdayjobs.com
Requires Playwright (not requests-based) due to heavy JS rendering.
"""

import logging
import time
from typing import Dict, List, Optional

from backend.form_filler.ats_handlers.base import BaseATSHandler

logger = logging.getLogger(__name__)


class WorkdayHandler(BaseATSHandler):
    """
    Handler for Workday ATS application forms.

    Workday is the most complex ATS — forms are multi-step,
    heavily JavaScript-rendered, and use custom widgets instead
    of standard HTML inputs.
    """

    def get_platform_name(self) -> str:
        return "workday"

    def extract_fields(self, page) -> List[Dict]:
        """
        Extract fields from a Workday application form.

        Workday uses custom ARIA-attributed widgets. Field containers
        are typically data-automation-id labeled.
        """
        fields = []
        try:
            # Workday uses data-automation-id attributes extensively
            field_containers = page.locator("[data-automation-id]")
            count = field_containers.count()

            for i in range(count):
                container = field_containers.nth(i)
                automation_id = container.get_attribute("data-automation-id") or ""

                # Skip non-field elements
                if not any(kw in automation_id for kw in (
                    "formField", "input", "select", "textArea", "dropdown"
                )):
                    continue

                # Try to find label
                label_el = container.locator("label, [data-automation-id*='label']").first
                label_text = label_el.inner_text() if label_el.count() > 0 else automation_id

                # Find the actual input
                input_el = container.locator("input, textarea, select, [role='combobox'], [role='listbox']").first
                if input_el.count() == 0:
                    continue

                tag = input_el.evaluate("el => el.tagName.toLowerCase()")
                input_type = input_el.get_attribute("type") or tag
                role = input_el.get_attribute("role") or ""

                if role == "combobox":
                    input_type = "select"

                options = []
                if input_type == "select" or role in ("combobox", "listbox"):
                    # Workday dropdowns need a click to reveal options
                    pass

                required = input_el.get_attribute("aria-required") == "true"

                fields.append({
                    "locator": f"[data-automation-id='{automation_id}'] input, [data-automation-id='{automation_id}'] textarea",
                    "label": label_text.strip().rstrip("*").strip(),
                    "type": input_type,
                    "options": options,
                    "required": required,
                    "context": label_text,
                })

        except Exception as e:
            logger.error("Failed to extract Workday fields: %s", e)

        return fields

    def fill_field(self, page, locator: str, value: str, field_type: str) -> bool:
        """Fill a single Workday form field."""
        try:
            element = page.locator(locator).first
            if element.count() == 0:
                return False

            if field_type in ("text", "email", "tel", "url", "number"):
                element.click()
                element.fill(value)
                # Workday sometimes needs a tab to trigger validation
                element.press("Tab")
            elif field_type == "textarea":
                element.click()
                element.fill(value)
            elif field_type == "select":
                # Workday custom dropdowns: click to open, then select
                element.click()
                time.sleep(0.3)  # Wait for dropdown to render
                option = page.locator(f"[role='option']:has-text('{value}')").first
                if option.count() > 0:
                    option.click()
            elif field_type == "checkbox":
                return False  # Never auto-check
            elif field_type == "file":
                element.set_input_files(value)
            else:
                element.fill(value)

            return True

        except Exception as e:
            logger.warning("Failed to fill Workday field %s: %s", locator, e)
            return False

    def detect_submit_button(self, page) -> Optional[str]:
        """Locate the Workday submit button."""
        selectors = [
            "[data-automation-id='bottom-navigation-next-button']",
            "[data-automation-id='submit']",
            "button:has-text('Submit')",
            "button:has-text('Next')",
        ]
        for selector in selectors:
            if page.locator(selector).count() > 0:
                return selector
        return None

    def navigate_multi_page(self, page) -> bool:
        """
        Workday forms are multi-page. Click 'Next' to advance.

        Returns True if a 'Next' button was found and clicked.
        """
        next_btn = page.locator(
            "[data-automation-id='bottom-navigation-next-button']"
        )
        if next_btn.count() > 0:
            next_btn.click()
            page.wait_for_load_state("networkidle")
            return True
        return False
