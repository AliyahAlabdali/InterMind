# Security model

The controls that are in place today, how each behaves, and what each one does not do. This is the
current model, not a claim that the application is hardened in general; the gaps are listed at the
end.

## The public job endpoint

`GET /jobs/{job_id}` needs no credential, because the candidate's interview screen calls it to name
the role before any interview, and therefore any token, exists. It returns a flat
`{id, role_title}` and nothing else: no analysed skills, competencies or responsibilities, no
seniority or summary, no raw `job_description`, no `recruiter_id`. The shape is flat rather than a
nested model so there is no object for a future field to be added to by accident.

A recruiter reading their own job uses `GET /jobs/{job_id}/detail`, which returns the whole analysis.
It is recruiter-only and owner-scoped through `get_for_recruiter`, and answers 404 (never 403) for
another recruiter's job, matching the convention used everywhere else.

## Rate limiting

Budgets live in `backend/app/core/limits.py`; the limiter is `backend/app/core/rate_limit.py`.

### In-process counters

The limiter keeps its counters in this process, which is acceptable only because the backend is
already single-process: recruiter sessions are in memory (`app.api.recruiter_session`) and the
deployment pins `--workers 1` (see [deployment.md](deployment.md)). Accepted interview state is in
PostgreSQL and protected across processes by row locking.

- Counters reset on restart, and App Service restarts containers routinely, so after a restart every
  budget is full again. This is a cost and abuse control, never a quota or a billing cap.
- Counters are not shared across processes or instances. With *N* instances the effective rate is
  *N* times the configured rate.
- Sessions and these counters both need a shared store before a second instance is correct, so they
  should move together rather than adding Redis for the limiter alone.

### Budgets

Rolling windows, not fixed wall-clock buckets, so a caller cannot spend one budget at `:59` and the
next at `:01`. Failed attempts consume their admission too, or a wrong password would be free to
retry.

| Operation | Bucket | Keyed by | Budget |
|---|---|---|---|
| Sign-up | `signup_global` | whole deployment | 50 / hour, 100 / day |
| Sign-in | `login_global` | whole deployment | 100 / 10 min |
| Job analysis (LLM) | `job_recruiter` | recruiter account | 10 / hour, 30 / day |
| | `job_global` | whole deployment | 60 / hour |
| Plan generation (LLM) | `plan_recruiter` | recruiter account | 20 / hour |
| | `plan_global` | whole deployment | 60 / hour |
| Create interview | `invite_recruiter` | recruiter account | 20 / hour, 50 / day |
| Submit answer (LLM) | `answer_interview` | interview id | 60 / 10 min, 200 / day |
| | `answer_global` | whole deployment | 300 / hour |
| Report generation (LLM) | `report_recruiter` | recruiter account | 30 / hour |
| Speech credentials | `speech_interview` | interview id | 60 / 10 min, 200 / day |
| | `speech_global` | whole deployment | 300 / hour, 600 / day |

Report generation is reachable from `GET /interviews/{id}/report` and from the cache-miss path of
`GET /jobs/{job_id}/interviews`, and both are charged `report_recruiter` because both spend the same
LLM call. On the listing route an exhausted budget degrades the row rather than failing the request:
the recruiter still sees who was invited and their status, and the score arrives on a later load.
That matches how the route already treats a session whose live state is unavailable, and stops one
job with several freshly completed interviews from taking down the whole candidate table.

The per-interview budgets sit deliberately above the length of any real interview. Answering an
interview to completion never returns 429, and a test holds that line: a limit a genuine candidate
could trip would be a correctness bug rather than a control.

### What each budget is charged to

Expensive work is charged to whoever causes it: the signed-in recruiter's account id for
recruiter-initiated LLM work, the interview id for the candidate loop. Both are identities the
request proves, so one caller's traffic never constrains another's.

`X-Forwarded-For`, `X-Real-IP` and `Forwarded` are never read anywhere in the application. They are
caller-supplied, so trusting one would let an attacker choose its own bucket on every request: both a
bypass and an unbounded source of dictionary keys.

### No per-visitor limit on sign-up and sign-in

Browser traffic does not reach the API directly. `frontend/vercel.json` rewrites `/api/*` to the App
Service origin, so Vercel proxies every call server-side and App Service then hands the request to the
application through its own front end. App Service exposes a link-local proxy address to the
application as `request.client.host`, identical for every caller, so there is no per-visitor identity
to key a bucket on. A per-address bucket would throttle unrelated visitors against each other while
describing itself as per-visitor protection.

Stated plainly: sign-up and sign-in have deployment-wide abuse protection, and no reliable
per-visitor throttling. This is not per-client brute-force protection. A single client is bounded
only by the deployment-wide ceiling it shares with everyone else.

What does constrain an attacker on those two endpoints today:

| | Control |
|---|---|
| Sign-up | `signup_global` 50/hour and 100/day; a 12-character password minimum (length only, per NIST); a 1 024-character password bound and a 320-character email bound enforced during request validation, before any hash; email-shape validation; uniqueness enforced by the database's unique index on the normalised address, so a duplicate is a 409 rather than a second account; no email delivery, so no mail-amplification vector |
| Sign-in | `login_global` 100/10 min; scrypt verification at n=2^15 (~300 ms), itself a per-attempt cost ceiling; a dummy verification on unknown addresses so timing does not reveal account existence; one identical failure response for wrong password and unknown email; every attempt counted whether it succeeds or fails; a session cookie that is `HttpOnly`, `SameSite=Strict` and revocable server-side |

Per-visitor limiting needs a verified trusted-proxy design (which hop is trusted, which forwarded
entry is authoritative, and proof a client cannot forge it) or protection at the infrastructure edge.
Neither is guessed at here.

### What is deliberately unlimited

