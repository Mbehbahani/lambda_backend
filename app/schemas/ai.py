"""
Pydantic models for request / response validation.
"""

from pydantic import BaseModel, Field


# ── Requests ────────────────────────────────────────────────────────────────


class AskRequest(BaseModel):
    """Body for the /ai/ask endpoint."""

    prompt: str = Field(
        ...,
        min_length=1,
        max_length=4000,
        description="User question to send to the AI model.",
    )
    system: str | None = Field(
        default=None,
        max_length=4000,
        description="Optional system prompt to guide the model.",
    )
    conversation_id: str | None = Field(
        default=None,
        description="Optional conversation ID for session memory. Auto-generated if omitted.",
    )


# ── Responses ───────────────────────────────────────────────────────────────


class AskResponse(BaseModel):
    """Successful AI response."""

    answer: str
    model: str
    usage: dict | None = None
    tool_calls: list[dict] | None = None
    conversation_id: str | None = None


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str


class ErrorResponse(BaseModel):
    detail: str
