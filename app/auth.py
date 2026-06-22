"""Supabase Auth token verification for the FastAPI app.

We don't verify JWTs locally — we hand the user's access token to Supabase GoTrue
(/auth/v1/user) and trust its verdict. That works whether the project signs tokens
with the legacy shared secret or the newer asymmetric keys, and there's no JWT
secret to store. A short per-token cache keeps a burst of requests in one session
from re-hitting GoTrue every time.
"""

from __future__ import annotations

import time

import httpx
from fastapi import Header, HTTPException, status

from src.rmagent.config import SUPABASE_ANON_KEY, SUPABASE_URL

_CACHE_TTL = 60.0  # seconds; tokens live ~1h, this just dedups request bursts
_cache: dict[str, tuple[float, dict]] = {}


def _verify_remote(token: str) -> dict:
    """Ask GoTrue who this token belongs to. Returns the user dict, or raises 401."""
    resp = httpx.get(
        f"{SUPABASE_URL}/auth/v1/user",
        headers={"apikey": SUPABASE_ANON_KEY, "Authorization": f"Bearer {token}"},
        timeout=10,
    )
    if resp.status_code != 200:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    return resp.json()


def verify_token(token: str) -> dict:
    """Validate a Supabase access token, returning the user claims (cached briefly)."""
    now = time.monotonic()
    hit = _cache.get(token)
    if hit and hit[0] > now:
        return hit[1]
    user = _verify_remote(token)
    _cache[token] = (now + _CACHE_TTL, user)
    return user


def require_auth(authorization: str | None = Header(default=None)) -> dict:
    """FastAPI dependency: require 'Authorization: Bearer <supabase access token>'.

    Returns the Supabase user dict ('id' is the auth uid) for downstream use.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    return verify_token(authorization.split(" ", 1)[1].strip())


def user_thread_id(user: dict, thread_id: str) -> str:
    """Namespace a client thread id under the user's auth id so threads stay private."""
    return f"{user['id']}:{thread_id}"
