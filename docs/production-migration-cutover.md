# InterMind Azure to Vercel + Neon: controlled cutover checklist

## Current continuation after the completed rollback (2026-10-25)

The first maintenance window ended with Azure serving the public site again.
The separate Neon `intermind_production` database already contains the verified
copy and migration head `d91e5a7c2b40`; it is **not an empty restore target**.
The one-time copy and restore described later in this document are **completed
history, not instructions for the next window**. Never run the original restore
or role-creation helper against the populated Neon database. A new maintenance
window, production ingress change, public rewrite, and eventual Azure retirement
each require explicit approval.

Completed: Neon has the least-privilege `intermind_app_runtime` role and the
isolated `intermind-api-production` deployment. Its real OpenAI, Azure Speech,
authentication, interview, and report smoke tests passed; marked test records
were guardedly erased. On 2026-10-25, all eight original Azure tables matched
the private backup manifest and Neon baseline by count and row fingerprint.
That result is a point-in-time comparison while Azure remains writable. The
Azure rollback key was then repaired: direct and public health, a verified-TLS
read-only database query, and a 13-token real `gpt-4o-mini` request passed after
restarting only `intermind-api`. Keep `RETENTION_ENABLED=false`.

### Next maintenance window: verification gates

1. Reconfirm exact Azure, Neon, and Vercel identities, healthy public Azure
   routing, the encrypted archive and recovery copy, Neon head
   `d91e5a7c2b40`, runtime TLS, Speech, and real OpenAI. Record the current
   known-good Azure frontend deployment. Do not infer current source equality
   from the earlier comparison.
2. Obtain separate approval for a reversible direct-Azure-main-site ingress
   block that leaves SCM/SSH reachable. Rehearse its reversal before use. Publish
   the rehearsed public maintenance deployment and verify all `/api` methods
   return 503; drain requests, block direct Azure writes, and confirm no
   independent/background writer. A maintenance page alone is not a freeze.
3. While the app container is still running but writes are blocked, repeat the
   verified-TLS, repeatable-read, read-only Azure counts and row fingerprints
   against the authenticated private manifest and populated Neon baseline.
   Compare the original columns of `interview_sessions`, excluding only the
   reviewed Neon retention clock. Stop if any source row differs. Do not restore
   over populated Neon; reverse maintenance and ingress blocking if a safe,
   separately approved reconciliation cannot be completed.
4. Only after equality passes, stop `intermind-api` and verify the write freeze.
   Keep `intermind-db`, Azure Speech, and the encrypted archive intact. Recheck
   Neon head, original counts/fingerprints, backend health, runtime privileges,
   and `RETENTION_ENABLED=false` before changing the public route.
5. Promote only the reviewed public frontend rewrite and accurate privacy
   notice. Verify exact backend and database identity, same-origin Secure and
   HttpOnly cookies, authentication, ownership, one bounded synthetic job to
   interview to report flow, Speech, and typed fallback. Record the first
   permitted Neon write; release maintenance only after every gate passes.
6. Before the first Neon write, rollback is the known-good Azure frontend,
   removal of the ingress block, and restart of Azure `intermind-api`, followed
   by direct/public health and real AI checks. After any Neon write, Azure is
   stale: return to maintenance and perform a separately approved guarded
   reverse transfer before routing back. Retire Azure only under later approval.

### Reliable Azure source comparison (rehearse while the site remains live)

The 2026-10-26 window stopped at gate 3 because a roughly 3 KB multiline paste
through the browser SSH terminal arrived with mixed/truncated lines. The SQL
syntax error was a transport failure, not a proven data difference. Do not paste
the comparison program into that terminal or infer success from a partial run.

The reviewed program is `backend/scripts/azure_source_fingerprint.py`. It runs
in the **main** App Service container, checks the exact site/process and Azure
database target, uses an `SSLContext` with certificate and hostname validation,
sets default transactions read-only, opens a repeatable-read read-only snapshot,
checks PostgreSQL 18, the source Alembic head and exact eight-table inventory,
then compares an aggregate of every table's count and archive-compatible row
fingerprint with the authenticated private backup. It prints only PASS/STOP,
never rows, credentials, or connection strings. Any mismatch stops the cutover.

