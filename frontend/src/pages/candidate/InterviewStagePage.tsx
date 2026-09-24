import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { useNavigate, useParams } from "react-router-dom"
import { AnimatePresence, motion } from "motion/react"
import { MessageSquareText } from "lucide-react"
import { getInterview, submitAnswer } from "../../api/interviews"
import { getCandidateInterviewPlan } from "../../api/interviewPlans"
import { ApiError } from "../../api/client"
import { useAsyncData } from "../../hooks/useAsyncData"
import { useCandidateToken } from "../../hooks/useCandidateToken"
import { usePrefersReducedMotion } from "../../hooks/usePrefersReducedMotion"
import { buildPhraseList, useSpeechInput, useSpeechOutput } from "../../speech"
import { Interviewer } from "../../interviewer/Interviewer"
import { InterviewerStatus } from "../../interviewer/InterviewerStatus"
import type { InterviewerState } from "../../interviewer/types"
import { Logo } from "../../brand/Logo"
import { Stage, StageMessage } from "../../components/interview/StageShell"
import { InterviewProgress } from "../../components/interview/InterviewProgress"
import { InterviewComposer } from "../../components/interview/InterviewComposer"
import { TranscriptPanel } from "../../components/interview/TranscriptPanel"
import { summarizeCoverage } from "../../lib/coverage"
import { fade, questionSwap } from "../../design/motion"
import type { InterviewState } from "../../types"
import { useDocumentTitle } from "../../hooks/useDocumentTitle"

/**
 * The live interview.
 *
 * The one screen in InterMind that inverts. Everything else - the site, the workspace, the
 * report - explains the product; this *is* the product, and it is built as a room rather than a
 * page: a dark field, the interviewer lit in it, and the question it is asking. There are no
 * cards, no panels and no sidebar, because every one of those would be another thing competing
 * with the only two that matter.
 *
 * Three rules hold the composition together.
 *
 * 1. **The question is the largest thing on screen.** Larger than any heading in the rest of
 *    the product. A candidate glancing up mid-thought has to be able to re-read what they were
 *    asked without hunting for it.
 * 2. **The interviewer is a participant, not an ornament.** Its state is the interview's state:
 *    it opens up while the floor is the candidate's, carries the speech envelope while it talks,
 *    closes in while it works out what to ask next. Those are different *shapes*, so they
 *    survive both reduced motion and colour-blindness.
 * 3. **Nothing internal is on screen.** No target, no competency, no evidence, no score, no
 *    question number. The candidate is in an interview; how it is run is not their problem.
 */

/**
 * Floor on how long the thinking state stays up, so the adaptive step always reads as a
 * deliberate moment rather than a flash. Real latency is never shortened - only topped up.
 */
const MIN_THINKING_MS = 1200
const MIN_THINKING_MS_REDUCED = 300

/** How long the interviewer holds the beat before a follow-up question lands. */
const FOLLOW_UP_BEAT_MS = 1100
const FOLLOW_UP_BEAT_MS_REDUCED = 300

const wait = (ms: number) => new Promise((resolve) => window.setTimeout(resolve, ms))

/**
 * The stage's page gutters, and the column split shared by the stage band and the composer
 * band. Written once: the composer sitting exactly under the question is what makes the layout
 * read as one composition rather than two stacked rows.
 */
const BAND = "mx-auto w-full max-w-[86rem] px-5 sm:px-8 lg:px-10"
const COLUMNS =
  "lg:grid-cols-[minmax(0,20rem)_minmax(0,1fr)] lg:gap-14 xl:grid-cols-[minmax(0,23rem)_minmax(0,1fr)] xl:gap-[4.5rem]"


/**
 * What to tell the candidate when sending an answer fails.
 *
 * Never the server's own words: those are written for whoever is on call, and a candidate
 * mid-interview needs to know what happened to their answer and what to do next, not which
 * status code came back.
 */
function submitFailureMessage(error: unknown): string {
  if (error instanceof ApiError && error.status === 0) {
    return "We couldn't reach InterMind just then. Your answer is still here - check your connection and send it again."
  }
  return "That answer didn't send. It's still here - try sending it again."
}