Every LLM-backed and state-creating operation is budgeted. The rest are single cheap reads, or writes
affecting only the caller's own session: `/health`, `GET /auth/recruiter/session`,
`POST /auth/recruiter/logout`, `/activity`, `GET /jobs`, `GET /jobs/{job_id}/detail`,
`GET /jobs/{job_id}/interview-plan` and `GET /interviews/{interview_id}`. All but the first three sit
behind a credential.

`GET /jobs/{job_id}` is both unauthenticated and unlimited. It is one indexed read returning
`{id, role_title}`, so it carries no LLM cost and almost no data. Flooding it is generic HTTP
volumetric abuse, which an in-process limiter cannot absorb and which belongs at the platform edge,
and limiting it per address would risk refusing a candidate reloading their own interview link.

### Ordering

Every budget is charged after the route's own access check. A budget keyed by recruiter or interview
identity needs that identity established first, and charging an unauthenticated caller's budget before
deciding whether they may act would let anyone exhaust a real user's allowance by guessing ids.
Sign-up and sign-in are the exception, having no authenticated identity to key on.

Budgets are charged before the expensive work, so a refused request costs no LLM call.

### Login and account enumeration

The login budget is deployment-wide and never keyed by the submitted email. A per-email budget would
trip only for addresses that have accounts, making the limiter itself the account-existence oracle
that the uniform "Incorrect email or password" response exists to prevent. Registered and
unregistered addresses are refused identically, same status and same body, once the ceiling is
reached. The 429 body names no bucket and no identity, for the same reason.

### Keeping the key table bounded

- Expiry. Aged-out events are swept on every call, and a key with no events left is deleted rather
  than kept as an empty entry.
- Refuse-before-record. Admission is refused before anything is written, so once a global ceiling is
  reached no new per-identity key can be created beneath it: a caller cycling identities cannot grow
  the table. Recruiter accounts and interviews, the identities in use, cannot be minted freely either,
  being bounded by the sign-up and invite ceilings.
- `MAX_TRACKED_KEYS` (20 000) is a hard backstop under both, in case a future bucket is added without
  a global companion. At the ceiling, tracked identities keep working and novel ones are refused.

`RateLimiter.check` is synchronous and holds a `threading.Lock` across its whole read-modify-write
with nothing awaited inside, which matters because the process does run other threads
(`asyncio.to_thread` in the Speech credential path): exactly `budget` of any number of racing callers
are admitted.

## Input size limits

Enforced by pydantic at the API boundary, so an oversized body is rejected during request validation,
before the handler runs and therefore before any LLM call or password hash.

| Input | Bound |
|---|---|
| Job description | 16 000 characters |
| Candidate answer | 6 000 characters |
| Candidate name / email | 320 characters |
| Recruiter password | 1 024 characters |
| Recruiter email | 320 characters |

These are resource protection, not product policy: each sits far above any real value, and long
realistic job descriptions and answers are still accepted.

## Azure Speech credential issuance

The Speech resource key never leaves the backend. The browser receives a bearer credential: minted
from the key for ten minutes on the local key path, or, under managed identity (the production path),
an Entra credential following its own expiry, with no key in existence at all
(`app.services.speech_token`).

`GET /interviews/{interview_id}/speech-token` gates in this order:

1. Authorization: this interview's own access token, or its owning recruiter's session
   (`require_candidate_access`). A token for interview A does not mint credentials for interview B;
   an invalid token and no token are both 401.
2. Still needed: a completed interview accepts no further answers, so it has no use for a microphone
   and issuing credentials for one spends a real resource on a dead session. 409, the same status
   `POST .../answers` returns for a finished interview.
3. Budget, per interview, only after the first two pass.

An interview whose durable state is unavailable is refused before Azure is contacted. Completion is
durable, so cache loss cannot restore eligibility. Issuance is serialized with answer acceptance, and
responses are marked `Cache-Control: no-store`.

These budgets count issuance only. An issued credential permits direct Azure Speech use until its real
expiry, even after the interview completes, and Azure does not bind it to one candidate, turn, answer,
audio duration or character quota. InterMind enforces no hard consumption limit while browser SDKs
hold direct credentials.

## Validation errors never echo values

FastAPI's default `RequestValidationError` handler returns pydantic's error list verbatim, and
pydantic v2 puts the rejected value in each error's `input` key, which would put a password that
failed validation straight into the 422 body, browser devtools, proxy logs and any error tracker. The
handler in `backend/app/api/errors.py` returns `type`, `loc` and `msg` only, and drops `input` and
`ctx` (`ctx` carries the value too for some constraint types). `msg` is what keeps a 422 actionable
and is the only part the frontend renders (`parseErrorDetail` in `frontend/src/api/client.ts`).

Nothing is logged there: a validation failure is routine, and the only thing distinguishing one log
line from the next is the value that must not be recorded.

## Deployment facts this model depends on

Each is a portal setting that can drift, so re-check after any infrastructure change:

- One instance. App Service plan Basic B1, manual scale-out, instance count 1, no autoscale rules.
  More than one instance multiplies every rate budget and, worse, breaks sign-in and live interviews.
- One worker, pinned by the startup command (see [deployment.md](deployment.md)).
- `REQUIRE_DATABASE=true` and `RECRUITER_SESSION_COOKIE_SECURE=true` are set.
- The application cannot see visitor IP addresses (see *No per-visitor limit on sign-up and sign-in*).

## Not covered yet

- Candidate-token hashing at rest, and token expiry or revocation.
- A data retention and deletion framework.
- Security headers and a content security policy.
- Shared state for horizontal scale: recruiter sessions and rate-limit counters together.
- Per-visitor rate limiting. Today's sign-up and sign-in protection is deployment-wide only.
