import { useCallback, useEffect, useState } from "react"
import type { FormEvent } from "react"
import { Link, useNavigate, useParams } from "react-router-dom"
import { getJob } from "../../api/jobs"
import { getInterview, listJobInterviews, startInterview } from "../../api/interviews"
import { ApiError, RECRUITER_ACCESS_TOKEN } from "../../api/client"
import { useAsyncData } from "../../hooks/useAsyncData"
import { Spinner } from "../../components/ui/Spinner"
import { ErrorBanner } from "../../components/ui/ErrorBanner"
import { PageHeader } from "../../components/ui/PageHeader"
import { Card } from "../../components/ui/Card"
import { Button } from "../../components/ui/Button"
import { TextInput } from "../../components/ui/TextInput"
import { CopyLinkButton } from "../../components/ui/CopyLinkButton"
import { StatusBadge } from "../../components/ui/StatusBadge"
import { EmptyState } from "../../components/ui/EmptyState"
import { formatRecommendation, formatSeniority } from "../../lib/format"
import type { InterviewStatus } from "../../types"

function candidateLink(interviewId: string, accessToken: string): string {
  // The candidate's own per-interview access token (see app.api.auth on the backend) travels
  // in the link itself - the candidate has no login, so this is the only way their client
  // learns it. Never the recruiter token: that would let the candidate reach recruiter-only
  // endpoints too.
  const params = new URLSearchParams({ token: accessToken })
  return `${window.location.origin}/candidate/interviews/${interviewId}?${params.toString()}`
}

const STATUS_ORDER: Record<InterviewStatus, number> = {
  completed: 0,
  in_progress: 1,
  not_started: 2,
}

