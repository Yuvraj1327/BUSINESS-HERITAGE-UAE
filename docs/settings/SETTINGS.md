# Settings section

Self-service account pages for every signed-in user (Owner and Branch User), under `/settings`.
They act only on the caller's own account, so they need no module grant (`NavItem.selfService`); the
Owner-only "System status" page stays in the same menu group behind its `settings` grant.

| Page | Route | What it does | Where it is stored |
|---|---|---|---|
| My Profile | `/settings/profile` | Edit full name, phone, profile photo. Shows email, role and branch read-only. Owners also get a link to User Management. | `profiles.full_name/phone/avatar_path` via `PATCH /auth/profile`; photo in Storage bucket `avatars` |
| Account & Security | `/settings/security` | Change password (current password re-checked), change email (confirmation link), this session's info, sign out other devices, sign out. | Supabase Auth only (`updateUser`, `signOut`) |
| Appearance | `/settings/appearance` | Light / Dark / System. Applied instantly, remembered on the device (`localStorage` `alsafa-theme`, applied before first paint) and saved to the account. | `user_preferences.preferences.theme` |
| Notifications | `/settings/notifications` | Show/hide critical, warning, info alerts in the header bell (Owners; Branch Users have no alert feed and see an explanation). In-app only. | `user_preferences.preferences.notifications` |
| Preferences | `/settings/preferences` | Date format, display time zone, language (English only for now). Currency (AED) and business time zone (Asia/Dubai) are shown as fixed. | `user_preferences.preferences` |
| About | `/settings/about` | App name, app and server version, support contact (`VITE_SUPPORT_EMAIL` / `VITE_SUPPORT_PHONE`, else "contact your administrator"), privacy summary. | – |

## Security model
* **Own row only.** The profile endpoint takes the user from the verified token, never from the request. The request model
  (`ProfileUpdate`) has no role / branch / active fields and rejects unknown ones, so a Branch User cannot change role or branch.
  The database enforces it as well: `profiles` writes stay Owner-only under RLS; `app.update_own_profile()` (SECURITY DEFINER,
  executable by `authenticated` only) can change just `full_name`, `phone`, `avatar_path` of `auth.uid()`'s active profile, and the
  0010 guard trigger still blocks self role/branch/status changes.
* **Preferences** live in `public.user_preferences` (RLS: own row only, active profile only), separate from the audited
  `profiles` table so a theme change does not appear in Activity History. The API validates them (`Preferences`: closed lists
  for theme, language, date format, timezone) and falls back to defaults if stored JSON is damaged.
* **Other users** are managed only through the existing Owner-only `/users` API (`user_management` grant).
* **Password / email** use Supabase Auth from the browser (`updateUser`), after re-authenticating with the current password.
  Email changes complete only when the confirmation link is opened (Supabase "secure email change" applies). The redirect is
  `/settings/security`; add it to the Supabase Auth redirect allow-list.
* **Profile photo**: private bucket `avatars`, 2 MB limit, `image/jpeg|png|webp` only (enforced by Storage itself), object path
  `<user id>/avatar-<uuid>.<ext>`. Storage RLS: a user can read/insert/update/delete only inside their own folder; an active Owner can
  read all. The browser also checks type, size and the file signature before uploading. The DB stores only the path
  (`profiles_avatar_path_chk` pins it to the user's own folder); the UI shows it through a one-hour signed URL.
  Replacing or removing a photo deletes the old object (best effort; an orphan stays private).

## Preferences and business rules
Preferences change *display only*. `dubaiToday()`, report dates, cut-offs and every amount stay Asia/Dubai / AED. The date format
and display time zone are applied by `formatDate` / `formatDateTime` (`utils/format.ts`); `RootLayout` sets them before the pages
render and remounts the shell when one changes. A few pages still format timestamps themselves in Dubai time (e.g. some detail
panels); they are unaffected by the display time zone.

## Theme
`.dark` in `styles/globals.css` overrides the same design tokens (navy identity kept, light-blue primary on deep navy surfaces).
A short block remaps the few hard-coded pale tints (`bg-sky-50`, `to-violet-50`, ...) used by cards and badges.
This replaces decision D24 ("light only in v1").

## API
| Method | Path | Notes |
|---|---|---|
| GET | `/auth/profile` | now also returns `phone`, `avatar_path`, `preferences` |
| PATCH | `/auth/profile` | `{full_name?, phone?, avatar_path?}`; omitted fields unchanged, `null` clears phone/photo. Blocked while a first-login password change is pending. |
| PUT | `/auth/preferences` | full `Preferences` object; returns the profile |

## Deploying
1. Apply `database/migrations/0019_user_settings.sql` (creates the `avatars` bucket and policies when Supabase Storage exists).
2. Deploy the API, then the frontend. Optional frontend env: `VITE_SUPPORT_EMAIL`, `VITE_SUPPORT_PHONE`.
3. Supabase Auth: allow `<app origin>/settings/security` as a redirect URL.

## Tests
* Frontend: `src/test/settings.test.tsx` (pages, validation, upload rules, theme, formatting) plus updated navigation/RBAC tests.
* Backend: `backend/tests/test_settings_profile.py` (service and schemas).
* Database: `TestUserSettings` in `database/tests/test_rbac.py` (needs a disposable PostgreSQL; **not run** in the session that wrote
  it because none was available). Storage policies are not covered by the plain-Postgres test database and need a check on a real
  Supabase project (upload as user A, try to read/overwrite user B's folder).