From the repository root, with the private encrypted backup and age identity
available, run:

```powershell
& .\.venv\Scripts\python.exe -B backend\scripts\prepare_azure_source_check.py
```

This helper authenticates the private archive, verifies that the reviewed script
is committed and pushed to `staging/vercel-neon`, checks the immutable GitHub raw
bytes against that exact Git blob, and prints **two short commands**. In the
authenticated SSH shell for the running `intermind-api` **main container**,
execute those exact commands in order. The first downloads only the pinned
script into `/tmp`; the second requires its raw-byte SHA-256 to match before
executing it with the aggregate expected digest. A failed download, hash check,
identity check, TLS check, transaction check, or fingerprint check is a STOP.
Remove only `/tmp/intermind-azure-source-check.py` afterward with the cleanup
command printed by the helper. No application file or setting is changed.

The short-command transport was rehearsed on the live App Service without a
database query: a public repository file was fetched from a pinned commit,
matched its local Git SHA-256, and its temporary copy was removed. Run the real
source check once while Azure is still live to prove the program and transport;
that result is only a point-in-time rehearsal. **Repeat it after public
maintenance and the verified direct-Azure ingress block have drained requests.**
Check the already populated Neon database independently against the same private
manifest. Do not stop Azure or release maintenance unless both exact baselines
pass at that frozen point. No new maintenance window is authorized by this
procedure alone.

**Preparation only.** The public Vercel project `intermind`, Azure App Service
`intermind-api`, Azure PostgreSQL `intermind-db`, and their routing remain unchanged.
The isolated Neon destination is project `intermind-production`, PostgreSQL 18,
database `intermind_production` in Frankfurt. It is not the staging project.
The new public backend target is the separate Vercel project
`intermind-api-production`. Never deploy the staging database URL there.

## Historical first-copy preparation (completed; do not repeat)

1. Complete isolated staging: apply retention revision `d91e5a7c2b40` after verifying
   the staging database and old head; deploy staging backend/frontend; smoke-test the
   privacy notice, owner-scoped deletion, and scheduled retention with synthetic data.
   Record the new head and provider usage. Keep the public rewrite unchanged.
2. Prepare a public maintenance page or equivalent temporary frontend route, and
   rehearse its deployment and reversal in **staging**. Confirm the page blocks new
   signup, job, interview, answer, and report requests; a visual banner alone does
   not freeze writes. Inventory any independent Azure writers or scheduled jobs.
   Use `frontend/vercel.maintenance.json` and `frontend/public/maintenance.html`
   only in a disposable deployment archive; leave the tracked public
   `frontend/vercel.json` unchanged. The maintenance rule returns HTTP 503 for
   every `/api` method and serves a static page for other paths. This blocks the
   same-origin frontend route, but direct calls to the backend remain possible
   until Azure App Service is stopped. Verify both paths before declaring the
   write freeze. Restore the prior frontend deployment if preflight fails.
3. Install verified PostgreSQL 18 client tools and the official `age` CLI locally.
   Create a dedicated `age` recipient; keep its private identity offline in the
   operator's password manager and a separate recovery location. Test a binary
   `pg_dump | age` and decrypt/restore on disposable synthetic local PostgreSQL 18.
   Keep the source database credential in process memory from a hidden prompt.
4. Confirm the Azure source host, database `intermind`, version, Alembic revision,
   extensions, table counts, and owner permissions with read-only queries. Confirm
   direct TLS with certificate and hostname verification. Confirm that the Neon
   destination is the **empty** `intermind_production` database on the correct direct
   endpoint, and verify the restore owner can create schema objects. Record counts
   privately without personal fields. Stop if versions or migration path differ.
5. Prepare `intermind-api-production` Production variables with the **pooled** Neon
   runtime URL for a separate least-privilege role, verified TLS, NullPool,
   PostgreSQL shared state, Secure cookies, real OpenAI `gpt-4o-mini`, the existing
   Azure Speech F0 key and `eastus` region, and only the intended frontend origin.
   Keep `RETENTION_ENABLED=false` until schema and deletion verification. Owner and
   backup credentials must never be Vercel runtime variables. Check the backend
   function region is `fra1` and the project has no unintended Git deployment.
