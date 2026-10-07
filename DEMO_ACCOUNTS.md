# QueMe Demo Accounts

Demo-only credentials for logging in to the QueMe app (`/login`). All four
accounts share the same password.

| Role        | Email                  | Password  | Lands on      |
|-------------|------------------------|-----------|---------------|
| Student     | `student@queme.app`    | `Demo@1234` | `/student`    |
| Teacher     | `teacher@queme.app`    | `Demo@1234` | `/teacher`    |
| Coordinator | `coordinator@queme.app`| `Demo@1234` | `/coordinator`|
| Admin       | `admin@queme.app`      | `Demo@1234` | `/admin`      |

## Important

- These are **demo credentials only** — never reuse this password anywhere real.
- The accounts live in the Supabase project configured in the root `.env`
  (`VITE_SUPABASE_URL`). Each account is an Auth user plus an **active**
  `profiles` row with the role above (a pending profile is rejected at login
  with "Your account is awaiting administrator activation").

## Creating / refreshing the accounts

```bash
python supabase/seed_demo_accounts.py --db-url "<connection string>"
```

- The connection string comes from the Supabase Dashboard → Settings →
  Database → Connection string (URI). If the direct `db.*` host fails
  (IPv6-only), use the session pooler host instead. It can also be provided
  as `SUPABASE_DB_URL` in the shell or root `.env`.
- The script is idempotent: it applies `supabase/migrations/*.sql` only when
  the schema is missing, creates missing demo users, resets their passwords
  to the values above, activates their profiles, and then verifies a real
  password login for every account.
- Supabase URL/keys are read from the root `.env`.

## Troubleshooting

- **"Your account is awaiting administrator activation"** — the `profiles`
  row is still `pending`; re-run the seed script.
- **"Your account is not authorized to access QueMe"** — the schema is
  missing (`profiles` table not found); run the seed script so the
  migrations are applied.
