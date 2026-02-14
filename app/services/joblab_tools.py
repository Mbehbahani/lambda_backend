"""
JobLab tool implementations - execute validated tool calls against Supabase.

All queries use the PostgREST API with parameterized query-string filters.
NO raw SQL is ever sent. The service_role key is used server-side only.
"""

import logging
from typing import Any

import requests

from app.config import get_settings
from app.schemas.tools import SAFE_COLUMNS, JobStatsInput, SearchJobsInput

logger = logging.getLogger(__name__)


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


def _apply_common_filters(
    qs: dict[str, str],
    *,
    country: str | None,
    is_remote: bool | None,
    is_research: bool | None,
    job_type_filled: str | None = None,
    posted_start: str | None,
    posted_end: str | None,
) -> None:
    """
    Apply shared filters used by both tools.
    This keeps stats/listing totals aligned with dashboard filtering.
    """
    # Keep AI analytics consistent with dashboard behavior.
    qs["has_url_duplicate"] = "eq.0"

    if country and isinstance(country, str) and country.strip():
        qs["country"] = f"ilike.%{country.strip()}%"

    if is_remote is not None:
        qs["is_remote"] = f"eq.{str(is_remote).lower()}"
    if is_research is not None:
        qs["is_research"] = f"eq.{str(is_research).lower()}"
    if job_type_filled and isinstance(job_type_filled, str) and job_type_filled.strip():
        qs["job_type_filled"] = f"ilike.%{job_type_filled.strip()}%"

    if posted_start and posted_end:
        qs["and"] = f"(posted_date.gte.{posted_start},posted_date.lte.{posted_end})"
    elif posted_start:
        qs["posted_date"] = f"gte.{posted_start}"
    elif posted_end:
        qs["posted_date"] = f"lte.{posted_end}"


# Tool: search_jobs

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
    if params.job_level_std:
        qs["job_level_std"] = f"ilike.%{params.job_level_std}%"
    if params.job_function_std:
        qs["job_function_std"] = f"ilike.%{params.job_function_std}%"
    if params.company_industry_std:
        qs["company_industry_std"] = f"ilike.%{params.company_industry_std}%"
    if params.platform:
        qs["platform"] = f"ilike.%{params.platform}%"

    _apply_common_filters(
        qs,
        country=params.country,
        is_remote=params.is_remote,
        is_research=params.is_research,
        job_type_filled=params.job_type_filled,
        posted_start=params.posted_start,
        posted_end=params.posted_end,
    )

    url = f"{_base_url()}/jobs"
    logger.info("search_jobs  url=%s  qs=%s", url, qs)

    resp = requests.get(url, headers=_headers(), params=qs, timeout=15)
    resp.raise_for_status()
    rows: list[dict[str, Any]] = resp.json()
    logger.info("search_jobs  returned %d rows", len(rows))
    return rows


# Tool: job_stats

def _paginated_fetch(
    url: str,
    headers: dict[str, str],
    qs: dict[str, str],
    *,
    page_size: int = 1000,
    max_rows: int = 15000,
    timeout: int = 15,
) -> list[dict[str, Any]]:
    """
    Paginate through PostgREST results using Range headers.
    Returns all matching rows up to *max_rows*.
    """
    all_rows: list[dict[str, Any]] = []
    offset = 0
    fetch_headers = {**headers, "Prefer": "count=exact"}

    while offset < max_rows:
        page_qs = {**qs, "limit": str(page_size), "offset": str(offset)}
        resp = requests.get(url, headers=fetch_headers, params=page_qs, timeout=timeout)
        resp.raise_for_status()
        page: list[dict[str, Any]] = resp.json()
        if not page:
            break
        all_rows.extend(page)
        if len(page) < page_size:
            break
        offset += page_size

    return all_rows


