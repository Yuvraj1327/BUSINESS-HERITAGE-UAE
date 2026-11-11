# OWNER_ACCOUNT_SETUP

There is no registration page and no way to become an Owner by signing up. Accounts exist because an operator created them. Nothing here uses invented emails or stored passwords: you use **your own real email**.

Do this once per environment (dev project, production project) after `SUPABASE_SETUP.md` and after the Step 2 migrations (0001–0009) are applied.

## A. First Owner – manual (no scripts, no service-role key)
1. **Create the Auth user.** Supabase dashboard → Authentication → Users → *Add user* → *Send invitation* (or *Create new user* with *Auto Confirm User*). Use the Owner's real email. If you create with a password, choose a strong one yourself; do not reuse it anywhere or write it into any file.
2. **Copy the user's UUID** (Users list → click the user → *User UID*).
3. **Insert the profile** in the SQL editor (runs as `postgres`, which is why this works before any Owner exists):
   ```sql
   insert into public.profiles (user_id, full_name, role, branch_id)
   values ('<PASTE-USER-UID>', '<Owner full name>', 'owner', null);
   ```
   Owners have `branch_id = null` (enforced by a CHECK constraint).
4. **Set the password** if you invited rather than created with one: open the app → *Forgot your password?* → follow the emailed link (open it in the same browser).
5. **Verify**: sign in at the app; the home page shows your name with the badge `OWNER` and "All branches". `GET /api/v1/auth/profile` with your session returns `role: owner`.

Rules: do this for exactly the people who should be Owners. Nothing in the app can promote a user later without an Owner (RLS: only an Owner may write `profiles`).

## A2. Branch Users – from the app (normal path)
Sign in as an Owner → **User Management → New Branch User** → full name, email, branch, password, confirm password → *Create user*.
The API (`POST /api/v1/users`, Owner only) creates the Supabase Auth user through the **Supabase Admin API** with the
password you chose, then inserts the profile (`role = 'branch'`, the chosen active branch, `must_change_password = true`).
**No email is sent**: give the user their email and initial password through a secure channel; they can sign in at once.
The role is never sent by the browser; Owners cannot be created this way. If the profile insert fails the Auth user is
removed again, so no half-created account remains.

Password rules (checked in the form and again by the API): 10-72 characters, upper and lower case letters, a number,
no leading/trailing space, must not contain the email name; the confirmation must match. Passwords are never stored in
`profiles`, logs, audit history or browser storage; they pass through the API to Supabase Auth only.

**First login:** the Branch User signs in with the initial password and sees only a *Change your password* page (current
password, new password, confirmation). Until they finish it the API answers every business request with
`403 password_change_required`. `POST /api/v1/auth/change-password` sets the new password via the Admin API and clears
`profiles.must_change_password` (migration `0018`). Forgot-password still works as before.

**Email confirmation (Owner decision D20):** by default the Auth email is marked confirmed so the user can sign in
immediately (`PROVISION_EMAIL_CONFIRMED=true`). Set it to `false` only if you want Supabase to require email
confirmation first; the user then cannot sign in until they confirm.

One-time server configuration (`backend/.env`, git-ignored; or the host's environment):
```
SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_SERVICE_ROLE_KEY=<Dashboard → Settings → API keys; server only>
PROVISION_EMAIL_CONFIRMED=true    # default; see D20
```
(`PASSWORD_RESET_REDIRECT_URL` is only needed by the operator script below and is no longer used by this form.)
Without the service-role key the form answers "Account creation is not configured on the server" (503); nothing is created.
Also in Supabase → Authentication → Providers/Settings, switch **"Allow new users to sign up" OFF** so nobody can self-register.

Error meanings: "Account not set up" at login = the Auth user has no profile (nobody provisioned a role/branch);
the fix is to create the profile (A for an Owner, A2/B for others). Nobody is ever auto-promoted.

## B. Further accounts – with the provisioning script
`backend/scripts/provision_account.py` (run from `backend/`, venv active) creates the Auth user **without a password**, inserts the profile, and emails a "set your password" link. If the profile insert fails the Auth user is deleted again (no orphans).

Environment (export in your shell for this command only; never put these in `.env`, a repo file, CI output or chat):
```bash
export SUPABASE_URL="https://<project-ref>.supabase.co"
export SUPABASE_SERVICE_ROLE_KEY="<from Dashboard → Settings → API keys; keep secret>"
export ADMIN_DATABASE_URL="<privileged Postgres connection string, e.g. the postgres role>"
export PASSWORD_RESET_REDIRECT_URL="https://<your-app-domain>/reset-password"   # must be in the Supabase redirect allow-list
```
Commands:
```bash
python scripts/provision_account.py create --email owner2@yourcompany.com --full-name "Second Owner" --role owner
python scripts/provision_account.py create --email satwa.manager@yourcompany.com --full-name "Satwa Manager" --role branch --branch "SATWA"
python scripts/provision_account.py adopt --user-id <UUID> --full-name "..." --role branch --branch "MIRDIF"   # user already created in the dashboard
python scripts/provision_account.py deactivate --email satwa.manager@yourcompany.com   # leaves the company
python scripts/provision_account.py activate   --user-id <UUID>
```
- Branch names must match one of the 10 branches (case-insensitive); an unknown name lists the valid ones.
- `--role branch` requires `--branch`; `--role owner` forbids it.
- `deactivate` sets `profiles.is_active = false` (API access stops immediately) **and** bans the Auth user (no new sessions). `activate` reverses both.
- Never delete users to "turn them off": profiles reference `auth.users` with `ON DELETE RESTRICT` on purpose, to preserve history.

## C. Consistency rules
- Auth user ↔ profile is 1:1 via `profiles.user_id = auth.users.id`. An Auth user without a profile can sign in but gets "Account not set up" and no data.
- `is_active = false` → "Account inactive" and no data, even with a valid token.
- Emails are managed in Supabase Auth only; the ERP stores the display name in `profiles.full_name`.
- If someone leaves: `deactivate`. If they return: `activate`.

## D. Safe local testing (no real people involved)
Use a **separate dev Supabase project**, not production. Create test accounts with addresses **you control** (for example plus-addressing on your own mailbox, `you+owner-test@yourdomain.com`, `you+satwa-test@…`) and delete them from the dev project when finished. Do not put real employees' addresses into a dev project, and never copy production data or credentials into it.
For work with no Supabase at all, the simulated environment in `e2e/` creates throw-away users in a throw-away database (`AUTH_TEST_RESULTS.md`).
