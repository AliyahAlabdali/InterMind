import { useCallback, useEffect, useRef, useState } from "react"
import { speechInput } from "./index"
import { speechLog } from "./debugLog"
import type { SpeechInputContext, SpeechInputError, SpeechInputSession } from "./types"

interface UseSpeechInputOptions {
  /** Called with each settled utterance, to append to the answer being composed. */
  onFinal: (text: string) => void
  /**
   * Which interview this is, for providers that authenticate per-interview (Azure fetches a
   * short-lived token scoped to it). Ignored by providers that need no credential.
   */
  context?: SpeechInputContext
}

/** What the candidate should understand the microphone to be doing right now. */
export type SpeechInputStatus = "idle" | "listening" | "restarting" | "unavailable"

/**
 * How many times a session may be restarted without producing any transcript before we stop
 * trying. Any result resets the counter, so a candidate who speaks in bursts is never cut off -
 * this only catches the case where recognition can never succeed (e.g. the speech service is
 * unreachable) and would otherwise restart forever.
 */
const MAX_SILENT_RESTARTS = 4

/** Chrome throws InvalidStateError if `start()` is called too soon after `end`. */
const RESTART_DELAY_MS = 250

/**
 * How long `stopAndCollect` waits for the utterance in flight to settle.
 *
 * Azure delivers the final for the sentence the candidate was still speaking shortly *after* the
 * microphone is asked to close, and that final is materially better than the interim on screen:
 * it has been rescored, punctuated and inverse-text-normalized. Committing the interim instead
 * is what submitted "computer which I'm projects" for "computer vision project".
 *
 * Short enough to be invisible next to the submit request that follows it, and it is an upper
 * bound rather than a delay - the wait ends the moment the final arrives, or the moment the
 * session reports itself closed, whichever comes first.
 */
export const FINAL_RESULT_GRACE_MS = 400

/** One pending `stopAndCollect`, resolved by the first of: a final, the session ending, timeout. */
interface FinalCollector {
  resolve: (text: string) => void
  timer: number
  settled: boolean
}

/**
 * Microphone capture, provider-agnostic.
 *
 * The resilience policy lives here rather than in the provider: browser STT ends sessions on
 * its own constantly (silence timeouts, dropped service connections, end-of-utterance), and
 * treating every `end` as "the candidate finished" is what made the button close after ~1s.
 * Instead, an end is only final if the candidate asked for it or the error was fatal -
 * otherwise the session restarts underneath an unchanged UI.
 *
 * A future backend provider simply never ends unexpectedly, so this policy costs it nothing.
 */
