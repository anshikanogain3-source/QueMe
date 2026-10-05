from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth import Principal, require_principal
from ..config import Settings, get_settings

router = APIRouter(prefix="/recordings", tags=["recordings"])


class SignedRecordingUrl(BaseModel):
    url: str
    expires_in: int


@router.post("/{recording_id}/signed-url", response_model=SignedRecordingUrl)
async def create_recording_link(
    recording_id: UUID,
    principal: Principal = Depends(require_principal),
    settings: Settings = Depends(get_settings),
) -> SignedRecordingUrl:
    if not settings.supabase_service_role_key:
        raise HTTPException(status_code=503, detail="Private recording delivery is not configured.")
    base_url = settings.supabase_url.rstrip("/")
    user_headers = {"apikey": settings.supabase_anon_key, "Authorization": f"Bearer {principal.access_token}"}
    async with httpx.AsyncClient(timeout=8) as client:
        # This query runs as the caller, so the database RLS policy—not a URL
        # parameter—decides whether the asset may be read.
        asset_response = await client.get(
            f"{base_url}/rest/v1/recording_assets", headers=user_headers,
            params={"id": f"eq.{recording_id}", "select": "bucket,object_path", "limit": "1"},
        )
        assets = asset_response.json() if asset_response.status_code == 200 else []
        if len(assets) != 1:
            raise HTTPException(status_code=404, detail="Recording not found.")
        asset = assets[0]
        signed = await client.post(
            f"{base_url}/storage/v1/object/sign/{asset['bucket']}/{asset['object_path']}",
            headers={"apikey": settings.supabase_service_role_key, "Authorization": f"Bearer {settings.supabase_service_role_key}"},
            json={"expiresIn": 60},
        )
    if signed.status_code != 200 or not signed.json().get("signedURL"):
        raise HTTPException(status_code=503, detail="Could not issue a recording link.")
    return SignedRecordingUrl(url=f"{base_url}/storage/v1{signed.json()['signedURL']}", expires_in=60)
