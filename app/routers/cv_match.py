"""
CV matching router – POST /ai/match-cv endpoint.
Handles both JSON (cv_text) and FormData (PDF file) uploads.
"""

import json
import logging

from fastapi import APIRouter, HTTPException, Request

from app.schemas.cv_match import CVMatchResponse
from app.services.cv_service import match_cv, extract_text_from_pdf

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai", tags=["ai"])


@router.post(
    "/match-cv",
    response_model=CVMatchResponse,
    summary="Match a CV against job listings using vector similarity",
)
async def match_cv_endpoint(request: Request):
    """
    Accept CV via JSON or FormData with optional filter criteria.

    - JSON: { "cv_text": "...", "countries": [...], ... }
    - FormData: file (PDF) + optional filter fields (JSON-encoded strings)

    If both file and cv_text are provided, concatenate them.
    """
    try:
        content_type = request.headers.get("content-type", "")
        combined_cv = ""
        filter_countries = []
        filter_levels = []
        filter_functions = []
        filter_platforms = []
        filter_remote = None
        filter_keyword = ""

        if "multipart/form-data" in content_type:
            # FormData path (PDF upload)
            form = await request.form()
            
            # Extract PDF text if provided
            file = form.get("file")
            if file and hasattr(file, "read"):
                pdf_content = await file.read()
                pdf_text = extract_text_from_pdf(pdf_content)
                combined_cv += pdf_text
            
            # Extract cv_text if provided
            cv_text = form.get("cv_text")
            if cv_text:
                combined_cv += "\n" + str(cv_text)
            
            # Parse filters from FormData (JSON-encoded strings)
            if form.get("countries"):
                filter_countries = json.loads(str(form.get("countries")))
            if form.get("job_levels"):
                filter_levels = json.loads(str(form.get("job_levels")))
            if form.get("job_functions"):
                filter_functions = json.loads(str(form.get("job_functions")))
            if form.get("platforms"):
                filter_platforms = json.loads(str(form.get("platforms")))
            if form.get("is_remote") and str(form.get("is_remote")).lower() != "null":
                filter_remote = json.loads(str(form.get("is_remote")))
            if form.get("role_keyword"):
                filter_keyword = str(form.get("role_keyword"))
        
        else:
            # JSON path
            body = await request.json()
            combined_cv = body.get("cv_text", "")
            filter_countries = body.get("countries", [])
            filter_levels = body.get("job_levels", [])
            filter_functions = body.get("job_functions", [])
            filter_platforms = body.get("platforms", [])
            filter_remote = body.get("is_remote")
            filter_keyword = body.get("role_keyword", "")

        combined_cv = combined_cv.strip()

        if not combined_cv or len(combined_cv) < 10:
            raise ValueError("CV text must be at least 10 characters.")

        logger.info(
            "POST /ai/match-cv  cv_len=%d  filters: countries=%s levels=%s",
            len(combined_cv), filter_countries, filter_levels,
        )

        result = match_cv(
            combined_cv,
            countries=filter_countries,
            job_levels=filter_levels,
            job_functions=filter_functions,
            platforms=filter_platforms,
            is_remote=filter_remote,
            role_keyword=filter_keyword,
        )
        logger.info(
            "CV match success  cv_id=%s  matches=%d",
            result.cv_id,
            len(result.matches),
        )
        return result

    except ValueError as exc:
        logger.warning("CV match validation error: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    except Exception as exc:
        logger.exception("CV match failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