6. Prepare, but do not publish, the frontend rewrite to the verified new backend
   URL. The privacy notice must change from Azure UAE North to Neon/Vercel Frankfurt
   **only when the public cutover occurs**. Keep a known-good frontend deployment
   with the Azure rewrite available for rollback.

## Historical first-copy window (completed; do not repeat)

**Staging rehearsal on 2026-10-24:** The isolated `intermind-frontend-staging`
deployment `dpl_DfzuDJUMaico7ykbPPURSeCnssFJ` served the maintenance page;
authenticated GET, POST, and OPTIONS requests to `/api/health` returned 503.
The previous staging deployment `dpl_DMKuqPzSgqaBcuebxJuDsGTpTJyU` was
promoted back, and same-origin `/api/health` again returned JSON with HTTP 200.
This rehearsal did not stop the staging backend or freeze any database writes.

The operator must separately approve the maintenance window, Azure write freeze,
encrypted copy, Neon writes, production deployment and public cutover. Do not start
from this checklist alone.

1. Publish the rehearsed maintenance page and confirm it blocks every public write
   path. Let in-flight requests drain. Stop only the Azure `intermind-api` App
   Service to enforce the freeze, then confirm it is stopped and no independent
   writer remains. Keep `intermind-db` running for the dump. Record freeze time.
2. In a read-only Azure transaction, record the source revision and per-table
   counts. Run one PostgreSQL 18 custom-format `pg_dump` from the frozen source,
   streaming binary output directly to `age` on existing private storage. Reject
   any warning or nonzero exit. Never create an unencrypted dump on disk. Record
   archive SHA-256, copy inventory, custodian and 30-day deletion date privately.
3. Verify decryption and `pg_restore --list`, then restore-test in an isolated
   disposable PostgreSQL 18 database. Proceed only after confirming counts and
   representative schema constraints. The original Azure database remains intact.
4. Reconfirm the exact empty Neon production destination and direct restore-owner
   connection over verified TLS. Restore with `pg_restore --exit-on-error
   --no-owner --no-acl` into that database. Check table counts, sequence values,
   constraints, and Alembic revision. Run only the reviewed Alembic revisions
   newer than the restored source head, using the direct owner role. Confirm final
   head `d91e5a7c2b40`; do not stamp a missing migration.
5. Create a separate Neon production runtime role without elevated Neon membership,
   ownership, schema CREATE, CREATEDB, CREATEROLE or BYPASSRLS. Grant only table and
   sequence operations the app uses, excluding `alembic_version`; verify effective
   permissions and pooled login with TLS. Keep its password server-side only.
6. Deploy only `intermind-api-production`. Check `/health`, a read-only DB query,
   cookies, authentication, rate limiting, OpenAI and Speech in controlled synthetic
   tests against **Neon production**. Do not admit public writes yet. Do not copy
   source data again after opening writes.
7. Change only the public frontend rewrite/privacy deployment and verify the live
   frontend calls the exact production backend, login persists, and one synthetic
   interview/report works. End maintenance only after the route, database identity,
   counts, and cost settings pass. Record the first permitted Neon write time.
8. Activate retention with a separate `CRON_SECRET` only after a synthetic expiry
   test and the daily cron setting are verified. The 90-day claim stays conditional
   until an actual scheduled purge is observed. Keep Azure resources untouched until
   a later explicit retirement approval.

## Rollback and retention

Before the first public Neon write, reverse the frontend to its known-good Azure
rewrite and restart Azure App Service; Azure still has the complete frozen data.
After Neon accepts new writes, Azure is stale. **Do not point the public frontend
back to Azure without another write freeze and a verified reverse data transfer**;
otherwise those new recruiter and candidate records would be lost. If a fault occurs,
return to maintenance while repairing Neon or planning a guarded reverse transfer.

Hold the encrypted migration archive and every private copy for at most 30 days after
successful cutover, track any deletion requests that must be replayed on restore,
then verify deletion of all listed copies. This manual plan costs $0 in new recurring
services if existing local storage is used, but has device-loss and operator-miss
risks; Neon and Azure provider backup retention is independent. Azure App Service
plan and PostgreSQL can stop incurring their recurring compute charges only after
separately approved retirement; Azure Speech F0 must remain for browser voice.