export function InterviewCandidatesPage() {
  const { jobId } = useParams<{ jobId: string }>()
  const navigate = useNavigate()

  const jobFetcher = useCallback(() => getJob(jobId!), [jobId])
  const job = useAsyncData(jobFetcher, [jobId])

  const candidatesFetcher = useCallback(() => listJobInterviews(jobId!), [jobId])
  const candidates = useAsyncData(candidatesFetcher, [jobId])

  const [progressByInterview, setProgressByInterview] = useState<Record<string, number>>({})

  useEffect(() => {
    const inProgress = (candidates.data ?? []).filter((c) => c.status === "in_progress")
    if (inProgress.length === 0) return
    let cancelled = false
    Promise.all(
      inProgress.map(async (c) => {
        try {
          const state = await getInterview(c.interview_id, RECRUITER_ACCESS_TOKEN)
          return [c.interview_id, state.turn_index] as const
        } catch {
          return null
        }
      }),
    ).then((results) => {
      if (cancelled) return
      setProgressByInterview((prev) => {
        const next = { ...prev }
        for (const result of results) {
          if (result) next[result[0]] = result[1]
        }
        return next
      })
    })
    return () => {
      cancelled = true
    }
  }, [candidates.data])

  const [showInviteForm, setShowInviteForm] = useState(false)
  const [candidateName, setCandidateName] = useState("")
  const [candidateEmail, setCandidateEmail] = useState("")
  const [isInviting, setIsInviting] = useState(false)
  const [inviteError, setInviteError] = useState<string | null>(null)
  const [newLink, setNewLink] = useState<{ interviewId: string; token: string } | null>(null)

  async function handleInvite(event: FormEvent) {
    event.preventDefault()
    if (!jobId || !candidateName.trim()) return
    setIsInviting(true)
    setInviteError(null)
    try {
      const interview = await startInterview(jobId, candidateName.trim(), candidateEmail.trim())
      if (!interview.candidate_access_token) {
        throw new Error("Server did not return an access token for the new interview.")
      }
      setNewLink({ interviewId: interview.interview_id, token: interview.candidate_access_token })
      setCandidateName("")
      setCandidateEmail("")
      setShowInviteForm(false)
      candidates.refetch()
    } catch (err) {
      setInviteError(
        err instanceof ApiError ? err.message : "Something went wrong inviting this candidate.",
      )
    } finally {
      setIsInviting(false)
    }
  }

  if (job.isLoading) return <Spinner label="Loading interview…" />
  if (job.error) return <ErrorBanner message={job.error} onRetry={job.refetch} />
  if (!job.data) return null

  const spec = job.data.job_spec
  const sortedCandidates = [...(candidates.data ?? [])].sort(
    (a, b) => STATUS_ORDER[a.status] - STATUS_ORDER[b.status],
  )
  const completedCount = sortedCandidates.filter((c) => c.status === "completed").length
  const inProgressCount = sortedCandidates.filter((c) => c.status === "in_progress").length
  const notStartedCount = sortedCandidates.filter((c) => c.status === "not_started").length

  return (
    <div className="flex flex-col gap-6 animate-enter">
      <PageHeader
        eyebrow="Interview"
        title={spec.role_title}
        description={
          sortedCandidates.length > 0
            ? `${sortedCandidates.length} candidate${sortedCandidates.length === 1 ? "" : "s"} · ${completedCount} completed · ${inProgressCount} in progress · ${notStartedCount} not started`
            : undefined
        }
      />

      <div className="flex flex-wrap items-center gap-4 text-xs text-ink-muted">
        <span>{formatSeniority(spec.seniority)}</span>
        <Link to={`/recruiter/interviews/${jobId}/job-analysis`} className="underline underline-offset-2 hover:text-ink">
          Job analysis
        </Link>
        <Link to={`/recruiter/interviews/${jobId}/plan`} className="underline underline-offset-2 hover:text-ink">
          Interview plan
        </Link>
      </div>

      <div className="flex items-center justify-between gap-3">
        <h2 className="text-sm font-semibold text-ink">Candidates</h2>
        {/* The single, unambiguous "Invite Candidate" action for this page - it used to also
            appear as its own button inside the empty state below, competing with this one for
            the same action. */}
        <Button onClick={() => setShowInviteForm((v) => !v)}>Invite Candidate</Button>
      </div>

      {inviteError && <ErrorBanner message={inviteError} />}

      {showInviteForm && (
        <Card>
          <form onSubmit={handleInvite} className="flex flex-col gap-4">
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <TextInput
                id="candidate-name"
                label="Candidate name"
                value={candidateName}
                onChange={(e) => setCandidateName(e.target.value)}
                placeholder="Ahmed Ali"
                required
              />
              <TextInput
                id="candidate-email"
                label="Candidate email"
                type="email"
                value={candidateEmail}
                onChange={(e) => setCandidateEmail(e.target.value)}
                placeholder="ahmed@example.com"
              />
            </div>
            <div className="flex justify-end gap-2">
              <Button type="button" variant="ghost" onClick={() => setShowInviteForm(false)}>
                Cancel
              </Button>
              <Button type="submit" isLoading={isInviting} disabled={!candidateName.trim()}>
                Generate Candidate Link
              </Button>
            </div>
          </form>
        </Card>
      )}

      {newLink && (
        <Card className="flex flex-wrap items-center justify-between gap-4 border-periwinkle/40 bg-periwinkle/5">
          <div className="min-w-0">
            <p className="text-sm font-medium text-ink">Candidate link ready</p>
            <p className="truncate text-xs text-ink-muted">
              {candidateLink(newLink.interviewId, newLink.token)}
            </p>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <CopyLinkButton link={candidateLink(newLink.interviewId, newLink.token)} />
            <Button variant="ghost" onClick={() => setNewLink(null)}>
              Dismiss
            </Button>
          </div>
        </Card>
      )}

      {candidates.isLoading && <Spinner label="Loading candidates…" />}
      {candidates.error && <ErrorBanner message={candidates.error} onRetry={candidates.refetch} />}

      {/* Hidden while the invite form is open or a link was just generated - showing the empty
          state at the same time as the invite form (or the just-generated link, before the
          candidate list refetch resolves) reads as if the invitation flow did nothing, since
          the page looks unchanged. */}
      {candidates.data && sortedCandidates.length === 0 && !showInviteForm && !newLink && (
        <EmptyState
          title="No candidates yet"
          description="Invite a candidate to begin this interview."
        />
      )}

      {sortedCandidates.length > 0 && (
        <Card className="overflow-x-auto p-0">
          <table className="w-full min-w-[640px] border-collapse text-sm">
            <thead>
              <tr className="border-b border-border text-left text-xs font-semibold uppercase tracking-wide text-ink-muted">
                <th className="px-5 py-3">Candidate</th>
                <th className="px-5 py-3">Status</th>
                <th className="px-5 py-3">Overall</th>
                <th className="px-5 py-3">Recommendation</th>
                <th className="px-5 py-3 text-right">Action</th>
              </tr>
            </thead>
            <tbody>
              {sortedCandidates.map((candidate) => (
                <tr key={candidate.interview_id} className="border-b border-border last:border-0">
                  <td className="px-5 py-3">
                    <p className="font-medium text-ink">{candidate.candidate_name}</p>
                    {candidate.candidate_email && (
                      <p className="text-xs text-ink-muted">{candidate.candidate_email}</p>
                    )}
                  </td>
                  <td className="px-5 py-3">
                    <StatusBadge status={candidate.status} />
                    {candidate.status === "in_progress" &&
                      progressByInterview[candidate.interview_id] !== undefined && (
                        <span className="ml-2 text-xs text-ink-muted">
                          Question {progressByInterview[candidate.interview_id]} so far
                        </span>
                      )}
                  </td>
                  <td className="px-5 py-3 text-ink">
                    {candidate.overall_score !== null
                      ? Math.round(candidate.overall_score * 100)
                      : "N/A"}
                  </td>
                  <td className="px-5 py-3 text-ink">
                    {candidate.recommendation ? formatRecommendation(candidate.recommendation) : "N/A"}
                  </td>
                  <td className="px-5 py-3 text-right">
                    {candidate.status === "completed" ? (
                      <Button
                        variant="secondary"
                        onClick={() =>
                          navigate(`/recruiter/interviews/${jobId}/reports/${candidate.interview_id}`)
                        }
                      >
                        View Report
                      </Button>
                    ) : (
                      <span className="text-ink-muted">N/A</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  )
}
