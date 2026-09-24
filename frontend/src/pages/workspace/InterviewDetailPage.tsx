import { useCallback, useRef, useState } from "react"
import type { FormEvent } from "react"
import { Link, useParams } from "react-router-dom"
import { AnimatePresence, motion } from "motion/react"
import { ArrowLeft, Check, Plus } from "lucide-react"
import { getJob } from "../../api/jobs"
import { createInterviewPlan, getInterviewPlan } from "../../api/interviewPlans"
import { listJobInterviews, startInterview } from "../../api/interviews"
import { ApiError } from "../../api/client"
import { useAsyncData } from "../../hooks/useAsyncData"
import { CandidateRow } from "../../components/workspace/CandidateRow"
import { OccupationMatchCard } from "../../components/plan/OccupationMatchCard"
import { Spinner, SkeletonRows } from "../../components/ui/Spinner"
import { ErrorBanner } from "../../components/ui/ErrorBanner"
import { Button } from "../../components/ui/Button"
import { TextInput } from "../../components/ui/TextInput"
import { CopyLinkButton } from "../../components/ui/CopyLinkButton"
import { EmptyState } from "../../components/ui/EmptyState"
import { PageIntro } from "../../components/ui/PageIntro"
import { candidateLink } from "../../lib/candidateLink"
import { formatSeniority } from "../../lib/format"
import { fade, rise, stagger, transition } from "../../design/motion"
import type { CandidateOverview } from "../../hooks/useWorkspaceOverview"
import { useDocumentTitle } from "../../hooks/useDocumentTitle"

/**
 * One role: its people, and the brief the interview was built from.
 *
 * Candidates come first because that is what this page is opened to do - invite someone, copy a
 * link, read a report. What the interview probes sits below on the warm band: it is the reason
 * the interviews are worth anything, but it is reference material, and putting a fourteen-row
 * requirement map above the candidate list buried the actions under it.
 */
