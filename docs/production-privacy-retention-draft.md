# Production privacy and retention preparation (local draft)

The professional privacy contact is **AliyahAlabdali24@gmail.com**, verified from the
published portfolio's `mailto:` link. The operator approved a 90-day target for
interview answers, evaluations, reports and related activity, and a 30-day target for
encrypted backups under the operator's control. Neither target is currently operational on the public
Azure deployment. This draft and the local privacy page update must not be described
as a live policy until deployed and verified.

## Current and planned processing

The public API and PostgreSQL database remain on Azure in UAE North. The frontend is
hosted by Vercel and may be served through its global network. The isolated future
backend and Neon PostgreSQL destination are configured for Frankfurt. Do not claim
that all processing stays there: live job analysis, interview evaluation and report
generation use the OpenAI API; optional browser audio goes to Azure AI Speech; font
requests go to Google Fonts. Provider processing, logs and retention follow their
separate terms. The app stores transcription text, not microphone audio.
The existing Azure Speech F0 resource `intermind-speech-aliyah` is configured in
**East US** (`eastus`), verified from the Azure portal resource overview.

The frontend privacy notice now identifies these recipients and regions, explains
the approved but inactive retention targets, and provides the verified contact for
access, correction and deletion requests. Requests require identity and ownership
verification. There is no automated candidate self-service erasure, account closure,
guaranteed response time or provider-wide immediate erasure.

## Application retention activation (future deployment only)

1. Review the additive Alembic revision `d91e5a7c2b40`, which backfills
   `interview_sessions.last_activity_at` from the last known session, activity or
   report timestamp. Apply it to staging first and verify the resulting head; it has
   not been applied to the Azure or isolated Neon production database.
2. Apply the revision to the intended destination with a verified direct owner
   connection and backup. Confirm the head and row counts before serving traffic.
3. Set `RETENTION_ENABLED=true`, `INTERVIEW_RETENTION_DAYS=90`, and an independent,
   randomly generated `CRON_SECRET` only on that backend project. Never put the secret
   in Git, the frontend or logs. Vercel Cron calls the authenticated daily route in
   `backend/vercel.json`; the route is disabled by default. Check the project's Hobby
   cron allowance and production deployment before enabling.
4. The daily job deletes a bounded batch of interviews whose last durable update and
   report creation are older than 90 days, plus aged orphan activity/candidate rows.
   It removes report, activity, interview and unshared candidate rows transactionally.
   After deployment, recruiter-owned interview deletion would be available through
   `DELETE /interviews/{interview_id}` only after authentication and ownership checks.
5. Verify a real scheduled invocation and a harmless synthetic expired record in the
   isolated destination before claiming automatic deletion. Observe repeated daily
   runs and alert or manually rerun after a missed invocation. Daily scheduling is
   not an exact-at-midnight guarantee. The route's response contains counts only.

No existing production record should be deleted or classified as synthetic solely
by name. Recruiter accounts and jobs remain until a verified manual closure request;
there is no automatic timetable for them. Candidate requests must be privately
verified and resolved with the relevant recruiter or operator; the new owner-scoped
endpoint is not a public candidate self-service route.

## Encrypted migration backup: 30-day target

No backup has been created by this draft. The smallest $0 incremental-cost plan is a
PostgreSQL 18 `pg_dump` custom-format stream piped **as binary bytes** into the official
`age` file-encryption CLI with a pre-created public recipient key. Keep the decryption
identity offline in the operator's password manager and one separate private recovery
copy. Use `PG*` process environment variables populated from hidden input; no password
or URL belongs in process arguments, shell history, Git or build logs. On Windows, use a
small reviewed binary-subprocess wrapper rather than a PowerShell text pipeline, which
can corrupt a custom-format dump. Confirm the Azure target, verified TLS, and a stopped
writer before running the dump. Check `pg_dump` and `pg_restore` major versions against
the Azure source and PostgreSQL 18 destination before the window.

Record the encrypted archive's SHA-256, creation time, custodian, every storage copy,
and a deletion date **30 days after successful cutover** in a private inventory. Verify
decryption, `pg_restore --list`, and a restore to an isolated disposable PostgreSQL 18
database before accepting the backup. Store two encrypted copies on existing private
media in separate locations; the archive is only as reliable as those devices and the
offline key. This introduces no paid cloud service, but requires manual monitoring and
does not provide provider-level durability or automatic expiry. At day 30, delete every
listed copy and verify the inventory; do not claim expiry is automatic until a tested
deletion mechanism exists. Avoid synchronized folders or untracked copies. A restore
during the 30-day window must reapply verified deletion requests received after backup
creation; keep a minimal private deletion ledger without answer content. Neon/Azure
provider-managed backup history is separate and must be checked against current terms.

## Public notice and privacy checks before cutover

- Review whether the applicable law requires more specific identity, legal-basis,
  transfer, consent or response-time wording. Cross-border transfer from UAE North
  to Frankfurt must be assessed before copying real user data. The operator has
  identified the current records as her own tests, but future user data needs a
  clear notice and a verified request path.
- Verify Azure Speech's configured region and each provider's current data terms.
- Update the notice to say Frankfurt is the **current** backend/database region only
  after the public route actually changes; until then it must describe Azure.
- Do not publish a statement that 90-day database deletion or 30-day backup deletion
  operates until both have been observed and the backup inventory/control exists.

References: [UAE data-protection overview](https://u.ae/en/about-the-uae/digital-uae/data/data-protection-laws.),
[OpenAI API data controls](https://developers.openai.com/api/docs/guides/your-data),
[Vercel cron behavior](https://vercel.com/docs/cron-jobs/manage-cron-jobs).
