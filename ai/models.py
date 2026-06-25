from pydantic import BaseModel, Field


class ScoringResult(BaseModel):
    score: int = Field(ge=0, le=100, description="Relevancy score 0-100")
    matching_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    reason: str = Field(description="One sentence explaining the score")
    seniority_match: bool = Field(description="Whether role level matches candidate seniority")
    seniority_level: str = Field(
        default="unknown",
        description="Detected seniority of the role: entry | associate | intern | mid | senior | unknown",
    )
    location_ok: bool = Field(
        default=True,
        description=(
            "True if the job is in Lahore or Islamabad, OR is remote without requiring "
            "Pakistan-specific work authorization / visa sponsorship"
        ),
    )
    salary_ok: bool = Field(
        default=True,
        description=(
            "True if salary is not mentioned (benefit of doubt), meets PKR 75000+, "
            "or meets USD 600+ per month. False only when a salary is explicitly stated "
            "and it falls below both thresholds."
        ),
    )
    requires_visa: bool = Field(
        default=False,
        description=(
            "True if the remote job explicitly requires work authorization, visa sponsorship, "
            "or residency in a specific country (e.g. 'must be US-based', 'EU work permit required')"
        ),
    )


class ProfileSummary(BaseModel):
    name: str = ""
    skills: list[str] = Field(default_factory=list)
    experience_years: int = 0
    domains: list[str] = Field(default_factory=list)
    seniority: str = Field(default="mid", description="junior | mid | senior")
    preferred_roles: list[str] = Field(default_factory=list)