export function InterviewDetailPage() {
  useDocumentTitle("Role")
  const { jobId } = useParams<{ jobId: string }>()

  const jobFetcher = useCallback(() => getJob(jobId!), [jobId])
  const job = useAsyncData(jobFetcher, [jobId])

  const planFetcher = useCallback(() => getInterviewPlan(jobId!), [jobId])
  const plan = useAsyncData(planFetcher, [jobId])

  const candidatesFetcher = useCallback(() => listJobInterviews(jobId!), [jobId])
  const candidates = useAsyncData(candidatesFetcher, [jobId])

  const [isBuildingPlan, setIsBuildingPlan] = useState(false)
  const [showInvite, setShowInvite] = useState(false)
  const [candidateName, setCandidateName] = useState("")
  const [candidateEmail, setCandidateEmail] = useState("")
  const [isInviting, setIsInviting] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  const [newLink, setNewLink] = useState<{ interviewId: string; token: string; name: string } | null>(
    null,
  )
  const nameFieldRef = useRef<HTMLInputElement>(null)

  function openInvite() {
    setShowInvite(true)
    // The form is the whole point of pressing the button, so put the cursor in it.
    window.setTimeout(() => nameFieldRef.current?.focus(), 60)
  }

  async function handleBuildPlan() {
    if (!jobId) return
    setIsBuildingPlan(true)
    setActionError(null)
    try {
      await createInterviewPlan(jobId)
      plan.refetch()
    } catch (err) {
      setActionError(
        err instanceof ApiError ? err.message : "Something went wrong building the interview.",
      )
    } finally {
      setIsBuildingPlan(false)
    }
  }

  async function handleInvite(event: FormEvent) {
    event.preventDefault()
    if (!jobId || !candidateName.trim()) return
    setIsInviting(true)
    setActionError(null)
    try {
      const interview = await startInterview(jobId, candidateName.trim(), candidateEmail.trim())
      if (!interview.candidate_access_token) {
        throw new Error("The server did not return a link for this candidate.")
      }
      setNewLink({
        interviewId: interview.interview_id,
        token: interview.candidate_access_token,
        name: candidateName.trim(),
      })
      setCandidateName("")
      setCandidateEmail("")
      setShowInvite(false)
      candidates.refetch()
    } catch (err) {
      setActionError(
        err instanceof ApiError ? err.message : "Something went wrong inviting this candidate.",
      )
    } finally {
      setIsInviting(false)
    }
  }

  if (job.isLoading) {
    return (
      <div className="shell py-16">
        <Spinner label="Loading this role…" block />
      </div>
    )
  }
  if (job.error) {
    return (
      <div className="shell py-16">
        <ErrorBanner message={job.error} onRetry={job.refetch} />
      </div>
    )
  }
  if (!job.data) return null

  const spec = job.data.job_spec
  const targets = plan.data?.coverage_targets ?? []
  const requiredCount = targets.filter((t) => t.requirement_level === "required").length
  const hasPlan = targets.length > 0

  const candidateOverviews: CandidateOverview[] = (candidates.data ?? []).map((summary) => ({
    summary,
    assessed: 0,
    total: 0,
    ratio: 0,
  }))

  return (
    <motion.div variants={stagger(0.07)} initial="hidden" animate="visible">
      <div className="border-b border-hair">
        <div className="shell py-10 sm:py-12">
          <motion.div variants={rise} className="mb-6">
            <Link
              to="/interviews"
              className="inline-flex min-h-[44px] items-center gap-1.5 text-sm text-fg-muted transition-colors hover:text-fg"
            >
              <ArrowLeft size={14} aria-hidden="true" />
              All interviews
            </Link>
          </motion.div>

          <PageIntro
            title={spec.role_title}
            lede={spec.summary || undefined}
            actions={
              // Only once the interview exists. Before that the page's single primary action
              // lives in the empty state below, next to the explanation for it - two identical
              // "Build the interview" buttons on one screen is noise, not emphasis.
              hasPlan ? (
                <Button onClick={openInvite}>
                  <Plus size={15} strokeWidth={2.2} aria-hidden="true" />
                  Invite candidate
                </Button>
              ) : undefined
            }
            meta={
              <p className="type-data text-fg-muted">
                {formatSeniority(spec.seniority)}
                {hasPlan && ` · ${targets.length} areas to explore · ${requiredCount} required`}
                {candidateOverviews.length > 0 &&
                  ` · ${candidateOverviews.length} ${
                    candidateOverviews.length === 1 ? "candidate" : "candidates"
                  }`}
              </p>
            }
          />
        </div>
      </div>

      <div className="shell flex flex-col gap-8 py-10 sm:py-12">
        {actionError && (
          <motion.div variants={rise}>
            <ErrorBanner message={actionError} />
          </motion.div>
        )}

        {/* Invite */}
        <AnimatePresence>
          {showInvite && (
            <motion.form
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              transition={transition.state}
              onSubmit={handleInvite}
              className="overflow-hidden"
            >
              <div className="plane-raised p-5 sm:p-6">
                <h2 className="type-group text-fg">Invite a candidate</h2>
                <p className="type-data mt-1.5 text-fg-muted">
                  This creates a private link for one person. Nobody else can use it.
                </p>
                <div className="mt-5 grid grid-cols-1 gap-4 sm:grid-cols-2">
                  <TextInput
                    id="candidate-name"
                    ref={nameFieldRef}
                    label="Name"
                    value={candidateName}
                    onChange={(e) => setCandidateName(e.target.value)}
                    autoComplete="off"
                    required
                  />
                  <TextInput
                    id="candidate-email"
                    label="Email"
                    type="email"
                    value={candidateEmail}
                    onChange={(e) => setCandidateEmail(e.target.value)}
                    autoComplete="off"
                    hint="Optional - it only labels the candidate for you."
                  />
                </div>
                <div className="mt-6 flex flex-wrap justify-end gap-2">
                  <Button type="button" variant="ghost" onClick={() => setShowInvite(false)}>
                    Cancel
                  </Button>
                  <Button type="submit" isLoading={isInviting} disabled={!candidateName.trim()}>
                    Create their link
                  </Button>
                </div>
              </div>
            </motion.form>
          )}
        </AnimatePresence>

        <AnimatePresence>
          {newLink && (
            <motion.div
              variants={fade}
              initial="hidden"
              animate="visible"
              exit="exit"
              role="status"
              className="flex flex-wrap items-center justify-between gap-x-6 gap-y-4 rounded-[20px] border border-accent/25 bg-accent-soft px-5 py-4"
            >
              <p className="flex items-start gap-2.5 text-sm text-fg">
                <Check size={16} aria-hidden="true" className="mt-0.5 shrink-0 text-accent" />
                <span>
                  <span className="font-medium">{newLink.name}</span> is ready to interview. Send
                  them this link - you can copy it again from their row at any time.
                </span>
              </p>
              <div className="flex items-center gap-2">
                <CopyLinkButton link={candidateLink(newLink.interviewId, newLink.token)} />
                <Button variant="ghost" size="sm" onClick={() => setNewLink(null)}>
                  Dismiss
                </Button>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Candidates */}
        <motion.section variants={rise}>
          <h2 className="type-group border-b border-hair-strong pb-3 text-fg">Candidates</h2>

          {candidates.isLoading && <SkeletonRows rows={2} />}

          {!candidates.isLoading && candidateOverviews.length === 0 && !showInvite && (
            <div className="pt-6">
              <EmptyState
                title={hasPlan ? "Nobody invited yet" : "Build the interview first"}
                body={
                  hasPlan
                    ? "Each candidate gets their own private link. The interview adapts to whoever opens it, so two people applying for this role will not get the same questions."
                    : "InterMind needs to read this role and decide what to assess before anyone can interview for it."
                }
                action={
                  hasPlan ? (
                    <Button onClick={openInvite}>
                      <Plus size={15} strokeWidth={2.2} aria-hidden="true" />
                      Invite the first candidate
                    </Button>
                  ) : (
                    <Button onClick={handleBuildPlan} isLoading={isBuildingPlan}>
                      Build the interview
                    </Button>
                  )
                }
              />
            </div>
          )}

          {candidateOverviews.length > 0 && (
            <motion.ul variants={stagger(0.04)} initial="hidden" animate="visible">
              {candidateOverviews.map((candidate) => (
                <CandidateRow key={candidate.summary.interview_id} candidate={candidate} />
              ))}
            </motion.ul>
          )}
        </motion.section>
      </div>

      {/* The plan's own inventory is deliberately not listed here.
          Enumerating all fifteen targets put the interview's internal brief on a recruiter
          page where it was neither actionable nor accurate about the candidate: every
          requirement appeared identical whether it had been assessed, partially evidenced or
          never reached at all, which reads as a scorecard of failures. The compact facts that
          are useful live in the header above (areas, required count, candidates); what any
          individual candidate actually reached is per-interview, and belongs to their own
          coverage rail in the list above and their report. */}

      {plan.isLoading && !hasPlan && (
        <div className="shell py-10">
          <Spinner label="Loading the interview plan…" />
        </div>
      )}

      {plan.data && (
        <motion.div variants={rise} className="shell py-10">
          <OccupationMatchCard
            match={plan.data.occupation_match}
            alternates={plan.data.alternate_matches}
            onetGroundingUsed={plan.data.onet_grounding_used}
          />
        </motion.div>
      )}
    </motion.div>
  )
}
