import { useCallback, useState } from "react"
import { useNavigate, useParams } from "react-router-dom"
import { getJob } from "../../api/jobs"
import { createInterviewPlan } from "../../api/interviewPlans"
import { ApiError } from "../../api/client"
import { useAsyncData } from "../../hooks/useAsyncData"
import { Spinner } from "../../components/ui/Spinner"
import { ErrorBanner } from "../../components/ui/ErrorBanner"
import { PageHeader } from "../../components/ui/PageHeader"
import { JobSummaryCard } from "../../components/job/JobSummaryCard"

export function JobAnalysisPage() {
  const { jobId } = useParams<{ jobId: string }>()
  const navigate = useNavigate()
  const [isPlanning, setIsPlanning] = useState(false)
  const [planError, setPlanError] = useState<string | null>(null)

  const jobFetcher = useCallback(() => getJob(jobId!), [jobId])
  const job = useAsyncData(jobFetcher, [jobId])

  async function handleContinue() {
    if (!jobId) return
    setIsPlanning(true)
    setPlanError(null)
    try {
      await createInterviewPlan(jobId)
      navigate(`/recruiter/interviews/${jobId}/plan`)
    } catch (err) {
      setPlanError(
        err instanceof ApiError ? err.message : "Something went wrong building the interview plan.",
      )
      setIsPlanning(false)
    }
  }

  if (job.isLoading) return <Spinner label="Loading job analysis…" />
  if (job.error) return <ErrorBanner message={job.error} onRetry={job.refetch} />
  if (!job.data) return null

  return (
    <div className="flex flex-col gap-6 animate-enter">
      <PageHeader eyebrow="Job Analysis" title="Role understanding" />
      {planError && <ErrorBanner message={planError} />}
      <JobSummaryCard
        job={job.data}
        onGeneratePlan={handleContinue}
        isGeneratingPlan={isPlanning}
      />
    </div>
  )
}
