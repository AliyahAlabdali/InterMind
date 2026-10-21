"""Frozen-input candidates for the five-job discrimination and evidence study.

The tiers describe how these scripts were constructed, not model predictions or human
labels. All three candidates for a job answer the same ten target questions. The first
three backend examples retain Claude's reviewed sample verbatim.
"""
# ruff: noqa: E501 - keep each authored answer on one line for comparison across tiers.

from __future__ import annotations

from dataclasses import dataclass

from .personas_sample import SAMPLE, Persona, PersonaAnswer


@dataclass(frozen=True)
class JobDescription:
    jd_id: str
    role_title: str
    text: str
    # (category, target, question, strong, mixed, weak)
    cases: tuple[tuple[str, str, str, str, str, str], ...]


BACKEND = JobDescription(
    "jd-senior-backend",
    "Senior Backend Engineer",
    "Senior backend engineer for a payments platform. Own PostgreSQL schema and query work, "
    "incident response, code review, API design, Python services, distributed queues, testing, "
    "security, deployment, and cross-team technical decisions.",
    (
        ("technology", "PostgreSQL", SAMPLE[0].answers[0].question, *(p.answers[0].answer for p in SAMPLE)),
        ("competency", "Incident response", SAMPLE[0].answers[1].question, *(p.answers[1].answer for p in SAMPLE)),
        ("competency", "Code review", SAMPLE[0].answers[2].question, *(p.answers[2].answer for p in SAMPLE)),
        ("task", "API design", "Describe an API change you owned.",
         "I changed order creation to use idempotency keys after retries duplicated payments. I versioned the route, migrated both consumers, and verified duplicate orders stopped without breaking the old client.",
         "I designed the idempotency key and tested replaying the same request twice. The mobile team handled migration and I checked their first deployment logs.",
         "The team updated our APIs several times. I attended the planning meetings and made sure my tickets were done."),
        ("technology", "Python", "What Python service problem did you solve recently?",
         "A Python worker held large PDF buffers across jobs. I profiled memory, moved conversion into a bounded subprocess, and measured stable resident memory over a week of production traffic.",
         "I maintain a Python worker and added retry handling when a partner timed out. I haven't measured whether it ever retries non-idempotent requests.",
         "Python is a flexible language and our services use it extensively. I mostly follow the patterns already in the repository."),
        ("task", "Queue processing", "How did you make a message consumer reliable?",
         "We saw duplicate fulfillment events after redelivery. I keyed writes by event ID, moved acknowledgement after commit, and replayed archived events to confirm one fulfillment per order.",
         "I built an idempotent consumer keyed by event ID and tested duplicates. I missed that poison messages could block the partition, so a teammate added the dead-letter path later.",
         "Our queue handles bursts well. I worked with the team on the overall design and helped monitor it."),
        ("competency", "Testing strategy", "Tell me about a production bug that changed your tests.",
         "A timezone edge broke monthly invoices. I added contract cases for three regions and a midnight UTC integration test; the next parsing regression failed CI before release.",
         "I added a regression test after an invoice bug, but we still mostly test happy paths and I haven't changed the test plan.",
         "Testing is important, and I usually run the suite before opening a pull request."),
        ("competency", "Security", "Describe an authorization weakness you addressed.",
         "A support route trusted an account ID from the request. I reproduced a cross-tenant read, bound the query to the authenticated tenant, and wrote a negative integration test.",
         "A support endpoint accepted an account ID without checking tenant membership. I reproduced a cross-tenant read in staging, changed the query to require the authenticated tenant, and added a two-tenant integration test before shipping.",
         "We follow security best practices and our platform group runs scans for the organization."),
        ("task", "Deployment", "How have you reduced the risk of a backend release?",
         "I added a canary for the payment worker, compared error rate and queue lag for 20 minutes, and automated rollback if either breached its threshold. One release rolled back before customers saw delays.",
         "I added a canary for the payment worker, compared error rate and queue lag for twenty minutes, and configured rollback when either crossed its agreed threshold. One release rolled back before a backlog reached customers.",
         "I am careful during releases and keep an eye on the dashboard while the team deploys."),
        ("competency", "Technical trade-offs", "Tell me about a design disagreement you resolved.",
         "I favored asynchronous settlement, but support needed immediate status. We measured partner latency, chose synchronous acceptance with an outbox for settlement, and documented the failure and retry behavior.",
         "I argued for a queue because queues are always more reliable than synchronous calls. The team disagreed and I accepted their choice, though we didn't test either approach.",
         "I listen to everyone in architecture meetings and try to find a compromise that keeps the team moving."),
    ),
)

