"""
AWS Bedrock service – thin wrapper around boto3.
Keeps all Bedrock interaction in one place so it can later be swapped for
LangChain or another orchestration layer without touching routers.

Supports:
  • Plain chat (messages only)
  • Tool calling (Anthropic Messages API ``tools`` parameter)
"""

import json
import logging
from typing import Any

import boto3
from botocore.exceptions import ClientError

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

# ── Singleton client ────────────────────────────────────────────────────────

_bedrock_client = None


def _get_client(settings: Settings | None = None):
    """Return a reusable bedrock-runtime client (created once)."""
    global _bedrock_client
    if _bedrock_client is None:
        settings = settings or get_settings()
        _bedrock_client = boto3.client(
            service_name="bedrock-runtime",
            region_name=settings.aws_region,
        )
    return _bedrock_client


# ── Public helpers ──────────────────────────────────────────────────────────


def invoke_claude(
    messages: list[dict[str, Any]],
    *,
    system: str | None = None,
    tools: list[dict[str, Any]] | None = None,
    max_tokens: int | None = None,
    temperature: float | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """
    Send a messages-API call to Claude via Bedrock and return the parsed
    response body.

    Parameters
    ----------
    messages    : list of {"role": …, "content": …} (content may be list)
    system      : optional system prompt
    tools       : optional list of tool definitions (Anthropic schema)
    max_tokens / temperature : per-call overrides (fall back to settings)
    """
    settings = settings or get_settings()
    client = _get_client(settings)

    body: dict[str, Any] = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": max_tokens or settings.bedrock_max_tokens,
        "temperature": temperature if temperature is not None else settings.bedrock_temperature,
        "messages": messages,
    }
    if system:
        body["system"] = system
    if tools:
        body["tools"] = tools

    logger.info(
        "Invoking Bedrock model=%s tokens=%s tools=%s",
        settings.bedrock_model_id,
        body["max_tokens"],
        len(tools) if tools else 0,
    )

    try:
        response = client.invoke_model(
            body=json.dumps(body),
            modelId=settings.bedrock_model_id,
            accept="application/json",
            contentType="application/json",
        )
    except ClientError as exc:
        logger.error("Bedrock invocation failed: %s", exc)
        raise

    response_body = json.loads(response["body"].read())
    return response_body


# ── Response parsing ────────────────────────────────────────────────────────


def extract_text(response_body: dict[str, Any]) -> str:
    """Pull the assistant's text out of a Bedrock Messages-API response."""
    content_blocks = response_body.get("content", [])
    return "".join(
        block["text"] for block in content_blocks if block.get("type") == "text"
    )


def extract_tool_calls(response_body: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Return a list of tool_use blocks from the response.
    Each dict has keys: id, name, input.
    """
    return [
        block
        for block in response_body.get("content", [])
        if block.get("type") == "tool_use"
    ]


def has_tool_use(response_body: dict[str, Any]) -> bool:
    """True when the model's stop_reason indicates a tool call."""
    return response_body.get("stop_reason") == "tool_use"


def quick_ask(prompt: str, *, system: str | None = None) -> str:
    """Convenience: single user prompt → assistant text."""
    resp = invoke_claude(
        messages=[{"role": "user", "content": prompt}],
        system=system,
    )
    return extract_text(resp)
