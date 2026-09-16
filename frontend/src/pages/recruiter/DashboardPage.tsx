import { useNavigate } from "react-router-dom"
import { listJobs } from "../../api/jobs"
import { useAsyncData } from "../../hooks/useAsyncData"
import { PageHeader } from "../../components/ui/PageHeader"
import { Button } from "../../components/ui/Button"
import { EmptyState } from "../../components/ui/EmptyState"
import { Spinner } from "../../components/ui/Spinner"
import { ErrorBanner } from "../../components/ui/ErrorBanner"
import { InterviewCard } from "../../components/dashboard/InterviewCard"

export function DashboardPage() {
  const navigate = useNavigate()
  const jobs = useAsyncData(listJobs, [])

  return (
    <div className="flex flex-col gap-6 animate-enter">
      <PageHeader
        eyebrow="Dashboard"
        title="Interviews"
        description="Every interview and candidate below reflects live backend state."
        actions={
          <Button onClick={() => navigate("/recruiter/interviews/new")}>New Interview</Button>
        }
      />

      {jobs.isLoading && <Spinner label="Loading interviews…" />}
      {jobs.error && <ErrorBanner message={jobs.error} onRetry={jobs.refetch} />}

      {jobs.data && jobs.data.length === 0 && (
        <EmptyState
          title="No interviews yet"
          description="Create your first interview by pasting a job description. InterMind will analyze the role and build an adaptive interview plan."
          action={
            <Button onClick={() => navigate("/recruiter/interviews/new")}>New Interview</Button>
          }
        />
      )}

      {jobs.data && jobs.data.length > 0 && (
        <div className="flex flex-col gap-3">
          {jobs.data.map((job) => (
            <InterviewCard key={job.id} job={job} />
          ))}
        </div>
      )}
    </div>
  )
}
