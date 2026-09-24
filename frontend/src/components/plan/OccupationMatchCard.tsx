import type { OccupationMatch } from "../../types"

interface OccupationMatchCardProps {
  match: OccupationMatch
  alternates: OccupationMatch[]
  onetGroundingUsed: boolean
}

/**
 * O*NET is internal grounding, not the headline of the plan (see the product review that
 * flagged raw TF-IDF percentages reading as if they were a qualification/hiring signal) - this
 * renders as a closed-by-default disclosure with plain-language framing and no similarity
 * scores, meant to sit below the job-description-driven plan content, not above it.
 */
export function OccupationMatchCard({ match, alternates, onetGroundingUsed }: OccupationMatchCardProps) {
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
              The job description is the primary source for this plan. As supplementary
              context, InterMind also referenced O*NET's{" "}
              <span className="font-medium text-fg">{match.title}</span> occupation profile,
              which it judged a confident match for this role.
            </>
          ) : (
            <>
              This plan is grounded entirely in the job description. InterMind checked O*NET
              for a supplementary occupation match, but no candidate (the closest being{" "}
              <span className="font-medium text-fg">{match.title}</span>) was a confident
              enough match to add anything beyond what the job description already provides.
            </>
          )}
        </p>

        {alternates.length > 0 && (
          <div>
            <p className="type-data mb-1.5 font-medium text-fg">Other occupations considered</p>
            <ul className="flex flex-col gap-1">
              {alternates.slice(0, 3).map((alt) => (
                <li key={alt.onet_soc_code} className="type-data text-fg-muted">
                  {alt.title}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </details>
  )
}