DATA = JobDescription(
    "jd-data-engineer", "Senior Data Engineer",
    "Build and operate analytical pipelines. Required areas: SQL, orchestration, data quality, "
    "streaming, warehouse modeling, Python, privacy, observability, backfills, stakeholder reporting.",
    (
        ("technology", "SQL", "How did you fix a slow or incorrect analytical query?",
         "A revenue join duplicated line items. I pre-aggregated by order, compared totals with ledger samples, and indexed settlement date; runtime fell from eleven to two seconds.",
         "I found a duplicate join, pre-aggregated by order, and reconciled a sample against finance. I didn't own the later performance tuning.",
         "I use SQL for everyday reporting. Our warehouse team handles the complicated queries."),
        ("task", "Pipeline orchestration", "Describe a workflow failure you made recoverable.",
         "A late upstream extract made downstream jobs publish partial totals. I added a readiness sensor, idempotent retries, and a quarantine step; two late deliveries recovered without manual edits.",
         "I added an upstream sensor, but the workflow still needs a manual rerun when the feed arrives after the cutoff.",
         "Our workflows generally run on schedule. I check that the dashboard is green each morning."),
        ("competency", "Data quality", "How have you prevented bad data from reaching a report?",
         "I set null-rate and row-count checks on daily orders and blocked publication on schema drift. A source change hit quarantine, and we backfilled only after reconciling source counts.",
         "I defined null-rate and count checks, and one schema drift failed safely. I never checked whether the alert reached the analyst on call.",
         "Analysts usually tell us if a number looks wrong. We can rerun a job when that happens."),
        ("technology", "Streaming", "What streaming system did you operate and what failed?",
         "Our Kafka consumer lagged after a partition skew. I changed the key, replayed one topic from a checkpoint, and measured p95 lag fall from nine minutes to under forty seconds.",
         "I increased Kafka partitions because throughput was low. It helped, although I didn't check whether ordering by customer still held.",
         "We use streaming for near-real-time information. I mostly work with the tables it creates."),
        ("task", "Warehouse modeling", "Explain a model you designed for analysts.",
         "I built an order fact with conformed customer and date dimensions, documented grain, and checked totals against billing before retiring two conflicting dashboards.",
         "I built a fact table and documented its grain. A teammate designed the shared dimensions, and I haven't checked how slowly changing attributes behave.",
         "A good warehouse needs facts and dimensions. Our team follows those concepts."),
        ("technology", "Python", "What Python data tooling did you build?",
         "I wrote a parser for three partner formats with typed validation and quarantined bad rows. Unit fixtures covered each schema version, and replaying a month of files matched the old totals.",
         "I wrote a Python parser for three partner formats, quarantined malformed rows, and added fixtures for each version. Replaying a month of files matched the previous totals before we cut over.",
         "I can use pandas to open CSV files and make plots when analysts ask for them."),
        ("competency", "Privacy", "How did you limit exposure of personal data?",
         "I tokenized customer IDs before analytics ingestion, restricted raw mapping to a separate role, and verified a routine analyst account could not reverse the mapping.",
         "I removed email from one export but didn't inspect historical partitions that may still contain it.",
         "Privacy is handled by our compliance department; I follow whatever policy they publish."),
        ("competency", "Observability", "How do you know a data pipeline is healthy?",
         "I tracked freshness, row count, failure rate, and backlog by source. One partner delay triggered a freshness page while the job itself still returned success, which exposed a gap in our old monitoring.",
         "I added a freshness dashboard and an alert for a missing batch. I haven't assigned an owner for out-of-hours alerts.",
         "I check that scheduled jobs are green. If users complain, we investigate."),
        ("task", "Backfills", "Walk me through a safe historical backfill.",
         "I backfilled six months by partition into a shadow table, checked per-day counts and checksums, and switched the view only after reconciling the full range. A bad day was retried without touching published data.",
         "I reran the full pipeline for older dates. We didn't isolate output, and I think analysts saw some duplicate rows until it finished.",
         "We can rerun jobs for historical dates when needed. I've never planned a large backfill."),
        ("competency", "Stakeholder reporting", "How did you explain an uncertain metric to a stakeholder?",
         "I showed finance the two definitions of active customer, quantified their 8% gap, and agreed on a documented source and cutover date before replacing the dashboard.",
         "I showed finance two definitions of active customer, traced the eight percent difference to returned orders, and agreed on a documented source and cutover date before replacing the dashboard.",
         "I try to make charts clear and use simple language when presenting numbers."),
    ),
)

