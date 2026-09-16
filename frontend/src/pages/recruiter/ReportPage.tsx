import { useCallback } from "react"
import { Link, useParams } from "react-router-dom"
import { getInterviewReport } from "../../api/interviews"
import { getJob } from "../../api/jobs"
import { useAsyncData } from "../../hooks/useAsyncData"
import { Spinner } from "../../components/ui/Spinner"
import { ErrorBanner } from "../../components/ui/ErrorBanner"
import { Card } from "../../components/ui/Card"
import { ReportHeader } from "../../components/report/ReportHeader"
import { StrengthWeaknessLists } from "../../components/report/StrengthWeaknessLists"
import { CompetencyAssessmentList } from "../../components/report/CompetencyAssessmentList"
import { QuestionEvaluationList } from "../../components/report/QuestionEvaluationList"

export function ReportPage() {
  const { interviewId } = useParams<{ interviewId: string }>()

  const reportFetcher = useCallback(() => getInterviewReport(interviewId!), [interviewId])
  const report = useAsyncData(reportFetcher, [interviewId])

  const jobId = report.data?.job_id
  const jobFetcher = useCallback(() => getJob(jobId!), [jobId])
  const job = useAsyncData(jobFetcher, [jobId], Boolean(jobId))

  if (report.isLoading) {
    return <Spinner label="Loading report…" />
  }

  if (report.error) {
    return <ErrorBanner message={report.error} onRetry={report.refetch} />
  }

  if (!report.data) return null

  const data = report.data

  return (
    <div className="flex flex-col gap-6 animate-enter">
      {jobId && (
        <Link
          to={`/recruiter/interviews/${jobId}`}
          className="text-xs text-ink-muted underline underline-offset-2 hover:text-ink"
        >
          ← Back to candidates
        </Link>
      )}
      <ReportHeader
        roleTitle={job.data?.job_spec.role_title ?? null}
        overallScore={data.overall_score}
        overallEvidenceStrength={data.overall_evidence_strength}
        recommendation={data.recommendation}
      />

      <Card>
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-muted">
          Summary
        </h3>
        <p className="text-sm leading-relaxed text-ink-soft">{data.summary}</p>
      </Card>

      <CompetencyAssessmentList assessments={data.competencies} />

      <StrengthWeaknessLists strengths={data.strengths} weaknesses={data.weaknesses} />

      <QuestionEvaluationList items={data.question_evaluations} />
    </div>
  )
}
