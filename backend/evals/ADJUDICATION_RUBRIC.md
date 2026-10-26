# Evidence adjudication rubric

**Protocol v1.0 · frozen before adjudication · one page by design**

You will see pairs: an **evidence statement** that InterMind's report used, and the **full
candidate answer text** that statement was allowed to draw on.

You will **not** see: the automatic rule's verdict, the coverage scores, which guard fired, the
persona, the target, the run, or the score. That is deliberate — the automatic rule is the thing
being audited, so any hint of its conclusion would anchor yours.

Cases reaching you are, by definition, the ones the deterministic rule could **not** resolve.
Expect them to be genuinely hard. A clean verbatim quote would never have reached you.

---

## The question you are answering

> **Did the candidate say, or clearly and necessarily imply, this?**

Not "is this a fair characterisation". Not "is this true of the candidate". Not "would a
recruiter find this reasonable". The evidence statement is being checked as a **report of what
was said**.

---

## Verdicts

### `supported`

Everything the statement asserts is present in the answer, allowing for rewording.

Paraphrase is explicitly permitted — the system asks the model for "short quotes **or close
paraphrases**". So synonym substitution, re-inflection, reordering and the dropping of filler
are all fine:

- *"configured horizontal pod autoscaling"* for *"set up the horizontal pod autoscaler"* →
  `supported`
- *"diagnosed the problem before changing anything"* for *"I checked it with explain analyze
  first rather than guessing"* → `supported`

### `unsupported`

The statement asserts something the answer does not — **including by addition, inflation,
inversion or reattribution.** The most common forms, all of which preserve most of the answer's
vocabulary:

| Form | Example against *"we were a team of six and shipped the migration in a quarter"* |
| :--- | :--- |
| **Attribution shift** | *"personally delivered the entire migration"* — "we" became "I" |
| **Scope inflation** | *"has experience operating this at scale"* from one service |
| **Quantity change** | any altered number, duration or magnitude |
| **Entity substitution** | a technology, service or system the answer never named in that role |
| **Relationship change** | cause and effect, or ordering, reversed |
| **Hedge removal that changes the claim** | *"it worked"* from *"I think it mostly worked"* |
| **Evaluative conclusion** | *"demonstrates strong ownership"* — a judgement, not a report |
| **Silence reported as finding** | *"no mention of connection pooling"* — an observation about the answer, not something the candidate said |

The test for the grey cases: **if the candidate read this statement back, would they say "yes,
that's what I said" — or "that's not quite what I said"?** The second is `unsupported`.

### `cannot_tell`

Reserved for genuine indeterminacy — the answer is ambiguous enough that the statement is
neither clearly a report of it nor clearly beyond it.

**This counts as `unsupported` in all headline figures** (the conservative direction) and is
also reported separately. So use it when it is honest, and do not use it to avoid a hard call
that you could actually make.

---

## The line to hold

The distinction that carries the whole metric: **reporting versus inferring.**

InterMind is allowed to *conclude* things about a candidate — that is what scores and
competency assessments are for. But an **evidence statement** has one job: to show the recruiter
what the candidate said that led to the conclusion. A statement that smuggles the conclusion
into the evidence defeats traceability, however reasonable the conclusion.

So:

- *"said the rollout caused a twenty-minute outage"* → a report → `supported`
- *"shows limited operational maturity"* → a conclusion → `unsupported`, even if you agree

Both might appear in a good report. Only the first is evidence.

---

## Practical notes

- Read the full answer before the statement, so you judge against the answer rather than
  scanning it for confirmation.
- A statement may be **partly** supported. If any asserted part is unsupported, the statement is
  `unsupported` — evidence is not graded, it either reports accurately or it does not.
- Length is irrelevant. Short statements are not automatically safe; a three-word statement can
  invert a claim.
- Do not penalise a statement for being incomplete. Omitting context is fine; adding content is
  not.
- Cases are shuffled and carry no identifying context. Do not look for patterns across them, and
  do not try to balance verdicts.