FRONTEND = JobDescription(
    "jd-frontend", "Senior Frontend Engineer",
    "Own an accessible and performant customer web app. Assess React, TypeScript, accessibility, "
    "state management, testing, design collaboration, performance, error handling, security, and delivery.",
    (
        ("technology", "React", "Describe a React component you redesigned.",
         "I split a large checkout form into stable field groups, removed derived state, and profiled renders. Keystroke delay on older phones fell from about 180 to 45 milliseconds.",
         "I split the checkout form into stable field groups, removed duplicated derived state, and profiled render counts on an older Android phone. Keystroke delay fell from roughly 170 to 50 milliseconds.",
         "I use React components every day and prefer hooks because they make code modern."),
        ("technology", "TypeScript", "Where did TypeScript catch a real product defect?",
         "A nullable shipping estimate crossed an API boundary as a number. I modeled the missing state explicitly, fixed both callers, and added a contract fixture that prevented the blank delivery date returning.",
         "I added a union type for the shipping response. It helped with one screen; other consumers still cast the payload to any.",
         "TypeScript makes JavaScript safer. I generally copy types from neighboring files."),
        ("competency", "Accessibility", "Tell me about an accessibility defect you fixed.",
         "A screen reader skipped checkout errors. I added an error summary, restored focus after validation, and tested keyboard and NVDA flows with a user before release.",
         "I replaced clickable divs with buttons, fixed focus after validation, and tested the error summary with a screen reader. A user found a dialog trap in the same session, which I fixed before release.",
         "We aim for accessible interfaces and use a component library with good defaults."),
        ("task", "State management", "How did you simplify difficult UI state?",
         "I removed duplicate cart totals from local and global stores, made server data authoritative, and tested offline retry behavior. We stopped seeing inconsistent totals between checkout steps.",
         "I moved cart data to a global store because global state is always simpler. We still sometimes show an old total after retry.",
         "I choose state libraries based on what the project already has and keep code tidy."),
        ("competency", "Testing", "What browser regression did you prevent with a test?",
         "A date picker failed when navigating by keyboard. I added a browser test for focus, selection, and Escape, and it caught a later refactor that reintroduced the trap.",
         "I added a browser regression test for keyboard focus, date selection, and Escape after a date picker trapped focus. It caught the same defect during a later component refactor.",
         "Our app has unit tests and I run them before merging."),
        ("competency", "Design collaboration", "Tell me about resolving a design and implementation conflict.",
         "The proposed mobile drawer covered the submit action. I prototyped two placements with design, tested thumb reach with users, and we moved the action above the safe-area inset.",
         "I flagged a spacing issue to design and they changed the mock. I didn't check it on a real phone afterward.",
         "I follow Figma closely and ask designers when something is unclear."),
        ("task", "Web performance", "What performance issue did you diagnose in production?",
         "A product page spent 600 milliseconds decoding oversized images. I served responsive sources, measured field LCP by device class, and cut p75 LCP from 3.4 to 2.5 seconds.",
         "I lazy-loaded images below the fold and the page felt quicker locally. I didn't compare field data.",
         "Fast websites matter and I try to avoid unnecessary dependencies."),
        ("task", "Error handling", "How did you help users recover from a failed request?",
         "A payment timeout left users unsure whether they had paid. I used an idempotent status lookup, showed a pending state, and offered retry only after confirmation; duplicate support cases fell.",
         "I added a toast for a failed request. It tells users to retry, but I don't know whether a previous attempt may still succeed.",
         "I show friendly error messages so users know something went wrong."),
        ("competency", "Frontend security", "What client-side security issue did you address?",
         "An internal note was rendered as HTML in an admin view. I removed the raw HTML path, escaped stored content, and added a test using a script payload that had executed in staging.",
         "I enabled sanitization on a rich-text field but never checked whether links and attributes were handled.",
         "The backend is responsible for security. I avoid putting passwords in code."),
        ("competency", "Delivery", "How did you release a risky UI change safely?",
         "We released a new checkout behind a cohort flag, watched completion and error rates, and rolled back a mobile-only regression within 15 minutes. We kept the old route until support signed off.",
         "I released checkout behind a cohort flag, watched completion and error rates, and rolled back a mobile-only regression within fifteen minutes. The old route stayed available until support confirmed recovery.",
         "I merge after review and trust the deployment pipeline to handle releases."),
    ),
)

