# Deploying InterMind

Frontend on Vercel, backend on Azure App Service, database on Azure Database for PostgreSQL.
Hostnames and connection strings below are placeholders; check the real values in the portals.

```
Browser
   |  https://<your-vercel-domain>
   v
Vercel --- /            -> the built React app (static)
       \-- /api/*       -> rewrite -> https://<your-azure-backend>/*
                                        |
                                        v
                          Azure (FastAPI) --> Azure Database for PostgreSQL
                                          \-> OpenAI, Azure AI Speech
```

The `/api` rewrite is load-bearing. It keeps the browser same-origin with the API, which is what
lets the recruiter session cookie stay `SameSite=Strict` (see *Cookies and CSRF*). Never point the
browser at the Azure origin directly.

## 1. Database

Create an Azure Database for PostgreSQL Flexible Server and a database on it, e.g. `intermind`.

- Networking: let the backend reach it (for App Service, either *Allow public access from Azure
  services* or a shared VNet). Do not open it to the internet.
- TLS is required by Azure. Append `?ssl=require`.
- No extensions needed. The schema uses standard types plus `JSONB`.

```
DATABASE_URL=postgresql://<user>:<password>@<server>.postgres.database.azure.com:5432/intermind?ssl=require
```

`postgres://` and a missing `+asyncpg` driver are normalised in `backend/app/db/engine.py`, so a
string copied out of the Azure portal works unchanged.

## 2. Migrations

The application never creates tables; Alembic owns the schema. Run migrations from `backend/`, where
`alembic.ini` lives and `prepend_sys_path = .` lets `alembic/env.py` import the `app` package:

```bash
cd backend
DATABASE_URL="postgresql://…" alembic upgrade head
DATABASE_URL="postgresql://…" alembic current   # prints the head revision
```

Run this before the new backend starts, on every deploy that includes a migration: from CI, from a
release step, or by hand from a machine that can reach the database. Never from application startup.

## 3. Backend on App Service

### Dependencies

`backend/requirements.txt` must stay at the root of whatever is deployed. Oryx reads it first and
otherwise hands `pyproject.toml` to Poetry, which fails here (setuptools with a PEP 621 `[project]`
table), installing nothing and leaving the app to die with `ModuleNotFoundError`. Set
`SCM_DO_BUILD_DURING_DEPLOYMENT=1` so the build runs at all.

The GitHub workflow uploads `backend/` as the artifact (`path: backend/` in
`.github/workflows/main_intermind-api.yml`), so `wwwroot` gets `app/`, `data/`, `alembic/`,
`requirements.txt` and `alembic.ini` at its top level. Paths in this document are from the repository
root; deployed equivalents drop the `backend/` prefix.

`backend/pyproject.toml` declares minimum bounds for development, `backend/requirements.txt` pins what
production runs. Keep them in step.

### Startup command

App Service detects only Django and Flask, so without a startup command you get the App Service
placeholder page instead of the API:

```bash
az webapp config set --resource-group <rg> --name intermind-api \
  --startup-file "python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1"
```

Port 8000 is what the App Service Python container expects. `gunicorn` is not a dependency and is
not used; the only thing it would add here is multiple workers.

`--workers 1` is required. Recruiter sessions are in memory, so two workers would each hold their own
set and recruiters would be signed out at random as requests landed on different ones. Accounts and
all data are in PostgreSQL and unaffected. Scaling out needs a shared session store first.

### The O\*NET knowledge base

`backend/data/processed/onet/onet_kb.jsonl` is tracked in git and ships inside the artifact.
`backend/app/core/config.py` derives its path from the package location, so `app/` and `data/` must
stay siblings. A deployment cannot rebuild the file: it comes from
`notebooks/ONET_knowledge_base_pipeline.ipynb` and the raw O\*NET text database, which is hundreds of
megabytes and is not in the repository. Without it the app starts and `/health` passes, but every
interview-plan request fails with a sanitized 500.

Nothing to do at deploy time. Do not remove it from git, and re-run the notebook and commit the
result when O\*NET publishes a new release.

### Environment variables

