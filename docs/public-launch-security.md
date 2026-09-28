# Public-launch security

What was hardened before InterMind was shared publicly, how each control behaves, and — more
importantly — what each control does **not** do. Phase 1 addressed the immediate blockers to
putting a link in public; it is not a claim that the application is hardened in general. The
deferred items are listed at the end.

---

## 1. The public job endpoint returns the role title only

`GET /jobs/{job_id}` needs no credential. The candidate's interview screen calls it to name the
role they are about to interview for, before any interview — and therefore any token — exists.

It used to return the full analysed `JobSpec`. The response model's docstring said it carried
"only the role", but its field was `job_spec: JobSpec`, so in practice every required and
preferred skill, every competency, the seniority, the summary and every responsibility derived
from the recruiter's job description were readable by anyone holding a job id. None of it was
rendered by the candidate screen, which reads the role title alone.

| | Before | After |
|---|---|---|
| Shape | `{id, job_spec, created_at}` | `{id, role_title}` |
| Analysed skills / competencies / responsibilities | public | owner-only |
| Seniority, summary | public | owner-only |
| Raw `job_description` | not returned | not returned |
| `recruiter_id` | not returned | not returned |

The public shape is a flat `role_title` rather than a nested model on purpose: there is no
object left for a future field to be added to by accident.

**Recruiter retrieval is preserved in full.** The workspace legitimately needs one job's whole
analysis by id — `InterviewDetailPage` renders its seniority and summary, `ReportPage` its
seniority — and it used to get that from the public route. Minimising the route without
replacing it would have taken those off the recruiter's own screens, so
`GET /jobs/{job_id}/detail` was added: recruiter-only, owner-scoped through `get_for_recruiter`,
and 404 (never 403) for another recruiter's job, matching the convention used everywhere else.

---

## 2. Rate limiting

### Design: why in-process

The limiter keeps its counters in this process. That is a real constraint, and it was accepted
rather than assumed, on one specific ground: **this backend is already single-process by
design, and in several places that are far more load-bearing than a rate limit.**

- Recruiter sessions live in memory (`app.api.recruiter_session`).
- The LangGraph checkpointer that holds live interview state is in memory
  (`app.api.deps.get_interview_graph`).
- The interview lock registry is in memory (`app.services.interview_session`).

A second instance would therefore break sign-in and break interviews long before it weakened a
rate limit. The documented deployment pins `--workers 1` for exactly this reason (see
[deployment.md](deployment.md)). So the limiter introduces **no new deployment constraint** — it
inherits one that is already there and already documented.

That is also why no Redis or other shared store was introduced: it would be new infrastructure
solving the least severe instance of a problem that already has three worse instances.

### Limitations — read these before scaling

- **Counters reset on restart.** App Service restarts containers routinely. After a restart
  every budget is full again. The limiter is a cost and abuse control, not a quota or a billing
  cap, and must never be relied on as one.
- **Counters are not shared across processes or instances.** With *N* instances the effective
  rate is *N ×* the configured rate. With more than one worker per instance, likewise.
- **Scaling out requires shared state anyway.** Sessions, interview state and these counters all
  need a shared store before a second instance is correct. They should move together.

### Budgets

Rolling windows, not fixed wall-clock buckets — a fixed bucket lets a caller spend a whole
budget at `:59` and another at `:01`. Failed attempts consume their admission too; otherwise a
wrong password would be free to retry.

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

Report generation is reachable from two routes — `GET /interviews/{id}/report` and the
cache-miss path of `GET /jobs/{job_id}/interviews` — and both are charged the same
`report_recruiter` allowance, because both spend the same LLM call. On the listing route an
exhausted budget **degrades the row rather than failing the request**: the recruiter still sees
who was invited and their status, and the score arrives on a later load. That matches the
treatment the route already gives a session whose live state is unavailable, and avoids letting
one job with several freshly completed interviews take down the whole candidate table.

The per-interview budgets are set deliberately above the length of any real interview — a
regression test asserts that answering an interview to completion never produces a 429, because
a limit a genuine candidate could trip would be a correctness bug rather than a control.

### Identity: what each budget is charged to

Budgets for expensive work are charged to whoever causes the cost — the signed-in recruiter's
account id for recruiter-initiated LLM work, the interview id for the candidate loop. Both are
identities the request actually proves, so one caller's traffic never constrains another's.

**Sign-up and sign-in are budgeted deployment-wide, not per visitor.** They have no
authenticated identity to key on, and this deployment has no trustworthy per-visitor identity to
substitute — see the next section.

`X-Forwarded-For`, `X-Real-IP` and `Forwarded` are **never** read, anywhere in the application.
They are caller-supplied, so trusting one would let an attacker choose its own bucket on every
request — both a bypass and an unbounded source of dictionary keys.

### Why there is no per-visitor rate limit

