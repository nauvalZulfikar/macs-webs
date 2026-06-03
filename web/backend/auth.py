"""Cookie-based multi-user auth.

Users hardcoded below (informal use, Tailscale-bound — not facing public internet).
Cookie value = HMAC(SECRET, "v2:<username>") so we can identify which user.

Revocation: logout adds the cookie value to an in-memory revoked set so
replaying the captured cookie no longer authenticates. Set is bounded
(LRU-ish — newest 4096 entries) to cap memory. The revoke set is reset on
process restart, which is acceptable because the SECRET-derived cookies
would also be invalidated by a SECRET rotation (which is the documented
way to do a global logout).
"""
import hashlib
import hmac
import os
from collections import OrderedDict

from fastapi import Request
from fastapi.responses import JSONResponse

SECRET = os.environ.get("PW_TOKEN", "")
PW_SECURE = os.environ.get("PW_SECURE_COOKIES", "0") == "1"
COOKIE_NAME = "pw_session"

if not SECRET:
    raise RuntimeError("PW_TOKEN not set (used as HMAC secret for session cookie).")

USERS = {
    "shaka": "pisang",
    "tamu":  "kelapa",
}

PUBLIC_PATHS = {"/api/auth/login", "/api/auth/me", "/api/health"}

_REVOKED_MAX = 4096
_revoked: "OrderedDict[str, bool]" = OrderedDict()


def _cookie_for(username: str) -> str:
    return hmac.new(SECRET.encode(), f"v2:{username}".encode(), hashlib.sha256).hexdigest()


_VALID_COOKIES = {_cookie_for(u): u for u in USERS}


def current_user(request: Request):
    cookie = request.cookies.get(COOKIE_NAME)
    if not cookie:
        return None
    if cookie in _revoked:
        return None
    return _VALID_COOKIES.get(cookie)


def is_logged_in(request: Request) -> bool:
    return current_user(request) is not None


def issue_cookie(response: JSONResponse, username: str) -> None:
    val = _cookie_for(username)
    # Re-issuing for the same user clears any prior revocation on the same value.
    _revoked.pop(val, None)
    response.set_cookie(
        key=COOKIE_NAME,
        value=val,
        max_age=60 * 60 * 24 * 30,
        path="/",
        httponly=True,
        samesite="strict",
        secure=PW_SECURE,
    )


def clear_cookie(response: JSONResponse, cookie_value: str | None = None) -> None:
    response.delete_cookie(COOKIE_NAME, path="/")
    if cookie_value:
        _revoked[cookie_value] = True
        _revoked.move_to_end(cookie_value)
        while len(_revoked) > _REVOKED_MAX:
            _revoked.popitem(last=False)


def verify_credentials(username: str, password: str) -> bool:
    expected = USERS.get(username)
    if expected is None:
        return False
    return hmac.compare_digest(expected.encode(), password.encode())


async def auth_middleware(request: Request, call_next):
    path = request.url.path
    if path in PUBLIC_PATHS or not path.startswith("/api/"):
        return await call_next(request)
    if not is_logged_in(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    return await call_next(request)
