"""Supabase token validation and trusted-server helpers."""
from dataclasses import dataclass

import httpx
from fastapi import Depends, Header, HTTPException

from .config import Settings, get_settings


@dataclass(frozen=True)
class Principal:
    user_id: str
    email: str
    access_token: str
    role: str


async def require_principal(
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> Principal:
    if not settings.supabase_url or not settings.supabase_anon_key:
        raise HTTPException(status_code=503, detail="Supabase authentication is not configured.")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="A bearer token is required.")
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=401, detail="A bearer token is required.")
    headers = {"apikey": settings.supabase_anon_key, "Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(timeout=5) as client:
        response = await client.get(f"{settings.supabase_url.rstrip('/')}/auth/v1/user", headers=headers)
        if response.status_code != 200:
            raise HTTPException(status_code=401, detail="The session is expired or invalid.")
        user = response.json()
        profile = await client.get(
            f"{settings.supabase_url.rstrip('/')}/rest/v1/profiles",
            headers={**headers, "Accept": "application/json"},
            params={"id": f"eq.{user['id']}", "select": "role,status"},
        )
    if profile.status_code != 200 or len(profile.json()) != 1:
        raise HTTPException(status_code=403, detail="No authorized profile exists for this account.")
    profile_data = profile.json()[0]
    if profile_data["status"] != "active":
        raise HTTPException(status_code=403, detail="This account is not active.")
    return Principal(user_id=user["id"], email=user.get("email", ""), access_token=token, role=profile_data["role"])


def require_admin(principal: Principal = Depends(require_principal)) -> Principal:
    if principal.role != "admin":
        raise HTTPException(status_code=403, detail="Administrator access is required.")
    return principal
