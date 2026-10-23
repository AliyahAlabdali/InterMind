# Isolated Vercel + Neon staging runbook (Phase 2A)

The Neon Free `intermind-staging` project exists in Frankfurt with PostgreSQL 17. Its
`intermind_staging` database was migrated and independently checked at
Alembic head `a7d4b9e2c103`, including the rate-limit sequence. Do not rerun the three
initial revisions. The additive retention revision `d91e5a7c2b40` is a separate,
owner-only staging migration and requires a fresh target/head check before applying.
The least-privilege `intermind_app_runtime` role has also been created and verified. **Do not
rerun the role setup.**
The isolated Vercel backend and frontend projects are deployed in the same workspace, with
Root Directories `backend` and `frontend` and no Git integration. Their Production variables
are configured; staging database access must pass a live pooled TLS check before acceptance.
Keep the Azure
App Service, Azure PostgreSQL database, production GitHub Actions workflow, and public
Vercel frontend running as-is.
Use synthetic staging data; do not copy production candidate records into a new provider for an
acceptance test.

## Repository layout and deployment contracts

- Backend Vercel project **Root Directory: `backend`**. `backend/pyproject.toml` names
  `app.main:app` as the one FastAPI entrypoint, `backend/.python-version` pins Python 3.12,
  and `backend/vercel.json` explicitly selects the FastAPI preset and Fluid Compute. The
  `functions.app/main.py` rule was rejected because it does not match Vercel's generated
  FastAPI function; use the application deadline instead. `backend/.vercelignore` keeps
  test/evaluation/raw files, setup scripts, and local `.env` files
  out of CLI uploads. Do **not** exclude `data/processed/onet/onet_kb.jsonl`; plan creation reads
  that tracked knowledge base at runtime. Build output, not a Windows wheel directory, decides
  whether the Linux function is under Vercel's 500 MB uncompressed limit.
  The isolated cloud project is `intermind-api-staging` in scope
  `aliyahs-projects-44a8830a` (project ID `prj_yWlDU1gmia3TfyQfmRHeISNZusRW`). It has no
  Git integration. Run its Vercel CLI commands from a **clean staging-branch archive root**:
  Vercel applies the configured `backend` Root Directory. The working checkout contains
  ignored private evaluation artifacts that the CLI may try to scan before applying
  `.vercelignore`; archiving the committed branch excludes them and the unrelated local
  README edit. Pass `--project intermind-api-staging --scope aliyahs-projects-44a8830a`
  explicitly so a local link cannot select the public project.
- Frontend staging project `intermind-frontend-staging` (ID
  `prj_C2B1eis22qvbqHVYe8UksQnrKUQF`) has **Root Directory: `frontend`**, separate from the public
  Vercel project. `frontend/vercel.staging.json` is intentionally not the default config.
  For a CLI deployment, copy the resolved staging config over `frontend/vercel.json` **inside
  a disposable clean archive only**. The CLI `--local-config frontend/vercel.staging.json`
  flag did not override the project-root config in a live deployment; `/api/health` still went
  to the Azure backend. Verify the active archive config and the staging backend's unique
  health response before any write test. Never use the public project's ID or alias. The
  tracked `frontend/vercel.json` remains the production Azure rewrite.
  Keep `VITE_API_BASE_URL` unset so the client calls `/api` on its own origin; the staging rewrite
  forwards `/api/:path*` to the backend's `/:path*`. The SPA fallback stays second.
- `backend/staging.env.example` is a checklist of **backend-only** variables. It contains
  placeholders, not deployable credentials. Set these as encrypted staging project environment
  variables in Vercel; do not put them in any `VITE_*` variable or frontend build setting.

Vercel's Python runtime currently lists 3.12, accepts FastAPI ASGI entrypoints, and has a
500 MB uncompressed Python function bundle limit. Python functions on Fluid Compute can run
up to 300 seconds on Hobby, but the cross-project frontend rewrite has a 120-second proxy
limit. The 105-second application deadline reserves time to respond before that proxy closes;
the staging function uses the Hobby Fluid Compute project default. Confirm Fluid Compute and the resolved limits in the actual
staging project; documentation alone cannot verify project settings.

