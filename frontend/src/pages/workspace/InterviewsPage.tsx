import { Link, useNavigate } from "react-router-dom"
import { motion } from "motion/react"
import { ArrowRight } from "lucide-react"
import { useWorkspaceOverview } from "../../hooks/useWorkspaceOverview"
import type { CandidateOverview, JobOverview } from "../../hooks/useWorkspaceOverview"
import { ActivityStream } from "../../components/workspace/ActivityStream"
import { CoverageRail } from "../../components/ui/CoverageRail"
import { PresenceMark } from "../../components/ui/PresenceMark"
import { SkeletonRows } from "../../components/ui/Spinner"
import { ErrorBanner } from "../../components/ui/ErrorBanner"
import { Button } from "../../components/ui/Button"
import { EmptyState } from "../../components/ui/EmptyState"
import { PageIntro } from "../../components/ui/PageIntro"
import { rise, stagger } from "../../design/motion"
import { timeOfDayGreeting } from "../../lib/greeting"
import { formatSeniority } from "../../lib/format"
import { useDocumentTitle } from "../../hooks/useDocumentTitle"

/**
 * The recruiter's command centre.
 *
 * The question it answers is "what is happening with my interviews", and the page answers it in
 * two registers. The obsidian panel is the system's own: it exists only while a candidate is
 * genuinely mid-interview, and what it shows is that interview, running, in the same material
 * as the room it is running in. Below it, on the light plane, is the inventory - every role,
 * how far it has got, what to do next. Light for reviewing; obsidian for the machine working.
 *
 * What it is not: a wall of statistic tiles, or a list where every row is a card or an
 * accordion. The counts are a sentence, the roles are rows, and the only dark surface on the
 * page appears because something is actually happening. When nothing is running, the panel is
 * simply absent - the page never manufactures activity to fill it.
 */

/** Everyone currently mid-interview, with the role they are interviewing for. */
interface LiveInterview {
  candidate: CandidateOverview
  job: JobOverview["job"]
}

function liveInterviewsOf(jobs: JobOverview[]): LiveInterview[] {
  return jobs.flatMap((overview) =>
    overview.candidates
      .filter((candidate) => candidate.summary.status === "in_progress")
      .map((candidate) => ({ candidate, job: overview.job })),
  )
}

/**
 * The live panel: the interview room's material, brought into the workspace.
 *
 * Contained rather than full-bleed, so it reads as a window onto something happening elsewhere
 * rather than as the page changing theme halfway down. Same obsidian, same veil, same
 * pale-sky-on-black type relationship as the room itself.
 */
function LivePanel({ live }: { live: LiveInterview[] }) {
  return (
    <motion.section
      variants={rise}
      aria-label="Interviews in progress"
      className="plane-raised relative overflow-hidden"
    >
      <span aria-hidden="true" className="veil-night" />

      <div className="relative px-4 py-5 sm:px-6 sm:py-6">
        <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-2 border-b border-hair px-2 pb-4">
          <h2 className="flex items-center gap-2.5 text-[0.9375rem] font-medium text-fg">
            <PresenceMark state="live" size={18} className="text-accent" />
            Happening now
          </h2>
          <p className="type-data text-fg-muted">
            {live.length === 1 ? "1 interview in progress" : `${live.length} interviews in progress`}
          </p>
        </div>

        <ul className="flex flex-col">
          {live.map(({ candidate, job }) => (
            <li key={candidate.summary.interview_id}>
              <Link
                to={`/interviews/${job.id}`}
                className="row-lift group/row grid grid-cols-1 items-center gap-x-8 gap-y-3 rounded-[12px] px-2 py-4 sm:grid-cols-[minmax(0,5fr)_minmax(0,4fr)_auto]"
              >
                <div className="min-w-0">
                  <p className="truncate text-[0.9375rem] font-medium text-fg">
                    {candidate.summary.candidate_name}
                  </p>
                  <p className="type-data mt-0.5 truncate text-fg-muted">
                    {job.job_spec.role_title}
                  </p>
                </div>

                {candidate.total > 0 ? (
                  <CoverageRail
                    assessed={candidate.assessed}
                    total={candidate.total}
                    active
                  />
                ) : (
                  <span className="type-data text-fg-muted">Just started</span>
                )}

                <span
                  aria-hidden="true"
                  className="hidden text-accent transition-transform duration-200 group-hover/row:translate-x-0.5 sm:block"
                >
                  <ArrowRight size={16} />
                </span>
              </Link>
            </li>
          ))}
        </ul>
      </div>
    </motion.section>
  )
}

function roleSummary(overview: JobOverview): string {
  const { candidates, completedCount, inProgressCount } = overview
  if (candidates.length === 0) return "No candidates yet"
  if (inProgressCount > 0) {
    return inProgressCount === 1 ? "1 interviewing now" : `${inProgressCount} interviewing now`
  }
  if (completedCount === candidates.length) {
    return completedCount === 1 ? "1 completed" : `${completedCount} completed`
  }
  return `${candidates.length} invited · ${completedCount} completed`
}

