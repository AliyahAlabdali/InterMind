import { useState } from "react"
import type { ReactNode } from "react"
import { useNavigate } from "react-router-dom"
import { AnimatePresence, motion } from "motion/react"
import { ArrowLeft, ArrowRight } from "lucide-react"
import { createJob } from "../../api/jobs"
import { createInterviewPlan } from "../../api/interviewPlans"
import { ApiError } from "../../api/client"
import { Button } from "../../components/ui/Button"
import { ErrorBanner } from "../../components/ui/ErrorBanner"
import { Interviewer } from "../../interviewer/Interviewer"
import { rise, stagger, transition } from "../../design/motion"
import { formatSeniority } from "../../lib/format"
import type { Job } from "../../types"
import { useDocumentTitle } from "../../hooks/useDocumentTitle"

/**
 * Creating an interview, as three named steps rather than one long form.
 *
 * The middle step is the reason for the shape. InterMind reads the job description and decides
 * what the role actually requires, and a recruiter needs to see and agree with that reading
 * before an interview is built on top of it - so "what InterMind understood" is a stage of the
 * flow, not a side effect of submitting.
 */
const STEPS = ["Describe the role", "Check what was read", "Build the interview"] as const

/** Real stages of the one request that is genuinely running - not a fabricated progress show. */
const ANALYSIS_STAGES = ["Reading the description", "Identifying requirements", "Mapping competencies"]

/** Below this, a description usually has not said enough for a useful interview. */
const SHORT_DESCRIPTION = 220

function Stepper({ current }: { current: number }) {
  return (
    <ol className="flex flex-wrap items-center gap-x-3 gap-y-2">
      {STEPS.map((step, index) => {
        const state = index < current ? "done" : index === current ? "current" : "todo"
        return (
          <li key={step} className="flex items-center gap-3">
            <span
              className={`type-data inline-flex items-center gap-2 ${
                state === "todo" ? "text-fg-muted" : "text-fg"
              }`}
            >
              <span
                aria-hidden="true"
                className={`inline-flex h-5 w-5 items-center justify-center rounded-full text-[0.6875rem] ${
                  state === "current"
                    ? "bg-fg text-canvas"
                    : state === "done"
                      ? "bg-accent-soft text-accent"
                      : "border border-hair-strong text-fg-muted"
                }`}
              >
                {state === "done" ? "✓" : index + 1}
              </span>
              <span className={state === "current" ? "font-medium" : ""}>{step}</span>
              {state === "current" && <span className="sr-only">(current step)</span>}
            </span>
            {index < STEPS.length - 1 && (
              <span aria-hidden="true" className="hidden h-px w-8 bg-hair-strong sm:block" />
            )}
          </li>
        )
      })}
    </ol>
  )
}

function AnalysisState({ label }: { label: string }) {
  return (
    <div className="flex flex-col items-start gap-8 py-14" role="status" aria-live="polite">
      <Interviewer state="thinking" className="h-32 w-32 sm:h-40 sm:w-40" />
      <AnimatePresence mode="wait">
        <motion.p
          key={label}
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -4 }}
          transition={transition.quick}
          className="text-sm text-fg-soft"
        >
          {label}…
        </motion.p>
      </AnimatePresence>
    </div>
  )
}

/** A labelled group of things InterMind pulled out of the description. */
function ReadGroup({
  label,
  children,
}: {
  label: string
  children: ReactNode
}) {
  return (
    <div className="grid grid-cols-1 gap-x-8 gap-y-2 border-t border-hair py-5 sm:grid-cols-[10rem_minmax(0,1fr)]">
      <h3 className="type-data pt-0.5 font-medium text-fg">{label}</h3>
      <div className="min-w-0">{children}</div>
    </div>
  )
}

