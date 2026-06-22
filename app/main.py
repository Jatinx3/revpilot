"""FastAPI server for the Revenue Manager agent.

- GET  /         : chat UI SPA (public; signs in via Supabase Auth)
- GET  /health   : live DB fingerprint (public; reviewers compare to LOAD_PROOF)
- GET  /config   : public Supabase client settings for the SPA
- GET  /history  : prior turns for a thread (Supabase bearer token required)
- POST /chat     : SSE stream of the agent run (Supabase bearer token required);
                   surfaces every tool/skill; pauses with an approval event for
                   get_as_of_otb. A `decision` field folds in HITL resume.
"""

from __future__ import annotations

import json
import pathlib
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.responses import FileResponse, StreamingResponse
from langgraph.types import Command
from pydantic import BaseModel

from agent.build_agent import build_agent
from app.auth import require_auth, user_thread_id
from app.checkpointer import make_checkpointer
from app.health import health_fingerprint
from src.rmagent.config import SUPABASE_ANON_KEY, SUPABASE_URL

STATIC = pathlib.Path(__file__).parent / "static"
_state: dict = {}

# Deep Agents filesystem/planning tools we don't surface in the activity panel
# (skills are surfaced via the SKILL.md read; domain tools + subagent task remain).
INTERNAL_TOOLS = {
    "write_todos", "read_file", "ls", "glob", "grep", "write_file", "edit_file",
}


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Build the agent once at startup with a durable checkpointer; close its pool on shutdown."""
    saver, pool = make_checkpointer()
    _state["agent"] = build_agent(checkpointer=saver)
    try:
        yield
    finally:
        if pool is not None:
            pool.close()


app = FastAPI(title="Grand Harbour Revenue Manager", lifespan=lifespan)


def agent():
    """Return the singleton deep agent built at startup."""
    return _state["agent"]


@app.get("/health")
def health():
    """Public health endpoint: live DB fingerprint for reconciliation with LOAD_PROOF."""
    return health_fingerprint()


@app.get("/config")
def config():
    """Public client config so the static SPA can init Supabase (anon key is public)."""
    return {"supabase_url": SUPABASE_URL, "supabase_anon_key": SUPABASE_ANON_KEY}


@app.get("/")
def index():
    """Serve the SPA publicly; it shows its own auth screen and signs in via Supabase."""
    return FileResponse(STATIC / "index.html")


@app.get("/history")
def history(thread_id: str, user: dict = Depends(require_auth)):
    """Return the visible conversation (user prompts + final answers) for a thread,
    reconstructed from the durable checkpointer so it survives reloads/restarts."""
    tid = user_thread_id(user, thread_id)
    state = agent().get_state({"configurable": {"thread_id": tid}})
    messages = (state.values or {}).get("messages", []) if state else []
    out = []
    for m in messages:
        cls = m.__class__.__name__
        if cls == "HumanMessage":
            out.append({"role": "user", "content": _text(m.content)})
        elif cls == "AIMessage" and not getattr(m, "tool_calls", None):
            text = _text(m.content)
            if text.strip():
                out.append({"role": "assistant", "content": text})
    return {"messages": out}


class ChatRequest(BaseModel):
    thread_id: str
    message: str | None = None
    decision: str | None = None  # approve | reject (HITL resume)


def _sse(payload: dict) -> str:
    """Encode a payload as one Server-Sent Events frame."""
    return f"data: {json.dumps(payload)}\n\n"


def _text(content) -> str:
    """Flatten a message content (str, or list of content blocks) to plain text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
            elif isinstance(block, str):
                parts.append(block)
        return "".join(parts)
    return str(content)


def _skill_name(path: str) -> str:
    """Derive a skill's name from its SKILL.md path (the parent directory name)."""
    p = pathlib.Path(path)
    return p.parent.name if p.name == "SKILL.md" else p.stem


