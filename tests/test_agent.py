"""Deep-agent wiring tests: graph introspection and config, no LLM calls.

Checks the fixed 5-tool surface, the HITL gate on get_as_of_otb, the isolated
segment subagent, on-demand skills, and configured memory.
"""

import json
import pathlib

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel

from agent.build_agent import (INTERRUPT_ON, SEGMENT_SUBAGENT, SKILL_SOURCES,
                               TOOLS, build_agent)

ROOT = pathlib.Path(__file__).resolve().parents[1]
EXPECTED_TOOLS = {
    "get_otb_summary", "get_segment_mix", "get_pickup_delta",
    "get_as_of_otb", "get_block_vs_transient_mix",
}


@pytest.fixture(scope="module")
def agent():
    """Build the agent with a fake model (no API key / no LLM call) for graph introspection."""
    return build_agent(model=GenericFakeChatModel(messages=iter([])))


def _node_names(agent):
    """Return the set of node names in the compiled agent graph."""
    return set(agent.get_graph().nodes)


# the tool surface is exactly five tools, no run_sql
def test_tool_surface_is_exactly_five():
    names = {t.__name__ for t in TOOLS}
    assert names == EXPECTED_TOOLS
    assert "run_sql" not in names
    assert not any("sql" in n for n in names)


# get_as_of_otb is human-gated (HITL)
def test_get_as_of_otb_is_hitl(agent):
    assert INTERRUPT_ON.get("get_as_of_otb") is True
    nodes = _node_names(agent)
    assert any("HumanInTheLoop" in n for n in nodes), "no HITL middleware in graph"


# segment work is isolated in its own subagent
def test_segment_work_isolated_in_subagent():
    sub_tools = {t.__name__ for t in SEGMENT_SUBAGENT["tools"]}
    assert sub_tools == {"get_segment_mix", "get_block_vs_transient_mix"}
    assert SEGMENT_SUBAGENT["name"] == "segment-analyst"


# skills are filesystem-backed and loaded on demand, not one big prompt
def test_skills_on_demand(agent):
    assert SKILL_SOURCES == ["skills"]
    assert any("Skills" in n for n in _node_names(agent)), "no SkillsMiddleware in graph"
    skill_files = list((ROOT / "skills").glob("**/SKILL.md"))
    assert len(skill_files) >= 6  # progressive disclosure, not one giant prompt


# memory is configured, so the agent is multi-turn, not stateless
def test_memory_configured(agent):
    assert agent.checkpointer is not None
    assert agent.store is not None


# multi-tool decomposition: planning middleware is wired into the graph
def test_planning_and_full_toolset(agent):
    nodes = _node_names(agent)
    assert any("TodoList" in n or "Planning" in n for n in nodes), "no planning middleware"
    assert len(TOOLS) >= 2  # composite questions can invoke multiple distinct tools


def test_multitool_decomposition_trace():
    # Uses a recorded trace from a real composite question ("what's driving August
    # 2026, and how have we booked in the last 7 days?") so this needs no live LLM
    # call. Assert the plan invoked at least 2 distinct required tools.
    trace = json.loads((ROOT / "tests/fixtures/multitool_trace.json").read_text())
    domain_tools = {e["name"] for e in trace if e["type"] == "tool"} & EXPECTED_TOOLS
    assert len(domain_tools) >= 2, f"expected >=2 distinct required tools, got {domain_tools}"


# the refusal/guardrail policy lives in a skill the agent can load
def test_guardrail_skill_encodes_refusal_policy():
    txt = (ROOT / "skills/data-guardrails/SKILL.md").read_text().lower()
    assert "cancelled" in txt and "provisional" in txt
    assert "do not comply" in txt or "state the policy" in txt


# System prompt forbids leaking internal machinery (skill/tool names) into answers
def test_system_prompt_forbids_naming_internals():
    from agent.build_agent import SYSTEM_PROMPT

    txt = SYSTEM_PROMPT.lower()
    assert "do not name your skills or tools" in txt
    assert "plain business terms" in txt


# Coverage grounding: non-contiguous months must collapse into separate ranges,
# never a single min->max span that hides the gap (regression for the
# "May 2026 within range" mis-explanation when data is two seasonal windows).
def test_coverage_ranges_preserve_gaps():
    from agent.build_agent import _collapse_month_ranges

    # Two windows with a Nov-2025..May-2026 gap (mirrors the real dataset).
    months = ["2025-06", "2025-07", "2025-08", "2025-09", "2025-10",
              "2026-06", "2026-07", "2026-08", "2026-09", "2026-10"]
    span = _collapse_month_ranges(months)
    assert span == "2025-06 to 2025-10, 2026-06 to 2026-10"
    # A gap month must not appear inside any stated range.
    assert "2026-05" not in span

    # Year boundary and a lone single month are handled.
    assert _collapse_month_ranges(["2025-11", "2025-12", "2026-01"]) == "2025-11 to 2026-01"
    assert _collapse_month_ranges(["2026-07"]) == "2026-07"
