"""
Tests for the Form Filling Layer.
"""

import pytest
from unittest.mock import MagicMock

from backend.parsing.profile_schema import (
    CandidateProfile,
    ContactInfo,
    Experience,
    Project,
)
from backend.form_filler.classifier import FieldClassifier, FieldCategory, _build_classifier_prompt
from backend.form_filler.field_mapper import map_field_value, _select_best_duration_bucket
from backend.form_filler.filler import FormFiller

@pytest.fixture
def sample_profile():
    return CandidateProfile(
        name="Anshul Das",
        contact=ContactInfo(
            address="Bangalore",
            github_url="https://github.com/AnshulDas007",
            linkedin_url="https://linkedin.com/in/anshuldas",
            email="anshul@example.com",
            phone="1234567890",
        ),
        experience=[
            Experience(
                type="internship",
                title="Software Intern",
                company="TechCorp",
                duration_months=6,
                start_date="2024-01",
                end_date="2024-06",
                description="Built an API.",
                is_fresher_relevant=True,
            )
        ],
        projects=[
            Project(
                name="AI App",
                description="Built an AI app.",
                github_url="https://github.com/AnshulDas007/ai-app",
                tech_stack=["Python"]
            )
        ],
        skills=["Python"],
        education=[],
    )

class TestFieldClassifier:
    def test_build_classifier_prompt(self):
        prompt = _build_classifier_prompt("Years of Python", "Skills section", "text")
        assert "Years of Python" in prompt
        assert "work_experience" in prompt
        
    def test_classify_field_success(self):
        mock_router = MagicMock()
        mock_router.complete.return_value = {"content": "work_experience"}
        classifier = FieldClassifier(model_router=mock_router)
        
        category = classifier.classify_field("Describe your past roles")
        assert category == FieldCategory.WORK_EXPERIENCE
        
    def test_classify_field_fallback(self):
        mock_router = MagicMock()
        mock_router.complete.return_value = {"content": "some_random_thing"}
        classifier = FieldClassifier(model_router=mock_router)
        
        category = classifier.classify_field("Weird field")
        assert category == FieldCategory.OTHER

class TestFieldMapper:
    def test_map_basic_fields(self, sample_profile):
        assert map_field_value(sample_profile, FieldCategory.FIRST_NAME) == "Anshul"
        assert map_field_value(sample_profile, FieldCategory.LAST_NAME) == "Das"
        assert map_field_value(sample_profile, FieldCategory.EMAIL) == "anshul@example.com"
        assert map_field_value(sample_profile, FieldCategory.PHONE) == "1234567890"
        
    def test_map_experience_does_not_mix_projects(self, sample_profile):
        val = map_field_value(sample_profile, FieldCategory.WORK_EXPERIENCE)
        assert "TechCorp" in val
        assert "AI App" not in val
        
    def test_map_projects_does_not_mix_experience(self, sample_profile):
        val = map_field_value(sample_profile, FieldCategory.PROJECT)
        assert "AI App" in val
        assert "TechCorp" not in val
        
    def test_map_years_of_experience(self, sample_profile):
        # 6 months = 0.5 years -> rounded down integer representation is "0"
        val = map_field_value(sample_profile, FieldCategory.YEARS_OF_EXPERIENCE)
        assert val == "0"
        
    def test_select_best_duration_bucket(self):
        options = ["0-1 years", "1-3 years", "3-5 years", "5+ years"]
        assert _select_best_duration_bucket(0.5, options) == "0-1 years"
        assert _select_best_duration_bucket(2.0, options) == "1-3 years"
        assert _select_best_duration_bucket(10.0, options) == "5+ years"

class TestFormFiller:
    def test_verify_fill_plan_success(self, sample_profile):
        filler = FormFiller()
        plan = [
            {"category": FieldCategory.WORK_EXPERIENCE, "value": "Worked at TechCorp"},
            {"category": FieldCategory.PROJECT, "value": "Built AI App"}
        ]
        assert filler._verify_fill_plan(plan, sample_profile) == True
        
    def test_verify_fill_plan_failure_mixed(self, sample_profile):
        filler = FormFiller()
        plan = [
            {"category": FieldCategory.WORK_EXPERIENCE, "value": "Built AI App"} # Mix!
        ]
        assert filler._verify_fill_plan(plan, sample_profile) == False
        
        plan2 = [
            {"category": FieldCategory.PROJECT, "value": "Worked at TechCorp"} # Mix!
        ]
        assert filler._verify_fill_plan(plan2, sample_profile) == False
