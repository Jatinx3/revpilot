"""Assemble the Revenue Manager deep agent (Phase 3).

A single create_deep_agent() call wired from the framework's building blocks:
  - model            : from MODEL_ID (default Gemini), swappable via env
  - tools            : the 5 typed RM tools (no raw SQL)
  - system_prompt    : sharp revenue-manager persona (answer style)
  - skills           : progressive-disclosure SKILL.md pack under skills/
  - subagents        : a focused segment/mix analyst (task-tool delegation)
  - interrupt_on     : HITL approval gate on the expensive get_as_of_otb rebuild
  - checkpointer+store: multi-turn GM conversation memory (not stateless)

Config is exposed as module constants so the structural agent tests can assert the
wiring without any LLM call.
"""

from __future__ import annotations

import os
import pathlib

from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend

from src.rmagent.config import MODEL_ID
from tools.rm_tools import (get_as_of_otb, get_block_vs_transient_mix,
                            get_otb_summary, get_pickup_delta, get_segment_mix)

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

# The fixed tool surface — exactly five tools, no run_sql.
TOOLS = [
    get_otb_summary,
    get_segment_mix,
    get_pickup_delta,
    get_as_of_otb,
    get_block_vs_transient_mix,
]

# Skill sources (directories scanned for SKILL.md), resolved by the filesystem backend.
SKILL_SOURCES = ["skills"]

# HITL: pause for human approval before the expensive point-in-time rebuild.
INTERRUPT_ON = {"get_as_of_otb": True}

# Required subagent: isolate segment / block-mix work behind the task tool.
SEGMENT_SUBAGENT = {
    "name": "segment-analyst",
    "description": (
        "Specialist for segment/market mix, OTA dependency, and block vs transient "
        "concentration. Delegate mix-composition questions here so the main agent's "
        "context stays focused."
    ),
    "system_prompt": (
        "You are a segment and mix analyst for a hotel revenue manager. Use "
        "get_segment_mix and get_block_vs_transient_mix to break a stay month down "
        "by segment, macro group, and group-vs-transient. Report shares of revenue "
        "and room nights, flag concentration, and recommend an action. Always report the "
        "month's total revenue exactly as get_segment_mix returns it (the denominator "
        "total); never invent or estimate any number. Never write SQL."
    ),
    "tools": [get_segment_mix, get_block_vs_transient_mix],
}

SYSTEM_PROMPT = (
    "You are the Revenue Manager for the Grand Harbour Hotel, briefing the General "
    "Manager. Answer in plain English like a sharp revenue manager in a morning "
    "briefing: lead with the headline number, explain the drivers, flag the key risk "
    "or opportunity, and end with a concrete recommended action. Always state your "
    "assumptions — default on-the-books is Posted, non-cancelled business.\n\n"
    "Stay in character as the revenue manager: never expose internal machinery in "
    "your answers. Do not name your skills or tools (e.g. 'the cancellation-watch "
    "skill', 'get_otb_summary'), and do not say things like 'my skill doesn't allow "
    "me to'. When you cannot answer, explain the limitation in plain business terms "
    "— e.g. 'I track cancellations at the month level, not individual bookings' — "
    "and offer the closest thing you can do.\n\n"
    "Report all monetary figures in GBP (£). Every figure you report, especially the "
    "headline total, must come directly from a tool result: never invent, estimate, or "
    "use a placeholder or example number, and never label a value as 'example' or 'not "
    "actual'. If a tool did not return a figure, drop that metric rather than guessing. "
    "Compose every answer from your tools and skills; never invent SQL. For any "
    "judgment question — OTA dependency, booking pace or pickup ('what changed', "
    "'how's pace'), group/block concentration, ADR/pricing, or cancellations — you "
    "MUST read the matching skill in your skills library with read_file (limit=1000) "
    "BEFORE answering, then apply its method, thresholds and recommended actions. A "
    "tool returning the raw numbers does NOT exempt you: the skill defines how to "
    "interpret them (e.g. pace compares the most recent week against the week before "
    "it, not a single window). For multi-part questions, plan the steps "
    "before calling tools, and delegate segment/mix work to the segment-analyst "
    "subagent. Mind the grain: rows are stay-nights, reservations are distinct "
    "bookings, room nights sum number_of_spaces.\n\n"
    "Format every briefing EXACTLY in this structure (Markdown):\n"
    "## <Short title> · <Month if relevant>\n"
    "- <Metric label>: <short value>\n"
    "- <Metric label>: <short value>\n"
    "(2 to 4 key metrics; values short, e.g. £13,735, 57, 29% of revenue)\n\n"
    "<one or two short paragraphs on the drivers and the key risk or opportunity>\n\n"
    "**Recommendation:** <one or two sentence concrete action>\n\n"
    "If the question is a clarification or has no metrics, reply in one or two plain "
    "sentences instead (no heading)."
)


