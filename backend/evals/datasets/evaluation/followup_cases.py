"""Blind final follow-up inputs. No reference labels or model predictions live here."""
# ruff: noqa: E501 - interview speech is kept as one string per case for dataset review.

from __future__ import annotations

from hashlib import sha256
from random import Random

from .followup_cases_sample import CASES as SAMPLE_CASES
from .followup_cases_sample import FollowUpCase

# Three independently written answers per question. Their position has no meaning: the
# combined collection is shuffled, and IDs are content hashes rather than ordinal labels.
_MORE: tuple[tuple[str, str, str], ...] = (
    ("API design", "Describe an API change you owned.", "We split a large create endpoint into a draft and confirm step after clients kept retrying timeouts. I added idempotency keys, migrated two consumers behind a versioned route, and watched duplicate orders fall from several a day to zero in the first month."),
    ("API design", "Describe an API change you owned.", "I worked on our API redesign, mostly the create endpoint. It was causing some trouble for a mobile client, and I made a change that seemed to help, but I can't remember which response codes we changed."),
    ("API design", "Describe an API change you owned.", "I mainly consumed the API from the frontend. I haven't designed an endpoint or decided its contract myself."),
    ("Accessibility", "How did you make a feature usable with a keyboard and screen reader?", "On our checkout form I replaced clickable divs with buttons, fixed the focus order after validation, and had a screen-reader user test the error summary. They found a modal focus trap I missed, which we fixed before release."),
    ("Accessibility", "How did you make a feature usable with a keyboard and screen reader?", "I added aria labels to the controls and checked it with a screen reader once. I don't remember how the dialog behaved when tabbing through it."),
    ("Accessibility", "How did you make a feature usable with a keyboard and screen reader?", "We had an accessibility team for that; I didn't work on those checks directly."),
    ("Incident response", "Tell me about an incident where you were on call.", "A queue backlog delayed invoices. I compared consumer lag with deploy time, rolled back a bad batch-size change, replayed the stuck messages, and added a lag alert. The recovery took 43 minutes; I wrote the timeline the next morning."),
    ("Incident response", "Tell me about an incident where you were on call.", "We had an incident with the message queue and I joined the bridge. It was stressful, and we eventually rolled back something. I wasn't the person deciding what to roll back."),
    ("Incident response", "Tell me about an incident where you were on call.", "I've only observed incidents in training. I have not been on call for a production system."),
    ("Data quality", "How have you caught bad data before it reached users?", "I added row-count and null-rate checks to the daily orders pipeline. A source schema change then triggered the quarantine table instead of publishing blank totals; we backfilled the affected day after checking the source extract."),
    ("Data quality", "How have you caught bad data before it reached users?", "I usually look at the dashboard after the pipeline runs and see whether numbers feel right. There was one odd spike last quarter, but I don't know whether it was a source issue."),
    ("Data quality", "How have you caught bad data before it reached users?", "The analysts checked the numbers. My part was scheduling the jobs, so I didn't define any quality checks."),
    ("Security review", "Describe a security issue you found or fixed.", "A support endpoint accepted an account ID without checking tenant membership. I reproduced the cross-account read in staging, added an ownership query, and wrote an integration test for a second tenant before the fix shipped."),
    ("Security review", "Describe a security issue you found or fixed.", "I tightened up an endpoint because it seemed like someone could guess an ID. I think we added a check in the controller, though I don't recall which user context we compared against."),
    ("Security review", "Describe a security issue you found or fixed.", "I haven't investigated an application security issue. I have used dependency scan results supplied by another team."),
    ("Experiment design", "Tell me about an experiment that changed a product decision.", "We randomized search-result ordering by user ID, set a two-week exposure window, and chose checkout starts as the primary measure. The new ranking lifted clicks but not starts, so we did not launch it."),
    ("Experiment design", "Tell me about an experiment that changed a product decision.", "We ran an A/B test on search. The variant got more clicks, and the product manager decided to keep it. I don't know how users were assigned or what the primary measure was."),
    ("Experiment design", "Tell me about an experiment that changed a product decision.", "I've read experiment reports, but I haven't designed or analyzed one myself."),
    ("Stakeholder communication", "How did you communicate a technical delay to nontechnical partners?", "When a payment migration slipped, I showed operations the failing reconciliation cases, the rollback option, and a revised date. We agreed to pilot with one region first and sent daily updates until balances matched."),
    ("Stakeholder communication", "How did you communicate a technical delay to nontechnical partners?", "I told the stakeholders the migration was more complicated than expected. I tried not to get too technical, but I wasn't involved in setting the revised plan."),
    ("Stakeholder communication", "How did you communicate a technical delay to nontechnical partners?", "My manager handled partner communication. I only updated the engineering ticket."),
    ("Caching", "Tell me about a cache you introduced or changed.", "We cached catalog metadata by product ID for five minutes, invalidated on publish, and compared hit rate with stale-read reports. The p95 catalog lookup fell from 180 to 55 milliseconds without a rise in support tickets."),
    ("Caching", "Tell me about a cache you introduced or changed.", "I put Redis in front of one lookup. It got faster in my local test, but I'm not sure how we expired entries when products changed."),
    ("Caching", "Tell me about a cache you introduced or changed.", "I know what a cache is, but I haven't configured one in an application."),
    ("CI/CD", "Describe a change you made to a deployment pipeline.", "Our integration suite took 35 minutes, so I split independent tests across four workers and kept database migrations serial. Median pipeline time dropped to 13 minutes; a flaky seed fixture needed a follow-up fix."),
    ("CI/CD", "Describe a change you made to a deployment pipeline.", "I edited our GitHub Actions workflow so tests ran earlier. I can't recall which jobs depended on the build or whether the change improved the total time."),
    ("CI/CD", "Describe a change you made to a deployment pipeline.", "DevOps owned the pipeline. I triggered deployments but did not alter its jobs."),
    ("Forecasting", "How did you validate a forecast before relying on it?", "For weekly demand I used rolling-origin backtests over 18 months, compared against seasonal naive, and reported error separately for high-volume stores. The model beat baseline overall but failed for new stores, so we kept a fallback there."),
    ("Forecasting", "How did you validate a forecast before relying on it?", "I made a forecast chart that looked close to the historical series. We used it for planning, though I don't remember comparing it with a simpler baseline."),
    ("Forecasting", "How did you validate a forecast before relying on it?", "I haven't built or validated a forecast; finance provided the numbers I used."),
    ("Mobile performance", "What did you do to improve a slow mobile screen?", "The product screen stalled on low-end phones. I traced it to a large image decode and repeated list rendering, resized assets and memoized rows, then measured a 40% drop in time to interaction on two older Android devices."),
    ("Mobile performance", "What did you do to improve a slow mobile screen?", "I removed some images because the screen felt slow. It looked better on my phone, but I didn't measure on lower-end devices."),
    ("Mobile performance", "What did you do to improve a slow mobile screen?", "I haven't worked on mobile performance. A different team maintained the app."),
    ("Database migration", "Describe a schema migration you shipped without downtime.", "I added the nullable column first, dual-wrote for one release, backfilled in batches of 5,000, and verified old and new reads before enforcing non-null. The rollback kept the old reader available until the backfill was complete."),
    ("Database migration", "Describe a schema migration you shipped without downtime.", "I changed a column type and ran a migration. I think the table was small enough that locking wasn't a problem, but we didn't check the lock time."),
    ("Database migration", "Describe a schema migration you shipped without downtime.", "I haven't owned a production database migration; a DBA handled those."),
    ("Observability", "How did you diagnose a service that was intermittently slow?", "I correlated p95 request traces with connection-pool waits and found a bursty export job exhausting the pool. We gave exports a separate pool and added saturation alerts; the daytime p95 returned below 300 milliseconds."),
    ("Observability", "How did you diagnose a service that was intermittently slow?", "I checked Grafana when users said it was slow. CPU looked okay, so I suspected the database, but I don't know what eventually fixed it."),
    ("Observability", "How did you diagnose a service that was intermittently slow?", "I haven't diagnosed an intermittent production slowdown myself."),
    ("Search relevance", "Tell me about improving search result quality.", "Support found exact product names buried behind broad matches. I added a title-field boost, tested against 120 labeled queries, and checked no-result and click-through rates after launch. Exact-name success rose from 72% to 91%."),
    ("Search relevance", "Tell me about improving search result quality.", "I increased a search boost and the first few examples looked better. I don't remember how we evaluated the wider query set."),
    ("Search relevance", "Tell me about improving search result quality.", "I integrated the search widget, but I haven't worked on ranking or relevance."),
    ("Cost optimization", "Describe a cloud cost reduction you led.", "We found idle staging nodes in the billing report, scheduled noncritical environments off overnight, and monitored startup failures for two weeks. Monthly spend fell by about $1,800 without affecting the daytime test queue."),
    ("Cost optimization", "Describe a cloud cost reduction you led.", "I suggested shutting down staging at night, but I don't know whether it was adopted or how much it saved."),
    ("Cost optimization", "Describe a cloud cost reduction you led.", "I haven't had access to cloud billing or made cost decisions."),
    ("Privacy", "How did you handle sensitive user data in a feature?", "For support exports I removed raw email from the default file, limited access to a scoped role, and set a seven-day deletion job. We tested that a standard support account could not retrieve another tenant's export."),
    ("Privacy", "How did you handle sensitive user data in a feature?", "We tried not to include personal data in logs. I removed a field from one log statement, but I didn't review the export path."),
    ("Privacy", "How did you handle sensitive user data in a feature?", "Legal and platform handled that. I haven't designed data handling for a feature."),
    ("Mentoring", "Tell me how you helped a less experienced teammate grow.", "I paired weekly with a new engineer on small payments changes, asked them to lead the third release while I reviewed, and used their questions to improve our runbook. They later took an on-call shift independently."),
    ("Mentoring", "Tell me how you helped a less experienced teammate grow.", "I answer junior engineers' questions in chat when I'm free. One person asked me about the queue code several times, but we didn't set a goal or follow up."),
    ("Mentoring", "Tell me how you helped a less experienced teammate grow.", "I haven't mentored anyone yet. I joined the team recently."),
    ("Incident postmortem", "How did an incident review change the system?", "After a retry storm, I reconstructed the sequence from traces, identified a missing jitter setting, and assigned owners to change client retries and add a load test. We verified the next peak did not reproduce the surge."),
    ("Incident postmortem", "How did an incident review change the system?", "We wrote a postmortem and said we should add more monitoring. I wasn't involved in checking whether the action items were completed."),
    ("Incident postmortem", "How did an incident review change the system?", "I have read postmortems but never helped run one."),
    ("ETL pipeline", "Describe a pipeline you made reliable.", "A partner feed sometimes sent duplicate invoices. I keyed writes by partner ID and invoice number, added a dead-letter queue for malformed rows, and replayed a week's files to verify counts matched finance totals."),
    ("ETL pipeline", "Describe a pipeline you made reliable.", "I added a retry to the import because it failed occasionally. I'm not sure whether repeated messages could create duplicates."),
    ("ETL pipeline", "Describe a pipeline you made reliable.", "I haven't built a data pipeline. I only queried its output."),
    ("Testing strategy", "Tell me about a bug your tests missed and what you changed.", "A timezone boundary broke invoice dates despite unit tests. I added contract fixtures for three zones and an end-to-end case around midnight UTC, then caught the same parsing regression in CI the following month."),
    ("Testing strategy", "Tell me about a bug your tests missed and what you changed.", "We had a date bug and added more tests. I remember the fix, but not what made the original suite miss it."),
    ("Testing strategy", "Tell me about a bug your tests missed and what you changed.", "I run the tests, but I haven't designed a testing strategy or added regression coverage."),
    ("Kubernetes", "What operational change did you make to a Kubernetes workload?", "A worker was restarting under peak load. I compared memory traces with pod limits, fixed a buffering leak, set requests from measured usage, and watched restart count stay at zero for two releases."),
    ("Kubernetes", "What operational change did you make to a Kubernetes workload?", "I increased the pod memory limit after seeing restarts. It stopped for a while, but I didn't know why memory was rising."),
    ("Kubernetes", "What operational change did you make to a Kubernetes workload?", "I haven't operated Kubernetes; I deploy through a platform tool that hides the cluster."),
    ("Code review", "How did your review change a teammate's implementation?", "I noticed an endpoint retried a non-idempotent payment call. We added a request key and a test that replayed the same webhook twice; I also asked for a comment explaining the retry contract."),
    ("Code review", "How did your review change a teammate's implementation?", "I suggested a cleaner helper method in a review. I think it was accepted, though I didn't check whether the behavior changed."),
    ("Code review", "How did your review change a teammate's implementation?", "I haven't reviewed another engineer's production code yet."),
    ("Conflict resolution", "Tell me about a disagreement over a technical approach.", "I preferred a queue while a teammate wanted synchronous writes. We listed failure modes, tested expected throughput, and agreed on synchronous writes with an outbox for the slow integration. I documented why."),
    ("Conflict resolution", "Tell me about a disagreement over a technical approach.", "We disagreed about using a queue. I explained my preference, and eventually the team picked one, but I can't say which constraint decided it."),
    ("Conflict resolution", "Tell me about a disagreement over a technical approach.", "I usually defer to the tech lead and haven't taken part in a technical disagreement."),
    ("Model evaluation", "How did you decide whether a machine-learning model was ready?", "For a fraud classifier I froze a later-month holdout, reviewed precision at the analyst team's fixed capacity, and compared false negatives by merchant segment. A lift in aggregate AUC wasn't enough because one segment regressed, so we delayed release."),
    ("Model evaluation", "How did you decide whether a machine-learning model was ready?", "We compared accuracy on a validation set and it looked higher. I don't remember whether the class balance changed or how the decision threshold was set."),
    ("Model evaluation", "How did you decide whether a machine-learning model was ready?", "I trained a tutorial model, but I've never made a release decision for one."),
    ("Network troubleshooting", "Describe a network fault you traced across services.", "Requests to one region timed out after a firewall rule change. I compared traceroutes from healthy and failing subnets, found the missing outbound route, restored it with infra, and verified error rates across both regions."),
    ("Network troubleshooting", "Describe a network fault you traced across services.", "We had timeouts to another service, and I tried a few connectivity checks. The infrastructure team eventually changed a rule, but I don't know which hop was failing."),
    ("Network troubleshooting", "Describe a network fault you traced across services.", "I haven't debugged a network fault beyond checking whether a host responded."),
    ("Product prioritization", "How did you decide which user problem to tackle first?", "We had competing requests for export formats and report speed. I combined support ticket frequency with observed task time, shipped a pagination fix first, and checked completion time fell for the most affected users."),
    ("Product prioritization", "How did you decide which user problem to tackle first?", "I favored the report issue because it sounded more urgent. I didn't have usage data and didn't check whether it helped after launch."),
    ("Product prioritization", "How did you decide which user problem to tackle first?", "The PM set priorities; I haven't chosen between competing user problems."),
)


def _build() -> tuple[FollowUpCase, ...]:
    cases = list(SAMPLE_CASES)
    for target, question, answer in _MORE:
        digest = sha256(f"{target}\0{question}\0{answer}".encode()).hexdigest()[:12]
        cases.append(FollowUpCase(f"fu-{digest}", target, question, answer))
    Random(20261011).shuffle(cases)
    assert len(cases) == 90 and len({c.case_id for c in cases}) == 90
    return tuple(cases)


CASES = _build()

# Evaluation context, deliberately omitted from the blind reviewer export. The label rubric
# judges the named target without being anchored by the application's category bucket.
TECHNOLOGY_TARGETS = frozenset({
    "PostgreSQL", "Kubernetes", "Redis", "Python", "SQL", "CI/CD",
})
TASK_TARGETS = frozenset({
    "API design", "Data quality", "Caching", "Forecasting", "Database migration",
    "Search relevance", "Cost optimization", "Privacy", "ETL pipeline",
    "Product prioritization", "Model evaluation", "Network troubleshooting",
})


def category_for(target: str) -> str:
    if target in TECHNOLOGY_TARGETS:
        return "technology"
    if target in TASK_TARGETS:
        return "task"
    return "competency"
