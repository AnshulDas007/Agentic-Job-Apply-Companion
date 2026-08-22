"""
Candidate profile schema.
Strict typing to ensure structural separation between experience, projects, and contact info.
"""

from typing import List, Literal, Optional
from pydantic import BaseModel, Field, model_validator

class Experience(BaseModel):
    type: Literal["internship", "full_time", "part_time", "contract"]
    title: str
    company: str
    duration_months: int = Field(ge=0, description="Exact duration in months, never rounded")
    start_date: str
    end_date: str
    description: str
    is_fresher_relevant: bool = Field(default=False, description="True if internship, used for 'years of experience' fields")

    @model_validator(mode="after")
    def check_no_project_fields(self) -> "Experience":
        # Additional safety check if we ever dynamically add fields
        if hasattr(self, "tech_stack"):
            raise ValueError("Experience cannot contain a tech_stack field. Use Project instead.")
        return self

class Project(BaseModel):
    name: str
    description: str
    github_url: Optional[str] = None
    tech_stack: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_no_experience_fields(self) -> "Project":
        if hasattr(self, "company") or hasattr(self, "duration_months"):
            raise ValueError("Project cannot contain company or duration_months fields. Use Experience instead.")
        return self

class ContactInfo(BaseModel):
    address: str
    github_url: str
    linkedin_url: str
    email: str
    phone: str

class Education(BaseModel):
    institution: str
    degree: str
    field_of_study: str
    start_date: str
    end_date: str
    gpa: Optional[str] = None

class CandidateProfile(BaseModel):
    name: str
    contact: ContactInfo
    experience: List[Experience] = Field(default_factory=list, description="ONLY real work/internship history")
    projects: List[Project] = Field(default_factory=list, description="ONLY personal/academic projects")
    skills: List[str] = Field(default_factory=list)
    education: List[Education] = Field(default_factory=list)
