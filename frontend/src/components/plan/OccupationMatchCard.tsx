import type { OccupationMatch } from "../../types"

interface OccupationMatchCardProps {
  match: OccupationMatch
  onetGroundingUsed: boolean
}

/**
 * O*NET is internal grounding, not the headline of the plan (see the product review that
 * flagged raw TF-IDF percentages reading as if they were a qualification/hiring signal) - this
 * renders as a closed-by-default disclosure with plain-language framing and no similarity
 * scores, meant to sit below the job-description-driven plan content, not above it.
 *
 * Only the top match is shown. The plan also carries the retrieval runners-up, which the planner
 * needs for its margin check, but they are ranked candidates with no score floor applied: for a
 * given role they can include occupations with almost no overlap, and listing them as "considered"
 * described work the planner never did with them.
 */
export function OccupationMatchCard({ match, onetGroundingUsed }: OccupationMatchCardProps) {
  return (
    <details className="group border-t border-hair pt-5 text-sm">
      <summary className="inline-flex min-h-[44px] cursor-pointer select-none list-none items-center gap-2 text-sm text-fg-muted transition-colors hover:text-fg">
        How this plan was grounded
        <span aria-hidden="true" className="transition-transform duration-200 group-open:rotate-180">▾</span>
      </summary>
      <div className="mt-4 flex max-w-2xl flex-col gap-3">
        <p className="text-sm leading-relaxed text-fg-soft">
          {onetGroundingUsed ? (
            <>
              The job description is the primary source for this plan. InterMind also used
              O*NET's <span className="font-medium text-fg">{match.title}</span> profile as
              supplementary role context.
            </>
          ) : (
            <>
              This plan comes entirely from the job description. InterMind looked for a
              supplementary O*NET occupation profile and found none close enough to add anything
              beyond what the description already provides.
            </>
          )}
        </p>
      </div>
    </details>
  )
}
