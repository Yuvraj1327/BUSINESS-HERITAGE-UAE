# Frontend setup (manual)

Stack: React 19, TypeScript (strict), Vite, Tailwind CSS 4, TanStack Query, Axios, Supabase Auth.

## 1. Requirements
- Node.js **20.19+, 22.12+ or 24+** (`node -v`).
- npm 10+.
- The FastAPI backend running on `http://localhost:8008` (see `README.md`: `cd backend && source .venv/bin/activate && uvicorn app.main:app --host 0.0.0.0 --port 8008 --reload`).

## 2. Install dependencies
```bash
cd frontend
npm ci            # exact versions from package-lock.json (use `npm install` only to change dependencies)
```

## 3. Environment variables
```bash
cp .env.example .env.local     # only if frontend/.env.local (or frontend/.env) does not exist yet
```
Edit `frontend/.env.local`:

| Variable | Required | Value |
| --- | --- | --- |
| `VITE_API_BASE_URL` | production: yes; dev default `http://localhost:8008/api/v1` | FastAPI base URL including `/api/v1` |
| `VITE_SUPABASE_URL` | yes (sign-in) | `https://<project-ref>.supabase.co` (https in production) |
| `VITE_SUPABASE_ANON_KEY` | yes (sign-in) | the Supabase **anon / publishable** key (public by design) |

Never put the service-role key, `sb_secret_*` keys or the database URL in any `VITE_*` variable; the app refuses to start if it detects one. `.env` and `.env.local` are git-ignored.

CORS: the backend must allow the origin the browser uses. `backend/.env` has `CORS_ORIGINS=http://localhost:5173` (the Vite dev server). If you serve the frontend from another origin, add it there (comma-separated, no wildcard) and restart the API.

## 4. Start the frontend
```bash
cd frontend
npm run dev        # http://localhost:5173 (port is fixed; the command fails if 5173 is busy)
```
Sign in with an account that exists in Supabase Auth and has a row in the `profiles` table (Owner: all branches; Branch User: own branch). Account creation: `docs/authentication/OWNER_ACCOUNT_SETUP.md`.

## 5. Checks
```bash
npm run typecheck
npm run lint
npm test
npm run build      # production bundle in dist/ (needs all three VITE_* variables)
npm run preview    # serve dist/ on http://localhost:4173 (add that origin to CORS_ORIGINS to use it)
```

## 6. Screens and the API they use
Every screen calls the real API through `src/services/*.service.ts` (Axios client in `src/lib/api-client.ts`, which adds the Supabase bearer token and `X-Request-ID`). A 401 signs the user out; a 403 shows an "Access denied" notice. Menu entries and routes are filtered by the permissions returned from `GET /auth/profile`; the server re-checks every request.

Branch Management (`/branches`) and User Management (`/users`) are read-only lists because the backend only offers `GET /branches` and `GET /users` (users: Owner only). Order refunds are not offered in the UI because `POST /orders/{id}/refund` is intentionally disabled on the server.

## 7. Troubleshooting
- "Sign-in is not configured": `VITE_SUPABASE_URL` / `VITE_SUPABASE_ANON_KEY` missing; restart `npm run dev` after editing env files.
- Network errors / CORS messages in the browser: API not running on 8008, wrong `VITE_API_BASE_URL`, or origin missing from `CORS_ORIGINS`.
- `npm test` crashing while starting workers: Node is older than 20.19 / 22.12; upgrade Node.
