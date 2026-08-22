"""
Tests for CandidateProfile schema to ensure structural separation rules.
"""

import pytest
from pydantic import ValidationError
from backend.parsing.profile_schema import Experience, Project, CandidateProfile, ContactInfo, Education

def test_experience_valid():
    exp = Experience(
        type="internship",
        title="Software Engineer Intern",
        company="Acme Corp",
        duration_months=6,
        start_date="Jan 2023",
        end_date="Jun 2023",
        description="Did some coding.",
        is_fresher_relevant=True
    )
    assert exp.title == "Software Engineer Intern"
    assert exp.duration_months == 6

def test_experience_negative_duration():
    with pytest.raises(ValidationError):
        Experience(
            type="internship",
            title="Intern",
            company="Acme",
            duration_months=-1,
            start_date="Jan",
            end_date="Feb",
            description="Bad duration",
            is_fresher_relevant=False
        )

def test_experience_invalid_type():
    with pytest.raises(ValidationError):
        Experience(
            type="freelance", # invalid literal
            title="Dev",
            company="Acme",
            duration_months=3,
            start_date="Jan",
            end_date="Feb",
            description="Freelance",
            is_fresher_relevant=False
        )

def test_project_valid():
    proj = Project(
        name="AI Agent",
        description="Build an agent",
        tech_stack=["Python", "Playwright"]
    )
    assert proj.name == "AI Agent"
    assert "Python" in proj.tech_stack

def test_candidate_profile_creation():
    contact = ContactInfo(
        address="123 Main St",
        github_url="https://github.com/test",
        linkedin_url="https://linkedin.com/in/test",
        email="test@test.com",
        phone="555-1234"
    )
    
    exp = Experience(
        type="full_time",
        title="Dev",
        company="Acme",
        duration_months=12,
        start_date="2022",
        end_date="2023",
        description="Work"
    )
    
    proj = Project(
        name="Side Project",
        description="Cool thing",
        tech_stack=[]
    )
    
    edu = Education(
        institution="University",
        degree="B.S.",
        field_of_study="CS",
        start_date="2018",
        end_date="2022"
    )
    
    profile = CandidateProfile(
        name="Test User",
        contact=contact,
        experience=[exp],
        projects=[proj],
        skills=["Python"],
        education=[edu]
    )
    
    assert profile.name == "Test User"
    assert len(profile.experience) == 1
    assert profile.experience[0].company == "Acme"
    assert len(profile.projects) == 1
    assert profile.projects[0].name == "Side Project"
