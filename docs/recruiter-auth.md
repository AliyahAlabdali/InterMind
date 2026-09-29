# Recruiter authentication

How a recruiter signs in, what that guarantees, and what it deliberately does not.

## Shape of it

Anyone can register at `/signup`. There is no configured account, no seed step and no credential in
configuration: the first person to register is the first account. Signing up issues a session
immediately, so it lands in the workspace instead of asking for the credentials just typed.

```
Email + password
      |  POST /auth/recruiter/signup   (or /auth/recruiter/login)
Account in the recruiter repository; password verified against a scrypt hash
      |
Opaque session id (secrets.token_urlsafe(32)), stored server-side
      |  Set-Cookie: HttpOnly; SameSite=Strict; Path=/
Recruiter workspace
```

| Concern | Where |
|---|---|
| Recruiter model, email normalisation, password policy | `backend/app/domain/recruiter.py` |
| Password hashing and verification | `backend/app/core/security.py` |
| Signup / login / logout / session status | `backend/app/api/routes/auth.py` |
| Account storage | `backend/app/repositories/ports.py`, `in_memory.py`, `sql.py` |
| Session store | `backend/app/api/recruiter_session.py` |
| Authorization dependencies | `backend/app/api/auth.py` |
| Route guard and sign-in page | `frontend/src/app/RequireRecruiter.tsx`, `frontend/src/pages/RecruiterLoginPage.tsx` |

## Accounts

`RecruiterRepository` has two implementations, selected at startup by whether `DATABASE_URL` is set:

- PostgreSQL (`SqlRecruiterRepository`). Accounts live in the `recruiters` table and survive a
  restart. Alembic owns the schema; the application never creates tables.
- In memory (`InMemoryRecruiterRepository`). The default when `DATABASE_URL` is unset, and what the
  test suite runs on. Accounts are lost when the process stops, so it is right for development and
  never right for a deployment. Startup logs a warning in this mode.

Email is normalised before storage and lookup, and uniqueness is the database's own unique index on
`recruiters.email`, enforced inside `add` rather than by a prior lookup: check-then-insert would let
two concurrent signups for the same address both pass.

The password minimum is 12 characters and length is the whole rule, since composition requirements
reliably produce `Password1!` and discourage long passphrases. Email validation is minimal (one `@`,
something either side, a dot in the domain, no whitespace), because a regex cannot establish
deliverability. Accounts are not marked verified, because nothing has verified them: there is no email
delivery in this product.

### Password hashing

`hashlib.scrypt` (RFC 7914) with a per-hash salt and the cost parameters encoded into the stored
string, so they can be raised later without invalidating existing hashes. `n = 2**15` with `r = 8`
needs about 32 MB per hash.

Sign-in never reveals whether an address has an account: the failure response is identical for an
unknown email and a wrong password, and a dummy verification runs when the email is unknown so an
unregistered address is not measurably faster to reject.

## Sessions

- Opaque, 32 bytes of `secrets` entropy. The value carries no identity and no part of the credential.
- In memory only. Every recruiter is signed out when the backend restarts, and sessions are not
  shared between processes, so this does not work behind a multi-worker or multi-instance deployment.
  Accounts and owned data are unaffected; only the session ends.
- Expire after `RECRUITER_SESSION_TTL_SECONDS` (default 8 hours).
- Logout revokes server-side, not just in the browser, so a copied cookie stops working.
- `HttpOnly`, so page scripts, and therefore any XSS, cannot read the session.
- `SameSite=Strict`. Set `RECRUITER_SESSION_COOKIE_SECURE=true` anywhere the app is served over
  HTTPS; a `Secure` cookie is never stored over plain HTTP, which is why it defaults to false for
  local development.

### CSRF

The app is served same-origin with its API: the dev server proxies `/api`, and a production
deployment does the same through Vercel. A `SameSite=Strict` cookie is never attached to a cross-site
request, so there is nothing for a forged request to ride on and no separate CSRF token scheme is
needed.

This property depends on the single-origin deployment. Splitting the frontend and API across
different sites breaks it and requires revisiting both the cookie policy and CSRF.

## Tenant isolation

With more than one account, "signed in" is not the same as "allowed". Ownership is resolved from the
session, never from the request:

- `current_recruiter_id` is the single source of truth for who the caller is, and every
  recruiter-scoped query takes its owner id from there. A request body can claim whatever it likes
  about ownership; it is never consulted.
- Reads and writes go through owner-scoped repository methods (`list_by_recruiter`,
  `get_for_recruiter`), so another recruiter's job, interview plan, interview, report or activity is
  a 404 rather than a filtered-out row.
- `jobs.recruiter_id` is a `RESTRICT` foreign key, so a recruiter cannot be deleted while they own
  jobs and no cascade can quietly erase candidate interview history.

## One way in

`require_recruiter_access` accepts only a live session cookie. There is no bearer-token path and no
test-only route in: tests sign in through the real signup and login endpoints.

A recruiter session also satisfies `require_candidate_access`, but only for their own candidate's
interview, resolved through the owning job. A recruiter may see what their candidate sees; the
reverse never holds. A candidate's interview token is checked only against its own interview's record
and is never consulted by `require_recruiter_access`.

Candidate authentication is separate: a per-interview opaque token carried in the invitation link.
Candidates have no account and never see a sign-in form.

## What this is not

Account sign-in, not an identity platform. There is no:

- team, role or sharing between recruiters. One account is one isolated workspace
- password reset or email verification, because there is no mail infrastructure
- account deletion
- MFA, SSO or OAuth
- per-recruiter audit trail beyond the activity feed
- session that survives a restart or is shared across processes
- per-visitor login throttling. Sign-in has a deployment-wide admission limit, which is not a
  per-client brute-force defence, and its counters reset on process restart
