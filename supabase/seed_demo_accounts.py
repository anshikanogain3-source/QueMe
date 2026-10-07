#!/usr/bin/env python
"""Create or refresh the QueMe demo accounts and verify they can log in.

Usage:
    python supabase/seed_demo_accounts.py --db-url "postgresql://postgres:...@db.<project>.supabase.co:5432/postgres"

The database URL can also be passed via the SUPABASE_DB_URL environment
variable. Supabase URL/keys are read from the root .env file.

What it does (idempotent):
  1. Applies supabase/migrations/*.sql if the schema is missing.
  2. Creates each demo account in Supabase Auth (or resets its password to
     the documented demo password).
  3. Activates the profile row with the demo role/status via the same
     trusted-role-change mechanism the admin workflow uses.
  4. Verifies a real password login and profile read for every account.

The demo credentials themselves are documented in DEMO_ACCOUNTS.md.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

import asyncpg
import httpx
from dotenv import dotenv_values

REPO_ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS_DIR = REPO_ROOT / "supabase" / "migrations"

# Must stay in sync with DEMO_ACCOUNTS.md.
DEMO_ACCOUNTS = (
    ("student", "student@queme.app", "Demo@1234", "Demo Student"),
    ("teacher", "teacher@queme.app", "Demo@1234", "Demo Teacher"),
    ("coordinator", "coordinator@queme.app", "Demo@1234", "Demo Coordinator"),
    ("admin", "admin@queme.app", "Demo@1234", "Demo Administrator"),
)


def load_config() -> tuple[str, str, str]:
    values = dotenv_values(REPO_ROOT / ".env")
    url = values.get("SUPABASE_URL") or values.get("QUEME_SUPABASE_URL")
    publishable = values.get("SUPABASE_PUBLISHABLE_KEY") or values.get("QUEME_SUPABASE_ANON_KEY")
    secret = values.get("SUPABASE_SECRET_KEY") or values.get("QUEME_SUPABASE_SERVICE_ROLE_KEY")
    missing = [name for name, val in (("SUPABASE_URL", url), ("SUPABASE_PUBLISHABLE_KEY", publishable), ("SUPABASE_SECRET_KEY", secret)) if not val]
    if missing:
        raise SystemExit(f"Missing in root .env: {', '.join(missing)}")
    return url.rstrip("/"), publishable, secret  # type: ignore[return-value]


async def ensure_schema(conn: asyncpg.Connection) -> None:
    applied = await conn.fetchval("select to_regclass('public.profiles') is not null")
    if applied:
        print("Schema already present (profiles exists); skipping migrations.")
        return
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        print(f"Applying migration {path.name} ...")
        await conn.execute(path.read_text())
    print("Migrations applied.")
async def find_or_create_user(client: httpx.AsyncClient, secret: str, url: str, email: str, password: str, full_name: str) -> str:
    headers = {"apikey": secret, "Authorization": f"Bearer {secret}"}
    user_id = None
    page = 1
    while True:
        response = await client.get(f"{url}/auth/v1/admin/users", params={"page": page, "per_page": 200}, headers=headers)
        response.raise_for_status()
        users = response.json().get("users", [])
        user_id = next((u["id"] for u in users if (u.get("email") or "").lower() == email.lower()), None)
        if user_id or len(users) < 200:
            break
        page += 1
    body = {"email": email, "password": password, "email_confirm": True, "user_metadata": {"full_name": full_name}}
    if user_id:
        response = await client.put(f"{url}/auth/v1/admin/users/{user_id}", headers=headers, json=body)
        response.raise_for_status()
        print(f"Reset password for existing user {email}")
    else:
        response = await client.post(f"{url}/auth/v1/admin/users", headers=headers, json=body)
        if response.status_code not in (200, 201):
            raise SystemExit(f"Could not create {email}: {response.status_code} {response.text}")
        user_id = response.json()["id"]
        print(f"Created auth user {email}")
    return user_id


async def activate_profile(conn: asyncpg.Connection, user_id: str, email: str, role: str, full_name: str) -> None:
    async with conn.transaction():
        await conn.execute("select set_config('app.trusted_role_change', 'on', true)")
        await conn.execute(
            """
            insert into public.profiles (id, email, full_name, role, status, activated_at)
            values ($1::uuid, $2, $3, $4::public.app_role, 'active', now())
            on conflict (id) do update
              set email = excluded.email,
                  full_name = excluded.full_name,
                  role = excluded.role,
                  status = 'active',
                  activated_at = coalesce(public.profiles.activated_at, now())
            """,
            user_id, email, full_name, role,
        )
    print(f"Profile {email} -> {role}/active")


async def verify_login(client: httpx.AsyncClient, url: str, publishable: str, email: str, password: str, role: str) -> None:
    response = await client.post(
        f"{url}/auth/v1/token?grant_type=password",
        headers={"apikey": publishable},
        json={"email": email, "password": password},
    )
    if response.status_code != 200:
        raise SystemExit(f"LOGIN FAILED for {email}: {response.status_code} {response.text}")
    payload = response.json()
    access_token = payload["access_token"]
    profile = await client.get(
        f"{url}/rest/v1/profiles",
        params={"id": f"eq.{payload['user']['id']}", "select": "role,status"},
        headers={"apikey": publishable, "Authorization": f"Bearer {access_token}"},
    )
    rows = profile.json()
    if profile.status_code != 200 or not rows or rows[0]["role"] != role or rows[0]["status"] != "active":
        raise SystemExit(f"PROFILE CHECK FAILED for {email}: {profile.status_code} {rows}")
    print(f"Verified login OK: {email} -> {role}/active")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Seed and verify the QueMe demo accounts.")
    parser.add_argument("--db-url", default=os.environ.get("SUPABASE_DB_URL"), help="Supabase Postgres connection string (or set SUPABASE_DB_URL)")
    args = parser.parse_args()
    if not args.db_url:
        raise SystemExit("Provide the database connection string via --db-url or SUPABASE_DB_URL (Supabase Dashboard -> Settings -> Database).")

    supabase_url, publishable, secret = load_config()
    conn = await asyncpg.connect(args.db_url)
    try:
        await ensure_schema(conn)
        async with httpx.AsyncClient(timeout=30) as client:
            for role, email, password, full_name in DEMO_ACCOUNTS:
                user_id = await find_or_create_user(client, secret, supabase_url, email, password, full_name)
                await activate_profile(conn, user_id, email, role, full_name)
                await verify_login(client, supabase_url, publishable, email, password, role)
    finally:
        await conn.close()
    print(f"\nAll {len(DEMO_ACCOUNTS)} demo accounts are ready. See DEMO_ACCOUNTS.md for the credentials.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(130)

