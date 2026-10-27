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

Budgets live in `backend/app/core/limits.py`. The public deployment uses the PostgreSQL limiter in
`backend/app/core/sql_rate_limit.py`; local development can use `backend/app/core/rate_limit.py`.

### Shared rolling windows

The public backend stores admission events in PostgreSQL. A transaction-scoped advisory lock
serializes admissions across Vercel functions, so the named budgets are checked and recorded
together. A database failure refuses admission. Accepted interview state is also in PostgreSQL
and protected across processes by row locking.

The public counters survive function restarts. They are an abuse and cost control, not a billing
cap. Each admitted request writes events to Neon, so sustained abuse can increase database usage.
Local in-memory mode still resets counters on restart and is not suitable for a scaled deployment.

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

`frontend/vercel.json` rewrites `/api/*` to the separate Vercel backend. The application does not
use forwarded addresses as a trusted visitor identity. It cannot safely key an authentication
budget by client IP without a verified proxy contract; a guessed address could be forged or could
group unrelated visitors together.

Stated plainly: sign-up and sign-in have deployment-wide abuse protection, and no reliable
per-visitor throttling. This is not per-client brute-force protection. A single client is bounded
only by the deployment-wide ceiling it shares with everyone else.

What does constrain an attacker on those two endpoints today:

| | Control |
|---|---|
| Sign-up | `signup_global` 50/hour and 100/day; a 12-character password minimum (length only, per NIST); a 1 024-character password bound and a 320-character email bound enforced during request validation, before any hash; email-shape validation; uniqueness enforced by the database's unique index on the normalised address, so a duplicate is a 409 rather than a second account; no email delivery, so no mail-amplification vector |
| Sign-in | `login_global` 100/10 min; new accounts and the unknown-account dummy use the same scrypt defaults (n=2^15) and verifier; this avoids cheaper dummy verification but does not guarantee identical endpoint timing; one identical failure response for wrong password and unknown email; every attempt counted whether it succeeds or fails; a session cookie that is `HttpOnly`, `SameSite=Strict` and revocable server-side |

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

### Keeping the event table bounded

- Events older than the longest rolling window are pruned during admission.
- An exhausted budget refuses the request before recording new events.
- The SQL limiter refuses admission if the table would exceed 200,000 events. This is a database
  safety bound, not a provider spending cap.

The transaction advisory lock in `SqlRateLimiter.check` protects the read-modify-write across
separate functions and Neon pooled connections.

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

The Speech resource key stays on the Vercel backend. The browser receives a short-lived bearer
credential minted from that key (`app.services.speech_token`). The retained Azure rollback backend
uses managed identity instead.

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

Each is a deployment setting that can drift, so re-check after any infrastructure change:

- The public backend has `REQUIRE_DATABASE=true`, `SHARED_STATE_BACKEND=postgres`, and
  `RECRUITER_SESSION_COOKIE_SECURE=true`.
- Its runtime uses Neon's pooled PostgreSQL connection with verified TLS. Recruiter sessions and
  rate limits use shared PostgreSQL state, not function memory.
- `/api` is rewritten on the public Vercel frontend; the browser keeps a first-party cookie.
- Authentication has no verified per-visitor IP identity (see *No per-visitor limit on sign-up and sign-in*).

## Not covered yet

- Candidate-token hashing at rest, and token expiry or revocation.
- Automatic retention scheduling and verified backup expiry. The deletion code exists, but
  `RETENTION_ENABLED=false` on the public deployment.
- Security headers and a content security policy.
- Per-visitor rate limiting. Today's sign-up and sign-in protection is deployment-wide only.
