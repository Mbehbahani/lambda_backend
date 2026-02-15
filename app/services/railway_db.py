"""
Railway PostgreSQL service – manages the user_cvs table.

Uses psycopg2 for synchronous access (matches project style).
Connection is created once and reused (singleton pattern).
"""

import json
import logging
from typing import Any

import psycopg2
import psycopg2.extras

from app.config import get_settings

logger = logging.getLogger(__name__)

# ── Singleton connection ────────────────────────────────────────────────────

_railway_conn = None


def _get_connection():
    """Return a reusable psycopg2 connection to Railway PostgreSQL (created once)."""
    global _railway_conn
    if _railway_conn is None or _railway_conn.closed:
        settings = get_settings()
        if not settings.railway_database_url:
            raise RuntimeError("RAILWAY_DATABASE_URL is not configured")
        _railway_conn = psycopg2.connect(settings.railway_database_url)
        _railway_conn.autocommit = True
        logger.info("Railway PostgreSQL connection established")
    return _railway_conn


def insert_cv(raw_text: str, embedding: list[float]) -> str:
    """
    Insert a CV into the user_cvs table with its embedding.

    Parameters
    ----------
    raw_text : str
        The raw CV text.
    embedding : list[float]
        512-dimensional embedding vector.

    Returns
    -------
    str
        The UUID of the newly inserted row.
    """
    conn = _get_connection()
    embedding_str = f"[{','.join(str(v) for v in embedding)}]"

    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            INSERT INTO user_cvs (raw_text, embedding)
            VALUES (%s, %s::vector)
            RETURNING id
            """,
            (raw_text, embedding_str),
        )
        row = cur.fetchone()

    cv_id = str(row["id"])
    logger.info("Railway: inserted CV  cv_id=%s  chars=%d", cv_id, len(raw_text))
    return cv_id


def update_matches(cv_id: str, matches_json: list[dict[str, Any]]) -> None:
    """
    Store the top matches JSON in the user_cvs row.

    Parameters
    ----------
    cv_id : str
        UUID of the CV row.
    matches_json : list[dict]
        Serialisable list of match objects.
    """
    conn = _get_connection()

    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE user_cvs
            SET top_matches = %s::jsonb
            WHERE id = %s::uuid
            """,
            (json.dumps(matches_json), cv_id),
        )

    logger.info("Railway: stored matches  cv_id=%s  count=%d", cv_id, len(matches_json))
