"""Server-only account provisioning. The browser never sees the service key."""
import hmac

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException

from ..auth import Principal, require_admin
from ..config import Settings, get_settings
from ..database import connect_database
from ..schemas import CreateManagedUser, ManagedUser

router = APIRouter(prefix="/admin", tags=["administration"])


async def _create_auth_user(request: CreateManagedUser, settings: Settings) -> dict:
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise HTTPException(status_code=503, detail="Supabase administrator provisioning is not configured.")
    async with httpx.AsyncClient(timeout=10) as client:
        result = await client.post(
            f"{settings.supabase_url.rstrip('/')}/auth/v1/admin/users",
            headers={"apikey": settings.supabase_service_role_key, "Authorization": f"Bearer {settings.supabase_service_role_key}"},
            json={"email": request.email, "email_confirm": True, "user_metadata": {"full_name": request.full_name}},
        )
    if result.status_code not in (200, 201):
        raise HTTPException(status_code=409 if result.status_code == 422 else 503, detail="The account could not be provisioned.")
    return result.json()


async def _delete_auth_user(user_id: str, settings: Settings) -> None:
    """Best-effort compensation if profile provisioning fails after Auth creation."""
    async with httpx.AsyncClient(timeout=5) as client:
        await client.delete(
            f"{settings.supabase_url.rstrip('/')}/auth/v1/admin/users/{user_id}",
            headers={"apikey": settings.supabase_service_role_key, "Authorization": f"Bearer {settings.supabase_service_role_key}"},
        )


@router.post("/users", response_model=ManagedUser, status_code=201)
async def create_managed_user(request: CreateManagedUser, admin: Principal = Depends(require_admin), settings: Settings = Depends(get_settings)) -> ManagedUser:
    user = await _create_auth_user(request, settings)
    connection = await connect_database(settings)
    try:
        await connection.execute("set role service_role")
        await connection.execute("select app.set_profile_role($1::uuid, $2::public.app_role)", user["id"], request.role)
    except Exception:
        await _delete_auth_user(user["id"], settings)
        raise
    finally:
        await connection.close()
    return ManagedUser(id=user["id"], email=request.email, role=request.role)


@router.post("/bootstrap", response_model=ManagedUser, status_code=201)
async def bootstrap_first_admin(request: CreateManagedUser, x_bootstrap_secret: str | None = Header(default=None), settings: Settings = Depends(get_settings)) -> ManagedUser:
    if request.role != "admin" or not settings.bootstrap_secret or not x_bootstrap_secret or not hmac.compare_digest(x_bootstrap_secret, settings.bootstrap_secret):
        raise HTTPException(status_code=403, detail="First-admin bootstrap is not authorized.")
    user = await _create_auth_user(request, settings)
    connection = await connect_database(settings)
    try:
        async with connection.transaction():
            await connection.execute("set local role service_role")
            await connection.execute("select set_config('app.bootstrap_secret', $1, true)", settings.bootstrap_secret)
            await connection.execute("select app.bootstrap_first_admin($1::uuid, $2, $3, $4)", user["id"], request.email, request.full_name, settings.bootstrap_secret)
    except Exception:
        await _delete_auth_user(user["id"], settings)
        raise
    finally:
        await connection.close()
    return ManagedUser(id=user["id"], email=request.email, role="admin")
