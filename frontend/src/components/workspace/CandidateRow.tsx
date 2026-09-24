import { useCallback } from "react"
import { Link } from "react-router-dom"
import { motion } from "motion/react"
import { ArrowRight } from "lucide-react"
import { getInterviewReport } from "../../api/interviews"
import { useAsyncData } from "../../hooks/useAsyncData"
import { CopyInterviewLinkIconButton } from "../dashboard/CopyInterviewLinkIconButton"
import { IconLink } from "../ui/IconButton"
import { StatusPill } from "../ui/StatusPill"
import { CoverageRail } from "../ui/CoverageRail"
import { ExternalLinkIcon } from "../ui/icons"
import { candidateLink } from "../../lib/candidateLink"
import { rise } from "../../design/motion"
import { formatEvidenceStrength, formatRecommendation } from "../../lib/format"
import type { CandidateOverview } from "../../hooks/useWorkspaceOverview"

/** How many evidenced areas a row shows before it stops being scannable. */
const MAX_CHIPS = 4

/**
 * One candidate, read as intelligence rather than as a contact record.
 *
 * A finished interview leads with what was actually established - the strength of the evidence
 * and the areas it covers - and carries the score as a supporting figure, not as the headline.
 * An interview still running shows how far it has got and nothing else, because no assessment
 * exists yet and putting a number there would be inventing one.
 *
 * Row actions stay hidden until the row is hovered or focused, and are always visible on touch:
 * three icons repeated down a list compete with the names, which are what you are scanning for.
 */
export function CandidateRow({ candidate }: { candidate: CandidateOverview }) {
  const { summary, assessed, total } = candidate
  const isCompleted = summary.status === "completed"

  const reportFetcher = useCallback(
    () => getInterviewReport(summary.interview_id),
    [summary.interview_id],
  )
  const report = useAsyncData(reportFetcher, [summary.interview_id], isCompleted)

  const evidenced =
    report.data?.competencies
      .filter((c) => c.evidence_strength === "strong" || c.evidence_strength === "moderate")
      .slice(0, MAX_CHIPS)
      .map((c) => c.name) ?? []

  return (
    <motion.li
      variants={rise}
      className="group/row border-b border-hair py-5 transition-colors duration-200 last:border-0 hover:bg-fg/[0.02]"
    >
      <div className="grid grid-cols-1 items-center gap-x-8 gap-y-3 sm:grid-cols-[minmax(0,4fr)_minmax(0,3fr)_minmax(0,4fr)_auto]">
        <div className="min-w-0">
          <p className="truncate text-[0.9375rem] font-medium text-fg">{summary.candidate_name}</p>
          {summary.candidate_email && (
            <p className="type-data mt-0.5 truncate text-fg-muted">{summary.candidate_email}</p>
          )}
        </div>

        <StatusPill status={summary.status} />

        {isCompleted ? (
          <div className="flex min-w-0 flex-wrap items-baseline gap-x-2.5 gap-y-1">
            {report.data && (
              <span className="text-sm text-fg">
                {formatEvidenceStrength(report.data.overall_evidence_strength)}
              </span>
            )}
            {summary.recommendation && (
              <span className="type-data text-fg-muted">
                {formatRecommendation(summary.recommendation)}
              </span>
            )}
            {summary.overall_score !== null && (
              <span className="type-data type-numeric ml-auto shrink-0 text-fg-muted">
                {Math.round(summary.overall_score * 100)}%
              </span>
            )}
          </div>
        ) : total > 0 ? (
          // The product's one progress language, same as the dashboard and the interview room.
          <CoverageRail assessed={assessed} total={total} active />
        ) : (
          <span className="type-data text-fg-muted">Hasn't started yet</span>
        )}

        <div className="flex items-center justify-end gap-0.5">
          <span className="row-actions flex items-center">
            <CopyInterviewLinkIconButton
              interviewId={summary.interview_id}
              accessToken={summary.candidate_access_token}
            />
            <IconLink
              label="Open this candidate's interview"
              icon={<ExternalLinkIcon />}
              href={candidateLink(summary.interview_id, summary.candidate_access_token)}
              target="_blank"
              rel="noopener noreferrer"
            />
          </span>
          {isCompleted && (
            <Link
              to={`/reports/${summary.interview_id}`}
              className="inline-flex min-h-[44px] shrink-0 items-center gap-1.5 rounded-full px-3 text-sm font-medium text-fg transition-colors hover:bg-fg/[0.06]"
            >
              Report
              <ArrowRight
                size={14}
                aria-hidden="true"
                className="transition-transform duration-200 group-hover/row:translate-x-0.5"
              />
            </Link>
          )}
        </div>
      </div>

      {/* O*NET task targets are whole sentences, and one of them unchecked turns this row into
          a paragraph - so chips are truncated to a readable width, with the full text on hover
          and in the report itself. */}
      {evidenced.length > 0 && (
        <ul className="mt-3 flex flex-wrap gap-1.5">
          {evidenced.map((name) => (
            <li
              key={name}
              title={name}
              className="max-w-[16rem] truncate rounded-full bg-accent-soft px-2.5 py-1 text-[0.75rem] text-accent"
            >
              {name}
            </li>
          ))}
        </ul>
      )}
    </motion.li>
  )
}
