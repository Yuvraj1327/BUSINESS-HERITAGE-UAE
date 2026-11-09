# PROJECT_SETUP (Step 3)

## Structure
```
frontend/
  src/ assets/ components/{ui,common,layout}/ layouts/ pages/ routes/ hooks/ services/ lib/ types/ schemas/
       utils/ constants/ config/ styles/ App.tsx main.tsx
  public/  vite.config.ts  eslint.config.js  .prettierrc  tsconfig*.json  components.json  vercel.json
backend/
  app/ api/v1/ core/ database/ models/ schemas/ repositories/ services/ middleware/ utils/ main.py
  alembic/ (env.py, versions/)  tests/  alembic.ini  pyproject.toml
  requirements.txt  requirements-dev.txt  requirements.lock
database/  migrations/ (0001-0009)  tests/        (Step 2)
docs/      architecture/  database/  PROJECT_SETUP.md  ENVIRONMENT_SETUP.md
```

## Technology notes and decisions
- Tailwind CSS **v4** (`@tailwindcss/vite`, tokens in `src/styles/globals.css`); shadcn/ui components were authored by hand in `src/components/ui` following shadcn conventions (new-york style, CSS variables). `components.json` is present so `npx shadcn add ...` works later.
- Design tokens: light theme, navy primary `#0f2a5c`, accent blue `#2563eb`, white surfaces, light-grey canvas `#f4f6fa`. Dark theme intentionally not included (decision D24).
- TypeScript strict plus `noUncheckedIndexedAccess`, path alias `@/ -> src/`. TypeScript is pinned to 5.9 because typescript-eslint supports `<6.1`.
- ESLint 10 (flat config) + Prettier. Vite 7, React 19, React Router 7.
- `ajv@^8` is a devDependency on purpose: `@hookform/resolvers` declares an optional peer on ajv 8 while ESLint ships ajv 6; pinning ajv 8 at the top level keeps `npm ci` consistent. Do not remove it unless those packages change.
- API client (`src/lib/api-client.ts`): Axios, request-id header, normalised `ApiError`, token-provider and 401 hooks for Step 4 (no auth yet). Global toasts via TanStack Query caches + Sonner; queries/mutations can opt out with `meta: { silent: true }`.
- Backend: app factory (`create_app`), request-id middleware with one structured access-log line per request, uniform error envelope `{error:{code,message,fields}, request_id}`, `/api/v1/health` (liveness) and `/api/v1/health/ready` (database check when configured). Docs disabled in production.
- SQLAlchemy engine is lazy (no connection at import); `Base` has no models yet. **Schema ownership:** Alembic will own `public`/`app` objects by wrapping `database/migrations/*.sql` in Step 4; `create_all` is never used. `alembic upgrade head` is currently a no-op (no revisions).
- Production routes: `design-system` preview page exists in development builds only.
- `frontend/vercel.json` rewrites all paths to `index.html` for client-side routing.

## Commands
See README.md. Frontend: `npm run dev|build|lint|typecheck|format|format:check`. Backend: `uvicorn app.main:app --reload`, `python -m pytest`, `ruff check .`, `ruff format .`, `alembic current`.

## Deployment notes (for Step 12)
Vercel: root `frontend`, build `npm run build`, output `dist`, set `VITE_*` variables. Render: root `backend`, build `pip install -r requirements.lock`, start `uvicorn app.main:app --host 0.0.0.0 --port $PORT`, set backend variables; free instances sleep when idle (decision D3).

## Not in this step
Authentication, roles, dashboards, business modules, customer orders. A frontend unit-test runner (Vitest) is not configured yet; Step 12 covers frontend testing.

## Schema compatibility
No change to the Step 2 schema was needed. (Note for Step 4: the SQL migrations use `auth.uid()`/`auth.users` and must run in a Supabase project, or with the test stub.)
