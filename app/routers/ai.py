"""
AI router - exposes Bedrock-backed endpoints.
Supports Claude tool calling for structured Supabase queries.
"""

import json
import logging
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException

from app.config import get_settings
from app.schemas.ai import AskRequest, AskResponse, ErrorResponse
from app.services.bedrock import (
    invoke_claude,
    extract_text,
    extract_tool_calls,
    has_tool_use,
)
from app.services.joblab_tools import TOOL_DEFINITIONS, TOOL_EXECUTORS
from app.services.conversation_memory import (
    get_last_tool,
    set_last_tool,
    get_pending_followup,
    set_pending_followup,
    clear_pending_followup,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai", tags=["ai"])


JOBLAB_SYSTEM = """
You are JobLab GenAI — a deterministic analytics assistant connected to a structured jobs database.

You operate under strict rules.

────────────────────────
1. DATABASE ENFORCEMENT
────────────────────────
If a user question involves:
- job listings
- job counts
- trends
- comparisons
- filters (country, date, remote, level, platform, research)
- specific job titles

You MUST call a tool.
You are NOT allowed to answer from memory.
You must never fabricate numbers.

Only answer directly if the question is unrelated to the jobs database.

────────────────────────
2. TOOL SELECTION RULES
────────────────────────
If the question contains:
- "how many"
- "count"
- "number of"
- "total"
- "percentage"
- "distribution"

→ Use job_stats with metric="count".

If the user wants listings:
- "show"
- "list"
- "find"
- "search"
- or asks about specific position names

→ Use search_jobs.

If the user asks about trends or changes:
→ Use job_stats with appropriate grouping.

If user mentions:
- trend
- increase
- decrease
- growth
- decline
- month-over-month
- comparison
- compare
- change

→ Use job_stats with group_by="posted_month".

────────────────────────
2a. SEMANTIC SEARCH RULES
────────────────────────
If the user question contains concept-level or meaning-based language such as:
- "related to"
- "about"
- "similar to"
- "positions mentioning"
- "jobs involving"
- "skills like"
- "roles that deal with"
- abstract topics, techniques, or domain concepts (e.g. "stochastic optimization", "container shipping forecasting", "NLP transformers")

→ You MUST call semantic_search_jobs.

semantic_search_jobs performs vector similarity search across job descriptions.
It finds jobs by meaning, not exact keyword match.

Do NOT combine semantic_search_jobs with search_jobs or job_stats in the same call.
Use only ONE tool type per request.

When presenting semantic search results:
- Summarize the matched job descriptions concisely.
- Mention the similarity score qualitatively (e.g. "highly relevant", "moderately related").
- Do not expose raw similarity numbers or vectors to the user.

Never mix tools unless necessary.

────────────────────────
3. AVAILABLE FILTERS
────────────────────────
You can filter by:
- country: actual country name (e.g. Germany, USA)
- is_remote: true/false for remote work
- is_research: true/false for research positions
- job_level_std: seniority (Junior, Mid, Senior, Lead, Manager, Director)
- job_function_std: function (Engineering, Data Science, Marketing, etc.)
- company_industry_std: industry (Technology, etc.)
- job_type_filled: employment type (Full-time, Part-time, Contract, Internship)
- platform: job source (LinkedIn and Indeed)
- posted_start / posted_end: ISO date boundaries
- role_keyword: free text match on job title (search_jobs only)

For job_stats you can group_by:
country, company_name, job_level_std, job_function_std, company_industry_std, job_type_filled, platform, posted_month

────────────────────────
4. TEMPORAL RULES (current database has been started from 2026-01-01)
────────────────────────
If the user specifies:
- a month + year (e.g., February 2026)
- a year
- a date range
- "after <date>"
- "before <date>"

You MUST convert it into ISO boundaries using:
posted_start and/or posted_end.

Example:
January 2026 →
posted_start = 2026-01-01
posted_end = 2026-01-31

Never ignore temporal constraints.

────────────────────────
5. STRICT DATA POLICY
────────────────────────
- Never hallucinate numbers.
- Never approximate.
- Never assume.
- Always rely strictly on tool output.
- Never drop an explicit user filter (country, research, remote, date, platform, level).
- If user asks for research positions, pass is_research=true.
- If user asks about remote jobs, pass is_remote=true.
- If user asks about a specific country, pass the country name directly (e.g. country="Germany").
- The database has real country names stored in the country column. Use the actual country name.
- If user mentions employment type (full-time, part-time, contract, internship), pass job_type_filled.
- If zero → say zero.
- If empty → say no data found.

────────────────────────
5a. MINIMAL FILTER POLICY
────────────────────────
- ONLY apply filters the user explicitly mentions.
- NEVER add extra filters the user did not ask for.
- If user says "count jobs by country posted after 2026-01-01", use ONLY group_by="country" and posted_start="2026-01-01". Do NOT add is_remote, is_research, job_level_std, job_function_std, platform, or any other filter unless the user explicitly asked for it.
- Adding unnecessary filters reduces the result set and produces incorrect counts.
- When unsure whether a filter is needed, do NOT include it.

────────────────────────
6. RESPONSE STYLE
────────────────────────
After receiving tool results:
- Provide a concise answer.
- Do not expose raw JSON.
- Offer optional follow-up filters.
- Remain analytical, not conversational.
- When grouped monthly data includes delta and percent_change, interpret trend direction.
- Mention increase/decrease magnitude concisely.
- Do not hallucinate beyond provided data.

────────────────────────
7. CONVERSATION MEMORY RULES
────────────────────────
If the user provides a short follow-up instruction (e.g. "only remote", "now Germany", "senior only"),
interpret it as a refinement of the previous tool call.
Modify previous filters accordingly instead of starting a new unrelated query.

────────────────────────
8. FOLLOW-UP CONFIRMATION RULES
────────────────────────
If you offer additional analysis or breakdown and the user responds with an affirmative answer
(e.g., "yes", "sure", "please"), interpret it as a confirmation to expand the previous query.
Provide a more detailed breakdown by calling the appropriate tool with additional grouping.
Never refuse an affirmative follow-up. Always interpret it as wanting more detail on the previous query.
"""

MAX_TOOL_ROUNDS = 5  # safety: prevent infinite tool loops
MAX_SOFT_ENFORCEMENT_RETRIES = 2
DB_RELATED_KEYWORDS = [
    "job",
    "jobs",
    "how many",
    "count",
    "list",
    "show",
    "find",
    "trend",
    "increase",
    "decrease",
    "growth",
    "decline",
    "month-over-month",
    "comparison",
    "compare",
    "change",
    "hiring",
    "posted",
    "research",
    "remote",
    "industry",
    "full-time",
    "part-time",
    "contract",
    "internship",
    # Semantic search triggers
    "related to",
    "about",
    "similar to",
    "positions mentioning",
    "jobs involving",
    "skills like",
    "roles that deal with",
]


def _is_database_related(prompt: str) -> bool:
    prompt_lower = prompt.lower()
    return any(keyword in prompt_lower for keyword in DB_RELATED_KEYWORDS)


# Short affirmative/vague follow-ups that imply "continue with previous context"
_AFFIRMATIVE_PATTERNS = [
    "yes", "yeah", "yep", "yup", "sure", "please", "ok", "okay",
    "go ahead", "do it", "show me", "tell me", "absolutely",
    "of course", "why not", "right", "correct", "exactly",
    "more", "details", "elaborate", "explain", "break it down",
    "breakdown", "continue", "go on", "please do",
]

# Negative patterns — user declining a follow-up offer
_NEGATIVE_PATTERNS = [
    "no", "nah", "nope", "no thanks", "no thank you",
    "not now", "not really", "never mind", "nevermind",
    "skip", "pass", "i'm good", "im good", "that's all",
    "thats all", "all good", "nothing else",
]

_NEGATED_RESEARCH_PATTERNS = [
    "non research",
    "non-research",
    "not research",
    "exclude research",
    "excluding research",
    "without research",
]

def _is_affirmative_followup(prompt: str) -> bool:
    """Check if prompt is a short affirmative/continuation response."""
    prompt_lower = prompt.strip().lower().rstrip("!.,?")
    return prompt_lower in _AFFIRMATIVE_PATTERNS


def _is_negative_followup(prompt: str) -> bool:
    """Check if prompt is a short negative/declining response."""
    prompt_lower = prompt.strip().lower().rstrip("!.,?")
    return prompt_lower in _NEGATIVE_PATTERNS


def _infer_research_filter(prompt: str) -> bool | None:
    """
    Infer an explicit research filter from user text.
    Returns:
      - True for research-only intent
      - False for non-research intent
      - None when no explicit intent is present
    """
    prompt_lower = prompt.lower()
    if any(pattern in prompt_lower for pattern in _NEGATED_RESEARCH_PATTERNS):
        return False
    if "research" in prompt_lower:
        return True
    return None


def _enforce_prompt_filters(
    tool_name: str,
    tool_input: dict[str, Any],
    prompt: str,
) -> dict[str, Any]:
    """
    Defensive guardrail: if the prompt clearly asks for a filter and the model omits it,
    inject that filter before executing the tool.
    """
    if tool_name not in {"search_jobs", "job_stats"}:
        return dict(tool_input)

    adjusted_input = dict(tool_input)

    research_filter = _infer_research_filter(prompt)
    if research_filter is not None and adjusted_input.get("is_research") is None:
        adjusted_input["is_research"] = research_filter

    return adjusted_input


def _build_followup_args(tool_name: str, tool_args: dict) -> tuple[str, dict]:
    """
    Convert a previous tool call into an expanded follow-up call.
    - job_stats count → search_jobs with same filters (show listings)
    - search_jobs → job_stats grouped by job_function_std (show breakdown)
    """
    if tool_name == "job_stats":
        # User asked for a count → now show the actual listings
        new_args: dict[str, Any] = {}
        for key in (
            "country",
            "is_remote",
            "is_research",
            "job_type_filled",
            "posted_start",
            "posted_end",
        ):
            if key in tool_args and tool_args[key] is not None:
                new_args[key] = tool_args[key]
        new_args["limit"] = 20
        return "search_jobs", new_args

    if tool_name == "search_jobs":
        # User saw listings → now show a statistical breakdown
        new_args = {"metric": "count", "group_by": "job_function_std"}
        for key in (
            "country",
            "is_remote",
            "is_research",
            "job_type_filled",
            "posted_start",
            "posted_end",
        ):
            if key in tool_args and tool_args[key] is not None:
                new_args[key] = tool_args[key]
        return "job_stats", new_args

    # Fallback: re-run same tool
    return tool_name, dict(tool_args)


@router.post(
    "/ask",
    response_model=AskResponse,
    responses={500: {"model": ErrorResponse}},
    summary="Ask the AI model a question (with tool calling)",
)
async def ask(body: AskRequest):
    """
    1. Check for pending follow-up confirmations (yes/no).
    2. Send the user prompt + tool definitions to Claude.
    3. If Claude responds with tool_use -> execute, append result, re-call.
    4. Repeat until Claude returns a final text answer (up to MAX_TOOL_ROUNDS).
    5. After response, set pending follow-up if assistant offered one.
    """
    settings = get_settings()

    # Ensure conversation_id exists
    conversation_id = body.conversation_id or str(uuid.uuid4())

    # ── Dialogue state: handle affirmative/negative follow-ups ──────────
    pending = get_pending_followup(conversation_id)

    if pending and _is_negative_followup(body.prompt):
        clear_pending_followup(conversation_id)
        return AskResponse(
            answer="Alright. Let me know if you'd like additional insights.",
            model=settings.bedrock_model_id,
            usage=None,
            tool_calls=None,
            conversation_id=conversation_id,
        )

    if pending and _is_affirmative_followup(body.prompt):
        clear_pending_followup(conversation_id)
        followup_tool = pending["tool_name"]
        followup_args = pending["tool_args"]

        # Build expanded tool call from the pending context
        exec_tool_name, exec_tool_args = _build_followup_args(followup_tool, followup_args)
        logger.info(
            "Pending follow-up confirmed: %s(%s) → %s(%s)",
            followup_tool, followup_args, exec_tool_name, exec_tool_args,
        )

        executor = TOOL_EXECUTORS.get(exec_tool_name)
        if executor is None:
            return AskResponse(
                answer=f"Unknown tool: {exec_tool_name}",
                model=settings.bedrock_model_id,
                usage=None,
                tool_calls=None,
                conversation_id=conversation_id,
            )

        try:
            result_data = executor(exec_tool_args)
            result_json = json.dumps(result_data, default=str)
        except Exception as exc:
            logger.exception("Follow-up tool %s failed", exec_tool_name)
            return AskResponse(
                answer=f"Tool execution failed: {exc}",
                model=settings.bedrock_model_id,
                usage=None,
                tool_calls=[{"name": exec_tool_name, "input": exec_tool_args}],
                conversation_id=conversation_id,
            )

        # Store this as the new last tool
        set_last_tool(conversation_id, exec_tool_name, exec_tool_args)

        # Send tool result to Claude for a natural language summary
        messages: list[dict[str, Any]] = [
            {
                "role": "user",
                "content": (
                    f"The user confirmed they want more details. "
                    f"I executed {exec_tool_name} with {json.dumps(exec_tool_args)}.\n\n"
                    f"Results:\n{result_json}\n\n"
                    f"Summarize these results clearly. Do not expose raw JSON."
                ),
            },
        ]
        raw = invoke_claude(messages=messages, system=JOBLAB_SYSTEM, tools=[])
        answer = extract_text(raw)

        # Set pending follow-up for the new result too
        set_pending_followup(conversation_id, {
            "type": "expand_previous_query",
            "tool_name": exec_tool_name,
            "tool_args": exec_tool_args,
        })

        return AskResponse(
            answer=answer,
            model=settings.bedrock_model_id,
            usage=raw.get("usage"),
            tool_calls=[{"name": exec_tool_name, "input": exec_tool_args}],
            conversation_id=conversation_id,
        )

    # ── Normal flow ─────────────────────────────────────────────────────

    # Use the dedicated system prompt; ignore any client-supplied one
    system = JOBLAB_SYSTEM

    # Retrieve last tool memory for follow-up refinement
    last_tool_name, last_tool_args = get_last_tool(conversation_id)

    messages = []

    # If user input is short and likely a refinement, inject a hint
    if last_tool_name and len(body.prompt.split()) <= 6:
        is_affirmative = _is_affirmative_followup(body.prompt)
        if is_affirmative:
            hint = (
                f"[Context: The previous tool used was '{last_tool_name}' "
                f"with arguments {json.dumps(last_tool_args)}. "
                f"The user said \"{body.prompt}\" which is an affirmative response. "
                f"They want more details or a breakdown of the previous results. "
                f"You MUST call a tool to provide this. Re-use the same filters "
                f"and add grouping or detail to give a richer answer.]"
            )
        else:
            hint = (
                f"[Context: The previous tool used was '{last_tool_name}' "
                f"with arguments {json.dumps(last_tool_args)}. "
                f"The user is likely refining those filters.]\n\n"
                f"{body.prompt}"
            )
        messages.append({"role": "user", "content": hint})
    else:
        messages.append({"role": "user", "content": body.prompt})

    # A prompt is DB-related if it matches keywords OR is a follow-up to a previous tool call
    db_related_prompt = _is_database_related(body.prompt) or (
        last_tool_name is not None and len(body.prompt.split()) <= 6
    )
    no_tool_retry_count = 0
    has_called_tool = False
    collected_tool_calls: list[dict[str, Any]] = []

    try:
        for _round in range(MAX_TOOL_ROUNDS):
            raw = invoke_claude(
                messages=messages,
                system=system,
                tools=TOOL_DEFINITIONS,
            )

            # No tool call -> either enforce or return text answer
            if not has_tool_use(raw):
                if (
                    db_related_prompt
                    and not has_called_tool
                    and no_tool_retry_count < MAX_SOFT_ENFORCEMENT_RETRIES
                ):
                    logger.warning(
                        "No tool call for DB-related prompt, applying soft enforcement retry %d/%d",
                        no_tool_retry_count + 1,
                        MAX_SOFT_ENFORCEMENT_RETRIES,
                    )
                    messages.append({"role": "assistant", "content": raw.get("content", [])})
                    messages.append(
                        {
                            "role": "user",
                            "content": "This question requires database access. You must call an appropriate tool.",
                        }
                    )
                    no_tool_retry_count += 1
                    continue

                if db_related_prompt and not has_called_tool:
                    return AskResponse(
                        answer="I could not complete this database request because no tool call was produced.",
                        model=settings.bedrock_model_id,
                        usage=raw.get("usage"),
                        tool_calls=collected_tool_calls or None,
                        conversation_id=conversation_id,
                    )

                answer = extract_text(raw)
                # If tools were called, set pending follow-up for confirmation tracking
                if has_called_tool and collected_tool_calls:
                    last_tc = collected_tool_calls[-1]
                    set_pending_followup(conversation_id, {
                        "type": "expand_previous_query",
                        "tool_name": last_tc["name"],
                        "tool_args": last_tc["input"],
                    })
                return AskResponse(
                    answer=answer,
                    model=settings.bedrock_model_id,
                    usage=raw.get("usage"),
                    tool_calls=collected_tool_calls or None,
                    conversation_id=conversation_id,
                )

            # Tool call(s) -> execute each one
            has_called_tool = True
            tool_calls = extract_tool_calls(raw)
            logger.info("Claude requested %d tool call(s)", len(tool_calls))

            # Append the full assistant content (text + tool_use blocks)
            messages.append({"role": "assistant", "content": raw["content"]})

            # Execute each tool and build tool_result blocks
            tool_results: list[dict[str, Any]] = []
            for tc in tool_calls:
                tool_name = tc["name"]
                raw_tool_input = tc["input"]
                tool_id = tc["id"]
                tool_input = _enforce_prompt_filters(tool_name, raw_tool_input, body.prompt)

                if tool_input != raw_tool_input:
                    logger.info(
                        "Adjusted tool input from prompt constraints: %s raw=%s adjusted=%s",
                        tool_name,
                        raw_tool_input,
                        tool_input,
                    )

                collected_tool_calls.append({"name": tool_name, "input": tool_input})

                executor = TOOL_EXECUTORS.get(tool_name)
                if executor is None:
                    result_content = json.dumps(
                        {"error": f"Unknown tool: {tool_name}"}
                    )
                else:
                    try:
                        result_data = executor(tool_input)
                        result_content = json.dumps(result_data, default=str)
                    except Exception as exc:
                        logger.exception("Tool %s failed", tool_name)
                        result_content = json.dumps(
                            {"error": f"Tool execution failed: {exc}"}
                        )

                # Store last successful tool call in memory
                if executor is not None:
                    set_last_tool(conversation_id, tool_name, tool_input)

                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_id,
                        "content": result_content,
                    }
                )

            messages.append({"role": "user", "content": tool_results})

        # Exhausted rounds - return whatever text we have
        answer = extract_text(raw)
        # Set pending follow-up if tools were called
        if has_called_tool and collected_tool_calls:
            last_tc = collected_tool_calls[-1]
            set_pending_followup(conversation_id, {
                "type": "expand_previous_query",
                "tool_name": last_tc["name"],
                "tool_args": last_tc["input"],
            })
        return AskResponse(
            answer=answer or "I was unable to complete the request within the allowed steps.",
            model=settings.bedrock_model_id,
            usage=raw.get("usage"),
            tool_calls=collected_tool_calls or None,
            conversation_id=conversation_id,
        )

    except Exception as exc:
        logger.exception("Bedrock / tool-call loop failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