Browser traffic does not reach the API directly. `frontend/vercel.json` rewrites `/api/*` to the
App Service origin, so Vercel proxies every call server-side, and Azure App Service then hands
the request to the application through its own front end.

The consequence was verified at runtime rather than assumed: **Azure App Service currently
exposes a link-local proxy address to the application as `request.client.host`**, identical for
every caller. It is not the visitor's address.

An earlier draft of this work keyed sign-up at 5/hour and sign-in at 10/10min on that value.
Because the value is constant, those buckets did not isolate anyone — they silently throttled
all unrelated visitors against each other, roughly ten times tighter than the deployment-wide
ceilings they sat beneath, while describing themselves as per-visitor protection. They were
removed rather than raised, because raising them would have kept the inaccurate description.

What this means, stated plainly:

- Sign-up and sign-in have **deployment-wide abuse protection**.
- They do **not** have reliable per-visitor throttling, and this document does not claim any.
- In particular, this is **not** per-client brute-force protection. A single client is bounded
  only by the deployment-wide ceiling it shares with everyone else.

Per-visitor limiting is deliberately deferred. Doing it correctly needs a verified trusted-proxy
design — establishing which hop is trusted, which forwarded entry is authoritative, and proving
a client cannot forge it — or infrastructure-level protection ahead of the application. Both are
Phase 2; neither is guessed at here.

What still constrains an attacker on these two endpoints today:

| | Control |
|---|---|
| Sign-up | `signup_global` 50/hour and 100/day; server-side password policy (12-character minimum, length-only per NIST); a 1 024-character password bound and a 320-character email bound enforced during request validation, before any hash; email-shape validation; uniqueness enforced by the database's unique index on the normalised address, so a duplicate is a 409 rather than a second account; no email delivery, so no mail-amplification vector |
| Sign-in | `login_global` 100/10 min; scrypt verification at n=2^15 (~300 ms), which is itself a per-attempt cost ceiling; a dummy verification on unknown addresses so timing does not reveal account existence; one identical failure response for both wrong-password and unknown-email; every attempt counted whether it succeeds or fails; the session cookie is `HttpOnly`, `SameSite=Strict` and revocable server-side |

### What is deliberately left unlimited

Every LLM-backed and state-creating operation is budgeted. The routes that are not are all
single cheap reads, or writes affecting only the caller's own session: `/health`,
`GET /auth/recruiter/session`, `POST /auth/recruiter/logout`, `/activity`, `GET /jobs`,
`GET /jobs/{job_id}/detail`, `GET /jobs/{job_id}/interview-plan` and
`GET /interviews/{interview_id}` — all but the first three behind a credential.

One is worth naming explicitly: **`GET /jobs/{job_id}` is unauthenticated and unlimited.** It is
a single indexed read returning `{id, role_title}`, so it carries no LLM cost and now almost no
data. Flooding it is generic HTTP volumetric abuse, which an in-process limiter cannot
meaningfully absorb and which belongs at the platform edge. Rate-limiting it per address would
also risk refusing a legitimate candidate reloading their own interview link. Accepted, and
recorded here rather than left implicit.

### Ordering: authorization first, budgets second

Every budget is charged **after** the route's own access check. A budget keyed by recruiter or
interview identity needs that identity established first, and — more importantly — charging an
unauthenticated caller's budget before deciding whether they may act at all would let anyone
exhaust a real user's allowance by guessing ids. There is a regression test for exactly that.

Sign-up and sign-in are the deliberate exception: they have no authenticated identity to key
on, so they are charged only against their deployment-wide ceiling.

Budgets are also charged **before** the expensive work, so a refused request costs no LLM call.

### Login and account enumeration

The login budget is deployment-wide and **never** keyed by the submitted email. A per-email
budget would trip only for addresses that have accounts, which would make the limiter itself the
account-existence oracle that the uniform "Incorrect email or password" response exists to
prevent. A regression test asserts that a registered and an unregistered address are refused
identically — same status, same body — once the ceiling is reached.

The 429 body names no bucket and no identity, for the same reason.

### Memory

Two mechanisms, plus a backstop:

1. **Expiry.** Aged-out events are swept on every call, and a key with no events left is deleted
   outright rather than kept as an empty entry.
2. **Refuse-before-record.** Admission is refused *before* anything is written, so once a global
   ceiling is reached no new per-identity key can be created beneath it. A caller cycling
   identities therefore cannot keep growing the table: every request arrives under an unseen
   identity, and none of them is recorded. The identities in use — recruiter accounts and
   interviews — cannot be minted freely either, being bounded by the sign-up and invite
   ceilings.
3. **`MAX_TRACKED_KEYS`.** A hard ceiling underneath both, so the table stays bounded even if a
   future bucket were added without a global companion. At the ceiling, identities already
   tracked keep working and novel ones are refused.

Unit tests cover all three, including a 5 000-identity rotation that must leave the table at a
size bounded by the global budget rather than by the number of identities tried.

### Concurrency