## Source checkout and private evaluation gate

The public staging branch must not contain ignored historical candidate answers,
report narratives, evaluation traces, frozen answer-bearing reviews, or credentials.
The 19 original raw outputs under `backend/evals/results/` and eight frozen
review/label inputs remain in a private backup. Follow
`backend/evals/recovery_v11/HISTORICAL_PROVENANCE_v1.2.md` for the exact backup
layout and raw-byte verification command. From a clean public checkout, run
`python -m pytest -q -m "not private_history"` in `backend/`; this explicitly
deselects tests requiring the private bundle. In an authorized local checkout
with the entire bundle restored, run `python -m evals.private_history` and the
full `python -m pytest -q`. Neither command calls the paid OpenAI API.

Before any future staging commit, stage an explicit file list, inspect
`git diff --cached --name-only` and `git diff --cached --check`, and confirm
that no ignored private file, `.env` file, credential, or test temp directory
is staged. The public frontend project's saved Ignored Build Step is "Only build
production", so staging branch pushes should not build a frontend preview. Confirm
the project activity after each push. Its default `frontend/vercel.json` still
rewrites `/api` to production Azure; do not change it.

## Neon staging database, TLS, and connections

1. The three original migrations are at head `a7d4b9e2c103` and
   `intermind_app_runtime` has passed least-privilege verification. Do not rerun,
   downgrade, or reset those migrations or role setup. The owner and
   existing `intermind_runtime` roles are too privileged for the application. The new role
   has `CONNECT`, `USAGE` on `public`, `SELECT`/`INSERT` on all nine application
   tables, `UPDATE` only on `interview_plans`, `interview_sessions`, and `interview_reports`,
   `DELETE` on `recruiter_sessions` and `rate_limit_events`, and `USAGE` only on
   `rate_limit_events_id_seq`. The retention addition also needs `DELETE` on
   `activity_events`, `interview_reports`, `interview_sessions`, and `candidates`;
   the guarded migration step grants only those four table permissions. It has no
   schema/database `CREATE`, privileged membership,
   ownership, or `alembic_version` access. New migration-created objects require a separate,
   reviewed grant update; do not give this role broad default privileges.
2. From Neon's connection details, obtain the **pooled** hostname (contains `-pooler`)
   for Vercel runtime `DATABASE_URL`. The owner connection uses the **direct** hostname
   only for the approved role setup; it must never be placed in Vercel. Keep URLs out of Git,
   terminal history, build logs, issue comments, and screenshots. Percent-encode URL-special
   characters in the password.
3. Runtime template:
   `postgresql+asyncpg://<USER>:<URL_ENCODED_PASSWORD>@<POOLER_HOST>/<DATABASE>`.
   Set `DATABASE_SSL_VERIFY_FULL=true` in the staging backend. The application passes an
   `SSLContext` to asyncpg with system-CA certificate and hostname verification enabled. Remove
   `sslmode` and `channel_binding` query parameters from copied Neon snippets when constructing
   this SQLAlchemy URL; do not add `?ssl=verify-full` or disable TLS verification.
   The `DATABASE_POOL_MODE=null` setting avoids keeping client connections alive in serverless
   functions; Neon pools on the server side. SQLAlchemy's asyncpg dialect gets unique prepared
   statement names in this mode. Do not disable TLS or certificate/hostname verification.
   Set `REQUIRE_DATABASE=true` and `SHARED_STATE_BACKEND=postgres` together, or restart and
   scale-to-zero will lose login sessions and reset rate limits.
