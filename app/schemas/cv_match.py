"""
Pydantic models for the CV matching endpoint.
"""

from pydantic import BaseModel, Field


class CVMatchRequest(BaseModel):
    """Body for POST /ai/match-cv."""

    cv_text: str = Field(
        ...,
        min_length=10,
        max_length=20000,
        description="Raw CV / resume text to match against jobs.",
    )

    # Optional filter criteria
    countries: list[str] = Field(
        default_factory=list,
        description="Filter by specific countries (e.g., ['USA', 'Germany'])",
    )
    job_levels: list[str] = Field(
        default_factory=list,
        description="Filter by seniority levels (e.g., ['Junior', 'Mid', 'Senior'])",
    )
    job_functions: list[str] = Field(
        default_factory=list,
        description="Filter by job functions (e.g., ['Engineering', 'Data Science'])",
    )
    platforms: list[str] = Field(
        default_factory=list,
        description="Filter by platforms (e.g., ['LinkedIn', 'Indeed'])",
    )
    is_remote: bool | None = Field(
        default=None,
        description="Filter by remote work (true = remote only, false = on-site only, null = both)",
    )
    role_keyword: str = Field(
        default="",
        description="Filter by keyword in job title",
    )


class JobMatch(BaseModel):
    """A single matched job with similarity score."""

    job_id: str
    title: str
    company: str
    similarity: float
    country: str = ""
    location: str = ""
    url: str = ""
    posted_date: str = ""
    job_level_std: str = ""
    job_function_std: str = ""
    job_type_filled: str = ""
    platform: str = ""
    is_remote: bool = False
    relaxed_criteria: bool = Field(
        default=False,
        description="True if this match doesn't meet all user filters (shown as fallback)",
    )


class CVMatchResponse(BaseModel):
    """Response returned by /ai/match-cv."""

    cv_id: str
    matches: list[JobMatch]