`RateLimiter.check` is synchronous, short, and holds a `threading.Lock` across its entire
read-modify-write. Nothing is awaited while the lock is held, and the process genuinely runs
other threads (`asyncio.to_thread` in the Speech credential path). A test races
`8 × budget` threads on one bucket through a barrier and asserts that exactly `budget` are
admitted — never more.

---

## 3. Input size limits

Enforced by pydantic at the API boundary, so an oversized body is rejected **during request
validation** — before the handler runs, and therefore before any LLM call is made or any
password is hashed. A regression test proves the LLM client is never reached for an oversized
job description.

| Input | Bound |
|---|---|
| Job description | 16 000 characters |
| Candidate answer | 6 000 characters |
| Candidate name / email | 320 characters |
| Recruiter password | 1 024 characters (pre-existing) |
| Recruiter email | 320 characters (pre-existing) |

These are resource protection, not product policy: each is far above any real value, and tests
assert that a long realistic job description and a long realistic answer are still accepted.

---

## 4. Azure Speech credential issuance

The Speech resource key has never left the backend and still does not: the browser receives a
short-lived authorization token minted from it, which expires in minutes
(`app.services.speech_token`). Under managed identity — the production path — no key exists at
all. This was already correct and is now covered by regression tests rather than only by design.

What changed is the gate order on `GET /interviews/{interview_id}/speech-token`:

1. **Authorization** — this interview's own access token, or its owning recruiter's session
   (`require_candidate_access`, unchanged). A token for interview A does not mint credentials
   for interview B; an invalid token and no token are both 401.
2. **Still needed** — a completed interview accepts no further answers, so it has no use for a
   microphone. Issuing Azure credentials for one spends a real resource on a dead session. Now
   409, the same status `POST .../answers` already returns for a finished interview.
3. **Budget** — per interview, and only after the first two pass.

An interview whose live state is *unavailable* is deliberately **not** refused. That state is
the in-memory LangGraph checkpoint, so it is gone after a restart; treating "cannot tell" as
"completed" would newly break voice input for an interview merely running on a restarted
process. Such an interview cannot submit answers either, and issuance stays bounded by the
per-interview budget, so allowing it costs at most a handful of short-lived tokens.

No Azure credential, setting or network configuration was changed.

---

## 5. Submitted passwords are never reflected

FastAPI's default `RequestValidationError` handler returns pydantic's error list verbatim, and
pydantic v2 puts the **rejected value itself** in each error's `input` key. A password that
failed validation — too long, or the wrong JSON type — therefore came straight back in the 422
response body, and from there into browser devtools, proxy logs and any error tracker.

This was true of every field on every endpoint, not only of passwords, so it is fixed once at
the root: a custom handler returns `type`, `loc` and `msg` and drops `input` and `ctx`. Keeping
`msg` is what leaves a 422 actionable, and it is the only part the frontend renders (see
`parseErrorDetail` in `frontend/src/api/client.ts`). `ctx` is dropped because for some
constraint types it carries the value too.

Nothing is logged by that handler: a validation failure is routine, and the only thing that
would distinguish one log line from the next is the value that must not be recorded.

Regression tests submit a recognisable canary password — too long, as an object, as an array —
and assert the canary appears nowhere in the response body, on both sign-up and sign-in. The
same is asserted for an oversized candidate answer, to prove the fix is general rather than
password-specific.

---

## Deployment facts this document depends on

Verified against the live deployment at the time of writing. Each one is a portal setting that
can drift, so re-check them after any infrastructure change:

- **One instance.** App Service plan Basic B1, manual scale-out, configured and active instance
  count 1, no autoscale rules. This is what makes an in-process limiter — and in-process
  sessions and interview state — correct rather than merely convenient. More than one instance
  multiplies every rate budget and, more seriously, breaks sign-in and live interviews.
- **One worker.** The startup command pins `--workers 1` (see [deployment.md](deployment.md)).
- **`REQUIRE_DATABASE=true`** and **`RECRUITER_SESSION_COOKIE_SECURE=true`** are set.
- **The application cannot see visitor IP addresses.** Azure App Service currently exposes a
  link-local proxy address to the application as `request.client.host`. Confirmed from the App
  Service log stream; see *Why there is no per-visitor rate limit*.

## Deferred to a later phase

Deliberately out of scope here, and none of them a public-launch blocker on their own:

- Candidate-token hashing at rest, and token expiry/revocation.
- Durable interview state (the LangGraph checkpointer is in memory).
- A data retention and deletion framework.
- Security headers and a content security policy.
- Shared state for horizontal scale — sessions, interview state and rate-limit counters
  together. Scaling beyond one process or instance requires a shared limiter; until then the
  counters are per-process and reset on restart.
- Per-visitor rate limiting, via a verified trusted-proxy design (which hop is trusted, which
  forwarded entry is authoritative, and proof a client cannot forge it) or protection at the
  infrastructure edge. Today's sign-up and sign-in protection is deployment-wide only.
