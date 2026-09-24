import { Link, useNavigate } from "react-router-dom"
import { motion } from "motion/react"
import { ArrowRight } from "lucide-react"
import { useWorkspaceOverview } from "../../hooks/useWorkspaceOverview"
import { CandidateRow } from "../../components/workspace/CandidateRow"
import { SkeletonRows } from "../../components/ui/Spinner"
import { ErrorBanner } from "../../components/ui/ErrorBanner"
import { Button } from "../../components/ui/Button"
import { EmptyState } from "../../components/ui/EmptyState"
import { PageIntro } from "../../components/ui/PageIntro"
import { rise, stagger } from "../../design/motion"
import { formatSeniority } from "../../lib/format"
import { useDocumentTitle } from "../../hooks/useDocumentTitle"

/**
 * Candidates, grouped by the role they are interviewing for.
 *
 * The grouping is the information architecture: a recruiter reads "how is this role going",
 * then scans the people inside it. One flat table of everyone would need a filter before it
 * said anything.
 *
 * The page opens on the cool shelf rather than the warm one the dashboard uses - the same
 * system, a different room. Its subject is what the interviews have established about people,
 * so each row leads with evidence and carries the number quietly behind it.
 */
export function CandidatesPage() {
  useDocumentTitle("Candidates")

  const navigate = useNavigate()
  const { jobs, isLoading, error, refetch } = useWorkspaceOverview()

  const withCandidates = jobs.filter((overview) => overview.candidates.length > 0)
  const total = jobs.reduce((sum, overview) => sum + overview.candidates.length, 0)
  const completed = jobs.reduce((sum, overview) => sum + overview.completedCount, 0)

  return (
    <motion.div variants={stagger(0.07)} initial="hidden" animate="visible">
      <div className="border-b border-hair">
        <div className="shell py-12 sm:py-14">
          <PageIntro
            title="Candidates"
            lede="Everyone InterMind has interviewed, and what each interview was able to establish."
            meta={
              total > 0 ? (
                <p className="type-data text-fg-muted">
                  {total} {total === 1 ? "candidate" : "candidates"}
                  {completed > 0 && ` · ${completed} with a finished report`}
                </p>
              ) : undefined
            }
          />
        </div>
      </div>

      <div className="shell flex flex-col gap-14 py-10 sm:py-12">
        {isLoading && <SkeletonRows rows={4} />}
        {error && <ErrorBanner message={error} onRetry={refetch} />}

        {!isLoading && !error && withCandidates.length === 0 && (
          <motion.div variants={rise}>
            <EmptyState
              title="No candidates yet"
              body="Candidates appear here as soon as you invite them, grouped under the role they're interviewing for. Their evidence fills in while they answer - you don't have to wait for them to finish."
              action={
                jobs.length > 0 ? (
                  <Button onClick={() => navigate("/interviews")}>
                    Pick a role to invite to
                    <ArrowRight size={16} aria-hidden="true" />
                  </Button>
                ) : (
                  <Button onClick={() => navigate("/interviews/new")}>
                    Create your first interview
                    <ArrowRight size={16} aria-hidden="true" />
                  </Button>
                )
              }
            />
          </motion.div>
        )}

        {withCandidates.map((overview) => (
          <motion.section key={overview.job.id} variants={rise}>
            <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1 border-b border-fg/15 pb-3">
              <Link
                to={`/interviews/${overview.job.id}`}
                className="inline-flex min-h-[44px] items-center text-[1.0625rem] font-medium text-fg transition-colors hover:text-accent"
              >
                {overview.job.job_spec.role_title}
              </Link>
              <p className="type-data text-fg-muted">
                {formatSeniority(overview.job.job_spec.seniority)} ·{" "}
                {overview.candidates.length}{" "}
                {overview.candidates.length === 1 ? "candidate" : "candidates"}
              </p>
            </div>

            <motion.ul variants={stagger(0.04)}>
              {overview.candidates.map((candidate) => (
                <CandidateRow key={candidate.summary.interview_id} candidate={candidate} />
              ))}
            </motion.ul>
          </motion.section>
        ))}
      </div>
    </motion.div>
  )
}