| Variable | Required | Notes |
|---|---|---|
| `DATABASE_URL` | yes | See *Storage mode* below. |
| `REQUIRE_DATABASE` | yes | `true`. Turns a missing `DATABASE_URL` into a refusal to start. |
| `RECRUITER_SESSION_COOKIE_SECURE` | yes | `true` anywhere the app is served over HTTPS. |
| `ALLOWED_ORIGINS` | yes | Your Vercel domain. See *CORS*. |
| `LLM_PROVIDER` | yes | `openai`. Defaults to `fake`, which serves a canned interviewer that looks like it works. |
| `OPENAI_API_KEY` | yes | |
| `OPENAI_MODEL` | no | defaults to `gpt-4o-mini` |
| `SCM_DO_BUILD_DURING_DEPLOYMENT` | yes | `1`. Without it the code deploys with no dependencies installed. |
| `SPEECH_PROVIDER` | yes | `azure` |
| `AZURE_SPEECH_AUTH` | yes | `managed_identity`. See *Azure Speech*. |
| `AZURE_SPEECH_RESOURCE_ID` | yes | The Speech resource's full ARM id. |
| `AZURE_SPEECH_HOST` | yes | The resource's custom-domain host. Not optional under managed identity. |
| `AZURE_SPEECH_KEY` | no | Leave unset in Azure. Managed identity needs no secret. |
| `AZURE_SPEECH_REGION` | no | Unused by managed identity. |
| `RECRUITER_SESSION_TTL_SECONDS` | no | defaults to 8 hours |
| `DATABASE_ECHO` | no | leave false; SQL logs can contain candidate answers |

Store these as App Service application settings or Key Vault references. None of them may ever be
given a `VITE_` prefix: that prefix compiles a value into the public JavaScript bundle. No recruiter
credentials live in configuration at all, since recruiters register themselves.

### Storage mode

`DATABASE_URL` alone is not enough. Without `REQUIRE_DATABASE=true`, a deployment that loses its
connection string starts anyway on in-memory repositories: it answers health checks, accepts signups
and runs real interviews, then discards every account, interview and report on the next container
restart, which App Service does routinely. Nothing fails until the data is gone.

With `REQUIRE_DATABASE=true` the process refuses to start and App Service reports a container crash.
The error names the two settings and never quotes a value.

To confirm which storage is live after a deploy, without log access:

```bash
curl https://<your-azure-backend>/health
# {"status":"ok","storage":"postgresql"}   <- what you want
# {"status":"ok","storage":"in-memory"}    <- data is being discarded
```

`storage` is a mode name only. It never carries the URL, host or credentials, and it does not test
database connectivity.

### Azure Speech

Production authenticates to Azure AI Speech with the App Service managed identity, so no Speech
resource key exists. The backend mints a bearer credential for the browser only while an interview is
active (`backend/app/services/speech_token.py`). That credential's Azure lifetime is independent of
interview completion, and issuance budgets are not audio-consumption limits.

Setup, once:

1. App Service, Identity, System assigned: On.
2. On the Speech resource, give that identity the **Cognitive Services Speech User** role.
   (`Cognitive Services Speech Contributor` also works and grants more than is needed.)
3. On the Speech resource, Networking, **Generate Custom Domain Name**. This is irreversible, and it
   is required: Azure rejects Entra credentials at the regional endpoint.
4. Set `AZURE_SPEECH_RESOURCE_ID` (Speech resource, Properties, Resource ID) and `AZURE_SPEECH_HOST`
   (the custom domain host, e.g. `my-speech.cognitiveservices.azure.com`).
5. Set `AZURE_SPEECH_AUTH=managed_identity` and leave `AZURE_SPEECH_KEY` unset.

`AZURE_SPEECH_AUTH` defaults to `auto`, which picks managed identity whenever
`AZURE_SPEECH_RESOURCE_ID` is set, so production works without step 5. Pin it anyway: a key added to
App Service settings later then becomes inert instead of silently downgrading to secret-based auth.

`AZURE_SPEECH_HOST` is required because the two credential paths send the browser to different
places. A key-issued token is regional, so the browser connects to `{region}.stt.speech.microsoft.com`.
An Entra token is only accepted at the resource's own custom domain, so the token response carries
`host` instead of `region`. Without the host the backend refuses to issue a token rather than hand out
one that could never connect.

Local development keeps using a key: `AZURE_SPEECH_REGION` plus `AZURE_SPEECH_KEY` in a local `.env`
selects the key path. Managed identity can also be exercised locally through `az login`, since the
backend uses `DefaultAzureCredential`; that needs the same role assignment on your own account.

## 4. Frontend on Vercel

Build settings: root directory `frontend`, build command `npm run build`, output directory `dist`.

