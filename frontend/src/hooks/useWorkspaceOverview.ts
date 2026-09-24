import { useCallback, useEffect, useState } from "react"
import { listJobs } from "../api/jobs"
import { getInterviewPlan } from "../api/interviewPlans"
import { getInterview, listJobInterviews } from "../api/interviews"
import { summarizeCoverage } from "../lib/coverage"
import type { CandidateSessionSummary, CoverageTarget, Job } from "../types"

export interface CandidateOverview {
  summary: CandidateSessionSummary
  /** Targets this candidate has moved past, of the plan's total. */
  assessed: number
  total: number
  ratio: number
}

export interface JobOverview {
  job: Job
  /** `null` when the job has no interview plan yet - a real state, not an error. */
  targets: CoverageTarget[] | null
  candidates: CandidateOverview[]
  completedCount: number
  inProgressCount: number
  /** Mean coverage across this job's candidates - 0 when nobody has been invited yet. */
  coverageRatio: number
}

interface WorkspaceOverview {
  jobs: JobOverview[]
  isLoading: boolean
  error: string | null
  refetch: () => void
}

/**
 * Assembles the recruiter workspace's view from the endpoints that already exist.
 *
 * This deliberately fans out (plan + candidate list per job, then interview state per
 * candidate) rather than inventing a summary the API doesn't return. Storage is in-memory
 * server-side so these resolve immediately, and it follows the fan-out pattern the candidate
 * table already used - but a real deployment should collapse this into one summary endpoint
 * rather than growing the fan-out.
 */
export function useWorkspaceOverview(): WorkspaceOverview {
  const [jobs, setJobs] = useState<JobOverview[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [nonce, setNonce] = useState(0)

  const refetch = useCallback(() => setNonce((n) => n + 1), [])

  useEffect(() => {
    let cancelled = false
    setIsLoading(true)
    setError(null)

    async function load() {
      try {
        const allJobs = await listJobs()

        const overviews = await Promise.all(
          allJobs.map(async (job): Promise<JobOverview> => {
            const [targets, candidates] = await Promise.all([
              getInterviewPlan(job.id)
                .then((plan) => plan.coverage_targets)
                .catch(() => null),
              listJobInterviews(job.id).catch(() => []),
            ])

            const candidateOverviews = await Promise.all(
              candidates.map(async (summary): Promise<CandidateOverview> => {
                if (!targets) {
                  return { summary, assessed: 0, total: 0, ratio: 0 }
                }
                try {
                  // Empty token: the recruiter session cookie authorises this, not a bearer credential.
                  const state = await getInterview(summary.interview_id, "")
                  const coverage = summarizeCoverage(targets, state)
                  return {
                    summary,
                    assessed: coverage.assessed,
                    total: coverage.total,
                    ratio: coverage.ratio,
                  }
                } catch {
                  // A candidate whose state can't be read still belongs in the list - it just
                  // contributes no coverage rather than disappearing.
                  return { summary, assessed: 0, total: targets.length, ratio: 0 }
                }
              }),
            )

            // A job doesn't have "targets assessed" of its own - its *candidates* do. The
            // job-level bar is therefore the mean of its candidates' coverage: how far this
            // interview has got, across the people taking it. With a single candidate it is
            // simply that candidate's own progress.
            const coverageRatio =
              candidateOverviews.length > 0
                ? candidateOverviews.reduce((sum, c) => sum + c.ratio, 0) / candidateOverviews.length
                : 0

            return {
              job,
              targets,
              candidates: candidateOverviews,
              completedCount: candidates.filter((c) => c.status === "completed").length,
              inProgressCount: candidates.filter((c) => c.status === "in_progress").length,
              coverageRatio,
            }
          }),
        )

        if (!cancelled) {
          setJobs(overviews)
          setIsLoading(false)
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Could not load the workspace.")
          setIsLoading(false)
        }
      }
    }

    void load()
    return () => {
      cancelled = true
    }
  }, [nonce])

  return { jobs, isLoading, error, refetch }
}
