import { useCallback, useEffect } from "react"
import { Link, useNavigate, useParams } from "react-router-dom"
import { motion } from "motion/react"
import { ArrowRight, Keyboard, Mic } from "lucide-react"
import { getInterview } from "../../api/interviews"
import { getJob } from "../../api/jobs"
import { useAsyncData } from "../../hooks/useAsyncData"
import { useCandidateToken } from "../../hooks/useCandidateToken"
import { Spinner } from "../../components/ui/Spinner"
import { ErrorBanner } from "../../components/ui/ErrorBanner"
import { Interviewer } from "../../interviewer/Interviewer"
import { rise, stagger } from "../../design/motion"
import { useDocumentTitle } from "../../hooks/useDocumentTitle"

/**
 * The doorway.
 *
 * Deliberately still a light page - the candidate has not started yet, and dropping someone
 * straight into the near-black room from an email link gives them nowhere to stand. But the
 * room is already visible: the interviewer sits in a contained panel of the interview's own
 * surface, lit exactly as it will be a moment later. Pressing Begin walks into that panel
 * rather than cutting to an unrelated screen.
 *
 * Three notes, no more. Everything a candidate needs to know before starting fits in a
 * sentence each, and a page of instructions before an interview reads as a warning.
 */
const NOTES = [
  {
    title: "One question at a time",
    body: "No timer and no list up front. You'll see the next question only once you've answered this one.",
  },
  {
    title: "It follows what you say",
    body: "Your answers decide what gets asked next, so this won't be the same interview anyone else gets.",
  },
  {
    title: "Speak or type",
    body: "Both work, and you can switch whenever you like. Take the time you need.",
  },
]

export function CandidateLandingPage() {
  useDocumentTitle("Your interview")
  const { interviewId } = useParams<{ interviewId: string }>()
  const navigate = useNavigate()

  const token = useCandidateToken(interviewId)

  const interviewFetcher = useCallback(
    () => getInterview(interviewId!, token ?? ""),
    [interviewId, token],
  )
  const interview = useAsyncData(interviewFetcher, [interviewId, token])

  const jobId = interview.data?.job_id
  const jobFetcher = useCallback(() => getJob(jobId!), [jobId])
  const job = useAsyncData(jobFetcher, [jobId], Boolean(jobId))

  useEffect(() => {
    if (interview.data?.status === "completed") {
      navigate(`/candidate/interviews/${interviewId}/complete`, { replace: true })
    }
  }, [interview.data?.status, interviewId, navigate])

  if (interview.isLoading || interview.data?.status === "completed") {
    return (
      <div className="shell py-16">
        <Spinner label="Opening your interview…" block />
      </div>
    )
  }
  if (interview.error) {
    return (
      <div className="shell py-16">
        <ErrorBanner message={interview.error} onRetry={interview.refetch} />
      </div>
    )
  }
  if (!interview.data) return null

  const isResuming = interview.data.history.length > 0
  const role = job.data?.job_spec.role_title

  return (
    <motion.div
      variants={stagger(0.08)}
      initial="hidden"
      animate="visible"
      className="shell grid grid-cols-1 items-center gap-10 py-10 lg:grid-cols-[minmax(0,6fr)_minmax(0,5fr)] lg:gap-16 lg:py-16"
    >
      <div className="flex flex-col items-start">
        <motion.div variants={rise}>
          <p className="type-data text-fg-muted">
            {interview.data.candidate_name ? `${interview.data.candidate_name} · ` : ""}
            {role ?? "Interview"}
          </p>
          <h1 className="type-page mt-2 text-balance text-fg">
            {isResuming ? "Ready to pick up where you left off?" : "You're about to meet your interviewer."}
          </h1>
          <p className="type-copy mt-4 text-fg-soft">
            This is a real interview, run by InterMind rather than a person. It asks one question
            at a time and decides what to explore next from what you actually say.
          </p>
        </motion.div>

        {/* Shown before the candidate starts, not buried in a policy page: they are about to be
            assessed by an AI system, and what that means for their answers is something they
            should be able to read first. Every sentence here describes behaviour that is
            actually implemented - the OpenAI evaluation call, the optional Azure transcription,
            and the fact that a person makes the decision. Nothing is claimed about accuracy. */}
        <motion.section
          variants={rise}
          aria-labelledby="ai-notice"
          className="mt-8 rounded-[14px] border border-hair-strong bg-raise px-5 py-4"
        >
          <h2 id="ai-notice" className="text-sm font-medium text-fg">
            How your answers are used
          </h2>
          <ul className="mt-3 flex flex-col gap-2 text-sm leading-relaxed text-fg-soft">
            <li>
              Your answers are analysed by an AI system, which scores them against the
              requirements of the role and quotes what you said as evidence.
            </li>
            <li>
              That analysis and your answers are shared with the hiring team. InterMind does not
              make the hiring decision; a person does.
            </li>
            <li>
              AI evaluation is not perfect and can misread an answer. If something matters, say
              it plainly rather than assuming it will be inferred.
            </li>
            <li>
              Answering by voice is optional. If you use it, your audio is sent to a speech
              service to be turned into text. Typing works just as well, and you can switch at
              any point.
            </li>
          </ul>
          <p className="mt-3 text-sm text-fg-muted">
            <Link
              to="/legal/privacy"
              className="underline decoration-hair-strong underline-offset-2 transition-colors hover:text-fg"
            >
              How your data is handled
            </Link>
          </p>
        </motion.section>

        <motion.div variants={rise} className="mt-8">
          <button
            type="button"
            onClick={() => navigate(`/candidate/interviews/${interviewId}/session`)}
            className="inline-flex min-h-[48px] items-center gap-2 rounded-full bg-fg px-7 text-[0.9375rem] font-medium text-canvas transition-colors duration-200 hover:bg-accent"
          >
            {isResuming ? "Continue the interview" : "Begin the interview"}
            <ArrowRight size={17} aria-hidden="true" />
          </button>
        </motion.div>

        <motion.dl variants={rise} className="mt-12 flex w-full flex-col border-t border-hair">
          {NOTES.map((note, index) => (
            <div key={note.title} className="grid grid-cols-1 gap-1 border-b border-hair py-4 sm:grid-cols-[11rem_minmax(0,1fr)] sm:gap-6">
              <dt className="flex items-center gap-2 text-sm font-medium text-fg">
                {index === 2 && (
                  <span className="flex items-center gap-1 text-fg-muted" aria-hidden="true">
                    <Mic size={13} />
                    <Keyboard size={13} />
                  </span>
                )}
                {note.title}
              </dt>
              <dd className="text-sm leading-relaxed text-fg-soft">{note.body}</dd>
            </div>
          ))}
        </motion.dl>
      </div>

      {/* The room, seen from outside it. Same surface, same light, same instrument - so
          starting reads as stepping through rather than as a page change. */}
      <motion.div variants={rise} className="order-first lg:order-none">
        <div className="plane-raised relative flex aspect-[4/3] items-center justify-center overflow-hidden sm:aspect-[16/10] lg:aspect-square">
          <span aria-hidden="true" className="veil-night" />
          <div className="relative">
            <span
              aria-hidden="true"
              className="stage-veil pointer-events-none absolute inset-[-25%] -z-10 rounded-full"
            />
            <Interviewer
              state="idle"
              tone="onDark"
              trackPointer
              className="h-40 w-40 sm:h-52 sm:w-52 lg:h-64 lg:w-64"
            />
          </div>
          <p className="type-data absolute bottom-5 left-0 right-0 text-center text-fg-muted">
            Your interviewer
          </p>
        </div>
      </motion.div>
    </motion.div>
  )
}
