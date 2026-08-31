"""
Dropdown and duration-bucket handler.

Handles the logic for mapping exact durations to coarse dropdown options.
Implements the build spec rule: always select the LOWEST valid bucket that
includes the candidate's actual duration — never round up.
"""

import logging
import re
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Year-bucket definitions (common dropdown patterns)
# ---------------------------------------------------------------------------

# Standard year-bucket patterns found on job application forms
YEAR_BUCKETS = [
    (0, 1, "0-1 years"),
    (1, 3, "1-3 years"),
    (3, 5, "3-5 years"),
    (5, 7, "5-7 years"),
    (7, 10, "7-10 years"),
    (10, 15, "10-15 years"),
    (15, float("inf"), "15+ years"),
]


def months_to_years(months: int) -> float:
    """Convert months to years (fractional)."""
    return months / 12.0


def select_year_bucket(
    duration_months: int,
    options: Optional[List[str]] = None,
) -> str:
    """
    Select the appropriate year bucket for a given duration.

    If form-specific options are provided, match against those.
    Otherwise, use the standard YEAR_BUCKETS.

    Args:
        duration_months: Exact duration in months.
        options: Optional list of dropdown option strings from the form.

    Returns:
        The selected option string.
    """
    years = months_to_years(duration_months)

    if options:
        return _match_form_options(years, options)

    # Use standard buckets
    for low, high, label in YEAR_BUCKETS:
        if low <= years < high:
            return label

    return YEAR_BUCKETS[-1][2]  # Fallback to highest bucket


def _match_form_options(years: float, options: List[str]) -> str:
    """
    Match exact years against actual form dropdown options.

    Parses each option to extract numeric ranges and selects the
    lowest valid bucket.
    """
    parsed: List[Tuple[float, float, str]] = []

    for opt in options:
        bounds = _parse_option_range(opt)
        if bounds:
            parsed.append((bounds[0], bounds[1], opt))

    if not parsed:
        # Cannot parse any option — return the first one as fallback
        logger.warning(
            "Could not parse any dropdown options: %s. Using first option.", options
        )
        return options[0] if options else ""

    # Sort by lower bound ascending
    parsed.sort(key=lambda x: x[0])

    # Select lowest bucket that includes the value
    for low, high, label in parsed:
        if low <= years <= high:
            return label

    # If years exceeds all buckets, return the highest
    return parsed[-1][2]


def _parse_option_range(option: str) -> Optional[Tuple[float, float]]:
    """
    Parse a dropdown option string into a numeric range.

    Handles patterns like:
      "0-1 years", "1 - 3 yrs", "0-1", "5+ years",
      "Less than 1 year", "More than 10 years"
    """
    text = option.strip().lower()

    # Pattern: "X-Y" or "X - Y" (with optional "years"/"yrs")
    range_match = re.match(
        r"(\d+(?:\.\d+)?)\s*[-–]\s*(\d+(?:\.\d+)?)\s*(?:years?|yrs?)?",
        text,
    )
    if range_match:
        return float(range_match.group(1)), float(range_match.group(2))

    # Pattern: "X+" or "X+ years"
    plus_match = re.match(
        r"(\d+(?:\.\d+)?)\s*\+\s*(?:years?|yrs?)?",
        text,
    )
    if plus_match:
        return float(plus_match.group(1)), float("inf")

    # Pattern: "Less than X" or "Under X"
    less_match = re.match(
        r"(?:less\s+than|under|below)\s+(\d+(?:\.\d+)?)\s*(?:years?|yrs?)?",
        text,
    )
    if less_match:
        return 0.0, float(less_match.group(1))

    # Pattern: "More than X" or "Over X"
    more_match = re.match(
        r"(?:more\s+than|over|above)\s+(\d+(?:\.\d+)?)\s*(?:years?|yrs?)?",
        text,
    )
    if more_match:
        return float(more_match.group(1)), float("inf")

    # Pattern: single number "X years" (exact match)
    single_match = re.match(
        r"(\d+(?:\.\d+)?)\s*(?:years?|yrs?)",
        text,
    )
    if single_match:
        val = float(single_match.group(1))
        return val, val

    return None


def select_experience_value(
    profile_experience_months: int,
    field_type: str = "number",
    options: Optional[List[str]] = None,
) -> str:
    """
    Select the appropriate experience value based on field type.

    Args:
        profile_experience_months: Total relevant experience in months.
        field_type: "number", "dropdown", or "text".
        options: Dropdown options if field_type is "dropdown".

    Returns:
        The value to fill in the field.
    """
    if field_type == "dropdown" and options:
        return select_year_bucket(profile_experience_months, options)
    elif field_type == "number":
        # Return exact months for month-granularity fields
        return str(profile_experience_months)
    else:
        # Text field — return human-readable
        years = months_to_years(profile_experience_months)
        if years < 1:
            return f"{profile_experience_months} months"
        elif years == int(years):
            return f"{int(years)} year{'s' if years != 1 else ''}"
        else:
            return f"{years:.1f} years"
