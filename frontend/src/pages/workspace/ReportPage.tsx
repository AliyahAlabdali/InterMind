import { useCallback } from "react"
import { Link, useParams } from "react-router-dom"
import { motion } from "motion/react"
import { ArrowLeft } from "lucide-react"
import { getInterview, getInterviewReport, listJobInterviews } from "../../api/interviews"
import { getJobDetail } from "../../api/jobs"
import { getInterviewPlan } from "../../api/interviewPlans"
import { useAsyncData } from "../../hooks/useAsyncData"
import { Spinner } from "../../components/ui/Spinner"
import { ErrorBanner } from "../../components/ui/ErrorBanner"
import { EvidenceTarget } from "../../components/report/EvidenceTarget"
import { EvidenceMark } from "../../components/report/EvidenceMark"
import { evidenceKind } from "../../lib/evidence"
import { InterviewTranscript } from "../../components/report/InterviewTranscript"
import { transcriptCounts } from "../../lib/transcript"
import { rise, stagger } from "../../design/motion"
import { formatRecommendation, formatSeniority } from "../../lib/format"
import type { CompletionReason } from "../../types"
import { useDocumentTitle } from "../../hooks/useDocumentTitle"

const COMPLETION_REASON_LABEL: Record<CompletionReason, string> = {
  sufficient_evidence: "Every required area was reached.",
  budget_exhausted: "The interview reached its length limit before every required area.",
}

/**
 * The report, as evidence rather than as a score.
 *
 * The old page opened on a 76px percentage, which is the one thing in here that should never be
 * read alone: it is a weighted mean over whatever the interview managed to assess, and on its
 * own it says nothing about what the candidate actually showed. So the assessment is a
 * contained band - recommendation in words first, the figure beside it, and the sentence
 * explaining what the figure means in the same block - and the body of the page is the evidence
 * that produced it.
 *
 * The order is the argument: what the interview concluded, then in one paragraph why, then each
 * requirement with the candidate's own words under it, then what was never reached, then the
 * conversation itself.
 */
