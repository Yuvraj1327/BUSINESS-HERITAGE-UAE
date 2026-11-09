# SUPABASE_SETUP

One-time configuration of a Supabase project for the ALSAFA ERP login. Do it twice: a **separate dev project** for development/testing, and the **production project**. Dashboard labels change over time; names below match Supabase's current docs, so search the dashboard if something has moved.

> **Not yet verified against a live project.** Step 4 was built and tested without Supabase credentials (see `AUTH_TEST_RESULTS.md`). Work through the checklist at the end the first time you connect a real project.

## 1. Create the project(s)
Create `alsafa-dev` and `alsafa-prod`. Never point a dev machine at production. Choose the region closest to the UAE that your plan offers. Apply the Step 2 migrations (`database/migrations/0001…0009`, see `docs/database/MIGRATION_GUIDE.md`) to each.

## 2. API keys → which one goes where
Dashboard → *Project Settings → API Keys* (also shows the Project URL).
| Key | Goes to | Notes |
|---|---|---|
| Project URL `https://<ref>.supabase.co` | `VITE_SUPABASE_URL` (frontend) and `SUPABASE_URL` (backend) | public |
| **Publishable** key `sb_publishable_…` (or the legacy `anon` key) | `VITE_SUPABASE_ANON_KEY` (frontend) | public by design; data is protected by RLS and the API |
| **Secret** key `sb_secret_…` (or legacy `service_role`) | **nowhere in the app.** Only your own shell when running `scripts/provision_account.py` | bypasses RLS. Never in `VITE_*`, Git, chat, CI logs, Vercel/Render env of the running app |

If a secret key was ever pasted somewhere it should not be, create a new one and delete the old one (Supabase rotates keys by adding a new key, then removing the old).

## 3. JWT signing keys (required: asymmetric)
The backend verifies tokens through the public JWKS (`JWT_SECURITY.md`). Dashboard → *Project Settings → JWT Keys (JWT Signing Keys)*:
1. If you see an asymmetric key (ECC P-256 / `ES256`, or RSA / `RS256`) marked **current**, you are done. Supabase has been migrating existing projects to this system; new projects start with it.
2. If the project still uses the legacy shared secret: click **Migrate JWT secret**, then **rotate to a new asymmetric key** and let old tokens age out (Supabase's migration guide has the safe, zero-downtime order). Do not copy the legacy secret into the backend.
3. Check it works (no auth needed):
   ```bash
   curl -s https://<ref>.supabase.co/auth/v1/.well-known/jwks.json
   ```
   The response must contain at least one key with a `kid`. An empty `keys` list means the project is still on the legacy secret.
4. Keep the **access token expiry at 1 hour or less** (default 3600 s).

## 4. Authentication → email sign-in, no public sign-ups
*Authentication → Sign In / Providers*:
- **Email** provider: enabled. Other providers (Google, phone, anonymous…): off.
- **Allow new users to sign up: OFF.** This is what makes public registration impossible even if someone calls the Auth API directly (the app also has no sign-up page). Admin-created and invited users still work.
- *Confirm email*: leave on. Users created by the provisioning script or the dashboard "Auto Confirm" are already confirmed.
- **Password policy**: minimum length **10**; require letters and digits (matches the form in the app); turn on *leaked password protection* if your plan includes it.

## 5. URL configuration and reset redirect URLs
*Authentication → URL Configuration*:
- **Site URL**: the production app URL, e.g. `https://erp.yourdomain.com` (dev project: `http://localhost:5173`).
- **Redirect URLs** (allow-list; `redirectTo` must match exactly or Supabase falls back to the Site URL):
  - production project: `https://erp.yourdomain.com/reset-password`
  - dev project: `http://localhost:5173/reset-password` (add a preview-URL pattern only if you use Vercel previews, and only in the dev project)
- The app sends `redirectTo = <current origin>/reset-password`. Open reset links **in the same browser** that requested them (PKCE).

## 6. Email delivery
*Authentication → Emails*:
- Supabase's built-in sender is for trials: it only delivers to your project team's addresses and is tightly rate-limited. **Configure custom SMTP** (any provider: Resend, SendGrid, Mailgun, your mail host) so reset and invitation emails reach staff. Use a sender on your own domain; disable link tracking in the provider, which can corrupt the reset link.
- Templates: keep the default *Reset Password* template (it uses `{{ .ConfirmationURL }}`, which works with the app's PKCE flow). Change wording/branding freely, not the link variable. Use *Invite user* for the first Owner if you like.
- *Rate limits*: after enabling SMTP, review the email-sent and sign-in rate limits (defaults are conservative; the app already reports "too many attempts").

## 7. Sessions
*Authentication → Sessions*: leave refresh-token rotation on (default). Optional (plan-dependent): inactivity timeout or time-boxed sessions if the owner wants forced re-login. The app handles both: refresh failure → "Your session has ended."

## 8. Database role for the API
The API must not connect as `postgres` or `service_role`.
```sql
-- run once as postgres in the SQL editor; choose your own long random password and keep it only in the host secret store
alter role app_api login password '<generate-a-long-random-password>';
```
`app_api` already exists (migration 0001): NOINHERIT, NOBYPASSRLS, member of `authenticated`. Build `DATABASE_URL` from the *Connect* dialog's pooler string, replacing the user with `app_api.<project-ref>` and using that password. Transaction-mode pooling (port 6543) is supported (prepared statements are disabled in the engine); the per-request `SET LOCAL ROLE` happens inside a transaction so it is pooler-safe. *(Pooler login with a custom role is the one piece not yet exercised against real Supabase.)*

## 9. Environment variables
| Where | Variable | Value |
|---|---|---|
| `frontend/.env.local` / Vercel | `VITE_API_BASE_URL` | `https://<api-host>/api/v1` |
| | `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY` | from step 2 (public values only) |
| `backend/.env` / Render | `APP_ENV` | `production` |
| | `SUPABASE_URL` | `https://<ref>.supabase.co` (issuer and JWKS derive from it) |
| | `DATABASE_URL` | `app_api` pooler URL from step 8 |
| | `CORS_ORIGINS` | `https://erp.yourdomain.com` |
Full table: `docs/ENVIRONMENT_SETUP.md`. In `production` the backend refuses to start without these, or with non-https Supabase URLs.

## 10. First-connection checklist (do once per project; tick as you go)
1. `curl …/jwks.json` returns a key (step 3).
2. Create the first Owner (`OWNER_ACCOUNT_SETUP.md`, path A).
3. Start backend + frontend; `GET /api/v1/health/ready` → `ready`.
4. Sign in → home page shows your name and `OWNER`; browser dev tools → Network: `/auth/profile` returns 200.
5. Reload the page and open a second tab: still signed in, no login flash.
6. Sign out; reload: login page.
7. *Forgot password* with your own address → email arrives → link opens `/reset-password` in the same browser → set a new password → sign in with it.
8. Try the reset link a second time → "Reset link not valid".
9. Call `POST https://<ref>.supabase.co/auth/v1/signup` with a made-up email and the publishable key → must be rejected ("signups not allowed").
10. Create a test Branch user, deactivate it with the script, confirm "Account inactive".
Record the results in `AUTH_TEST_RESULTS.md` (section "Real Supabase checks").