4. The direct owner URL is **not** a runtime setting. The three initial migrations have
   already completed. Before deploying code that reads `last_activity_at`, use the direct
   `intermind_staging_owner` connection with `DATABASE_SSL_VERIFY_FULL=true` to confirm
   the database is `intermind_staging`, the direct host is the staging Neon endpoint, and
   the starting Alembic head is `a7d4b9e2c103`. Then apply only the reviewed additive
   revision with `alembic upgrade d91e5a7c2b40` and verify the head and new column.
   The guarded local command is
   `python -B backend/scripts/apply_staging_retention_migration.py --apply` from the
   repository root; it prompts privately for the direct host and owner password,
   verifies the previously authenticated staging endpoint digest and old head,
   then requires the typed confirmation `MIGRATE AND GRANT intermind_staging` before
   calling Alembic and granting the four narrow `DELETE` permissions. A failure
   after confirmation requires a read-only head check before any retry.
   Never use the pooled runtime URL for Alembic. Do not include the owner URL in shell
   history, files, deployment variables, or logs.
5. Use `DATABASE_ECHO=false`. Check the real staging connection succeeds over verified TLS and
   that the application queries work through the pooled URL from Vercel Linux. A local PostgreSQL
   test cannot prove Neon PgBouncer compatibility, network latency, or certificate availability.

`backend/app/db/engine.py` still defaults to Azure's existing pool mode; the null pool is
opt-in. `backend/alembic/env.py` already uses NullPool for migrations. The SQL session and
rate-limit stores are selected only by `SHARED_STATE_BACKEND=postgres` in
`backend/app/main.py`. Authentication cookies remain HttpOnly, SameSite=Strict, Secure in
staging, and server-side logout revokes the stored token digest. PostgreSQL row locks protect
interview turn acceptance across function instances. `GET /health` reports the selected storage
mode but does **not** check live database connectivity; verify with authenticated reads/writes.
Every admitted rate-limited request writes PostgreSQL events under one transaction advisory
lock. That is suitable for low traffic but a sustained public attack can consume Neon compute
and make a Free project unavailable even while application requests are rejected. Inspect usage
and concurrency during staging before exposing the endpoint broadly.

## Provider credentials and settings

Provision a staging-scoped OpenAI API key with access to real `gpt-4o-mini`; set
`LLM_PROVIDER=openai` and `OPENAI_MODEL=gpt-4o-mini`. The example uses a 30-second timeout,
zero SDK retries, and a 105-second request deadline. These are staging hypotheses: measure the
full job-analysis, plan, answer, and report paths before choosing final values. A timed-out
request may still have incurred an OpenAI charge. Do not automatically retry an answer POST;
refresh the interview and submit only the currently displayed turn.

For Azure Speech F0, supply a **server-side** staging Speech resource key and region. Explicitly
set `AZURE_SPEECH_AUTH=key`, `SPEECH_PROVIDER=azure`, and leave managed-identity resource ID
unset. The backend exchanges the key for a short-lived authorization token; the browser never
receives the resource key. The speech-token endpoint still requires candidate access and applies
its issuance budget. If staging and production share one F0 resource, their free quota is shared;
check that before testing voice. Typed answers must remain usable when Speech is unavailable.
The existing `intermind-speech-aliyah` Free resource's Azure portal region is **East US**
(`eastus`); this is a processing region separate from the Frankfurt backend/database.

Use the staging frontend origin in `ALLOWED_ORIGINS` for direct API diagnostics. Same-origin
browser requests use the rewrite and do not depend on CORS. Verify the proxy preserves `Set-Cookie`
and sends the cookie on later `/api` requests. Do not set a separate API origin in Vite.

## Staging acceptance checklist (all required before any cutover proposal)

- [ ] Linux Vercel build reports the Python 3.12 entrypoint, one ASGI function, correct
      `backend/` root, included O*NET JSONL, and uncompressed bundle **below 500 MB**.
- [ ] Measure first request after idle: cold-start latency, peak/resident memory, no OOM or
      import failure. Repeat after Neon scales to zero. Record p50/p95 for warmed requests.
- [ ] Vercel to Neon pooled URL: verified TLS, repeated asyncpg/SQLAlchemy queries,
      transactions, simultaneous requests, no prepared-statement collision or stale connection.
