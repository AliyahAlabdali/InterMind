import { useState } from "react"
import { useNavigate } from "react-router-dom"
import { createJob } from "../api/jobs"
import { createInterviewPlan } from "../api/interviewPlans"
import { ApiError } from "../api/client"
import { JobDescriptionForm } from "../components/job/JobDescriptionForm"
import { JobSummaryCard } from "../components/job/JobSummaryCard"
import { ErrorBanner } from "../components/ui/ErrorBanner"
import type { Job } from "../types"

export function HomePage() {
  const navigate = useNavigate()
  const [job, setJob] = useState<Job | null>(null)
  const [isCreating, setIsCreating] = useState(false)
  const [isPlanning, setIsPlanning] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleCreateJob(description: string) {
    setIsCreating(true)
    setError(null)
    try {
      const created = await createJob(description)
      setJob(created)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong creating the job.")
    } finally {
      setIsCreating(false)
    }
  }

  async function handleGeneratePlan() {
    if (!job) return
    setIsPlanning(true)
    setError(null)
    try {
      await createInterviewPlan(job.id)
      navigate(`/jobs/${job.id}/plan`)
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Something went wrong generating the plan.",
      )
      setIsPlanning(false)
    }
  }

  return (
    <div className="flex flex-col gap-8">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight text-ink">
          Plan an intelligent interview
        </h1>
        <p className="mt-2 max-w-2xl text-sm text-ink-soft">
          Paste a job description and InterMind will extract the role, match it against
          O*NET occupational data, and build a grounded, competency-based interview plan.
        </p>
      </div>

      {error && <ErrorBanner message={error} />}

      {!job && <JobDescriptionForm onSubmit={handleCreateJob} isSubmitting={isCreating} />}

      {job && (
        <JobSummaryCard job={job} onGeneratePlan={handleGeneratePlan} isGeneratingPlan={isPlanning} />
      )}
    </div>
  )
}