def execute_job_stats(raw_input: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Aggregate job counts grouped by a whitelisted column.

    PostgREST does not support GROUP BY natively, so we fetch the grouped
    column and aggregate in-process.  We paginate to avoid silently
    truncating results.
    """
    params = JobStatsInput(**raw_input)

    select_column = "posted_date" if params.group_by == "posted_month" else params.group_by
    qs: dict[str, str] = {
        "select": select_column,
    }

    _apply_common_filters(
        qs,
        country=params.country,
        is_remote=params.is_remote,
        is_research=params.is_research,
        job_type_filled=params.job_type_filled,
        posted_start=params.posted_start,
        posted_end=params.posted_end,
    )

    url = f"{_base_url()}/jobs"
    logger.info("job_stats  url=%s  qs=%s", url, qs)

    rows = _paginated_fetch(url, _headers(), qs)
    logger.info("job_stats  fetched %d total rows", len(rows))

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
                    None if previous_count == 0 else round((delta / previous_count) * 100, 2)
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
        "job_level_std": getattr(params, "job_level_std", None),
        "job_function_std": getattr(params, "job_function_std", None),
        "company_industry_std": getattr(params, "company_industry_std", None),
        "job_type_filled": params.job_type_filled,
        "platform": getattr(params, "platform", None),
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


# Tool registry

# Claude tool schemas (Anthropic Messages API format)
TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "search_jobs",
        "description": (
            "Search the jobs database using structured filters. "
            "Returns matching job listings with key fields. "
            "Use this when users ask to list, show, find, or search for specific jobs."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "role_keyword": {
                    "type": "string",
                    "description": "Search keyword to filter by position name/title (e.g. Data Scientist, Software Engineer, Product Manager). Matched against the actual_role column.",
                },
                "country": {
                    "type": "string",
                    "description": "Country name filter (e.g. Germany, Sweden, USA). Matched with case-insensitive partial match.",
                },
                "is_remote": {"type": "boolean", "description": "Filter for remote jobs only (true) or non-remote only (false)"},
                "is_research": {"type": "boolean", "description": "Filter for research positions only (true) or non-research only (false)"},
                "job_level_std": {
                    "type": "string",
                    "description": "Standardised seniority level (e.g. Junior, Mid, Senior, Lead, Manager, Director)",
                },
                "job_function_std": {
                    "type": "string",
                    "description": "Standardised job function category (e.g. Engineering, Data Science, Marketing, Sales, Design, Product, Finance, HR, Operations)",
                },
                "company_industry_std": {
                    "type": "string",
                    "description": "Standardised company industry (e.g. Technology, Finance, Healthcare, Education, Retail)",
                },
                "job_type_filled": {
                    "type": "string",
                    "description": "Employment type (e.g. Full-time, Part-time, Contract, Internship)",
                },
                "platform": {
                    "type": "string",
                    "description": "Job platform source (e.g. LinkedIn, Indeed, Glassdoor)",
                },
                "posted_start": {
                    "type": "string",
                    "description": "ISO date YYYY-MM-DD – return jobs posted on or after this date (inclusive)",
                },
                "posted_end": {
                    "type": "string",
                    "description": "ISO date YYYY-MM-DD – return jobs posted on or before this date (inclusive)",
                },
                "limit": {"type": "integer", "description": "Max results to return (default 20, max 100)"},
            },
        },
    },
    {
        "name": "job_stats",
        "description": (
            "Get aggregated job statistics (counts) grouped by a dimension. "
            "Use this for questions about totals, trends over time, distributions, "
            "or comparisons across categories."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "metric": {
                    "type": "string",
                    "enum": ["count"],
                    "description": "Aggregation metric (currently only count is supported)",
                },
                "group_by": {
                    "type": "string",
                    "enum": [
                        "country",
                        "company_name",
                        "job_level_std",
                        "job_function_std",
                        "company_industry_std",
                        "job_type_filled",
                        "platform",
                        "posted_month",
                    ],
                    "description": "Dimension to group results by. Use posted_month for time-series / trend analysis.",
                },
                "country": {"type": "string", "description": "Optional country filter (e.g. Germany, Sweden)"},
                "is_remote": {"type": "boolean", "description": "Optional remote filter"},
                "is_research": {"type": "boolean", "description": "Optional research filter"},
                "job_type_filled": {
                    "type": "string",
                    "description": "Optional employment type filter (e.g. Full-time, Part-time, Contract, Internship)",
                },
                "posted_start": {
                    "type": "string",
                    "description": "ISO date YYYY-MM-DD – count jobs posted on or after this date",
                },
                "posted_end": {
                    "type": "string",
                    "description": "ISO date YYYY-MM-DD – count jobs posted on or before this date",
                },
            },
            "required": ["metric", "group_by"],
        },
    },
]

# Map tool name -> executor function
TOOL_EXECUTORS: dict[str, Any] = {
    "search_jobs": execute_search_jobs,
    "job_stats": execute_job_stats,
}
