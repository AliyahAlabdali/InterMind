"""EVALUATION inputs - representative sample of the follow-up dataset. INPUTS ONLY.

Protocol v1.0 section 4. This file contains no labels, no author-intended verdicts, no category
names, and no InterMind predictions. Case ids are opaque and the order is shuffled, so neither
position nor identifier carries information about the expected answer.

No separately sealed author-intent file was created. The independent human labels are the only
reference standard; no construction-intent comparison is claimed.

This sample is 12 of the planned 90 cases. It is shown for review of style, realism and
difficulty, not for labelling. Answers are written as spoken candidate speech - hedges, filler,
self-correction, mid-sentence repair - because that is what the speech path actually produces,
and a dataset of clean written prose would not test the evaluator on its real input.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FollowUpCase:
    """One labelling unit. Everything here is shown to the reviewer; nothing else exists."""

    case_id: str
    target: str
    question: str
    answer: str
    #: Shown only when the answer responds to an earlier turn on the same target.
    prior_exchange: tuple[tuple[str, str], ...] = ()


CASES: tuple[FollowUpCase, ...] = (
    FollowUpCase(
        case_id="fu-0431",
        target="PostgreSQL",
        question="Tell me about a time you had to improve the performance of a database query.",
        answer=(
            "Yeah so there was a report that was timing out for one of our bigger tenants. I "
            "pulled the plan with explain analyze and it was doing a sequential scan on the "
            "line items table, which was something like four million rows at that point. Added "
            "a composite index on tenant_id and created_at because that's what the where clause "
            "actually filtered on. Took it from about nine seconds to maybe two hundred "
            "milliseconds. The thing I'd do differently is I didn't check whether the index "
            "slowed down our bulk inserts until a week later."
        ),
    ),
    FollowUpCase(
        case_id="fu-0117",
        target="Kubernetes",
        question="How have you worked with Kubernetes?",
        answer=(
            "We run everything on it, the whole platform. It's been really good for us "
            "honestly, way better than the VM setup we had before — deployments are much less "
            "scary now and we can scale things up when we need to."
        ),
    ),
    FollowUpCase(
        case_id="fu-0902",
        target="Apache Kafka",
        question="Describe your experience building event-driven systems with Kafka.",
        answer=(
            "I'm going to be straight with you, I haven't used Kafka properly. I did a tutorial "
            "on it a while back and I've read about partitions and consumer groups, but every "
            "queueing thing I've actually put in production has been SQS, or Celery with Redis "
            "behind it. So I know the shape of the problem but not that tool."
        ),
    ),
    FollowUpCase(
        case_id="fu-0288",
        target="Incident response",
        question="Walk me through how you handled a production incident.",
        answer=(
            "Checkout went down on a Friday afternoon, about twenty minutes of downtime. It was "
            "a deploy I'd pushed — the new pods were taking traffic before the app had finished "
            "booting, so the load balancer was routing to things that weren't ready. I rolled it "
            "back first and then added readiness probes before redeploying. Wrote it up on "
            "Monday and we made readiness probes a required field in the chart template."
        ),
    ),
    FollowUpCase(
        case_id="fu-0654",
        target="System design",
        question="How would you design a service to handle payment authorisation at scale?",
        answer=(
            "Right, so — sorry, when you say at scale do you mean like, requests per second, or "
            "are you more interested in how I'd handle the multi-region side of it? Because "
            "those are pretty different answers."
        ),
    ),
    FollowUpCase(
        case_id="fu-0775",
        target="Monitoring and observability",
        question="What's your experience with monitoring and observability?",
        answer="I set up the dashboards and the alerting for our services.",
    ),
    FollowUpCase(
        case_id="fu-0046",
        target="Python",
        question="Tell me about a non-trivial piece of Python you've written.",
        answer=(
            "So I'd say the async scraper. It was pulling from about forty supplier APIs and the "
            "original version did them one at a time, took like an hour. I rewrote it with "
            "asyncio and a semaphore to cap concurrency at — I think twenty? — because a couple "
            "of the suppliers started rate limiting us. Got it down to about four minutes. The "
            "annoying bit was that two of the APIs didn't like keep-alive so I had to special "
            "case those with their own session."
        ),
    ),
    FollowUpCase(
        case_id="fu-0513",
        target="Code review",
        question="How do you approach reviewing other people's code?",
        answer=(
            "I think code review is really important for knowledge sharing across the team. I "
            "try to be constructive and not block people unnecessarily, and I always try to "
            "leave at least one positive comment as well as the critical ones. It's about "
            "raising the bar collectively rather than gatekeeping."
        ),
    ),
    FollowUpCase(
        case_id="fu-0369",
        target="Docker",
        question="How have you used Docker in your work?",
        answer=(
            "We containerised the API. I wrote the Dockerfile — multi-stage build, so the final "
            "image only has the runtime deps, it's about ninety megs. Non-root user. I didn't "
            "do the Compose setup for local dev, that was already there when I joined."
        ),
    ),
    FollowUpCase(
        case_id="fu-0820",
        target="Terraform",
        question="Describe how you've managed infrastructure as code.",
        answer=(
            "Yeah, all our infra is in Terraform. State's in an S3 backend with DynamoDB "
            "locking. We've got modules for the standard service shape so spinning up a new "
            "service is mostly just filling in variables. I've definitely had the experience of "
            "someone running apply locally and clobbering state, which is why we moved it into "
            "CI only."
        ),
    ),
    FollowUpCase(
        case_id="fu-0197",
        target="Mentoring",
        question="Have you mentored more junior engineers?",
        answer=(
            "A bit, yeah. I mean we had two juniors join last year and I was kind of the person "
            "they'd come to with questions. I wouldn't say I had a formal mentoring thing set "
            "up, it was more ad hoc than that, but I did quite a lot of pairing with one of "
            "them when she was picking up the payments codebase."
        ),
    ),
    FollowUpCase(
        case_id="fu-0742",
        target="PostgreSQL",
        question="You mentioned indexing. How do you decide what to index?",
        answer=(
            "Honestly a lot of it is looking at what the query planner is actually doing rather "
            "than guessing from the query text. If I see a sequential scan on a big table I'll "
            "look at what's in the where clause and the order by, and the order of the columns "
            "in a composite index matters a lot — leftmost prefix has to match how you're "
            "filtering or it won't get used at all."
        ),
        prior_exchange=(
            (
                "Tell me about a time you had to improve the performance of a database query.",
                "There was a report query timing out. I added an index and it got much faster.",
            ),
        ),
    ),
)
