

interface Link {
  label: string
  body: string
  /** The one node that carries the accent, because it is the step a recruiter is buying. */
  accent?: boolean
}

/**
 * One requirement, followed from the job description to the line in the report.
 *
 * This answers the question a hiring lead actually has on a first visit, which is not "how is
 * this built" but "where does that score come from". It is the product's central claim drawn
 * rather than asserted.
 *
 * The labels used to be the product's internal vocabulary: "The role needs", "Which is recorded
 * as", "Evidence". On their own those raise more questions than they answer, and "evidence" by
 * itself invites "evidence of what?". Each label is now a plain sentence fragment that reads
 * straight into the line beneath it, so the chain can be followed without knowing any of the
 * product's terms.
 *
 * Illustrative content, labelled as such below: nothing here is a real candidate, and the site
 * never shows one.
 */
const LINKS: Link[] = [
  {
    label: "The job asks for",
    body: "Someone who can keep a database working as the product changes around it.",
  },
  {
    label: "So InterMind asks",
    body: "How did you handle schema changes as the system grew?",
  },
  {
    label: "The candidate answers",
    body: "Versioned every migration, with a rollback path for each one.",
  },
  {
    label: "Which shows they have",
    body: "Done this on a running system, not just read about it",
    accent: true,
  },
  {
    label: "So the report records",
    body: "A score for that requirement, with the answer above attached to it.",
  },
]

export function EvidenceChain() {
  return <div className="evidence-chain">
    <ol className="flex flex-col">
      {LINKS.map((link, index) => <li key={link.label} className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-5 sm:gap-x-7">
        <div className="flex flex-col items-center" aria-hidden="true">
          <span className={`mt-2 h-2 w-2 shrink-0 rounded-full ${link.accent ? "bg-accent" : "bg-fg/70"}`} />
          {index < LINKS.length - 1 && <span className="w-px flex-1 bg-fg/20" />}
        </div>
        <div className="pb-9"><p className="type-meta text-fg-muted">{link.label}</p>
          <p className={`mt-2 text-lg leading-snug sm:text-xl ${link.accent ? "text-accent" : "text-fg"}`}>{link.body}</p>
        </div>
      </li>)}
    </ol>
    <p className="max-w-md text-sm leading-relaxed text-fg-soft">An example, to show the shape of it. In a real interview the requirement, the question and the answer all come from the role you provided and what the candidate actually said.</p>
  </div>
}