export function useSpeechInput({ onFinal, context }: UseSpeechInputOptions) {
  const [status, setStatus] = useState<SpeechInputStatus>("idle")
  const [partial, setPartial] = useState("")
  const [notice, setNotice] = useState<string | null>(null)

  const sessionRef = useRef<SpeechInputSession | null>(null)
  /** True only while the candidate wants the microphone open. */
  const wantsMicRef = useRef(false)
  const restartsRef = useRef(0)
  const restartTimerRef = useRef(0)
  const partialRef = useRef("")
  const lastErrorRef = useRef<SpeechInputError | null>(null)
  const openSessionRef = useRef<() => Promise<void>>(async () => {})
  /**
   * Which recognition session's callbacks currently count.
   *
   * A provider session does not go quiet the instant it is asked to stop - a final result for
   * the utterance already in flight can still land afterwards, by which point those same words
   * have already been committed (flushed on stop, or taken by the caller when an answer was
   * submitted). Every session captures the epoch it opened with and drops its own callbacks
   * once that epoch has moved on, so a late transcript can never be appended twice.
   */
  const epochRef = useRef(0)
  /** Non-null only while `stopAndCollect` is waiting out its grace window. */
  const collectorRef = useRef<FinalCollector | null>(null)

  // Held in a ref so `start` doesn't need to be re-created (and the live session torn down)
  // every time the caller passes a new closure.
  const onFinalRef = useRef(onFinal)
  useEffect(() => {
    onFinalRef.current = onFinal
  }, [onFinal])

  // Same reasoning as onFinal: held in a ref so a new object identity each render doesn't
  // rebuild `start` and tear down a live session.
  const contextRef = useRef(context)
  useEffect(() => {
    contextRef.current = context
  }, [context])

  /** Commit whatever interim text exists, so an unexpected end never discards speech. */
  const flushPartial = useCallback(() => {
    const pending = partialRef.current.trim()
    partialRef.current = ""
    setPartial("")
    if (pending) {
      speechLog("react", "flushing interim transcript", pending)
      onFinalRef.current(pending)
    }
  }, [])

  /** Drop interim text without committing it - for when the caller has already taken it. */
  const discardPartial = useCallback(() => {
    partialRef.current = ""
    setPartial("")
  }, [])

  /**
   * End a pending `stopAndCollect` with the text that won, and close the session down.
   *
   * Idempotent, and it is the *only* way a collected utterance leaves the hook: it hands the
   * words to the caller rather than to `onFinal`, which is what keeps them from being both
   * returned and appended. Retiring the epoch here means anything the provider delivers after
   * this point - a second final, a straggling partial, the session's own `onEnd` - is ignored.
   */
  const finishCollecting = useCallback((text: string) => {
    const collector = collectorRef.current
    if (!collector || collector.settled) return
    collector.settled = true
    collectorRef.current = null
    window.clearTimeout(collector.timer)

    epochRef.current += 1
    sessionRef.current = null
    partialRef.current = ""
    setPartial("")
    collector.resolve(text.trim())
  }, [])

  const openSession = useCallback(async () => {
    // Exactly one recognizer may ever hold the microphone: two of them transcribe every
    // utterance twice, and both copies get appended to the answer. If one is somehow still
    // live, close it rather than skipping this open - skipping would be how a restart gets
    // silently dropped and the microphone never comes back.
    if (sessionRef.current) {
      speechLog("react", "closing a still-live session before opening another")
      const stale = sessionRef.current
      sessionRef.current = null
      stale.stop()
    }
    // Opening supersedes any open still in flight: that one's callbacks stop counting, and its
    // own continuation closes it when it finally resolves.
    const epoch = (epochRef.current += 1)
    const isCurrent = () => epoch === epochRef.current

    try {
      const session = await speechInput.start(
        {
        onPartial: (text) => {
          if (!isCurrent()) return
          // Revising the draft after the candidate has submitted would only change what the
          // fallback below commits, and never for the better.
          if (collectorRef.current) return
          // Any transcript proves recognition is working: forgive earlier silent restarts.
          restartsRef.current = 0
          partialRef.current = text
          setPartial(text)
          setNotice(null)
          setStatus("listening")
        },
        onFinal: (text) => {
          if (!isCurrent()) return
          // The grace window is open: this is the settled version of the utterance the
          // candidate was still speaking when they submitted. It goes to the caller, which
          // asked for it, and must not also be appended here.
          if (collectorRef.current) {
            speechLog("react", "final settled within the grace window")
            finishCollecting(text)
            return
          }
          restartsRef.current = 0
          partialRef.current = ""
          setPartial("")
          setNotice(null)
          setStatus("listening")
          onFinalRef.current(text)
        },
        onError: (inputError) => {
          if (!isCurrent()) return
          speechLog("react", "onError", inputError)
          lastErrorRef.current = inputError
          if (inputError.fatal) {
            wantsMicRef.current = false
            setNotice(inputError.message)
            setStatus("unavailable")
          }
          // Non-fatal errors are not surfaced here: `onEnd` decides whether to restart, and
          // showing "Reconnecting…" only makes sense once we know the session actually ended.
        },
        onEnd: () => {
          if (!isCurrent()) return
          // The session closed while the grace window was open, so no final is coming: settle
          // for the interim now rather than waiting out a timeout that cannot change anything.
          if (collectorRef.current) {
            speechLog("react", "session closed during the grace window - using the interim")
            finishCollecting(partialRef.current)
            return
          }
          // This session is over. Retiring its epoch here means a provider that reports the
          // same ending twice (Azure fires both `canceled` and `sessionStopped`) cannot queue
          // two restarts, and a straggling final cannot reach the answer.
          epochRef.current += 1
          sessionRef.current = null
          // Whatever was mid-utterance belongs to the candidate, not to the session.
          flushPartial()

          if (!wantsMicRef.current) {
            speechLog("react", "end - candidate stopped, staying closed")
            setStatus((current) => (current === "unavailable" ? current : "idle"))
            return
          }

          if (restartsRef.current >= MAX_SILENT_RESTARTS) {
            speechLog("react", "end - restart budget exhausted")
            wantsMicRef.current = false
            setNotice("Voice input isn't available right now. You can continue by typing.")
            setStatus("unavailable")
            return
          }

          restartsRef.current += 1
          speechLog("react", "end - unexpected, restarting", restartsRef.current)
          setStatus("restarting")
          setNotice(lastErrorRef.current?.message ?? "Still listening…")
          window.clearTimeout(restartTimerRef.current)
          restartTimerRef.current = window.setTimeout(() => {
            if (!wantsMicRef.current) return
            // Via a ref: this is a self-restarting loop, so referencing the callback directly
            // would mean reading it while it is still being initialised.
            void openSessionRef.current()
          }, RESTART_DELAY_MS)
        },
        },
        contextRef.current,
      )

      // The candidate may have pressed stop - or the restart budget may have run out - while
      // this session was still opening. Without this guard a late resolve would switch the
      // microphone back on and wipe the message explaining why it closed.
      if (!wantsMicRef.current || !isCurrent()) {
        speechLog("react", "session opened after it was no longer wanted - closing it")
        session.stop()
        return
      }

      sessionRef.current = session
      setStatus("listening")
      setNotice(null)
    } catch (error) {
      if (!isCurrent()) return
      const inputError = error as SpeechInputError
      speechLog("react", "start() rejected", inputError)
      wantsMicRef.current = false
      sessionRef.current = null
      setStatus("unavailable")
      setNotice(
        inputError?.message ?? "Voice input isn't available right now. You can continue by typing.",
      )
    }
  }, [finishCollecting, flushPartial])

  useEffect(() => {
    openSessionRef.current = openSession
  }, [openSession])

  const start = useCallback(async () => {
    if (sessionRef.current || wantsMicRef.current) {
      speechLog("react", "start() ignored - already listening")
      return
    }
    speechLog("react", "start() from UI")
    wantsMicRef.current = true
    restartsRef.current = 0
    lastErrorRef.current = null
    setNotice(null)
    await openSession()
  }, [openSession])

  /**
   * Close the microphone.
   *
   * `discardPartial` covers the one case where the caller has already taken the interim text
   * for itself - submitting an answer reads `partial` straight out of the composer - and
   * committing it again here would put the same words in twice.
   */
  /**
   * Close the microphone and *return* the last utterance instead of appending it.
   *
   * What submitting an answer uses. The words the candidate was still speaking are the tail of
   * their answer, and until now they were taken from the interim draft on screen - Azure had not
   * finished with them. This waits out a short grace window for the settled result and returns
   * whichever is better, so the answer that reaches evaluation is the rescored one.
   *
   * Exactly one of the two is ever produced, and it is returned rather than pushed through
   * `onFinal`: the caller owning the text is what makes double-committing structurally
   * impossible rather than merely guarded against.
   */
  const stopAndCollect = useCallback(async (): Promise<string> => {
    speechLog("react", "stopAndCollect() from UI")
    wantsMicRef.current = false
    window.clearTimeout(restartTimerRef.current)

    const session = sessionRef.current
    if (!session) {
      // Nothing is listening - either the candidate typed their answer, or the microphone was
      // already closed. The draft, if any, is all there is.
      const pending = partialRef.current.trim()
      partialRef.current = ""
      setPartial("")
      return pending
    }

    const collected = await new Promise<string>((resolve) => {
      const collector: FinalCollector = { resolve, settled: false, timer: 0 }
      collector.timer = window.setTimeout(() => {
        speechLog("react", "grace window elapsed - using the interim transcript")
        finishCollecting(partialRef.current)
      }, FINAL_RESULT_GRACE_MS)
      // Registered before the provider is asked to stop: a provider that settles the utterance
      // synchronously inside `stop()` must still find the collector waiting for it.
      collectorRef.current = collector
      session.stop()
    })

    setStatus((current) => (current === "unavailable" ? current : "idle"))
    setNotice(null)
    return collected
  }, [finishCollecting])

  const stop = useCallback(
    (options?: { discardPartial?: boolean }) => {
      speechLog("react", "stop() from UI")
      wantsMicRef.current = false
      window.clearTimeout(restartTimerRef.current)
      // A collect in flight (the candidate submitted, then closed the microphone before the
      // grace window elapsed) owns the interim text already. Settle it rather than leaving a
      // promise pending forever, and let it - not the flush below - commit those words.
      if (collectorRef.current) {
        finishCollecting(options?.discardPartial ? "" : partialRef.current)
        setStatus("idle")
        setNotice(null)
        return
      }
      // Retire the epoch *before* asking the provider to stop: a final result for the utterance
      // already in flight can arrive during or after that call, and those words are committed
      // by the flush below (or were taken by the caller).
      epochRef.current += 1
      const session = sessionRef.current
      sessionRef.current = null
      session?.stop()
      if (options?.discardPartial) discardPartial()
      else flushPartial()
      setStatus("idle")
      setNotice(null)
    },
    [discardPartial, finishCollecting, flushPartial],
  )

  const toggle = useCallback(() => {
    if (wantsMicRef.current) stop()
    else void start()
  }, [start, stop])

  useEffect(
    () => () => {
      wantsMicRef.current = false
      window.clearTimeout(restartTimerRef.current)
      // Unmounting mid-submit must not leave the caller awaiting a promise that can never
      // settle: hand it whatever was heard and let the timer go with the component.
      const collector = collectorRef.current
      if (collector && !collector.settled) {
        collector.settled = true
        collectorRef.current = null
        window.clearTimeout(collector.timer)
        collector.resolve(partialRef.current.trim())
      }
      epochRef.current += 1
      sessionRef.current?.stop()
    },
    [],
  )

  return {
    start,
    stop,
    stopAndCollect,
    toggle,
    status,
    /** Visually active for both listening and a silent restart - the candidate shouldn't have
     * to press the button again because Chrome ended a turn. */
    isRecording: status === "listening" || status === "restarting",
    partial,
    /** Candidate-facing message only - never a browser error code. */
    notice,
    isUnavailable: status === "unavailable",
    isSupported: speechInput.isSupported(),
  }
}
