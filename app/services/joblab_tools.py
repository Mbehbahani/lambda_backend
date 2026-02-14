"""
JobLab tool implementations – execute validated tool calls against Supabase.

All queries use the PostgREST API with parameterised query-string filters.
NO raw SQL is ever sent.  The service_role key is used server-side only.
"""

import logging
from typing import Any

import requests

from app.config import get_settings
from app.schemas.tools import (
    SAFE_COLUMNS,
    SearchJobsInput,
    JobStatsInput,
)

logger = logging.getLogger(__name__)

# ── Helpers ─────────────────────────────────────────────────────────────────


def _headers() -> dict[str, str]:
    """Auth headers for Supabase REST (service_role, bypasses RLS)."""
    settings = get_settings()
    return {
        "apikey": settings.supabase_service_role_key,
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def _base_url() -> str:
    return f"{get_settings().supabase_url.rstrip('/')}/rest/v1"


# ── Tool: search_jobs ──────────────────────────────────────────────────────


def execute_search_jobs(raw_input: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Build a PostgREST query from validated filters and return matching rows.
    Only the columns in SAFE_COLUMNS are selected.
    """
    params = SearchJobsInput(**raw_input)

    qs: dict[str, str] = {
        "select": ",".join(SAFE_COLUMNS),
        "order": "posted_date.desc.nullslast",
        "limit": str(params.limit),
    }

    # Text search filters (PostgREST ilike operators)
    if params.role_keyword:
        qs["actual_role"] = f"ilike.%{params.role_keyword}%"
    if params.country:
        qs["country"] = f"ilike.%{params.country}%"
    if params.is_remote is not None:
        qs["is_remote"] = f"eq.{str(params.is_remote).lower()}"
    if params.job_level_std:
        qs["job_level_std"] = f"ilike.%{params.job_level_std}%"
    if params.job_function_std:
        qs["job_function_std"] = f"ilike.%{params.job_function_std}%"
    if params.company_industry_std:
        qs["company_industry_std"] = f"ilike.%{params.company_industry_std}%"
    if params.platform:
        qs["platform"] = f"ilike.%{params.platform}%"
    if params.is_research is not None:
        qs["is_research"] = f"eq.{str(params.is_research).lower()}"

    # Date-range filters (PostgREST AND logic via separate params)
    if params.posted_start and params.posted_end:
        # PostgREST: combine with and=(posted_date.gte.<start>,posted_date.lte.<end>)
        qs["and"] = f"(posted_date.gte.{params.posted_start},posted_date.lte.{params.posted_end})"
    elif params.posted_start:
        qs["posted_date"] = f"gte.{params.posted_start}"
    elif params.posted_end:
        qs["posted_date"] = f"lte.{params.posted_end}"

    url = f"{_base_url()}/jobs"
    logger.info("search_jobs  url=%s  qs=%s", url, qs)

    resp = requests.get(url, headers=_headers(), params=qs, timeout=15)
    resp.raise_for_status()
    rows: list[dict[str, Any]] = resp.json()
    logger.info("search_jobs  returned %d rows", len(rows))
    return rows


# ── Tool: job_stats ─────────────────────────────────────────────────────────


def execute_job_stats(raw_input: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Aggregate job counts grouped by a whitelisted column.

    PostgREST doesn't support GROUP BY natively, so we fetch the column
    and aggregate in-process (fast — the column is indexed, and we only
    pull one field per row with a generous limit).
    """
    params = JobStatsInput(**raw_input)

    select_column = "posted_date" if params.group_by == "posted_month" else params.group_by
    qs: dict[str, str] = {
        "select": select_column,
        "limit": "5000",
    }

    if params.country:
        qs["country"] = f"ilike.%{params.country}%"
    if params.is_remote is not None:
        qs["is_remote"] = f"eq.{str(params.is_remote).lower()}"

    # Date-range filters
    if params.posted_start and params.posted_end:
        qs["and"] = f"(posted_date.gte.{params.posted_start},posted_date.lte.{params.posted_end})"
    elif params.posted_start:
        qs["posted_date"] = f"gte.{params.posted_start}"
    elif params.posted_end:
        qs["posted_date"] = f"lte.{params.posted_end}"

    url = f"{_base_url()}/jobs"
    logger.info("job_stats  url=%s  qs=%s", url, qs)

    resp = requests.get(url, headers=_headers(), params=qs, timeout=15)
    resp.raise_for_status()
    rows: list[dict[str, Any]] = resp.json()

    if params.group_by == "posted_month":
        logger.info("job_stats  monthly grouping activated total_rows=%d", len(rows))
        month_counts: dict[str, int] = {}
        for row in rows:
            posted_date = row.get("posted_date")
            if not posted_date:
                continue
            month_key = str(posted_date)[:7]
            if len(month_key) != 7 or month_key[4] != "-":
                continue
            month_counts[month_key] = month_counts.get(month_key, 0) + 1

        sorted_months = sorted(month_counts.keys())
        result: list[dict[str, Any]] = []
        previous_count: int | None = None
        for month in sorted_months:
            count = month_counts[month]
            if previous_count is None:
                delta = None
                percent_change = None
            else:
                delta = count - previous_count
                percent_change = (
                    None
                    if previous_count == 0
                    else round((delta / previous_count) * 100, 2)
                )

            result.append(
                {
                    "value": month,
                    "count": count,
                    "delta_from_previous": delta,
                    "percent_change": percent_change,
                }
            )
            previous_count = count

        logger.info("job_stats  delta calculation executed months=%d", len(result))
        return result

    # If the grouped dimension is already constrained by a matching filter,
    # return a single total count instead of a one-bucket grouped result.
    group_dimension_filters: dict[str, Any] = {
        "country": params.country,
    }
    dimension_filter_value = group_dimension_filters.get(params.group_by)
    total_only_mode = (
        params.metric == "count"
        and dimension_filter_value is not None
        and str(dimension_filter_value).strip() != ""
    )
    if total_only_mode:
        total_count = len(rows)
        logger.info(
            "job_stats  total-only mode activated group_by=%s filter=%s total_count=%d",
            params.group_by,
            dimension_filter_value,
            total_count,
        )
        return [{"value": "total", "count": total_count}]

    # In-process aggregation
    counts: dict[str, int] = {}
    col = params.group_by
    for row in rows:
        key = row.get(col) or "Unknown"
        counts[key] = counts.get(key, 0) + 1

    # Sort descending by count, return top 25
    result = sorted(
        [{"value": k, "count": v} for k, v in counts.items()],
        key=lambda x: x["count"],
        reverse=True,
    )[:25]

    logger.info("job_stats  groups=%d  total_rows=%d", len(result), len(rows))
    return result


# ── Tool registry ──────────────────────────────────────────────────────────

# Claude tool schemas (Anthropic Messages API format)
TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "search_jobs",
        "description": (
            "Search the jobs database using structured filters. "
            "Returns matching job listings with key fields."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "role_keyword": {"type": "string", "description": "Search keyword to filter by position name/title (e.g. 'Data Scientist', 'Software Engineer', 'Product Manager')"},
                "country": {"type": "string", "description": "Country name filter"},
                "is_remote": {"type": "boolean", "description": "Remote jobs only"},
                "job_level_std": {"type": "string", "description": "Job level (e.g. Junior, Mid, Senior)"},
                "job_function_std": {"type": "string", "description": "Job function category"},
                "company_industry_std": {"type": "string", "description": "Company industry"},
                "platform": {"type": "string", "description": "Job platform (e.g. LinkedIn, Indeed)"},
                "is_research": {"type": "boolean", "description": "Research positions only"},
                "posted_start": {"type": "string", "description": "ISO date YYYY-MM-DD — return jobs posted on or after this date (inclusive)"},
                "posted_end": {"type": "string", "description": "ISO date YYYY-MM-DD — return jobs posted on or before this date (inclusive)"},
                "limit": {"type": "integer", "description": "Max results (default 20, max 100)"},
            },
        },
    },
    {
        "name": "job_stats",
        "description": (
            "Get aggregated job statistics (counts) grouped by a dimension. "
            "Use this for questions about trends, distributions, or totals."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "metric": {
                    "type": "string",
                    "enum": ["count"],
                    "description": "Aggregation metric",
                },
                "group_by": {
                    "type": "string",
                    "enum": [
                        "country",
                        "company_name",
                        "job_level_std",
                        "job_function_std",
                        "platform",
                        "posted_month",
                    ],
                    "description": "Column to group results by",
                },
                "country": {"type": "string", "description": "Optional country filter"},
                "is_remote": {"type": "boolean", "description": "Optional remote filter"},
                "posted_start": {"type": "string", "description": "ISO date YYYY-MM-DD — count jobs posted on or after this date"},
                "posted_end": {"type": "string", "description": "ISO date YYYY-MM-DD — count jobs posted on or before this date"},
            },
            "required": ["metric", "group_by"],
        },
    },
]

# Map tool name → executor function
TOOL_EXECUTORS: dict[str, Any] = {
    "search_jobs": execute_search_jobs,
    "job_stats": execute_job_stats,
}
