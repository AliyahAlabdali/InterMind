"""DEVELOPMENT set: validates the deterministic grounding rule's mechanics. NOT evaluation data.

PROTOCOL v1.0, section 3. These cases exist to calibrate and stress ``harness.grounding`` -
THETA, the guards, and the minimum-length rule were chosen against *this* file and nothing
else. No case here may appear in ``datasets/evaluation/``, and no number computed from this
file may ever be reported as an InterMind performance metric. Its only outputs are a frozen
threshold and a documented account of where the rule is blind.

``semantic_truth`` is the author's judgement of whether the evidence is genuinely supported by
the answer. That is legitimate here, because what is being validated is the *routing rule*, not
InterMind: the question asked of each case is "does the rule reach a safe conclusion", and the
rule only ever has three options - auto-accept, or route to a human, or (never) auto-reject.

The error that matters is a **false accept**: the rule auto-accepts something a human would
call unsupported. A case routed to adjudication is never an error, only a cost. The target for
freezing THETA is therefore zero false accepts on this set, with adjudication load kept
reasonable - not maximum agreement with ``semantic_truth``.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GroundingDevCase:
    case_id: str
    category: str
    answer: str
    evidence: str
    semantic_truth: str  # "supported" | "unsupported"
    note: str


#: One realistic answer reused across many cases, so differences in verdict are attributable to
#: the evidence string rather than to a different answer.
K8S = (
    "So we moved the payment service onto Kubernetes about two years ago - I wrote the Helm "
    "charts myself and set up the horizontal pod autoscaler. Honestly the rollout was rough, "
    "we had a bad deploy that took checkout down for about twenty minutes before I added "
    "readiness probes."
)

PG = (
    "The slow one was a report query joining orders to line items. It was doing a sequential "
    "scan over about four million rows. I added a composite index on tenant id and created at, "
    "and it went from roughly nine seconds to under two hundred milliseconds. I checked it with "
    "explain analyze first rather than guessing."
)

KAFKA = (
    "I have not really used Kafka in anger. I read the docs and did a tutorial once, but every "
    "queue I have shipped was SQS or Celery with Redis as the broker."
)

TEAM = (
    "We were a team of six and we shipped the whole migration in a quarter. There was a lot of "
    "coordination with the data team and the rollout went pretty smoothly overall."
)

CASES: tuple[GroundingDevCase, ...] = (
    # --- exact / near-exact -------------------------------------------------------------
    GroundingDevCase(
        "exact-quote",
        "exact",
        K8S,
        "I wrote the Helm charts myself",
        "supported",
        "Contiguous substring. Must land in Tier 1.",
    ),
    GroundingDevCase(
        "exact-with-punctuation",
        "exact",
        PG,
        "I checked it with explain analyze first, rather than guessing.",
        "supported",
        "Differs only in punctuation; normalisation should still make this Tier 1.",
    ),
    # --- synonym-heavy valid paraphrase -------------------------------------------------
    GroundingDevCase(
        "paraphrase-synonym-heavy",
        "valid_paraphrase",
        K8S,
        "configured horizontal pod autoscaling and readiness probes for the payment service",
        "supported",
        "'set up'->'configured', 'autoscaler'->'autoscaling'. Genuine paraphrase; expected to "
        "fall below THETA and be adjudicated. Demonstrates the rule is strict, not generous.",
    ),
    GroundingDevCase(
        "paraphrase-inflection",
        "valid_paraphrase",
        PG,
        "added a composite index on tenant id and created at to remove a sequential scan",
        "supported",
        "Almost all content tokens present; inflection and reordering only.",
    ),
    GroundingDevCase(
        "paraphrase-restated",
        "valid_paraphrase",
        PG,
        "diagnosed the slow report query with explain analyze before changing anything",
        "supported",
        "Faithful restatement using mostly the answer's own words.",
    ),
    # --- short evidence strings ---------------------------------------------------------
    GroundingDevCase(
        "short-single-token",
        "short",
        K8S,
        "Kubernetes",
        "unsupported",
        "One token. Naming a technology the answer mentions is not evidence of anything about "
        "the candidate. MIN_CONTENT_TOKENS_FOR_LEXICAL must block auto-accept.",
    ),
    GroundingDevCase(
        "short-two-token",
        "short",
        K8S,
        "used Kubernetes",
        "supported",
        "Defensible but coverage would be a coarse 1.0 on two tokens. Must be adjudicated, not "
        "auto-accepted - the same shape as the unsupported case above.",
    ),
    GroundingDevCase(
        "short-three-token-overclaim",
        "short",
        TEAM,
        "led the migration",
        "unsupported",
        "'led' is absent; the answer says 'we'. A three-token string must not auto-accept.",
    ),
    # --- negation -----------------------------------------------------------------------
    GroundingDevCase(
        "negation-inverted",
        "negation",
        KAFKA,
        "has used Kafka in production queues",
        "unsupported",
        "Inverts the answer. Coverage is high because tokens overlap.",
    ),
    GroundingDevCase(
        "negation-preserved",
        "negation",
        KAFKA,
        "has not really used Kafka in anger",
        "supported",
        "Correctly negated and near-verbatim, but 'has' vs the answer's 'have' defeats the "
        "exact-substring test, so the negation guard routes it to a human. Supported evidence "
        "sent to review: a cost, not an error, and the conservative direction.",
    ),
    GroundingDevCase(
        "negation-added",
        "negation",
        PG,
        "did not verify the query plan before adding the index",
        "unsupported",
        "Adds a negation the answer contradicts. Negation guard must route this to a human.",
    ),
    # --- changed quantities -------------------------------------------------------------
    GroundingDevCase(
        "quantity-changed",
        "quantity",
        PG,
        "reduced the report query from nine seconds to under twenty milliseconds",
        "unsupported",
        "'two hundred' -> 'twenty'. Written as words, so the numeric guard cannot see it. A "
        "known blind spot the protocol must state.",
    ),
    GroundingDevCase(
        "quantity-digit-changed",
        "quantity",
        PG,
        "scanned about 40 million rows before the index was added",
        "unsupported",
        "Digit-bearing token '40' absent from the answer (which says four million). The numeric "
        "guard must catch this.",
    ),
    GroundingDevCase(
        "quantity-digit-correct",
        "quantity",
        K8S,
        "checkout was down for about 20 minutes after a bad deploy",
        "unsupported",
        "'20' as a digit is absent (answer says 'twenty'), so the guard routes to adjudication "
        "even though the claim is true. Over-routing, which is the safe direction.",
    ),
    # --- changed entities ---------------------------------------------------------------
    GroundingDevCase(
        "entity-swapped-service",
        "entity",
        K8S,
        "moved the checkout service onto Kubernetes and wrote its Helm charts",
        "unsupported",
        "'payment' -> 'checkout'. Both words appear in the answer but in different roles, so "
        "coverage stays high. Bag-of-words cannot detect the role swap.",
    ),
    GroundingDevCase(
        "entity-swapped-tech",
        "entity",
        KAFKA,
        "shipped queues using SQS and Celery with Redis as the broker",
        "supported",
        "Entities correct; should be close to exact.",
    ),
    GroundingDevCase(
        "entity-wrong-tech",
        "entity",
        PG,
        "added a composite index on tenant id and created at in MongoDB",
        "unsupported",
        "Adds an entity never mentioned. One extra content token should drop coverage.",
    ),
    # --- changed technical qualifiers ---------------------------------------------------
    GroundingDevCase(
        "qualifier-scope-widened",
        "qualifier",
        K8S,
        "has production experience operating Kubernetes clusters at scale",
        "unsupported",
        "'at scale' and 'clusters' are extrapolation from one service. Evaluative conclusion "
        "rather than something said.",
    ),
    GroundingDevCase(
        "qualifier-sole-ownership",
        "qualifier",
        TEAM,
        "personally delivered the entire migration within a quarter",
        "unsupported",
        "Converts 'we, a team of six' into sole ownership - the most consequential qualifier "
        "error a hiring report can make.",
    ),
    GroundingDevCase(
        "qualifier-hedge-dropped",
        "qualifier",
        TEAM,
        "the rollout went smoothly",
        "supported",
        "Drops 'pretty' and 'overall'. Short, so adjudication rather than auto-accept.",
    ),
    # --- high overlap, changed relationship ---------------------------------------------
    GroundingDevCase(
        "relation-reversed-causality",
        "relation",
        K8S,
        "added readiness probes which caused a bad deploy to take checkout down",
        "unsupported",
        "Reverses cause and effect using only the answer's own tokens. Coverage near 1.0. The "
        "clearest demonstration that coverage is not semantics.",
    ),
    GroundingDevCase(
        "relation-reversed-order",
        "relation",
        PG,
        "added the composite index first and then ran explain analyze to confirm the plan",
        "unsupported",
        "Reverses the stated order; every content token is present.",
    ),
    GroundingDevCase(
        "relation-attribution-shifted",
        "relation",
        K8S,
        "the team wrote the Helm charts and set up the horizontal pod autoscaler",
        "unsupported",
        "Shifts attribution from 'I' to 'the team'; 'I' is a stopword so it is invisible to the "
        "rule. A documented blind spot.",
    ),
    # --- clearly unsupported ------------------------------------------------------------
    GroundingDevCase(
        "unsupported-fabricated",
        "unsupported",
        K8S,
        "managed a multi-region cluster migration with zero downtime",
        "unsupported",
        "Fabricated and contradicts the stated twenty-minute outage.",
    ),
    GroundingDevCase(
        "unsupported-silence",
        "unsupported",
        PG,
        "no mention of connection pooling or read replicas",
        "unsupported",
        "Reports silence as a finding - explicitly forbidden by the prompt. Note the negation "
        "guard also catches it.",
    ),
    GroundingDevCase(
        "unsupported-generic-praise",
        "unsupported",
        TEAM,
        "demonstrates strong ownership and technical leadership",
        "unsupported",
        "Pure evaluative language with no lexical anchor. Coverage should be near zero.",
    ),
)