PLATFORM = JobDescription(
    "jd-platform", "Platform Engineer",
    "Operate cloud infrastructure for a growing service. Assess Kubernetes, infrastructure as code, "
    "CI/CD, observability, incident response, networking, secrets, reliability, cost, and collaboration.",
    (
        ("technology", "Kubernetes", "Tell me about a Kubernetes workload you stabilized.",
         "A worker restarted under load. I traced memory growth to buffering, fixed the leak, set requests from measured usage, and verified zero restarts across two peak periods.",
         "I raised the memory limit after restarts and checked the next deploy. I didn't find why usage rose.",
         "Our applications run on Kubernetes and it generally makes scaling easy."),
        ("task", "Infrastructure as code", "Describe an infrastructure change you made repeatable.",
         "I moved manual database replica setup into Terraform modules, imported existing resources, reviewed a no-op plan, and validated restoration in a test region.",
         "I moved manual replica setup into a Terraform module, imported existing resources, checked a no-op plan, and used it to recreate the replica in a test region before touching production.",
         "Terraform is useful for consistent environments. I usually apply plans others prepare."),
        ("task", "CI/CD", "How did you improve deployment safety or speed?",
         "I parallelized independent tests, kept migrations serial, and added a canary health gate. Pipeline median fell from 34 to 16 minutes without increasing rollback rate.",
         "I changed the test job to run earlier. I haven't measured total pipeline time or checked if failures surface sooner.",
         "We use CI and code review, so releases are mostly automated."),
        ("competency", "Observability", "What signals helped you diagnose a hard failure?",
         "Traces showed connection-pool wait climbing while CPU stayed flat. I isolated an export workload, added pool saturation alerts, and watched p95 request time return below 300 milliseconds.",
         "I saw pool saturation and moved exports to another worker pool. I set an alert but it sometimes pages on harmless bursts.",
         "I look at logs and dashboards when something appears wrong."),
        ("competency", "Incident response", "Describe a production incident you led.",
         "A routing change isolated one region. I coordinated rollback, compared error rates by zone, and wrote the timeline and follow-up tests. Traffic recovered in 28 minutes.",
         "I joined the bridge and restarted affected pods. Networking found the routing fault later; I didn't coordinate the investigation.",
         "Our on-call process is good, and the team works together during incidents."),
        ("technology", "Networking", "How did you trace a connectivity problem?",
         "One subnet could not reach a partner endpoint. I compared routes and packet captures from healthy and failing nodes, found an egress ACL change, and verified access after rollback.",
         "I compared routes and packet captures from healthy and failing subnets, found an egress ACL change, and verified the partner endpoint recovered after the rule was rolled back.",
         "I know basic DNS and TCP concepts, but specialists usually handle networking."),
        ("task", "Secrets management", "How did you rotate a credential without outage?",
         "I issued overlapping database credentials, deployed readers that accepted both, rotated writers, and revoked the old key after checking zero old-key connections.",
         "I rotated a credential in our vault and restarted services. One worker failed until we updated its environment variable.",
         "We store secrets in a vault, so they're secure by default."),
        ("competency", "Reliability", "How did you use an SLO to make a decision?",
         "We set a 99.9% checkout availability objective and a rolling error budget. After two incidents consumed most of it, we postponed a risky deploy and funded retry testing.",
         "We have an uptime target on a dashboard, but I don't know what decision changes when it is missed.",
         "Reliability is always a priority, and I work to keep the platform stable."),
        ("task", "Cloud cost", "What cloud cost did you reduce and how did you verify it?",
         "Billing showed idle staging nodes. I scheduled noncritical clusters off overnight, monitored test queue failures, and confirmed monthly spend fell by $1,800 after four weeks.",
         "I suggested reducing staging capacity, but I don't know whether the change saved money or delayed tests.",
         "I try not to waste compute resources and use sensible instance sizes."),
        ("competency", "Collaboration", "Tell me about a platform change adopted by other teams.",
         "I interviewed three service teams about deploy pain, built a small self-service rollback tool, and paired with each on its first use. Support tickets dropped after the rollout.",
         "I interviewed three service teams about deployment failures, built a self-service rollback tool for their common case, and paired with each team on its first use. Support tickets fell after rollout.",
         "I keep documentation current and am approachable when other teams need help."),
    ),
)

