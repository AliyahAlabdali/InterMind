# InterMind production migration handoff — updated 2026-10-25

## Pause point and source of truth

No maintenance is in progress. The public `intermind-ai.vercel.app` frontend still
routes `/api` to the **running Azure** backend and database. The usage-limit pause
has ended, but no fresh cutover authorization is in force. Do not start
maintenance, change routing, deploy, modify either database, enable retention
purging, or retire Azure from this document alone.
The user's unrelated `README.md` edit must remain untouched.

The previous maintenance window copied **every** Azure record to a separate Neon
production database, then rolled public traffic back to Azure. Azure remains the
write source of truth. A 2026-10-25 read-only comparison found Azure's eight
original tables identical in count and full-row multiset fingerprint to the
authenticated backup manifest and the verified Neon baseline. This is a
**point-in-time** result, not a write freeze; Azure can change afterward.

## Exact resources and deployed state

| Surface | Current state |
| --- | --- |
| Azure | Subscription `a28b5169-612e-41fb-9549-1bf540bbe43a`, resource group `intermind-rg`, Linux Python App Service `intermind-api` (B1), PostgreSQL Flexible Server `intermind-db`, database `intermind`, PostgreSQL 18, UAE North. App and DB remain running. Source Alembic head `f3a821d9c604`. Keep both for rollback. |
| Azure Speech | Existing F0 resource `intermind-speech-aliyah`, region `eastus`, remains required for voice. Azure App Service uses its current managed-identity integration; the isolated Vercel backend uses a server-side Speech key. |
| Public Vercel | Project `intermind`, alias `intermind-ai.vercel.app`, currently on the known-good Azure rewrite deployment `dpl_F9QwiGNdkS8eybSiKeFitfxR6ZpV`. The rehearsed maintenance deployment was `dpl_6Nr5NU9NPQ8CqrumeSzWYpGYH16f`; verify deployment identities before any promotion. Public `frontend/vercel.json` remains unchanged. Production GitHub Actions deploys Azure only from `main`. |
| Isolated Vercel backend | Project `intermind-api-production`, ID `prj_qQeG1PbB8kUtH096VVcTVaTTMCou`, scope `aliyahs-projects-44a8830a`, root `backend`, function region `fra1`. Deployed and tested in isolation at the backend target recorded in `backend/scripts/production_backend_smoke.py`; it has **not** received public frontend traffic. Production variables use the Neon pooled runtime URL, verified TLS, NullPool, PostgreSQL shared state, Secure cookies, real `gpt-4o-mini`, Azure Speech F0, and `RETENTION_ENABLED=false`. No owner credential belongs in Vercel. |
| Neon production | Separate project `intermind-production` (`jolly-hall-66091099`), branch `br-dark-sun-ba18c1sp`, Frankfurt, PostgreSQL 18, database `intermind_production`. The full original copy and reviewed migrations are present; head `d91e5a7c2b40`. The separate `intermind_app_runtime` role has minimum grants, no elevated Neon membership, and verified pooled TLS login. This is **populated**; never rerun the original restore or role-creation command against it. Do not confuse it with `intermind-staging`. |

The Azure App Service's old `OPENAI_API_KEY` returned HTTP 401 when checked. The
replacement key was validated against `gpt-4o-mini` metadata, configured **only**
on the isolated Vercel backend, and picked up by its redeployment. Thus an Azure
rollback presently restores routing and stored data but may leave real AI calls
broken. Restore a valid Azure key under separate approval before relying on a
fully functional Azure rollback; never copy a key into chat, Git, or logs.

## Completed safeguards and tests

- The 2026-10-24 encrypted PostgreSQL 18 custom archive
  `.env.production-dump-20261024T050307Z.pgdump.age` and private aggregate manifest
  `.env.production-dump-20261024T050307Z.manifest.json` remain ignored. Archive
  SHA-256: `afbaf1ae13186150e7e1289ce906efb1e7cde067e81d8ea2d419b9ee49980664`.
  Age authentication, archive inventory, transactional restore, source counts,
  constraints, indexes, sequences, old revision, and final Alembic chain passed.
  No plaintext dump was saved. The existing age identity has a separately
  passphrase-encrypted recovery copy, verified by decryption and downloaded on
  another device; the passphrase is stored separately. Inventory and review all
  archive/key copies for the approved 30-day retention target. Do not discard
  the only rollback backup while migration remains incomplete.
