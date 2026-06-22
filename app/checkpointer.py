"""Durable multi-turn memory: a Supabase-backed LangGraph checkpointer.

Falls back to an in-memory saver if Postgres is unavailable, so the app always
boots. The checkpointer persists conversation + HITL state across restarts and is
thread-safe via a connection pool.
"""

from __future__ import annotations


def make_checkpointer():
    """Return (checkpointer, pool). pool is None when falling back to in-memory."""
    try:
        from psycopg_pool import ConnectionPool
        from langgraph.checkpoint.postgres import PostgresSaver

        from src.rmagent.config import DATABASE_URL

        # prepare_threshold=0 disables prepared statements — Supabase's pooler runs in
        # transaction mode, which breaks them. autocommit is what PostgresSaver expects.
        pool = ConnectionPool(
            DATABASE_URL,
            min_size=1,
            max_size=4,
            open=True,
            kwargs={"autocommit": True, "prepare_threshold": 0},
        )
        saver = PostgresSaver(pool)
        saver.setup()
        print("checkpointer: using Supabase PostgresSaver (durable multi-turn) ✓")
        return saver, pool
    except Exception as exc:  # never block startup on memory durability
        from langgraph.checkpoint.memory import InMemorySaver

        print(f"checkpointer: Postgres unavailable ({exc}); using in-memory saver")
        return InMemorySaver(), None
