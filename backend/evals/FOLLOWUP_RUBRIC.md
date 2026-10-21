# Follow-up labelling rubric

**Rubric v1.0 · used for the independent human labeling · one page by design**

You will see, for each case: the **target** being assessed, the **question** asked, the
**candidate's answer**, and (where the answer refers back to something) the **prior exchange**
for that target.

You will **not** see: what InterMind predicted, any author-intended label, any category name,
any score, any generated follow-up, or any failure classification. That is deliberate — your
labels are the reference standard, so they must be formed independently.

---

## The question you are answering

> **Would a competent human interviewer ask a follow-up about this target before moving on?**

Not "could one". Not "would it be nice to know more" — there is always more to know. The test is
whether a skilled interviewer, wanting a fair and sufficient assessment of **this target**,
would consider it irresponsible to move on without asking one more thing.

---

## Decision procedure

Apply in order. Stop at the first rule that fires.

**1. Did the candidate explicitly state they lack this experience?**
→ `NO_FOLLOW_UP_WARRANTED`

Never ask someone to give an example of something they just said they have never done. "I have
not used Kafka", "that was before my time", "I have only ever used the other one instead" — all
of these resolve the target. Pressing further is interrogation, not interviewing.

**2. Is the answer off-topic, confused about what the target is, or otherwise non-substantive,
with nothing concrete to probe?**
→ `NO_FOLLOW_UP_WARRANTED`

The distinction that matters: if there is nothing in the answer to ask *about*, a follow-up can
only be a generic prompt ("can you say more?"), which is not adaptive interviewing. If instead
the answer contains something specific but underdeveloped, that is rule 4.

**3. Does the answer fully demonstrate the target with specifics — real work, concrete
decisions, enough detail that a reader could assess competence?**
→ `NO_FOLLOW_UP_WARRANTED`

Brevity is not a deficiency. A short, precise, complete answer needs no follow-up.

**4. Does a specific, concrete, answer-grounded detail remain unexplored, such that asking about
it would materially change your assessment of this target?**
→ `FOLLOW_UP_WARRANTED`

"Answer-grounded" is the key constraint: the follow-up must arise from something the candidate
actually said. A claim without substantiation, a part-described piece of work, a named
technology with no account of how it was used, an answer that discusses something adjacent to
the target without addressing the target itself — these all qualify.

**5. Genuinely cannot decide?**
→ `AMBIGUOUS`

Use this sparingly but without hesitation when it is honest. It is handled explicitly: ambiguous
cases are excluded from the primary F1 and reported separately, with a sensitivity analysis
bounding their effect in both directions. A forced guess would be worse than an honest
`AMBIGUOUS`.

---

## Things that are not the test

- **Whether the answer is good.** A strong answer can still warrant a follow-up; a weak one can
  resolve a target completely. Quality and completeness are different axes.
- **Whether you personally find the topic interesting.**
- **Whether the candidate was articulate.** Fluency is not substance, and hesitancy is not
  absence. An answer full of hedges can be perfectly complete; a polished one can be hollow.
- **Whether the candidate is likely to get the job.**
- **What you would ask next if you had unlimited time.** Assume a bounded interview.

---

## Worked examples

These are calibration examples, not drawn from the dataset.

**Target: PostgreSQL** · *"Yeah, I've done a lot of query optimisation work in Postgres."*
→ `FOLLOW_UP_WARRANTED`. A claim with nothing substantiating it. Something specific is being
referred to ("a lot of query optimisation work") and asking which query, and what was done,
would change the assessment. Rule 4.

**Target: PostgreSQL** · *"The slow one was a report query doing a sequential scan over about
four million rows. I added a composite index on tenant id and created at, checked it with
explain analyze first, and it went from nine seconds to under two hundred milliseconds."*
→ `NO_FOLLOW_UP_WARRANTED`. Complete and specific. Rule 3.

**Target: Kafka** · *"Honestly, no. I've read the docs and done a tutorial, but everything I've
actually shipped used SQS or Celery."*
→ `NO_FOLLOW_UP_WARRANTED`. Explicit lack. Rule 1. Note this is *also* a short answer and *also*
low-scoring — neither is the reason.

**Target: Kubernetes** · *"We use it for everything. The whole platform runs on it and it's
been great for us — much better than what we had before."*
→ `FOLLOW_UP_WARRANTED`. Fluent and entirely about the team. Nothing yet indicates what *this
candidate* did. Rule 4.

**Target: System design** · *"Sorry, do you mean how I'd design the API, or the database
schema?"*
→ `NO_FOLLOW_UP_WARRANTED` under this rubric. A clarifying question is not an answer with an
unexplored detail; there is nothing substantive to probe. Rule 2. (It is a reasonable candidate
behaviour — but the rubric asks about follow-up warrant, not candidate merit.)

**Target: Monitoring** · *"I set up the dashboards and alerting for our services."*
→ `FOLLOW_UP_WARRANTED`. Real, relevant, specific-ish, but materially underdeveloped: which
tooling, what was alerted on, did it work. Rule 4. This is the commonest shape in practice.

---

## Practical notes

- Judge the answer **against the stated target**, not against the question's wording. An answer
  can address the question while missing the target.
- Where a prior exchange is shown, the answer is a follow-up response — judge whether *another*
  follow-up is warranted on top of it.
- Label every case independently. Do not try to balance your labels, and do not infer anything
  from case order, which is shuffled.
- There is no expected distribution. Whatever your labels are, they are the reference standard.