- [x] Direct URL migration reached Alembic head on **staging only**. No Azure data copied.
- [ ] Restart/recycle function; recruiter session, jobs, interview snapshots, and reports persist.
- [ ] Concurrent auth attempts hit one atomic global and per-actor budget. Expiry restores
      access after the rolling window. A database outage refuses admission; it never bypasses
      the limiter.
- [ ] Recruiter signup/login, ownership isolation, Secure/HttpOnly/SameSite cookie, expiry,
      logout revocation across a restart; verify unrelated recruiter cannot read jobs/reports.
- [ ] Real OpenAI `gpt-4o-mini`: analyze a synthetic job, create a plan and candidate invite,
      run an adaptive interview with follow-ups, then generate and read the report.
- [ ] Browser microphone recognition and speech output work through Azure Speech F0; expired
      tokens refresh; denied microphone/network failure leaves typed-answer flow functional.
- [ ] Staging frontend `/api` calls are same-origin and cookie-bearing; no browser-visible DB,
      OpenAI, or Speech resource key. Direct backend CORS permits only intended origins.
- [ ] Each LLM-heavy operation finishes before the 105-second application and 120-second rewrite
      boundaries. Inject an
      LLM timeout and confirm no duplicate answer acceptance or partially durable report.
- [ ] Inspect Vercel build/function/transfer usage, Neon storage/CU-hours/transfer/restore
      window, Azure Speech F0 usage, and OpenAI paid usage. Verify no provider upgraded to a
      paid plan, and set available alerts or budgets before opening staging to testers.

Record test timestamps, region, request counts, latency, function memory, bundle size, and
remaining quotas. Keep staging private or unlisted until these checks pass. A successful local
test suite is necessary but cannot substitute for this Linux/provider acceptance run.

### Short end-to-end smoke pass after approved deployment

Use only synthetic names, email addresses, and a short synthetic job description. This pass
calls the **real** `gpt-4o-mini` model and may incur OpenAI charges.

1. Open the isolated staging frontend in a fresh browser profile. Confirm its `/api/health`
   request reaches the staging backend and reports PostgreSQL shared state. In developer tools,
   verify API requests remain on the staging frontend origin. Stop if any request goes to Azure
   or the public frontend.
2. Sign up a synthetic recruiter, confirm the session cookie is `Secure`, `HttpOnly`,
   `SameSite=Strict`, and reload the workspace. Log out, confirm the session is revoked, then
   log back in. Check a second browser without the cookie cannot read the recruiter workspace.
3. Create one synthetic job and its interview plan. Confirm the plan uses O*NET grounding and
   both remain visible after a reload. Invite one synthetic candidate and open its link in a
   separate browser profile. Keep its bearer token only in that browser/session.
4. Answer with typed responses through completion, including any adaptive follow-up. Refresh
   between two turns to prove the interview snapshot survives a fresh request. Confirm an old
   turn cannot be submitted twice. Open the recruiter report; confirm evidence and scores
   appear, then reload it to confirm the stored report is returned without regeneration.
5. Try browser Speech recognition and playback using the staging F0 token. Deny microphone
   access once and confirm typed answers remain usable. Review Vercel function logs for errors
   and Neon, Speech F0, and OpenAI usage after the pass; stop if limits or charges exceed the
   intended test budget.

Keep the public frontend, Azure API, and Azure database untouched throughout this pass.

## Isolated staging deployment procedure

1. Configure only `intermind-api-staging` with the variables from
   `backend/staging.env.example`, using the new runtime role's **pooled** Neon URL, a
   staging-scoped real OpenAI key, and the server-side Speech F0 key. Keep
   `VITE_API_BASE_URL` unset on the separate staging frontend.