function RoleRow({ overview }: { overview: JobOverview }) {
  const { job, targets, candidates, coverageRatio, inProgressCount } = overview
  const total = targets?.length ?? 0
  // The mean across this role's candidates, expressed in the same ticks the interview room uses
  // rather than as a percentage standing in for them.
  const assessed = total > 0 ? Math.round(coverageRatio * total) : 0

  return (
    <motion.li variants={rise}>
      <Link
        to={`/interviews/${job.id}`}
        className="row-lift group/row grid grid-cols-1 items-center gap-x-8 gap-y-3 rounded-[14px] border-b border-hair px-4 py-5 last:border-0 sm:grid-cols-[minmax(0,5fr)_minmax(0,3fr)_minmax(0,4fr)_auto]"
      >
        <div className="min-w-0">
          <h3 className="flex items-center gap-2 text-[0.9375rem] font-medium text-fg">
            {inProgressCount > 0 && <PresenceMark state="live" size={14} className="text-accent" />}
            <span className="truncate">{job.job_spec.role_title}</span>
          </h3>
          <p className="type-data mt-1 text-fg-muted">
            {formatSeniority(job.job_spec.seniority)}
            {targets === null ? " · interview not built yet" : ` · ${total} areas`}
          </p>
        </div>

        <p className="text-sm text-fg-soft">{roleSummary(overview)}</p>

        {candidates.length > 0 && total > 0 ? (
          <CoverageRail assessed={assessed} total={total} label={`${assessed} of ${total} areas`} />
        ) : (
          <span aria-hidden="true" />
        )}

        <span
          aria-hidden="true"
          className="hidden text-fg-muted transition-transform duration-200 group-hover/row:translate-x-0.5 group-hover/row:text-fg sm:block"
        >
          <ArrowRight size={16} />
        </span>
      </Link>
    </motion.li>
  )
}

export function InterviewsPage() {
  useDocumentTitle("Interviews")

  const navigate = useNavigate()
  const { jobs, isLoading, error, refetch } = useWorkspaceOverview()

  const live = liveInterviewsOf(jobs)
  const candidateCount = jobs.reduce((sum, j) => sum + j.candidates.length, 0)
  const completedCount = jobs.reduce((sum, j) => sum + j.completedCount, 0)

  /** The counts as one sentence. Only the parts that are actually true are said. */
  const parts: string[] = []
  if (jobs.length > 0) parts.push(`${jobs.length} ${jobs.length === 1 ? "role" : "roles"}`)
  if (candidateCount > 0) {
    parts.push(`${candidateCount} ${candidateCount === 1 ? "candidate" : "candidates"}`)
  }
  if (completedCount > 0) parts.push(`${completedCount} completed`)

  return (
    <motion.div variants={stagger(0.07)} initial="hidden" animate="visible">
      <div className="border-b border-hair">
        <div className="shell py-12 sm:py-14">
          {/* No action on this header: "New interview" already sits in the bar a few
              centimetres above, and two identical primary buttons in one eyeful read as a
              mistake rather than as emphasis. */}
          <PageIntro
            kicker={`${timeOfDayGreeting()}.`}
            title="Interviews"
            lede="Every role you've given InterMind, and what its candidates are doing right now."
            meta={
              parts.length > 0 ? (
                <p className="type-data text-fg-muted">{parts.join(" · ")}</p>
              ) : undefined
            }
          />
        </div>
      </div>

      <div className="shell flex flex-col gap-10 py-10 sm:py-12">
        {isLoading && <SkeletonRows rows={3} />}
        {error && <ErrorBanner message={error} onRetry={refetch} />}

        {!isLoading && !error && live.length > 0 && <LivePanel live={live} />}

        {!isLoading && !error && jobs.length === 0 && (
          <motion.div variants={rise}>
            <EmptyState
              title="No interviews yet"
              body="InterMind builds an interview from the job description itself - you don't write the questions, and the interview decides what to ask next from what each candidate says."
              hints={[
                "Paste a job description and InterMind reads the role.",
                "Check what it understood, then let it build the interview.",
                "Send each candidate their own link and watch the evidence arrive.",
              ]}
              action={
                <Button onClick={() => navigate("/interviews/new")}>
                  Create your first interview
                  <ArrowRight size={16} aria-hidden="true" />
                </Button>
              }
            />
          </motion.div>
        )}

        {!isLoading && !error && jobs.length > 0 && (
          <motion.section variants={rise}>
            <div className="mb-3 flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1">
              <h2 className="type-data font-medium text-fg">All roles</h2>
              <p className="type-data text-fg-muted">
                Open one to invite candidates or read a report
              </p>
            </div>

            {/* The list sits *in* a surface rather than floating on white. This is the plane the
                workspace was missing: without it, rows separated by a 10%-opacity hairline are
                the only structure on the page. */}
            <div className="plane-raised px-2 py-1">
              <motion.ul variants={stagger(0.04)}>
                {jobs.map((overview) => (
                  <RoleRow key={overview.job.id} overview={overview} />
                ))}
              </motion.ul>
            </div>
          </motion.section>
        )}
      </div>

      {/* The system's own record of what it has been doing - the second obsidian surface, and
          the reason the workspace and the interview room read as one product. */}
      <motion.section variants={rise} className="relative border-t border-hair">
        <div className="shell relative py-12 sm:py-14">
          <div className="flex flex-wrap items-baseline justify-between gap-x-8 gap-y-2 border-b border-hair pb-4">
            <h2 className="type-group text-fg">Recent activity</h2>
            <p className="type-data text-fg-muted">
              Recorded as it happened, across every interview
            </p>
          </div>
          <div className="mt-2">
            <ActivityStream />
          </div>
        </div>
      </motion.section>
    </motion.div>
  )
}
