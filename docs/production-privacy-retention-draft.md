# Production privacy and retention planning record

The public backend and database now run on Vercel and Neon in Frankfurt. The published notice is
`frontend/src/pages/legal/PrivacyPage.tsx`. Automatic deletion remains disabled. Azure is retained
for rollback, and its pre-cutover data-location statements are historical.

The professional privacy contact is **AliyahAlabdali24@gmail.com**, verified from the
published portfolio's `mailto:` link. The operator approved a 90-day target for
interview answers, evaluations, reports and related activity, and a 30-day target for
encrypted backups under the operator's control. Neither target is operating automatically on the
public deployment. The published privacy notice states this limitation.

## Current processing

The public API runs on Vercel and PostgreSQL runs on Neon in Frankfurt. The frontend is
hosted by Vercel and may be served through its global network. Do not claim
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

## Application retention activation (not approved)

1. Revision `d91e5a7c2b40` is already applied to Neon production. Do not rerun
   the migration. Check the current schema and backup before any new retention change.
2. After separate approval and staging verification, set `RETENTION_ENABLED=true`,
   `INTERVIEW_RETENTION_DAYS=90`, and an independent,
   randomly generated `CRON_SECRET` only on that backend project. Never put the secret
   in Git, the frontend or logs. Vercel Cron calls the authenticated daily route in
   `backend/vercel.json`; the route is disabled by default. Check the project's Hobby
   cron allowance and production deployment before enabling.
3. The daily job deletes a bounded batch of interviews whose last durable update and
   report creation are older than 90 days, plus aged orphan activity/candidate rows.
   It removes report, activity, interview and unshared candidate rows transactionally.
   The owner-scoped `DELETE /interviews/{interview_id}` route requires authentication and
   ownership checks; it is separate from the disabled automatic purge.
4. Verify a real scheduled invocation and a harmless synthetic expired record in the
   isolated destination before claiming automatic deletion. Observe repeated daily
   runs and alert or manually rerun after a missed invocation. Daily scheduling is
   not an exact-at-midnight guarantee. The route's response contains counts only.

No existing production record should be deleted or classified as synthetic solely
by name. Recruiter accounts and jobs remain until a verified manual closure request;
there is no automatic timetable for them. Candidate requests must be privately
verified and resolved with the relevant recruiter or operator; the new owner-scoped
endpoint is not a public candidate self-service route.

## Encrypted migration backup: 30-day target

The cutover used a PostgreSQL 18 custom-format backup encrypted with `age`. The encrypted
archive and a separately verified recovery identity remain private. No password, connection URL,
backup content or identity belongs in Git or logs. The archive is a recovery asset, not a
snapshot of writes made after cutover.

The 30-day target requires a private inventory of every encrypted copy, a custodian and a
reviewed expiry date. Deletion is manual and must not be claimed as automatic. Before removing
any copy, confirm that the separate Azure rollback and Neon recovery requirements have been met.
A restore must reapply verified deletion requests received after backup creation. Neon and Azure
provider-managed backup history follows separate retention terms.

## Public notice and remaining privacy checks

- Review whether the applicable law requires more specific identity, legal-basis,
  transfer, consent or response-time wording. The operator identified the migrated
  records as her own tests; future user data needs a clear notice and a verified
  request path for cross-border processing.
- Verify Azure Speech's configured region and each provider's current data terms.
- Keep the published notice aligned with the current Vercel and Neon route, Azure Speech region,
  and any later provider or retention change.
- Do not publish a statement that 90-day database deletion or 30-day backup deletion
  operates until both have been observed and the backup inventory/control exists.

References: [UAE data-protection overview](https://u.ae/en/about-the-uae/digital-uae/data/data-protection-laws.),
[OpenAI API data controls](https://developers.openai.com/api/docs/guides/your-data),
[Vercel cron behavior](https://vercel.com/docs/cron-jobs/manage-cron-jobs).