export function NewInterviewPage() {
  useDocumentTitle("New interview")

  const navigate = useNavigate()
  const [description, setDescription] = useState("")
  const [job, setJob] = useState<Job | null>(null)
  const [isAnalyzing, setIsAnalyzing] = useState(false)
  const [isBuilding, setIsBuilding] = useState(false)
  const [stageIndex, setStageIndex] = useState(0)
  const [error, setError] = useState<string | null>(null)

  const step = isBuilding ? 2 : job ? 1 : 0
  const isShort = description.trim().length > 0 && description.trim().length < SHORT_DESCRIPTION

  async function handleAnalyze() {
    const trimmed = description.trim()
    if (!trimmed) return
    setIsAnalyzing(true)
    setError(null)
    setStageIndex(0)
    // Advance the label while the single real request is in flight, so the wait is legible.
    const ticker = window.setInterval(
      () => setStageIndex((i) => Math.min(i + 1, ANALYSIS_STAGES.length - 1)),
      750,
    )
    try {
      setJob(await createJob(trimmed))
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong reading the role.")
    } finally {
      window.clearInterval(ticker)
      setIsAnalyzing(false)
    }
  }

  async function handleBuild() {
    if (!job) return
    setIsBuilding(true)
    setError(null)
    try {
      await createInterviewPlan(job.id)
      navigate(`/interviews/${job.id}`)
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Something went wrong building the interview.",
      )
      setIsBuilding(false)
    }
  }

  return (
    <motion.div variants={stagger(0.07)} initial="hidden" animate="visible">
      <div className="border-b border-hair">
        <div className="shell py-10 sm:py-12">
          <motion.div variants={rise} className="mb-6">
            <button
              type="button"
              onClick={() => navigate("/interviews")}
              className="inline-flex min-h-[44px] items-center gap-1.5 text-sm text-fg-muted transition-colors hover:text-fg"
            >
              <ArrowLeft size={14} aria-hidden="true" />
              All interviews
            </button>
          </motion.div>

          <motion.div variants={rise} className="flex flex-col gap-6">
            <h1 className="type-page text-fg">New interview</h1>
            <Stepper current={step} />
          </motion.div>
        </div>
      </div>

      <div className="shell py-10 sm:py-12">
        <div className="max-w-3xl">
        {error && (
          <div className="mb-8">
            <ErrorBanner message={error} />
          </div>
        )}

        <AnimatePresence mode="wait">
          {isAnalyzing ? (
            <motion.div key="analyzing" exit={{ opacity: 0 }}>
              <AnalysisState label={ANALYSIS_STAGES[stageIndex]} />
            </motion.div>
          ) : job ? (
            <motion.section
              key="review"
              variants={stagger(0.05)}
              initial="hidden"
              animate="visible"
              className="flex flex-col"
            >
              <motion.div variants={rise}>
                <h2 className="type-group text-fg">Here's what InterMind read</h2>
                <p className="type-copy mt-2 text-sm text-fg-muted">
                  The interview is built from this. If something important is missing, go back and
                  add it to the description rather than correcting it here.
                </p>
              </motion.div>

              <motion.div variants={rise} className="mt-8">
                <ReadGroup label="Role">
                  <p className="text-[0.9375rem] font-medium text-fg">{job.job_spec.role_title}</p>
                </ReadGroup>

                <ReadGroup label="Seniority">
                  <p className="text-[0.9375rem] text-fg">
                    {formatSeniority(job.job_spec.seniority)}
                  </p>
                </ReadGroup>

                {job.job_spec.summary && (
                  <ReadGroup label="In short">
                    <p className="type-copy text-[0.9375rem] text-fg-soft">
                      {job.job_spec.summary}
                    </p>
                  </ReadGroup>
                )}

                {job.job_spec.skills.length > 0 && (
                  <ReadGroup label="Skills">
                    <ul className="flex flex-wrap gap-1.5">
                      {job.job_spec.skills.map((skill) => (
                        <li
                          key={skill.name}
                          className={`rounded-full px-2.5 py-1 text-[0.8125rem] ${
                            skill.required
                              ? "bg-accent-soft text-accent"
                              : "border border-hair text-fg-soft"
                          }`}
                        >
                          {skill.name}
                          {skill.required && <span className="sr-only"> (required)</span>}
                        </li>
                      ))}
                    </ul>
                    <p className="type-data mt-2.5 text-fg-muted">
                      Filled chips are required by the description; outlined ones are preferred.
                    </p>
                  </ReadGroup>
                )}

                {job.job_spec.competencies.length > 0 && (
                  <ReadGroup label="Competencies">
                    <ul className="flex flex-wrap gap-1.5">
                      {job.job_spec.competencies.map((competency) => (
                        <li
                          key={competency.name}
                          className="rounded-full border border-hair px-2.5 py-1 text-[0.8125rem] text-fg-soft"
                        >
                          {competency.name}
                        </li>
                      ))}
                    </ul>
                  </ReadGroup>
                )}
              </motion.div>

              <motion.div
                variants={rise}
                className="mt-8 flex flex-wrap items-center gap-3 border-t border-hair-strong pt-8"
              >
                <Button onClick={handleBuild} isLoading={isBuilding}>
                  Build the interview
                  <ArrowRight size={16} aria-hidden="true" />
                </Button>
                <Button
                  variant="ghost"
                  onClick={() => {
                    setJob(null)
                    setError(null)
                  }}
                >
                  Back to the description
                </Button>
              </motion.div>
            </motion.section>
          ) : (
            <motion.div key="compose" variants={rise} className="flex flex-col gap-4">
              <div>
                <label htmlFor="job-description" className="text-sm font-medium text-fg">
                  Job description
                </label>
                <p className="type-data mt-1.5 text-fg-muted">
                  Paste it as written - responsibilities and requirements included. You never write
                  the questions; the interview decides those live, from each candidate's answers.
                </p>
              </div>

              <textarea
                id="job-description"
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                placeholder="Senior Backend Engineer: you'll own our payments platform…"
                rows={9}
                aria-describedby={isShort ? "jd-length-hint" : undefined}
                className="w-full resize-y rounded-[16px] border border-hair-strong bg-raise px-5 py-4 text-[0.9375rem] leading-relaxed text-fg outline-none transition-colors duration-200 placeholder:text-fg-muted/70 focus:border-accent"
              />

              <div className="flex flex-wrap items-center justify-between gap-4">
                <p id="jd-length-hint" className="type-data text-fg-muted">
                  {isShort
                    ? "That looks brief - the more the description says, the better the interview gets."
                    : " "}
                </p>
                <Button onClick={handleAnalyze} disabled={!description.trim()}>
                  Read the role
                  <ArrowRight size={16} aria-hidden="true" />
                </Button>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
        </div>
      </div>
    </motion.div>
  )
}
