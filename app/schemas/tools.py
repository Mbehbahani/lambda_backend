"""
Pydantic models for Claude tool-call input validation.
Every filter value is validated against a whitelist or strict format
before it ever reaches a Supabase query.
"""

import re
from typing import Optional

from pydantic import BaseModel, Field, field_validator

# ── Whitelists ──────────────────────────────────────────────────────────────
# Only these column values are accepted.  Anything else is rejected.

ALLOWED_GROUP_BY = frozenset(
    [
        "country",
        "company_name",
        "job_level_std",
        "job_function_std",
        "platform",
        "posted_month",
    ]
)
ALLOWED_METRICS = frozenset(["count"])

SAFE_COLUMNS = [
    "job_id",
    "actual_role",
    "company_name",
    "country",
    "is_remote",
    "job_level_std",
    "posted_date",
    "platform",
]

# ISO date regex  YYYY-MM-DD
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

DEFAULT_LIMIT = 20
HARD_MAX_LIMIT = 100


# ── search_jobs ─────────────────────────────────────────────────────────────

def _check_iso_date(v: Optional[str], field_name: str) -> Optional[str]:
    """Validate a single ISO date string."""
    if v is not None and not _DATE_RE.match(v):
        raise ValueError(f"{field_name} must be ISO format YYYY-MM-DD")
    return v


class SearchJobsInput(BaseModel):
    """Validated input for the search_jobs tool."""

    role_keyword: Optional[str] = None
    country: Optional[str] = None
    is_remote: Optional[bool] = None
    job_level_std: Optional[str] = None
    job_function_std: Optional[str] = None
    company_industry_std: Optional[str] = None
    platform: Optional[str] = None
    is_research: Optional[bool] = None
    posted_start: Optional[str] = None
    posted_end: Optional[str] = None
    limit: int = Field(default=DEFAULT_LIMIT, ge=1, le=HARD_MAX_LIMIT)

    @field_validator("posted_start")
    @classmethod
    def _validate_posted_start(cls, v: Optional[str]) -> Optional[str]:
        return _check_iso_date(v, "posted_start")

    @field_validator("posted_end")
    @classmethod
    def _validate_posted_end(cls, v: Optional[str]) -> Optional[str]:
        return _check_iso_date(v, "posted_end")

    @field_validator("limit", mode="before")
    @classmethod
    def _clamp_limit(cls, v: int) -> int:
        if v is None:
            return DEFAULT_LIMIT
        return min(int(v), HARD_MAX_LIMIT)


# ── job_stats ───────────────────────────────────────────────────────────────

class JobStatsInput(BaseModel):
    """Validated input for the job_stats tool."""

    metric: str
    group_by: str
    country: Optional[str] = None
    is_remote: Optional[bool] = None
    is_research: Optional[bool] = None
    posted_start: Optional[str] = None
    posted_end: Optional[str] = None

    @field_validator("metric")
    @classmethod
    def _validate_metric(cls, v: str) -> str:
        if v not in ALLOWED_METRICS:
            raise ValueError(f"metric must be one of {sorted(ALLOWED_METRICS)}")
        return v

    @field_validator("group_by")
    @classmethod
    def _validate_group_by(cls, v: str) -> str:
        if v not in ALLOWED_GROUP_BY:
            raise ValueError(f"group_by must be one of {sorted(ALLOWED_GROUP_BY)}")
        return v

    @field_validator("posted_start")
    @classmethod
    def _validate_posted_start(cls, v: Optional[str]) -> Optional[str]:
        return _check_iso_date(v, "posted_start")

    @field_validator("posted_end")
    @classmethod
    def _validate_posted_end(cls, v: Optional[str]) -> Optional[str]:
        return _check_iso_date(v, "posted_end")