- The isolated production backend passed bounded synthetic signup/login/logout,
  secure-cookie and durable-session checks, owned job creation and real OpenAI
  analysis/planning, adaptive interview, report generation, and Azure Speech F0
  token issuance. The three uniquely marked smoke runs were guardedly cleaned;
  all original Neon record counts and row fingerprints remained unchanged.
  Staging previously passed the browser experience and maintenance rehearsal.
  Browser voice and same-origin cookies on the **public new route** remain to be
  checked at cutover.
- The 2026-10-25 Azure SSH comparison verified the exact running `intermind-api`
  instance, its live `uvicorn` process, Azure `intermind` on PostgreSQL 18,
  certificate-and-hostname TLS, a repeatable-read read-only transaction, and
  source Alembic head. Every original table matched the authenticated manifest
  and verified Neon baseline: `activity_events=41`, `alembic_version=1`,
  `candidates=9`, `interview_plans=14`, `interview_reports=4`,
  `interview_sessions=9`, `jobs=14`, `recruiters=12`; all fingerprints matched.
  No SQL write occurred. Oryx runs this Python app from a temporary runtime
  directory, so `/home/site/wwwroot/app/main.py` is **not** a valid container
  identity check. Verify `app/main.py` in the running app process's working
  directory (and `APP_PATH` if set). The one-time SSH snippet was removed after
  the comparison; regenerate/review it from the private manifest if needed.
- The user personally reviewed the existing accounts/candidates and believes
  they are their own test records. Preserve every record regardless. The draft
  privacy/retention notice is in `docs/production-privacy-retention-draft.md`;
  do not claim automatic 90-day deletion until the scheduler is activated and
  observed. `RETENTION_ENABLED=false`; do not enable purging during cutover.

## Remaining prerequisites and risks

1. **Final consistency path.** Direct local TCP to Azure PostgreSQL port 5432
   times out, although the server is Ready. The App Service SSH comparison works
   only while the app container is running. The public maintenance frontend
   blocks same-origin `/api`, but direct Azure API calls could still write until
   the App Service is stopped. Before a final comparison, arrange a verified
   write block on the Azure **main-site ingress while leaving SCM/SSH available**,
   drain requests and confirm no independent/background writer; then compare
   through the running app container and stop it. Alternatively establish a
   verified read-only database path that works after stopping the app. The
   temporary ingress rule requires explicit approval and a tested reversal.
   If neither path is available, **do not declare a consistent cutover**.
2. Azure's OpenAI key is expired, so the documented Azure rollback is not yet
   feature-complete. Resolve this under separate production-setting approval
   or explicitly accept that limitation before the next window. The Vercel
   backend's new key and real AI smoke have passed.
3. The public rewrite/privacy deployment and its exact backend target are not
   live. Verify the Vercel project/deployment IDs, backend region, Production
   variable **names** and nonsecret values, and current direct backend health
   again before cutover. Do not print secret values. The privacy notice must
   accurately disclose Frankfurt/Neon, OpenAI, and East US Azure Speech when
   the new route becomes public.
4. The original encrypted archive is a recovery asset, not a fresh snapshot of
   future Azure writes. If the frozen Azure fingerprints differ, stop the
   cutover and plan a new encrypted copy into a separately verified **empty**
   destination; never overwrite/reset the populated Neon production database.
   Review the backup inventory and 30-day deletion/replacement deadline.

## Resume commands and guardrails

Run read-only commands only after confirming the current branch and targets:

```powershell
git status --short --branch
python -B backend/scripts/production_azure_site_control.py --status
vercel project inspect intermind-api-production --scope aliyahs-projects-44a8830a --json
```

Use an authenticated Azure browser SSH session on the **main app container**
for the reviewed aggregate comparison if local database TCP remains blocked.
The source aggregate logic and private manifest verification are in
`backend/scripts/production_encrypted_backup.py` and
`backend/scripts/cleanup_production_backend_smoke.py`. The local cross-database
helper `backend/scripts/compare_azure_neon_readonly.py` requires working TCP to
both databases; its last Azure connection timed out. Do not retry it expecting
the network condition to have changed. Use hidden credential prompts only.

