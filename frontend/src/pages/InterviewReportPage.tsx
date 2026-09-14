import { useCallback } from "react"
import { useParams } from "react-router-dom"
import { getInterviewReport } from "../api/interviews"
import { getJob } from "../api/jobs"
import { useAsyncData } from "../hooks/useAsyncData"
import { Spinner } from "../components/ui/Spinner"
import { ErrorBanner } from "../components/ui/ErrorBanner"
import { Card } from "../components/ui/Card"
import { ReportHeader } from "../components/report/ReportHeader"
import { StrengthWeaknessLists } from "../components/report/StrengthWeaknessLists"
import { CompetencyAssessmentList } from "../components/report/CompetencyAssessmentList"
import { QuestionEvaluationList } from "../components/report/QuestionEvaluationList"

export function InterviewReportPage() {
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
    <div className="flex flex-col gap-6">
      <ReportHeader
        roleTitle={job.data?.job_spec.role_title ?? null}
        overallScore={data.overall_score}
        recommendation={data.recommendation}
      />

      <Card>
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-muted">
          Summary
        </h3>
        <p className="text-sm leading-relaxed text-ink-soft">{data.summary}</p>
      </Card>

      <StrengthWeaknessLists strengths={data.strengths} weaknesses={data.weaknesses} />

      <CompetencyAssessmentList assessments={data.competencies} />

      <QuestionEvaluationList items={data.question_evaluations} />
    </div>
  )
}
