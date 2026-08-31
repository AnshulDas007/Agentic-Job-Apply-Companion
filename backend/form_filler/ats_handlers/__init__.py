"""
ATS Handlers package.

Platform-specific form adapters for different Applicant Tracking Systems.
Each handler knows how to extract fields and navigate the form flow
for its specific ATS platform.
"""

from backend.form_filler.ats_handlers.base import BaseATSHandler
from backend.form_filler.ats_handlers.greenhouse import GreenhouseHandler
from backend.form_filler.ats_handlers.lever import LeverHandler
from backend.form_filler.ats_handlers.workday import WorkdayHandler
from backend.form_filler.ats_handlers.ashby import AshbyHandler
from backend.form_filler.ats_handlers.generic import GenericHandler

ATS_HANDLERS = {
    "greenhouse": GreenhouseHandler,
    "lever": LeverHandler,
    "workday": WorkdayHandler,
    "ashby": AshbyHandler,
    "generic": GenericHandler,
}


def get_handler_for_url(url: str) -> BaseATSHandler:
    """
    Detect the ATS platform from the URL and return the appropriate handler.

    Args:
        url: The job application URL.

    Returns:
        An ATS handler instance for the detected platform.
    """
    url_lower = url.lower()

    if "greenhouse.io" in url_lower or "boards.greenhouse" in url_lower:
        return GreenhouseHandler()
    elif "lever.co" in url_lower or "jobs.lever" in url_lower:
        return LeverHandler()
    elif "myworkday" in url_lower or "workday.com" in url_lower:
        return WorkdayHandler()
    elif "ashbyhq.com" in url_lower or "jobs.ashby" in url_lower:
        return AshbyHandler()
    else:
        return GenericHandler()
