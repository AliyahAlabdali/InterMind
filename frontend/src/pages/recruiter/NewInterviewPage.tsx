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
        title="Turn a job description into a structured interview"
        description="Paste the role requirements below. InterMind will identify the skills and competencies that matter and build an interview tailored to the role, autonomously, from job description to candidate report."
      />

      {error && <ErrorBanner message={error} />}

      <JobDescriptionForm onSubmit={handleCreateJob} isSubmitting={isCreating} />
    </div>
  )
}
