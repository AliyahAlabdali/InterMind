import { useState } from "react"
import { useNavigate } from "react-router-dom"
import { createJob } from "../../api/jobs"
import { ApiError } from "../../api/client"
import { JobDescriptionForm } from "../../components/job/JobDescriptionForm"
import { ErrorBanner } from "../../components/ui/ErrorBanner"
import { PageHeader } from "../../components/ui/PageHeader"

export function NewInterviewPage() {
  const navigate = useNavigate()
  const [isCreating, setIsCreating] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleCreateJob(description: string) {
    setIsCreating(true)
    setError(null)
    try {
      const job = await createJob(description)
      navigate(`/recruiter/interviews/${job.id}/job-analysis`)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong creating the job.")
      setIsCreating(false)
    }
  }

  return (
    <div className="flex flex-col gap-8 animate-enter">
      <PageHeader
        eyebrow="Create Interview"
        title="Plan an intelligent interview"
        description="Paste a job description and InterMind will extract the role, match it against O*NET occupational data, and build a grounded, competency-based interview plan. InterMind is autonomous by default — you define the role, it handles the interview intelligence."
      />

      {error && <ErrorBanner message={error} />}

      <JobDescriptionForm onSubmit={handleCreateJob} isSubmitting={isCreating} />
    </div>
  )
}