`frontend/vercel.json` holds the rewrite that makes the browser same-origin with the API. Keep its
destination pointing at the current backend:

```json
{
  "rewrites": [
    { "source": "/api/:path*", "destination": "https://<your-azure-backend>/:path*" }
  ]
}
```

| Variable | Value |
|---|---|
| `VITE_SPEECH_PROVIDER` | `azure` |
| `VITE_API_BASE_URL` | leave unset; it defaults to `/api`, which is the rewrite |

Pointing `VITE_API_BASE_URL` at the Azure origin would make the browser talk to a second site
directly and break the cookie.

## Cookies and CSRF

The recruiter session cookie is `HttpOnly; SameSite=Strict; Secure; Path=/` with no `Domain`
attribute, so the browser scopes it to the host that set it, which through the rewrite is your Vercel
domain. Because the browser only ever talks to one origin, every API call is first-party, the cookie
is attached normally, and no cross-site request can carry it, which is why there is no CSRF token
scheme (see [recruiter-auth.md](recruiter-auth.md)).

Drop the rewrite and this stops being true: the cookie becomes cross-site, `SameSite=Strict`
suppresses it, and sign-in breaks. The fix is not `SameSite=None`, which would need a real CSRF
defence. Keep the rewrite.

## CORS

With the rewrite the browser never makes a cross-origin request, so CORS is not exercised by the app.
It stays configured for direct API access (tooling, `curl`, a staging frontend):

```
ALLOWED_ORIGINS=https://<your-vercel-domain>
```

An explicit list, never `*`: a wildcard cannot be combined with credentialed requests, and doing it
anyway with session cookies would be a real hole.

## HTTPS

Both tiers. Vercel terminates TLS for you; on Azure enable *HTTPS Only* so plain HTTP is redirected.
`RECRUITER_SESSION_COOKIE_SECURE=true` depends on it, because a `Secure` cookie is never stored over
plain HTTP, so sign-in would appear to succeed and then not work.

## Deploy order

Migrations first, then the backend, then the frontend, so nothing calls an API that has not been
updated yet.

1. Confirm `backend/requirements.txt` and `backend/data/processed/onet/onet_kb.jsonl` are committed.
2. Set every required application setting, including the Azure Speech ones.
3. Set the startup command.
4. From `backend/`, on a machine that can reach the database:
   `DATABASE_URL="postgresql://…" alembic upgrade head`, then `alembic current`.
5. Deploy the backend. `curl https://<your-azure-backend>/health` must return
   `{"status":"ok","storage":"postgresql"}`. Anything else means stop and fix.
6. Set `VITE_SPEECH_PROVIDER=azure` on Vercel and deploy the frontend.
7. Smoke test: sign up and sign in, create a job and an interview plan (this is what exercises the
   knowledge base), then start an interview and press the microphone. The speech-token response
   should carry `host` and a `null` `region`.

On a brand new deployment, register the first recruiter through **Create your workspace** on the
site. There is no seed account and no bootstrap step: the first person to register is the first
account. Then create a job, invite a candidate, and confirm the invitation link works in a private
window.

## Verifying persistence

Once, on the real deployment: register a recruiter, create a job, restart the backend (App Service,
Restart), then sign in again. Sign-in should succeed and the job and candidate table should still be
there. Accounts and data survive a restart because they are in PostgreSQL; sessions do not, so you
sign in again.

Accepted answers, evaluations, pending questions and completion are stored before success is
returned, so an active interview resumes from its last accepted turn. The graph's in-memory
checkpointer is an execution cache rebuilt from that snapshot. An unsubmitted browser draft stays
client-side, and evidence already lost from sessions created before the snapshot migration cannot be
reconstructed.

## Known limitations

- Single backend process. Sessions are in memory; scaling out needs a shared session store.
- Unsubmitted answers are not persisted by the backend. Accepted interview evidence is durable.
- Login admission is limited deployment-wide, with no per-visitor throttle, and counters reset on
  process restart.
- No email verification and no password reset, because there is no mail infrastructure. Do not add a
  "Forgot password?" link until there is.
- One account per person. No teams, no roles, no audit trail.
- No account deletion. `jobs.recruiter_id` is `RESTRICT`, so a recruiter cannot be deleted while they
  own jobs, and no cascade can quietly erase candidate interview history. Deletion semantics are
  future product and legal work.