Do **not** rerun `production_neon_restore.py`, `production_runtime_role.py
--role-only`, or `--configure-only`: the destination is populated, the role
exists, and the backend is already configured. The isolated smoke script makes
synthetic writes and paid OpenAI calls; do not rerun it without a new bounded
test decision. The `docs/production-migration-cutover.md` checklist contains
historical one-time restore steps; its empty-destination instructions do not
apply to the current populated Neon database.

At handoff preparation, branch `staging/vercel-neon` was at
`801591329b61b2e3550eab855247b8462fc52f12` before this documentation
commit. Check Git status and HEAD on resume. `README.md` is the user's unrelated
modification. The cutover checklist remained uncommitted; multiple migration
helpers, two temporary local preflight scripts, and maintenance assets are
untracked. Review `git status`
before any future staging/commit; never include ignored backup/key artifacts.

## Freshly approved final maintenance window only

1. Reconfirm exact Azure/Neon/Vercel identities, live public Azure health,
   encrypted archive integrity/recovery, verified Neon original fingerprints,
   valid OpenAI/Speech configuration, and a reversible write-block method.
   Record the current public Azure rewrite deployment. Stop on any mismatch.
2. Promote the rehearsed temporary maintenance frontend on public `intermind`;
   verify GET/POST/OPTIONS `/api` and all write paths return 503. Apply the
   separately approved Azure main-site ingress block (SCM still reachable),
   drain in-flight requests, and verify no independent writer. While the app
   container is still running, repeat the verified-TLS, read-only Azure count
   and fingerprint comparison against the private manifest and Neon baseline.
   If the block or comparison cannot be proven, reverse maintenance and stop.
3. Stop only `intermind-api`; verify stopped state and no remaining writer.
   Leave `intermind-db`, Azure Speech, the encrypted archive, and the existing
   Vercel backend intact. If source records differ from Neon, **do not route**;
   seek a separately approved fresh encrypted copy/reconciliation into an
   empty target, or roll back to Azure. Never run the old full restore against
   populated Neon.
4. If exact equality persists, reconfirm Neon original counts/fingerprints,
   revision `d91e5a7c2b40`, least-privilege pooled runtime TLS, backend health,
   real OpenAI `gpt-4o-mini`, Speech token, and retention disabled. Promote
   only the reviewed public frontend rewrite plus accurate privacy notice.
5. Verify live same-origin `/api`, HTTPS/Secure/HttpOnly cookie login/logout,
   recruiter ownership, one bounded synthetic job → plan → adaptive candidate
   interview → report, browser Speech recognition/playback and typed fallback,
   and no unexpected provider charges. Record the **first public Neon write**;
   clean up only uniquely marked synthetic records with guarded checks.
   Release maintenance only if every gate passes. Keep Azure and backup ready.

**Rollback before the first public Neon write:** return public `intermind` to
`dpl_F9QwiGNdkS8eybSiKeFitfxR6ZpV`, remove the temporary main-site ingress
block, start only Azure `intermind-api`, and verify direct and same-origin health
plus real AI/Speech. If Azure's key remains invalid, the AI part of that gate
cannot pass; do not describe rollback as feature-complete. Preserve Neon and the
archive. **After any public Neon write:** Azure is stale. Return to maintenance,
hold Neon writes, repair Neon or perform a separately approved verified reverse
transfer before ever routing back to Azure. Never silently lose new records.

## Approval and Azure retirement gates

**Next approval required before any final maintenance window:** a refreshed coordinated
maintenance window that explicitly includes the reversible direct-Azure-ingress
write block (or a verified post-stop read-only DB path), the final frozen
comparison, conditional public rewrite, and rollback. Resolve the Azure OpenAI
key limitation first or explicitly approve the degraded rollback risk. This
handoff is not authorization to execute any of those actions.

Only after the live Vercel/Neon route is stable, all original and new records
are verified, rollback/retention obligations are met, and a **separate explicit
retirement approval** is given, stop/delete paid Azure App Service `intermind-api`
and its B1 App Service plan (after confirming no other app shares it), and retire
Azure PostgreSQL `intermind-db` with a verified retained backup and deletion
decision. Stopping the app alone does not eliminate plan charges; database
storage/backups may also continue billing. Keep Azure Speech F0 and any required
security/monitoring resources. Do not delete the whole resource group by default.