def _plan_steps(todos) -> list[str]:
    """Extract plain-text step titles from a write_todos `todos` argument.

    Surfaces the agent's plan (the planning building block) — structured steps, not
    raw chain-of-thought. Defensive about item shape (dicts or strings).
    """
    if not isinstance(todos, list):
        return []
    steps: list[str] = []
    for t in todos:
        text = (t.get("content") or t.get("title") or "") if isinstance(t, dict) else str(t)
        text = text.strip()
        if text:
            steps.append(text)
    return steps


def _stream(req: ChatRequest):
    """Stream the agent run as SSE: emit skill loads, tool calls, HITL approvals,
    and the final answer; resumes a paused run when req.decision is set."""
    cfg = {"configurable": {"thread_id": req.thread_id}}
    if req.decision:
        graph_input = Command(resume={"decisions": [{"type": req.decision}]})
    else:
        graph_input = {"messages": [{"role": "user", "content": req.message or ""}]}

    emitted_skills: set[str] = set()  # a skill is "used" once — don't repeat re-reads
    plan_emitted = False  # surface the agent's plan once (initial decomposition)
    try:
        for chunk in agent().stream(graph_input, cfg, stream_mode="updates"):
            if "__interrupt__" in chunk:
                interrupt = chunk["__interrupt__"][0].value
                reqs = interrupt.get("action_requests", []) if isinstance(interrupt, dict) else []
                # get_as_of_otb is the only HITL-gated tool, so it's the safe default
                # if the interrupt payload ever comes through without action_requests.
                ar = reqs[0] if reqs else {"name": "get_as_of_otb", "args": {}}
                yield _sse({"type": "approval", "tool": ar.get("name"), "args": ar.get("args", {})})
                return
            for _node, update in chunk.items():
                messages = update.get("messages", []) if isinstance(update, dict) else []
                for m in messages:
                    cls = m.__class__.__name__
                    if cls == "AIMessage":
                        for tc in getattr(m, "tool_calls", []) or []:
                            args = tc.get("args", {})
                            if tc["name"] == "read_file" and "SKILL.md" in str(args.get("file_path", "")):
                                name = _skill_name(args["file_path"])
                                if name not in emitted_skills:
                                    emitted_skills.add(name)
                                    yield _sse({"type": "skill", "name": name})
                            elif tc["name"] == "write_todos":
                                steps = _plan_steps(args.get("todos"))
                                if steps and not plan_emitted:
                                    plan_emitted = True
                                    yield _sse({"type": "plan", "steps": steps})
                            elif tc["name"] not in INTERNAL_TOOLS:
                                yield _sse({"type": "tool", "name": tc["name"], "args": args})
                        text = _text(m.content)
                        if text and not (getattr(m, "tool_calls", None)):
                            yield _sse({"type": "answer", "text": text})
                    elif cls == "ToolMessage" and m.name not in INTERNAL_TOOLS:
                        yield _sse({"type": "tool_result", "name": m.name, "preview": str(m.content)[:240]})
        # Fallback: if the graph paused at a human-in-the-loop interrupt, surface it.
        state = agent().get_state(cfg)
        if state.next:
            for task in state.tasks:
                for it in (getattr(task, "interrupts", None) or []):
                    val = it.value if hasattr(it, "value") else it
                    reqs = val.get("action_requests", []) if isinstance(val, dict) else []
                    ar = reqs[0] if reqs else {"name": "get_as_of_otb", "args": {}}
                    yield _sse({"type": "approval", "tool": ar.get("name"), "args": ar.get("args", {})})
                    return
        yield _sse({"type": "done"})
    except Exception as exc:  # surface errors to the UI rather than hanging
        yield _sse({"type": "error", "message": f"{type(exc).__name__}: {exc}"})


@app.post("/chat")
def chat(req: ChatRequest, user: dict = Depends(require_auth)):
    """Authenticated chat endpoint returning the agent run as an SSE stream."""
    # namespace the client's thread under this user so threads can't be read across users
    req.thread_id = user_thread_id(user, req.thread_id)
    return StreamingResponse(_stream(req), media_type="text/event-stream")
