"""EVALUATION inputs - persona construction rules and a worked sample. INPUTS ONLY.

Protocol v1.0 section 5. Personas drive the discrimination gate and supply the interviews from
which evidence strings are harvested for section 3.

Construction rules, binding on all 15 persona-JD combinations
-------------------------------------------------------------
**Written against the job description's targets only.** The answer-evaluation prompt was not
consulted while writing these. If personas were written against the rubric the evaluator is
scored by, the discrimination result would measure circularity rather than judgment.

**Strong** - describes real, specific work: named systems, concrete decisions, quantities where
natural, and at least one admitted limitation or mistake per interview. Critically, it must
*not* read as an enumeration of the JD's keyword list; wherever possible the competency is
demonstrated through a described decision rather than by naming the technology. A persona that
simply recites every expected term would test keyword overlap, not comprehension.

**Mixed** - genuinely strong on three or four targets and genuinely thin on three or four, with
at least one confidently-stated incorrect claim somewhere in the set. Not an artificial midpoint
and not uniformly mediocre: an uneven real candidate, whose average is a consequence of the
unevenness rather than the design goal.

**Weak** - fluent, cooperative, plausible and substantively empty. Generalities, deflection to
what the team did, tutorial-level description of what a technology is rather than what the
candidate did with it, process language standing in for experience. **Never incoherent and
never obviously unqualified** - a weak persona that sounds incompetent makes the metric
worthless, because separating competence from incoherence is trivial and is not what a hiring
tool is for.

All three personas answer the *same* targets for a given JD, so score differences are
attributable to answer quality alone.

Known limitation: these are scripted, not transcribed from real candidates. No speech-to-text
disfluency of the kind the live system receives, and no adversarial behaviour. This is the
ceiling on external validity and is recorded in PROTOCOL.md section 15.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PersonaAnswer:
    target: str
    question: str
    answer: str


@dataclass(frozen=True)
class Persona:
    persona_id: str
    jd_id: str
    #: "strong" | "mixed" | "weak" - the construction tier, used for analysis grouping only.
    tier: str
    answers: tuple[PersonaAnswer, ...]


#: Worked sample: three personas, one JD, three of its ten targets. Shown for review of realism
#: and of whether the tiers are genuinely distinguishable without being caricatures.
SAMPLE: tuple[Persona, ...] = (
    Persona(
        persona_id="p-sbe-strong",
        jd_id="jd-senior-backend",
        tier="strong",
        answers=(
            PersonaAnswer(
                target="PostgreSQL",
                question="Tell me about your experience with relational database design.",
                answer=(
                    "The piece I'd point to is the tenancy model on the payments service. We "
                    "started with a tenant_id column on every table and shared indexes, which "
                    "was fine until one customer was about forty times bigger than the median "
                    "and their queries started affecting everyone else's latency. I moved them "
                    "onto partitioned tables by tenant, which meant the planner could prune "
                    "instead of scanning. What I got wrong was the migration order — I added "
                    "the partitioning before I'd checked how our ORM generated the insert "
                    "statements, so for about two days writes were going to the default "
                    "partition and I had to backfill them."
                ),
            ),
            PersonaAnswer(
                target="Incident response",
                question="Walk me through a production incident you handled.",
                answer=(
                    "We had authorisation failures spike to about thirty percent for eleven "
                    "minutes. The thing that made it hard was that our dashboards were green — "
                    "the service was healthy, it was the upstream processor returning a new "
                    "error code we were treating as a generic failure and retrying into. So we "
                    "were amplifying their problem. I shut off the retry path first to stop "
                    "making it worse, then we failed over to the secondary processor. The real "
                    "fix was that we'd been retrying on any non-2xx, which I'd written, so "
                    "afterwards I made the retry policy explicit about which codes are "
                    "actually retryable."
                ),
            ),
            PersonaAnswer(
                target="Code review",
                question="How do you approach reviewing other people's code?",
                answer=(
                    "I try to separate the things that are actually wrong from the things I'd "
                    "just have done differently, and only block on the first kind. If I've got "
                    "a stylistic preference I'll say it's a preference. The question I ask most "
                    "often is what happens on the second call — a lot of bugs I've found in "
                    "review are idempotency problems that look fine on the happy path. And if "
                    "I've left more than about five comments I'll usually just go and talk to "
                    "the person instead, because at that point the design is the issue, not the "
                    "code."
                ),
            ),
        ),
    ),
    Persona(
        persona_id="p-sbe-mixed",
        jd_id="jd-senior-backend",
        tier="mixed",
        answers=(
            PersonaAnswer(
                target="PostgreSQL",
                question="Tell me about your experience with relational database design.",
                answer=(
                    "I've done a fair bit of schema work. Normalising things properly, foreign "
                    "keys, that sort of thing. On the last project I set up the migrations with "
                    "Alembic and we kept everything versioned. I'd say my strongest bit is "
                    "probably writing the queries rather than designing the schema from "
                    "scratch, I've usually come into something that already existed."
                ),
            ),
            PersonaAnswer(
                target="Incident response",
                question="Walk me through a production incident you handled.",
                answer=(
                    "We had a memory leak in one of the workers that would build up over about "
                    "a week and then it'd start OOMing. The fix in the end was just a cron that "
                    "restarted them nightly, which I know isn't a real fix, but we never got to "
                    "the bottom of it. I think it was something in the PDF library holding onto "
                    "file handles. Python's garbage collector doesn't handle circular "
                    "references, so if the library had a cycle in it that'd explain why it never "
                    "got cleaned up."
                ),
            ),
            PersonaAnswer(
                target="Code review",
                question="How do you approach reviewing other people's code?",
                answer=(
                    "Pretty thoroughly — I'll read the whole diff rather than skimming. I look "
                    "for whether there are tests, whether the naming makes sense, and whether "
                    "there's anything that looks like it'd break under load. I'd rather ask a "
                    "question than tell someone they're wrong, especially if they know that part "
                    "of the codebase better than me."
                ),
            ),
        ),
    ),
    Persona(
        persona_id="p-sbe-weak",
        jd_id="jd-senior-backend",
        tier="weak",
        answers=(
            PersonaAnswer(
                target="PostgreSQL",
                question="Tell me about your experience with relational database design.",
                answer=(
                    "Yeah, I've worked with Postgres quite a lot across a few different "
                    "projects. It's a really solid database — we used it for pretty much "
                    "everything. Designing the schema is important to get right early because "
                    "it's hard to change later, so we always spent time on that as a team up "
                    "front. Relational databases are good when you need consistency, which for "
                    "the kind of data we had was definitely the case."
                ),
            ),
            PersonaAnswer(
                target="Incident response",
                question="Walk me through a production incident you handled.",
                answer=(
                    "We did have outages from time to time, like any team. The main thing I "
                    "learned is that communication is really important during an incident — "
                    "making sure everyone knows who's doing what and that stakeholders are kept "
                    "in the loop. We had a process where we'd get on a call and work through it "
                    "together, and then afterwards we'd do a blameless postmortem to figure out "
                    "what went wrong. It's about learning from it rather than pointing fingers."
                ),
            ),
            PersonaAnswer(
                target="Code review",
                question="How do you approach reviewing other people's code?",
                answer=(
                    "I think it's one of the most valuable things a team does. You catch bugs "
                    "early, and it spreads knowledge so you don't end up with one person being "
                    "the only one who understands something. I always try to be respectful in "
                    "my comments because text can come across harsher than you mean it. And I "
                    "try to turn reviews around quickly so I'm not blocking anyone."
                ),
            ),
        ),
    ),
)