export function ReportPage() {
  const { interviewId } = useParams<{ interviewId: string }>()

  const reportFetcher = useCallback(() => getInterviewReport(interviewId!), [interviewId])
  const report = useAsyncData(reportFetcher, [interviewId])

  const jobId = report.data?.job_id
  const jobFetcher = useCallback(() => getJobDetail(jobId!), [jobId])
  const job = useAsyncData(jobFetcher, [jobId], Boolean(jobId))

  const planFetcher = useCallback(() => getInterviewPlan(jobId!), [jobId])
  const plan = useAsyncData(planFetcher, [jobId], Boolean(jobId))

  // Who this is about. The report itself carries no candidate identity, so it comes from the
  // role's own session list - a report that never names the person is a real gap, not a style
  // choice.
  const sessionsFetcher = useCallback(() => listJobInterviews(jobId!), [jobId])
  const sessions = useAsyncData(sessionsFetcher, [jobId], Boolean(jobId))

  // The conversation itself, for the record below. The report payload deliberately keeps one
  // entry per requirement (the answer that settled it), so a requirement explored over two turns
  // appears there once - which is right for scoring and wrong for a transcript. The interview's
  // own state carries every turn, and a recruiter reaches it with their session (empty candidate
  // token). Failing this fetch must never take the report down: it is the last section, and
  // everything above it comes from the report itself.
  const interviewFetcher = useCallback(() => getInterview(interviewId!, ""), [interviewId])
  const interview = useAsyncData(interviewFetcher, [interviewId], Boolean(interviewId))
  const candidate = sessions.data?.find((s) => s.interview_id === interviewId)
  // null until the name is known, so the tab never flashes a wrong title.
  useDocumentTitle(candidate ? `${candidate.candidate_name} · Report` : null)

  if (report.isLoading) {
    return (
      <div className="shell py-16">
        <Spinner label="Loading this report…" block />
      </div>
    )
  }
  if (report.error) {
    return (
      <div className="shell py-16">
        <ErrorBanner message={report.error} onRetry={report.refetch} />
      </div>
    )
  }
  if (!report.data) return null

  const data = report.data
  const scorePercent = Math.round(data.overall_score * 100)

  const assessed = data.competencies.filter((c) => c.evidence_strength !== "not_assessed")
  const notAssessed = data.competencies.filter((c) => c.evidence_strength === "not_assessed")
  const requiredTotal =
    plan.data?.coverage_targets.filter((t) => t.requirement_level === "required").length ?? 0
  const requiredAssessed = Math.max(requiredTotal - data.unassessed_required_targets.length, 0)

  // A target established from an answer to a different question has a history entry too, so that
  // its evidence is attributable - but it was never asked, so it has no place in a transcript.
  // The report already marks exactly those, by the same id the turn carries.
  const notAsked = new Set(
    data.question_evaluations
      .filter((item) => item.assessment_method === "cross_target")
      .map((item) => item.question_id),
  )
  const targetIds = plan.data?.coverage_targets.map((t) => t.id) ?? []
  const turns = (interview.data?.history ?? []).filter((turn) => !notAsked.has(turn.question_id))
  const transcript = transcriptCounts(turns, targetIds)
  const transcriptUnavailable = !interview.isLoading && turns.length === 0

  return (
    <motion.div variants={stagger(0.07)} initial="hidden" animate="visible">
      {/* Who and what */}
      <div className="border-b border-hair">
        <div className="shell py-10 sm:py-12">
          <motion.div variants={rise} className="mb-6">
            <Link
              to="/candidates"
              className="inline-flex min-h-[44px] items-center gap-1.5 text-sm text-fg-muted transition-colors hover:text-fg"
            >
              <ArrowLeft size={14} aria-hidden="true" />
              All candidates
            </Link>
          </motion.div>

          <motion.header variants={rise}>
            <p className="type-data text-fg-muted">Interview report</p>
            <h1 className="type-page mt-2 text-balance text-fg">
              {candidate?.candidate_name ?? "Candidate"}
            </h1>
            <p className="type-data mt-2 text-fg-muted">
              {job.data?.job_spec.role_title ?? "Role"}
              {job.data && ` · ${formatSeniority(job.data.job_spec.seniority)}`}
              {candidate?.candidate_email && ` · ${candidate.candidate_email}`}
            </p>
          </motion.header>
        </div>
      </div>

      {/* The assessment. Contained, and never a number on its own. */}
      <motion.section variants={rise} className="relative border-y border-hair bg-raise">
        <span aria-hidden="true" className="veil-night" />
        <div className="shell relative py-10 sm:py-12">
          <h2 className="type-data text-fg-muted">Assessment</h2>

          <div className="mt-5 flex flex-wrap items-baseline gap-x-12 gap-y-6">
            <div>
              <p className="type-group text-fg">{formatRecommendation(data.recommendation)}</p>
              <p className="type-data mt-1.5 text-fg-muted">Evidence assessment</p>
            </div>
            {/* `overall_evidence_strength` is deliberately not shown beside this. It is a second
                banding of the same score the assessment already reads out, with different cut
                points, so the two labels disagree in words about one number (0.20 read as
                "Limited evidence" here and "Insufficient evidence" there). The field stays in the
                payload for callers that want the band itself. */}
            <div>
              <p className="type-group type-numeric text-fg">{scorePercent}%</p>
              <p className="type-data mt-1.5 text-fg-muted">Weighted score</p>
            </div>
            {requiredTotal > 0 && (
              <div>
                <p className="type-group type-numeric text-fg">
                  {requiredAssessed} of {requiredTotal}
                </p>
                <p className="type-data mt-1.5 text-fg-muted">Required areas reached</p>
              </div>
            )}
          </div>

          <p className="type-copy mt-8 border-t border-hair pt-5 text-sm text-fg-soft">
            {data.score_basis_note} {COMPLETION_REASON_LABEL[data.completion_reason]} This is an
            assessment of the interview evidence for you to weigh, not a hiring decision.
          </p>
        </div>
      </motion.section>

      {/* The reading */}
      <div className="shell flex flex-col gap-14 py-12 sm:py-14">
        <motion.section variants={rise}>
          <h2 className="type-group text-fg">In summary</h2>
          <p className="type-copy mt-4 text-[1.0625rem] text-fg-soft">{data.summary}</p>

          {(data.strengths.length > 0 || data.weaknesses.length > 0) && (
            <div className="mt-10 grid grid-cols-1 gap-x-12 gap-y-8 sm:grid-cols-2">
              <div>
                <h3 className="type-data border-b border-hair pb-2 font-medium text-fg">
                  What stood out
                </h3>
                <ul className="mt-4 flex flex-col gap-3">
                  {data.strengths.length === 0 && (
                    <li className="text-sm text-fg-muted">Nothing recorded.</li>
                  )}
                  {data.strengths.map((item, index) => (
                    <li key={index} className="text-sm leading-relaxed text-fg-soft">
                      {item}
                    </li>
                  ))}
                </ul>
              </div>
              <div>
                <h3 className="type-data border-b border-hair pb-2 font-medium text-fg">
                  Worth exploring further
                </h3>
                <ul className="mt-4 flex flex-col gap-3">
                  {data.weaknesses.length === 0 && (
                    <li className="text-sm text-fg-muted">Nothing recorded.</li>
                  )}
                  {data.weaknesses.map((item, index) => (
                    <li key={index} className="text-sm leading-relaxed text-fg-soft">
                      {item}
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          )}
        </motion.section>

        {/* The evidence itself - the page's real body. */}
        <motion.section variants={rise}>
          <div className="flex flex-col gap-2 border-b border-hair-strong pb-3 lg:flex-row lg:items-end lg:justify-between lg:gap-10">
            <h2 className="type-group text-fg">Evidence</h2>
            <p className="type-data max-w-md text-fg-muted">
              Each requirement the interview reached, and what the candidate actually said about
              it. Open a row to read their own words.
            </p>
          </div>

          <motion.ul variants={stagger(0.03)} className="mt-2">
            {assessed.map((assessment) => (
              <EvidenceTarget
                key={`${assessment.category}-${assessment.name}`}
                assessment={assessment}
              />
            ))}
          </motion.ul>

          <Legend />
        </motion.section>
      </div>

      {/* What the interview never got to. Deliberately on its own quiet surface, and worded so
          it cannot be read as a finding about the candidate. */}
      {(data.unassessed_required_targets.length > 0 || notAssessed.length > 0) && (
        <motion.section variants={rise} className="border-y border-hair">
          <div className="shell py-12 sm:py-14">
            <h2 className="type-group text-fg">Not established</h2>
            <p className="type-copy mt-3 text-sm text-fg-soft">
              The interview ended before these were settled. This is a statement about how far the
              conversation got, not a judgement about the candidate.
            </p>

            {data.unassessed_required_targets.length > 0 && (
              <div className="mt-8">
                <h3 className="type-data border-b border-hair pb-2 font-medium text-fg">
                  Required, never reached
                </h3>
                <ul className="mt-3 flex flex-col">
                  {data.unassessed_required_targets.map((name) => (
                    <li
                      key={name}
                      className="flex items-center gap-3 border-b border-hair py-2.5 text-sm text-fg-soft last:border-0"
                    >
                      <EvidenceMark kind="none" />
                      {name}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {notAssessed.length > 0 && (
              <div className="mt-8">
                <h3 className="type-data border-b border-hair pb-2 font-medium text-fg">
                  Asked about, but nothing established
                </h3>
                <ul className="mt-3 flex flex-col">
                  {notAssessed.map((item) => (
                    <li
                      key={`${item.category}-${item.name}`}
                      className="flex items-center gap-3 border-b border-hair py-2.5 text-sm text-fg-soft last:border-0"
                    >
                      <EvidenceMark
                        kind={evidenceKind(item.evidence_type, item.evidence_strength)}
                      />
                      {item.name}
                      <span className="type-data ml-auto text-fg-muted">
                        {item.evidence_label || "Not assessed"}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </motion.section>
      )}

      {/* The conversation, in full. */}
      <div className="shell py-12 sm:py-14">
        <motion.section variants={rise}>
          <div className="flex flex-col gap-2 border-b border-hair-strong pb-3 lg:flex-row lg:items-end lg:justify-between lg:gap-10">
            <h2 className="type-group text-fg">Interview record</h2>
            <p className="type-data max-w-md text-fg-muted">
              {/* No count until the turns are actually in hand, so the page never claims a
                  number while the history is still loading or missing. */}
              {turns.length === 0
                ? "Everything above is a reading of this."
                : `Everything above is a reading of this. ${transcript.total} ${
                    transcript.total === 1 ? "question" : "questions"
                  } asked${
                    transcript.followUps > 0
                      ? `, including ${transcript.followUps} follow-${
                          transcript.followUps === 1 ? "up" : "ups"
                        }`
                      : ""
                  }.`}
            </p>
          </div>
          <div className="mt-6">
            {turns.length > 0 && <InterviewTranscript turns={turns} targetIds={targetIds} />}
            {transcriptUnavailable && (
              <p className="text-sm text-fg-muted">
                The conversation is not available for this interview. The assessment and evidence
                above were built while it was still on record.
              </p>
            )}
          </div>
        </motion.section>
      </div>
    </motion.div>
  )
}

/** What the marks mean. Short, and only the states this product actually produces. */
function Legend() {
  const items = [
    { kind: "demonstrated" as const, label: "Demonstrated with a concrete example" },
    { kind: "partial" as const, label: "Partly shown" },
    { kind: "claimed" as const, label: "Claimed, not substantiated" },
    { kind: "lack" as const, label: "Candidate said they lack this" },
    { kind: "none" as const, label: "Nothing established either way" },
  ]

  return (
    <ul className="mt-6 flex flex-wrap gap-x-6 gap-y-2">
      {items.map((item) => (
        <li key={item.kind} className="type-data flex items-center gap-2 text-fg-muted">
          <EvidenceMark kind={item.kind} />
          {item.label}
        </li>
      ))}
    </ul>
  )
}
