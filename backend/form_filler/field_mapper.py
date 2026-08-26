"""
Field Mapper Module.

Maps classified form fields to exact values from the CandidateProfile.
Enforces the structural separation of experience vs projects.
"""

import logging
from typing import Optional, Union, List

from backend.parsing.profile_schema import CandidateProfile
from backend.form_filler.classifier import FieldCategory

logger = logging.getLogger(__name__)

def map_field_value(
    profile: CandidateProfile,
    category: FieldCategory,
    field_label: str = "",
    options: Optional[List[str]] = None
) -> Optional[Union[str, bool]]:
    """
    Given a CandidateProfile and a classified FieldCategory, 
    return the exact string to fill in the form field.
    
    Args:
        profile: The candidate's structured profile.
        category: The FieldCategory determined by the classifier.
        field_label: The original field label (useful for context, e.g., "Years of Python").
        options: Dropdown options if it's a select field.
        
    Returns:
        The string to fill, or True/False for checkboxes, or None if unknown/empty.
    """
    if category == FieldCategory.FIRST_NAME:
        # Assumes first word is first name, rest is last name
        return profile.name.split(" ")[0] if profile.name else ""
        
    elif category == FieldCategory.LAST_NAME:
        parts = profile.name.split(" ")
        return " ".join(parts[1:]) if len(parts) > 1 else ""
        
    elif category == FieldCategory.FULL_NAME:
        return profile.name
        
    elif category == FieldCategory.EMAIL:
        return profile.contact.email
        
    elif category == FieldCategory.PHONE:
        return profile.contact.phone
        
    elif category == FieldCategory.ADDRESS:
        return profile.contact.address
        
    elif category == FieldCategory.GITHUB_URL:
        return profile.contact.github_url
        
    elif category == FieldCategory.LINKEDIN_URL:
        return profile.contact.linkedin_url
        
    elif category == FieldCategory.PORTFOLIO_URL:
        # Fallback to github if no portfolio is explicit, but strictly don't mix github/linkedin
        return profile.contact.github_url
        
    elif category == FieldCategory.SKILLS:
        return ", ".join(profile.skills)
        
    elif category == FieldCategory.WORK_EXPERIENCE:
        # strictly read from profile.experience
        if not profile.experience:
            return ""
        # Format the most relevant/recent experience
        # If the form has multiple blocks, a more advanced ATS handler will map them one by one.
        # This is for a generic text area asking for experience.
        exp = profile.experience[0] 
        return f"{exp.title} at {exp.company} ({exp.start_date} to {exp.end_date}): {exp.description}"
        
    elif category == FieldCategory.PROJECT:
        # strictly read from profile.projects
        if not profile.projects:
            return ""
        proj = profile.projects[0]
        tech = ", ".join(proj.tech_stack) if proj.tech_stack else ""
        return f"{proj.name} ({tech}): {proj.description}"
        
    elif category == FieldCategory.YEARS_OF_EXPERIENCE:
        # Must only derive from `is_fresher_relevant` internships or actual full_time roles.
        # Calculate total months of relevant experience
        total_months = sum(
            exp.duration_months 
            for exp in profile.experience 
            if exp.is_fresher_relevant or exp.type == "full_time"
        )
        total_years = total_months / 12.0
        
        # If it's a dropdown option
        if options:
            return _select_best_duration_bucket(total_years, options)
            
        # If it's a numeric input, return rounded down to nearest half year or integer
        # Never inflate. So if 0.5 years, return "0" or "0.5" depending on typical forms. Let's return exact string.
        if total_years < 1.0:
            return "0"
        return str(int(total_years))
        
    elif category == FieldCategory.EDUCATION:
        if not profile.education:
            return ""
        edu = profile.education[0]
        return f"{edu.degree} in {edu.field_of_study}, {edu.institution}"
        
    elif category == FieldCategory.SIGNATURE:
        # e-signature - safe to fill with name per rules if standalone
        return profile.name
        
    return None

import re

def _select_best_duration_bucket(years: float, options: List[str]) -> str:
    """
    Given a list of dropdown options (e.g. "0-1 years", "1-3 years", "5+ years"), 
    select the lowest bucket that includes the given years of experience.
    Never round up.
    """
    if not options:
        return ""
        
    options_lower = [o.lower() for o in options]
    
    # Check for < 1 year
    if years < 1.0:
        for opt, opt_orig in zip(options_lower, options):
            if "0" in opt or "entry" in opt or "< 1" in opt or "less than 1" in opt:
                return opt_orig

    # Extract bounds and check
    for opt, opt_orig in zip(options_lower, options):
        # Find all numbers in the string
        nums = [float(n) for n in re.findall(r'\d+', opt)]
        if not nums:
            continue
            
        if len(nums) >= 2:
            low, high = nums[0], nums[1]
            if low <= years <= high:
                return opt_orig
        elif len(nums) == 1:
            # Could be "5+ years" or "5 years or more"
            if "+" in opt or "more" in opt or "greater" in opt or ">" in opt:
                if years >= nums[0]:
                    return opt_orig
            else:
                # E.g., "2 years"
                if years >= nums[0]:
                    return opt_orig

    # Default to the lowest option if we can't figure it out, to never inflate.
    return options[0]
