"""Pilot-only inputs: disjoint from development and final evaluation."""
# ruff: noqa: E501 - pilot answer strings are deliberately single-line dataset rows.

from evals.datasets.evaluation.followup_cases_sample import FollowUpCase
from evals.datasets.evaluation.personas import JobDescription
from evals.datasets.evaluation.personas_sample import Persona, PersonaAnswer

FOLLOWUPS = (
    FollowUpCase("pilot-a1", "Redis", "How did you handle stale cache entries?", "We added a cache to the catalog because reads were slow, but I don't remember what happened when a product was edited."),
    FollowUpCase("pilot-a2", "Terraform", "What infrastructure change did you automate?", "I imported our manually created test bucket, checked a no-op plan, and used the module to recreate it in another region."),
    FollowUpCase("pilot-a3", "Analytics", "Tell me how you validated a business metric.", "Finance owned the definition. I used their dashboard but never checked the event data."),
    FollowUpCase("pilot-a4", "Testing", "What test found a bug before release?", "A contract test caught a renamed field in a partner response; I updated the parser and added a fixture for the old format."),
    FollowUpCase("pilot-a5", "Design", "How did you resolve a usability complaint?", "Someone said the form was confusing. I changed the order of the fields, and it seemed better afterward."),
    FollowUpCase("pilot-a6", "Monitoring", "What did you alert on for your service?", "We watched request errors by route, paged on sustained 5xx rate, and tested the page during a scheduled failure drill."),
)

JOB = JobDescription(
    "pilot-support", "Support Systems Engineer",
    "Maintain an internal ticketing platform. Assess Python, SQL, incident response, API integration, and communication.",
    (
        ("technology", "Python", "Tell me about a Python automation you shipped.",
         "I wrote a Python ticket deduplicator, tested it against a month's exports, and reduced duplicate assignments by 30%. I reviewed false merges with support, changed the matching key, and deployed the job behind a daily review queue before making it automatic.",
         "I wrote a small Python cleanup script that a teammate reviewed, but I didn't schedule or monitor it.",
         "I can edit Python scripts, although I mostly run the ones the team already has."),
        ("technology", "SQL", "What SQL query did you have to correct?",
         "A one-to-many join inflated open-ticket counts, so I grouped events per ticket and reconciled totals with the source list.",
         "I fixed a join that showed duplicates, but I didn't check counts against the source system.",
         "I use saved SQL queries to look up ticket records."),
        ("competency", "Incident response", "Tell me about a support platform outage.",
         "When ticket ingestion stopped, I traced it to an expired webhook token, rotated it, replayed the queue, and added an expiry alert.",
         "I joined the outage bridge and restarted a worker; another engineer found the token issue.",
         "The team handles outages quickly and keeps stakeholders updated."),
        ("task", "API integration", "How did you make a partner integration reliable?",
         "I made webhook writes idempotent by partner event ID and verified duplicate deliveries did not create duplicate tickets.",
         "I added retries to the webhook handler, but I didn't test duplicate delivery.",
         "Our system integrates with several partner APIs and generally works well."),
        ("competency", "Communication", "How did you explain a technical problem to support staff?",
         "I showed agents which tickets were delayed, gave an hourly recovery estimate, and confirmed with them that the backlog cleared.",
         "I told agents there was an issue and sent another message once engineering fixed it.",
         "I try to use simple language when explaining technical issues."),
    ),
)

PERSONAS = tuple(
    Persona(f"pilot-{tier}", JOB.jd_id, tier,
            tuple(PersonaAnswer(row[1], row[2], row[index]) for row in JOB.cases))
    for tier, index in (("strong", 3), ("mixed", 4), ("weak", 5))
)

JOBS = (JOB,)