def _collapse_month_ranges(months: list[str]) -> str:
    """Collapse sorted 'YYYY-MM' months into a human range string.

    Coverage is not contiguous (seasonal windows with gaps), so a bare min->max
    span would hide the gaps and let the model accept or mis-explain empty months
    (e.g. claiming 2026-05 is "within range" when no data exists). Adjacent months
    fold into "lo to hi"; a lone month stays bare; gaps split into a new range.
    """

    def _next(m: str) -> str:
        y, mm = int(m[:4]), int(m[5:7])
        return f"{y + (mm == 12):04d}-{(mm % 12) + 1:02d}"

    ranges = []
    start = prev = months[0]
    for m in months[1:]:
        if m == _next(prev):
            prev = m
            continue
        ranges.append((start, prev))
        start = prev = m
    ranges.append((start, prev))
    return ", ".join(a if a == b else f"{a} to {b}" for a, b in ranges)


def _runtime_context() -> str:
    """Ground the agent in today's date and the dataset's real coverage window.

    Coverage is seasonal and regenerates daily (currently two non-adjacent
    windows), so the covered months are read from the DB at build time and
    collapsed into ranges rather than hardcoded or reduced to a single min->max
    span. Without this the model invents example months or mis-explains the gaps.
    Returns an empty string if the DB is unavailable so the agent still builds.
    """
    from datetime import date

    try:
        from src.rmagent.db import query

        rows = query(
            "select distinct to_char(stay_date,'YYYY-MM') as m "
            "from reservations_hackathon where stay_date is not null order by m"
        )
        months = [r["m"] for r in rows if r["m"]]
    except Exception:
        return ""
    if not months:
        return ""

    span = _collapse_month_ranges(months)
    today = date.today().isoformat()
    return (
        f"\n\nContext: today is {today}. The dataset covers ONLY these stay-month "
        f"ranges (coverage is not continuous): {span}. Every month inside a listed "
        f"range is valid, whether past or future; months outside every listed range "
        f"have no data at all. Accept any in-range month and call the tool. Only refuse "
        f"a month that falls outside all listed ranges, and when you refuse, state the "
        f"actual available ranges ({span}) so the user can pick a valid month. If the "
        f"user gives no month, ask for one and suggest a valid in-range example."
    )


def _resolve_model(model_id: str):
    """Map a MODEL_ID string to a model usable by create_deep_agent.

    `openrouter:<model>` uses the OpenAI-compatible OpenRouter gateway. Any other
    provider-prefixed id (e.g. `google_genai:...`, `openai:...`) passes through to the
    framework's init_chat_model to resolve.
    """
    if model_id.startswith("openrouter:"):
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=model_id.split(":", 1)[1],
            base_url="https://openrouter.ai/api/v1",
            api_key=os.environ.get("OPENROUTER_API_KEY", ""),
            temperature=0,
        )
    return model_id


def build_agent(model=None, checkpointer=None, store=None):
    """Build and return the compiled deep agent.

    `model` may be a provider id string or a BaseChatModel (tests pass a fake model
    to avoid API calls). Defaults to MODEL_ID from the environment.
    """
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.store.memory import InMemoryStore

    return create_deep_agent(
        model=model if model is not None else _resolve_model(MODEL_ID),
        tools=TOOLS,
        system_prompt=SYSTEM_PROMPT + _runtime_context(),
        skills=SKILL_SOURCES,
        subagents=[SEGMENT_SUBAGENT],
        interrupt_on=INTERRUPT_ON,
        backend=FilesystemBackend(root_dir=str(REPO_ROOT), virtual_mode=False),
        checkpointer=checkpointer if checkpointer is not None else InMemorySaver(),
        store=store if store is not None else InMemoryStore(),
    )
