"""FastAPI OIDC validation + RBAC."""
from __future__ import annotations

from typing import Any

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException
from jose import jwt


OIDC_ISSUER = "https://idp.example.com"
OIDC_AUDIENCE = "ml-platform"
ROLE_MAP = {
    "ml-platform-admin":  {"jobs:submit", "jobs:cancel", "models:promote"},
    "ml-engineer":        {"jobs:submit", "jobs:cancel"},
    "ml-viewer":          {"jobs:read", "models:read"},
}


_jwks_cache: dict[str, Any] = {}


def _jwks() -> dict:
    if not _jwks_cache:
        r = httpx.get(f"{OIDC_ISSUER}/.well-known/jwks.json")
        _jwks_cache.update(r.json())
    return _jwks_cache


def auth_user(authorization: str = Header(...)) -> dict:
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "missing bearer token")
    token = authorization.split(" ", 1)[1]
    try:
        claims = jwt.decode(token, _jwks(), audience=OIDC_AUDIENCE, issuer=OIDC_ISSUER)
    except jwt.JWTError as e:
        raise HTTPException(401, f"invalid token: {e}")
    return claims


def require_permission(permission: str):
    def dep(user: dict = Depends(auth_user)):
        groups = user.get("groups", [])
        allowed = set().union(*(ROLE_MAP.get(g, set()) for g in groups))
        if permission not in allowed:
            raise HTTPException(403, f"missing permission: {permission}")
        return user
    return dep


app = FastAPI()


@app.post("/v1/training-jobs")
def submit(user: dict = Depends(require_permission("jobs:submit"))):
    return {"submitted_by": user["sub"]}
