"""
Profile store management.
Handles loading, saving, and gap checking for the CandidateProfile.
"""

import json
import os
import shutil
from pathlib import Path
from typing import List, Optional

import yaml
from pydantic import ValidationError

from backend.parsing.profile_schema import CandidateProfile

PROFILE_JSON_PATH = Path("data/candidate_profile.json")
PROFILE_YAML_PATH = Path("data/candidate_profile.yaml")

def load_profile() -> Optional[CandidateProfile]:
    """Load the candidate profile from JSON if it exists."""
    if not PROFILE_JSON_PATH.exists():
        return None
    
    try:
        with open(PROFILE_JSON_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return CandidateProfile(**data)
    except (json.JSONDecodeError, ValidationError) as e:
        import logging
        logging.error(f"Failed to load profile: {e}")
        return None

def save_profile(profile: CandidateProfile, backup: bool = True) -> None:
    """Save the candidate profile to JSON and YAML."""
    os.makedirs(PROFILE_JSON_PATH.parent, exist_ok=True)
    
    if backup and PROFILE_JSON_PATH.exists():
        backup_path = PROFILE_JSON_PATH.with_suffix(".json.bak")
        shutil.copy2(PROFILE_JSON_PATH, backup_path)
        
    data = profile.model_dump()
    
    # Save JSON
    with open(PROFILE_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        
    # Save YAML
    with open(PROFILE_YAML_PATH, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)

def check_profile_gaps(profile: CandidateProfile) -> List[str]:
    """
    Check the profile for empty/missing fields that might be needed.
    Returns a list of field descriptions that are missing.
    """
    gaps = []
    
    if not profile.contact.phone or profile.contact.phone == "string" or profile.contact.phone == "":
        gaps.append("Phone Number")
    
    if not profile.contact.address or profile.contact.address == "string" or profile.contact.address == "":
        gaps.append("Address / Location")
        
    # Add other typical gaps (notice period, visa status, etc. would go here if added to schema)
    
    return gaps