export function InterviewStagePage() {
  useDocumentTitle("Your interview")
  const { interviewId } = useParams<{ interviewId: string }>()
  const navigate = useNavigate()
  const token = useCandidateToken(interviewId)
  const reducedMotion = usePrefersReducedMotion()

  const interviewFetcher = useCallback(
    () => getInterview(interviewId!, token ?? ""),
    [interviewId, token],
  )
  const initial = useAsyncData(interviewFetcher, [interviewId, token])

  /** The state returned by the most recent answer, which is newer than the initial fetch. */
  const [advanced, setAdvanced] = useState<InterviewState | null>(null)
  const interview = advanced ?? initial.data

  const [answer, setAnswer] = useState("")
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [showFollowUpBeat, setShowFollowUpBeat] = useState(false)
  const [transcriptOpen, setTranscriptOpen] = useState(false)

  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const spokenRef = useRef<string | null>(null)
  const lastQuestionRef = useRef<string | null>(null)
  /** Guards the submit path itself, which `isSubmitting` cannot: state is a render behind. */
  const inFlightRef = useRef(false)

  const jobId = interview?.job_id
  // Read with this interview's own access token: the endpoint is recruiter-owner scoped, and a
  // candidate reaches it only for the job they are actually interviewing for (app/api/auth.py).
  const planFetcher = useCallback(
    () => getCandidateInterviewPlan(jobId!, token ?? ""),
    [jobId, token],
  )
  const plan = useAsyncData(planFetcher, [jobId, token], Boolean(jobId) && Boolean(token))

  // What this interview is actually about, in the plan's own words. Biasing recognition toward
  // these is what keeps "PyTorch" from being heard as "Pie Charts" - see ../../speech/phrases.
  // The plan is already fetched for the progress rail, so this costs no extra request.
  const phrases = useMemo(
    () => buildPhraseList((plan.data?.coverage_targets ?? []).map((target) => target.target)),
    [plan.data],
  )

  const speech = useSpeechOutput()
  const voice = useSpeechInput({
    onFinal: (text) => setAnswer((current) => (current ? `${current} ${text}` : text).trim()),
    // The Azure provider mints a short-lived speech token scoped to this interview and biases
    // its decoder with the phrase list; the browser provider ignores all of this.
    context: useMemo(
      () => ({ interviewId, accessToken: token ?? undefined, phrases }),
      [interviewId, token, phrases],
    ),
  })

  useEffect(() => {
    if (interview?.finished) {
      navigate(`/candidate/interviews/${interviewId}/complete`, { replace: true })
    }
  }, [interview?.finished, interviewId, navigate])

  const questionText = interview?.current_question_text ?? ""
  const isFollowUp = Boolean(interview?.current_question_is_follow_up)

  // Speak each new question once. Keyed on the text itself so a follow-up - which keeps the
  // same target id - is still spoken.
  const speak = speech.speak
  useEffect(() => {
    if (!questionText || isSubmitting || showFollowUpBeat) return
    if (spokenRef.current === questionText) return
    spokenRef.current = questionText
    speak(questionText)
  }, [questionText, isSubmitting, showFollowUpBeat, speak])

  /**
   * Put the cursor where the candidate has to act next, once a new question has landed.
   *
   * Only where there is a real pointer. On a phone, focusing the field opens the keyboard over
   * the question the candidate has not read yet - the announcement below does that job there.
   */
  useEffect(() => {
    if (!questionText || showFollowUpBeat) return
    const previous = lastQuestionRef.current
    lastQuestionRef.current = questionText
    if (previous === null || previous === questionText) return
    if (!window.matchMedia("(pointer: fine)").matches) return
    textareaRef.current?.focus()
  }, [questionText, showFollowUpBeat])

  const coverage = useMemo(
    () => summarizeCoverage(plan.data?.coverage_targets ?? [], interview ?? null),
    [plan.data, interview],
  )

  const interviewerState: InterviewerState = isSubmitting
    ? "thinking"
    : showFollowUpBeat
      ? "followUp"
      : speech.isSpeaking
        ? "speaking"
        : "listening"

  const voiceStopAndCollect = voice.stopAndCollect
  const speechCancel = speech.cancel

  const handleSubmit = useCallback(async () => {
    if (!interviewId || inFlightRef.current) return
    // Claimed before the grace window below rather than after it: that window is real elapsed
    // time, during which a second press would otherwise start a second submission.
    inFlightRef.current = true

    // Whatever is still being heard is part of the answer - it is on screen, and dropping it
    // because it had not settled yet would lose the candidate's last sentence. `stopAndCollect`
    // waits briefly for the recognizer to settle that sentence and hands back the better of the
    // two, returning the words instead of appending them so they land in the answer exactly
    // once. See `useSpeechInput.FINAL_RESULT_GRACE_MS`.
    const spoken = await voiceStopAndCollect()
    const composed = [answer.trim(), spoken.trim()].filter(Boolean).join(" ").trim()
    if (!composed) {
      inFlightRef.current = false
      return
    }

    speechCancel()
    setIsSubmitting(true)
    setSubmitError(null)
    const startedAt = Date.now()

    try {
      const updated = await submitAnswer(interviewId, composed, token ?? "")
      const floor = reducedMotion ? MIN_THINKING_MS_REDUCED : MIN_THINKING_MS
      const remaining = floor - (Date.now() - startedAt)
      if (remaining > 0) await wait(remaining)

      setAnswer("")
      setIsSubmitting(false)

      // A follow-up gets its own beat before the question lands, so it reads as a consequence
      // of what was just said rather than simply the next item on a list.
      if (!updated.finished && updated.current_question_is_follow_up) {
        setShowFollowUpBeat(true)
        await wait(reducedMotion ? FOLLOW_UP_BEAT_MS_REDUCED : FOLLOW_UP_BEAT_MS)
        setShowFollowUpBeat(false)
      }
      setAdvanced(updated)
    } catch (error) {
      // The interview finished in another tab, or a duplicate landed second: not a failure,
      // just somewhere else to be.
      if (error instanceof ApiError && error.status === 409) {
        navigate(`/candidate/interviews/${interviewId}/complete`, { replace: true })
        return
      }
      setSubmitError(submitFailureMessage(error))
      setIsSubmitting(false)
    } finally {
      inFlightRef.current = false
    }
  }, [answer, interviewId, navigate, reducedMotion, speechCancel, token, voiceStopAndCollect])

  if (initial.isLoading || (!interview && !initial.error)) {
    return (
      <Stage>
        <StageMessage title="Setting up your interview" body="This only takes a moment." />
      </Stage>
    )
  }

  if (interview?.finished) {
    return (
      <Stage>
        <StageMessage title="That's the interview" body="Taking you to the last screen." />
      </Stage>
    )
  }

  if (initial.error || !interview) {
    return (
      <Stage>
        <StageMessage
          title="We couldn't open your interview"
          body="The link may have expired, or InterMind may be unreachable right now."
          onRetry={initial.refetch}
        />
      </Stage>
    )
  }

  const locked = isSubmitting || showFollowUpBeat
  // See .type-question-md / -sm: a generated question can be two lines or nine, and the
  // largest size only serves the short ones.
  const questionScale =
    questionText.length > 200 ? "type-question-sm" : questionText.length > 115 ? "type-question-md" : ""
  const turns = interview.history
  const swap = reducedMotion ? fade : questionSwap

  return (
    <Stage>
      <header className="relative z-20 flex items-center justify-between gap-4 px-5 py-4 sm:px-8 lg:px-10">
        <div className="flex min-w-0 items-center gap-4">
          <Logo size={22} tone="onDark" />
          {plan.data?.role_title && (
            <>
              {/* Below lg the header has to hold the progress and the transcript as well, and
                  a role title truncated to "SENIOR BACKEND SOFTWAR..." tells the candidate
                  less than no role title at all. */}
              <span className="hidden h-4 w-px shrink-0 bg-white/15 lg:block" aria-hidden="true" />
              <p className="type-stage-meta hidden truncate text-sky-pale/70 lg:block">
                {plan.data.role_title}
              </p>
            </>
          )}
        </div>

        <div className="flex shrink-0 items-center gap-4 sm:gap-7">
          <InterviewProgress
            assessed={coverage.assessed}
            total={coverage.total}
            active={Boolean(coverage.activeId)}
            className="w-[6.5rem] sm:w-44 lg:w-60"
          />

          {turns.length > 0 && (
            <button
              type="button"
              onClick={() => setTranscriptOpen(true)}
              className="inline-flex min-h-[44px] items-center gap-2 rounded-full border border-white/25 px-4 text-sm text-sky-pale transition-colors duration-200 hover:border-white/35 hover:text-white"
            >
              <MessageSquareText size={15} aria-hidden="true" />
              <span className="hidden sm:inline">Transcript</span>
              <span className="type-numeric text-xs text-sky-pale/75">{turns.length}</span>
            </button>
          )}
        </div>
      </header>

      {/* Two bands. The stage holds the interviewer and the question on one line, so the
          question reads as something the figure beside it just said; the composer sits along the
          bottom, aligned under the question rather than centred in the page, because that is
          where the answer to that question goes. Vertically centring one tall column containing
          all three put the question a head above the interviewer and broke that reading. */}
      <main className="relative z-10 flex flex-1 flex-col">
        <div className={`${BAND} flex flex-1 flex-col lg:grid ${COLUMNS} lg:items-center`}>
          {/* The interviewer. On a phone it sits in line with its own status so the question can
              still start above the fold; on a wide screen it takes a column of its own. */}
          <div className="flex shrink-0 items-center gap-5 pt-2 lg:flex-col lg:items-start lg:gap-2 lg:pt-0">
            <div className="relative shrink-0">
              {/* The interviewer's own light, and the one ambient cue that the floor is the
                  candidate's: it lifts while the interviewer is waiting and settles back while
                  it is speaking or working. A glow rather than a ring drawn around the canvas,
                  because a ring is a shape that does not belong to the instrument - and with
                  motion reduced it would sit there as a bare circle with nothing to say. */}
              <span
                aria-hidden="true"
                className={`stage-veil pointer-events-none absolute inset-[-22%] -z-10 rounded-full transition-opacity duration-700 ${
                  interviewerState === "listening" ? "opacity-100" : "opacity-55"
                }`}
              />
              <Interviewer
                state={interviewerState}
                level={speech.level}
                tone="onDark"
                className="h-[6.75rem] w-[6.75rem] sm:h-[9rem] sm:w-[9rem] md:h-[12rem] md:w-[12rem] lg:h-[20rem] lg:w-[20rem] xl:h-[23rem] xl:w-[23rem]"
              />
            </div>

            <InterviewerStatus state={interviewerState} level={speech.level} className="lg:pl-2" />
          </div>

          {/* The question, and the one announcement channel for it. A stable live region: the
              nodes inside it change, this element does not, which is what makes a screen reader
              read the new question rather than nothing. */}
          <div
            aria-live="polite"
            aria-atomic="true"
            className="relative flex min-h-[9rem] flex-1 flex-col justify-center py-7 sm:min-h-[11rem] lg:min-h-0 lg:max-w-[44rem] lg:flex-none lg:py-0"
          >
            {/* Reaches back across the gap to the interviewer. It redraws with each new
                question, which is the whole point: this one came from that. */}
            <span
              key={`tie-${questionText}-${showFollowUpBeat}`}
              aria-hidden="true"
              className="rule-draw absolute -left-14 top-[0.62em] hidden h-px w-14 bg-gradient-to-r from-transparent to-sky-pale/45 lg:block xl:-left-[4.5rem] xl:w-[4.5rem]"
            />

            <AnimatePresence mode="wait">
              {showFollowUpBeat ? (
                <motion.div key="follow-up-beat" variants={swap} initial="hidden" animate="visible" exit="exit">
                  <p className="type-stage-meta text-sky-pale/70">Going deeper</p>
                  <p className="type-sub mt-4 max-w-[26ch] text-balance text-white/85">
                    Let's stay with that a moment longer.
                  </p>
                </motion.div>
              ) : (
                <motion.div key={questionText} variants={swap} initial="hidden" animate="visible" exit="exit">
                  {isFollowUp && (
                    <p className="type-stage-meta text-sky-pale/70">Following up on your answer</p>
                  )}
                  <h1 className={`type-question text-balance text-white ${questionScale} ${isFollowUp ? "mt-4" : ""}`}>
                    {questionText}
                  </h1>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </div>

        {/* Pinned on a phone so the controls stay reachable however long the answer gets; the
            base of the composition on a wide one. */}
        <div className="sticky bottom-0 z-20 bg-black pb-[max(0.75rem,env(safe-area-inset-bottom))] pt-3 lg:static lg:bg-transparent lg:pb-14 lg:pt-0">
          <div className={`${BAND} lg:grid ${COLUMNS}`}>
            <div aria-hidden="true" className="hidden lg:block" />
            <div className="lg:max-w-[44rem]">
              <AnimatePresence>
                {submitError && (
                  <motion.p
                    role="alert"
                    variants={fade}
                    initial="hidden"
                    animate="visible"
                    exit="exit"
                    className="mb-3 rounded-[14px] border border-white/18 bg-white/[0.07] px-4 py-3 text-sm leading-relaxed text-white"
                  >
                    {submitError}
                  </motion.p>
                )}
              </AnimatePresence>

              <InterviewComposer
                value={answer}
                onChange={setAnswer}
                interim={voice.partial}
                onSubmit={handleSubmit}
                locked={locked}
                isSubmitting={isSubmitting}
                voice={voice}
                textareaRef={textareaRef}
              />
            </div>
          </div>
        </div>
      </main>

      <TranscriptPanel turns={turns} open={transcriptOpen} onClose={() => setTranscriptOpen(false)} />
    </Stage>
  )
}