2. With deployment approval, export the committed staging branch to a new temporary directory
   and run the CLI from that archive root. The following PowerShell commands do not copy
   ignored files or local edits. Do not run them from `backend/`, because the cloud project's
   Root Directory already adds `backend`.

   ```powershell
   $stagePath = Join-Path $env:TEMP ("intermind-staging-" + [guid]::NewGuid().ToString("N"))
   New-Item -ItemType Directory -Path $stagePath | Out-Null
   git archive --format=zip --output (Join-Path $stagePath "source.zip") staging/vercel-neon
   Expand-Archive -LiteralPath (Join-Path $stagePath "source.zip") -DestinationPath (Join-Path $stagePath "source")
   Set-Location (Join-Path $stagePath "source")
   vercel deploy --dry --project intermind-api-staging --scope aliyahs-projects-44a8830a
   vercel deploy --prod --project intermind-api-staging --scope aliyahs-projects-44a8830a
   ```

   Inspect the dry-run file list and framework before the final command; confirm that it
   includes the O*NET JSONL and no private evaluation outputs or `.env` files. Deploy the
   **staging project** only.
   `--prod` here means the production environment of the isolated staging project; it does not
   target the existing public frontend. Validate `/health` and actual DB operations. The
   backend project has no Git integration; a branch push alone does not deploy it.
   The separate frontend project already exists. In the temporary archive only, replace
   `STAGING_BACKEND_HOST.example.invalid` in `frontend/vercel.staging.json` with the real
   staging backend host, then copy that resolved file over the archive's
   `frontend/vercel.json`. Verify the active config contains no Azure hostname. From the archive
   root, deploy with:

   ```powershell
   vercel deploy --prod --project intermind-frontend-staging --scope aliyahs-projects-44a8830a
   ```

   Do not use the public frontend project or edit its tracked `frontend/vercel.json` rewrite.
   Before signup or job creation, check that the frontend's `/api/health` reaches the current
   staging backend deployment, not the Azure origin. A generic `storage: postgresql` response
   alone does not prove which database receives writes.
3. Run the checklist, collect real provider usage, repair any blocker locally, and present
   results for a later cutover decision. Do not change the public rewrite or remove Azure
   resources without another explicit approval.

### Usage planning (estimates, not measurements)

Assume 20 manual end-to-end staging runs, each with roughly 60 seconds of function lifetime
and at most 5 minutes of active database time including idle cooldown. That is about 0.33
function-hours (at 2 GB, at most ~0.67 GB-hours of memory accounting) and ~1.7 database
compute-hours at 0.25 CU (~0.42 CU-hours). Extra calls from UI navigation, retries, builds,
logs, and concurrent users add usage. The confirmed 8.7 MB production logical DB size suggests
synthetic staging data will be far under 1 GB, but that is not a measured staging size. Vercel
Hobby usage is shared with the existing public frontend on the account. OpenAI calls remain paid;
budget alerts are not a guaranteed hard cap. A shared Azure F0 Speech quota may also be depleted
by staging tests. Check live account usage before each wider test session.

As currently published, Vercel Hobby includes 4 active CPU-hours, 360 GB-hours of provisioned
memory, and 1,000,000 function invocations; Neon Free includes 100 CU-hours per project per
month and 1 GB of database storage. These provider limits can change and are not proof that
this account has unused allowance. Keep usage below the live limits rather than relying on a
free-tier label alone.

Sources: [Vercel Python runtime](https://vercel.com/docs/functions/runtimes/python),
[FastAPI entrypoint](https://vercel.com/kb/guide/ship-a-fastapi-app-on-vercel),
[Vercel function limits](https://vercel.com/docs/functions/limitations),
[Vercel proxy limit](https://vercel.com/docs/limits),
[Hobby included usage](https://vercel.com/docs/plans/hobby),
[CLI alternate config](https://vercel.com/docs/cli/global-options),
[Neon Free plan](https://neon.com/blog/neon-free-plan-1-gb-per-project),
[Neon pooler](https://neon.com/blog/pgbouncer-the-one-with-prepared-statements),
[asyncpg TLS modes](https://magicstack.github.io/asyncpg/current/api/index.html),
[SQLAlchemy asyncpg + PgBouncer](https://docs.sqlalchemy.org/en/20/dialects/postgresql.html).
