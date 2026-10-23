# InterMind Azure to Vercel + Neon: controlled cutover checklist

**Preparation only.** The public Vercel project `intermind`, Azure App Service
`intermind-api`, Azure PostgreSQL `intermind-db`, and their routing remain unchanged.
The isolated Neon destination is project `intermind-production`, PostgreSQL 18,
database `intermind_production` in Frankfurt. It is not the staging project.
The new public backend target is the separate Vercel project
`intermind-api-production`. Never deploy the staging database URL there.

## Before the maintenance window

1. Complete isolated staging: apply retention revision `d91e5a7c2b40` after verifying
   the staging database and old head; deploy staging backend/frontend; smoke-test the
   privacy notice, owner-scoped deletion, and scheduled retention with synthetic data.
   Record the new head and provider usage. Keep the public rewrite unchanged.
2. Prepare a public maintenance page or equivalent temporary frontend route, and
   rehearse its deployment and reversal in **staging**. Confirm the page blocks new
   signup, job, interview, answer, and report requests; a visual banner alone does
   not freeze writes. Inventory any independent Azure writers or scheduled jobs.
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

## Approved maintenance window: single consistent copy

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
