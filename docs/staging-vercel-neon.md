# Isolated Vercel + Neon staging runbook (Phase 2A)

This is preparation only. The Neon Free `intermind-staging` project already exists in
Frankfurt with PostgreSQL 17. No staging deployment has been authorized. Keep the Azure
App Service, Azure PostgreSQL database, production GitHub Actions workflow, and public
Vercel frontend running as-is.
Use synthetic staging data; do not copy production candidate records into a new provider for an
acceptance test.

## Repository layout and deployment contracts

- Backend Vercel project **Root Directory: `backend`**. `backend/pyproject.toml` names
  `app.main:app` as the one FastAPI entrypoint, `backend/.python-version` pins Python 3.12,
  and `backend/vercel.json` limits the function to 110 seconds. It excludes test/evaluation/raw
  files from the function. `backend/.vercelignore` also keeps those files and local `.env` files
  out of CLI uploads. Do **not** exclude `data/processed/onet/onet_kb.jsonl`; plan creation reads
  that tracked knowledge base at runtime. Build output, not a Windows wheel directory, decides
  whether the Linux function is under Vercel's 500 MB uncompressed limit.
- Frontend staging project **Root Directory: `frontend`**, separate from the public Vercel
  project. `frontend/vercel.staging.json` is intentionally not the default config. After approval,
  replace its example-invalid backend hostname with the staging backend hostname and select it
  with Vercel CLI `--local-config`/`-A` while deploying the **staging project only**. Never use
  the public project's ID or alias. `frontend/vercel.json` remains the production Azure rewrite.
  Keep `VITE_API_BASE_URL` unset so the client calls `/api` on its own origin; the staging rewrite
  forwards `/api/:path*` to the backend's `/:path*`. The SPA fallback stays second.
- `backend/staging.env.example` is a checklist of **backend-only** variables. It contains
  placeholders, not deployable credentials. Set these as encrypted staging project environment
  variables in Vercel; do not put them in any `VITE_*` variable or frontend build setting.

Vercel's Python runtime currently lists 3.12, accepts FastAPI ASGI entrypoints, and has a
500 MB uncompressed Python function bundle limit. Python functions on Fluid Compute can run
up to 300 seconds on Hobby, but the cross-project frontend rewrite has a 120-second proxy
limit. The 105-second application deadline and 110-second function ceiling reserve time to
respond before that proxy closes. Confirm Fluid Compute and the resolved limits in the actual
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
is staged. A branch push may create a preview of the existing public Vercel
frontend if its Git integration builds all branches. Check that project's
dashboard branch/deployment settings before pushing; its default
`frontend/vercel.json` still rewrites `/api` to production Azure. This local
preparation does not authorize a branch push or any cloud deployment.

## Neon staging database, TLS, and connections

1. **Only after approval**, inspect the existing Frankfurt PostgreSQL 17 Neon Free project
   `intermind-staging`; verify its branch and database names in the Neon dashboard rather than
   assuming them. Use an empty staging database. Use a direct
   migration-owner connection for Alembic and a separate runtime role that can connect, use the
   `public` schema, read/write application tables, and use their sequences, but cannot run DDL.
   After migration, grant the runtime role `CONNECT` on that database, `USAGE` on the schema,
   `SELECT, INSERT, UPDATE, DELETE` on application tables, and `USAGE, SELECT` on sequences;
   set corresponding default privileges for later migration-created objects. Verify the Free
   plan and usage settings in that account. If role separation is not available in the selected
   plan, document the owner-role exposure as a staging security risk before deploying.
2. From Neon's connection details, obtain **two** hostnames for the same staging database:
   pooled (the host has `-pooler`) for Vercel runtime `DATABASE_URL`, and direct (no `-pooler`)
   for the one-time Alembic migration. Keep both URLs out of Git, terminal history, build logs,
   issue comments, and screenshots. Percent-encode URL-special characters in the password.
3. Runtime template:
   `postgresql+asyncpg://<USER>:<PASSWORD>@<POOLER_HOST>/<DATABASE>?ssl=verify-full`.
   The `DATABASE_POOL_MODE=null` setting avoids keeping client connections alive in serverless
   functions; Neon pools on the server side. SQLAlchemy's asyncpg dialect gets unique prepared
   statement names in this mode. Do not disable TLS or certificate/hostname verification.
   Set `REQUIRE_DATABASE=true` and `SHARED_STATE_BACKEND=postgres` together, or restart and
   scale-to-zero will lose login sessions and reset rate limits.
4. Migration template, **only against the new empty staging database**:
   `postgresql+asyncpg://<USER>:<PASSWORD>@<DIRECT_HOST>/<DATABASE>?ssl=verify-full`.
   `backend/alembic/env.py` reads `DATABASE_URL`; there is no separate migration URL. Before
   running `alembic upgrade head` from `backend/`, confirm the selected host ends in
   `.neon.tech`, does **not** contain `-pooler`, and names the staging database. Then check
   `alembic current` and compare with the repository head. Never point this step at Azure.
5. Use `DATABASE_ECHO=false`. Check the real staging connection succeeds over verified TLS and
   that the database, pooled URL, and migrations work from Vercel Linux. A local PostgreSQL
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
- [ ] Direct URL migration reaches Alembic head on **staging only**. Restart/recycle function;
      recruiter session, jobs, interview snapshots, and reports persist. No Azure data copied.
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
- [ ] Each LLM-heavy operation finishes before the 105/110/120-second boundaries. Inject an
      LLM timeout and confirm no duplicate answer acceptance or partially durable report.
- [ ] Inspect Vercel build/function/transfer usage, Neon storage/CU-hours/transfer/restore
      window, Azure Speech F0 usage, and OpenAI paid usage. Verify no provider upgraded to a
      paid plan, and set available alerts or budgets before opening staging to testers.

Record test timestamps, region, request counts, latency, function memory, bundle size, and
remaining quotas. Keep staging private or unlisted until these checks pass. A successful local
test suite is necessary but cannot substitute for this Linux/provider acceptance run.

## Next phase, only with explicit approval

1. Confirm current Hobby/Free plan terms and remaining account-wide Vercel usage; select the
   staging region. Verify the existing isolated Frankfurt Neon `intermind-staging` project
   and its PostgreSQL 17 branch/database, then finish configuring separate staging Vercel backend
   and frontend projects. Do not connect an auto-deploy workflow to the public production project.
2. Set backend secrets from `backend/staging.env.example` directly in the staging backend
   project, using a staging OpenAI key and Speech F0 key. Set the runtime Neon pooled URL only
   in that project. Keep `VITE_API_BASE_URL` unset on the staging frontend.
3. On a trusted local machine, set `DATABASE_URL` temporarily to the **direct** staging Neon URL,
   verify the hostname/database, and run `alembic upgrade head` and `alembic current` from
   `backend/`. Clear that local variable afterward. No production migration is part of staging.
4. Deploy the backend project from `backend/` and validate `/health` plus actual DB operations.
   Replace `STAGING_BACKEND_HOST.example.invalid` in `frontend/vercel.staging.json` with the
   real staging host, then deploy the **separate** frontend project from `frontend/` with
   `vercel deploy -A vercel.staging.json` while explicitly selecting its staging project.
5. Run the checklist, collect real provider usage, repair any blocker locally, and present
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