PRODUCT = JobDescription(
    "jd-product-analyst", "Product Analyst",
    "Analyze product behavior and guide decisions. Assess SQL, experiment design, metric definition, "
    "dashboarding, segmentation, forecasting, data quality, stakeholder communication, privacy, and prioritization.",
    (
        ("technology", "SQL", "Tell me about an analysis where SQL correctness mattered.",
         "A funnel query counted repeat sessions as new users. I changed the grain to first eligible session, checked results against event samples, and corrected the reported conversion rate from 12% to 9%.",
         "A funnel join counted repeat sessions as new users. I changed the grain to first eligible session, checked a sample against event logs, and corrected conversion from twelve to nine percent.",
         "I write SQL to pull data and usually start from existing dashboard queries."),
        ("competency", "Experiment design", "Describe an experiment you designed and interpreted.",
         "We randomized search ranking by user, preselected checkout starts as primary, and held exposure for two weeks. Clicks rose but starts did not, so I advised against rollout.",
         "I analyzed an A/B test and found more clicks. I didn't know assignment was by session, so repeat visitors could see both variants.",
         "A/B tests are a good way to see what users like. Product usually defines them."),
        ("task", "Metric definition", "How did you resolve two conflicting definitions of a metric?",
         "Finance and product counted active customers differently. I quantified the 8% gap, traced it to returns, and documented one definition and a cutover date for both teams.",
         "Finance and product used conflicting active-customer rules. I quantified their eight percent gap, traced it to returns, and documented one definition and a cutover date for both dashboards.",
         "I use the numbers on the approved dashboard to avoid confusion."),
        ("technology", "Dashboarding", "What dashboard changed a team's behavior?",
         "I built a checkout drop-off dashboard by device and stage, validated event completeness, and watched the mobile team fix a payment step that had a 20% higher abandonment rate.",
         "I built a device breakdown dashboard and shared it. I didn't track whether anyone acted on it.",
         "I make charts that are clear and visually appealing for stakeholders."),
        ("competency", "Segmentation", "How did segment analysis change a conclusion?",
         "Aggregate retention rose, but I split by acquisition cohort and saw a low-retention paid cohort shrinking. Within each cohort retention was flat, so I warned against crediting the onboarding change.",
         "I compared retention by channel, but the sample in one channel was small and I didn't examine that uncertainty.",
         "Different customer groups behave differently, so I usually apply filters in reports."),
        ("task", "Forecasting", "How did you assess whether a forecast was useful?",
         "I used rolling backtests against seasonal naive for weekly demand, reported error by store age, and kept a fallback for new stores where the model underperformed.",
         "I fit a trend line to weekly demand and used it for planning. I didn't compare it with a seasonal baseline.",
         "Forecasting is useful for planning; finance normally owns the forecast."),
        ("competency", "Data quality", "What data issue did you discover before publication?",
         "A mobile event lost its user ID after an app update. I compared null rates by version, blocked the weekly report, and used a repaired event feed after matching counts with server logs.",
         "I traced a user-ID null spike to a mobile release, blocked the weekly report, and matched repaired event counts against server logs before publishing corrected numbers.",
         "I check charts for obvious anomalies before sending them."),
        ("competency", "Stakeholder communication", "How did you explain a result that a stakeholder disliked?",
         "Marketing expected a campaign lift. I showed confidence intervals, the preselected measure, and a segment breakdown, then agreed on a follow-up test rather than changing the metric afterward.",
         "Marketing expected a campaign lift. I showed the interval around the preselected outcome and a segment breakdown, then agreed on a follow-up test instead of changing the metric after seeing results.",
         "I try to communicate clearly and respectfully when results are disappointing."),
        ("task", "Privacy", "How did privacy requirements shape an analysis?",
         "I replaced user-level exports with cohort aggregates, suppressed groups under 20 people, and verified analysts could no longer query the raw identifier through the shared view.",
         "I removed emails from an export. I didn't check whether other identifiers could still join it back to users.",
         "I know data privacy matters, and the company has rules we follow."),
        ("competency", "Prioritization", "How did you choose between competing analysis requests?",
         "I estimated decision value and effort for three requests, chose a checkout failure analysis ahead of a cosmetic dashboard, and reviewed its effect with product after the fix shipped.",
         "I prioritized the loudest stakeholder request so the team could move quickly. I didn't ask what decision it would change.",
         "I organize requests in a backlog and work on the highest priority item."),
    ),
)

JOBS = (BACKEND, DATA, FRONTEND, PLATFORM, PRODUCT)


def _personas() -> tuple[Persona, ...]:
    result: list[Persona] = []
    for job in JOBS:
        for tier, answer_index in (("strong", 3), ("mixed", 4), ("weak", 5)):
            answers = tuple(
                PersonaAnswer(target=row[1], question=row[2], answer=row[answer_index])
                for row in job.cases
            )
            result.append(Persona(f"{job.jd_id}-{tier}", job.jd_id, tier, answers))
    assert len(result) == 15 and all(len(p.answers) == 10 for p in result)
    return tuple(result)


PERSONAS = _personas()
