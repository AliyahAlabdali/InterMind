import { useCallback, useEffect, useRef, useState } from "react"
import { speechOutput } from "./index"
import type { SpeechOutputContext, SpeechOutputSession } from "./types"

/**
 * How long to wait for a provider to report that it started before giving up on it.
 *
 * This exists because failure here is not always an event. WebKit can drop `speechSynthesis`
 * entirely when it dislikes the call - no sound, no `end`, and no `error` - which used to leave
 * `isSpeaking` latched on forever and the interviewer stuck mid-sentence on screen. Generous
 * enough that a slow Azure round trip is never mistaken for a failure.
 */
const START_TIMEOUT_MS = 8000

/**
 * Speaks text through whichever output provider is wired in, exposing just what the UI needs:
 * whether it's speaking, and the live envelope that drives the interviewer's ripple and the
 * waveform bars.
 *
 * `context` carries this interview's identity so the Azure provider can authorize its token
 * request; the browser provider ignores it.
 */
export function useSpeechOutput(context?: SpeechOutputContext) {
  const [isSpeaking, setIsSpeaking] = useState(false)
  const [level, setLevel] = useState(0)
  const sessionRef = useRef<SpeechOutputSession | null>(null)
  const watchdogRef = useRef(0)

  // Read through a ref so `speak` keeps a stable identity: it is an effect dependency in the
  // interview screen, and a new function on every render would re-speak the same question.
  // Synced in an effect rather than during render, and declared before the interview screen's
  // own narration effect, so the ref is already current by the time `speak` is called.
  const contextRef = useRef(context)
  useEffect(() => {
    contextRef.current = context
  }, [context])

  const clearWatchdog = useCallback(() => {
    if (watchdogRef.current) {
      window.clearTimeout(watchdogRef.current)
      watchdogRef.current = 0
    }
  }, [])

  const settle = useCallback(() => {
    clearWatchdog()
    setIsSpeaking(false)
    setLevel(0)
    sessionRef.current = null
  }, [clearWatchdog])

  const cancel = useCallback(() => {
    sessionRef.current?.cancel()
    settle()
  }, [settle])

  const speak = useCallback(
    (text: string) => {
      if (!text.trim() || !speechOutput.isSupported()) return
      sessionRef.current?.cancel()
      clearWatchdog()
      setIsSpeaking(true)

      // Cleared by `onStart`. If nothing ever starts - the silent-drop case - this is what
      // releases the UI instead of leaving it speaking forever.
      watchdogRef.current = window.setTimeout(settle, START_TIMEOUT_MS)

      // Narration is an enhancement, and this is called from a render effect: a provider that
      // throws synchronously would unmount the interview screen and take the question with it.
      // Failure here must cost the candidate the voice and nothing else.
      try {
        sessionRef.current = speechOutput.speak(
          text,
          {
            onStart: clearWatchdog,
            onEnd: settle,
            onError: settle,
            onLevel: setLevel,
          },
          contextRef.current,
        )
      } catch {
        settle()
      }
    },
    [clearWatchdog, settle],
  )

  // Never let a question keep talking after the candidate has navigated away.
  useEffect(
    () => () => {
      if (watchdogRef.current) window.clearTimeout(watchdogRef.current)
      speechOutput.cancelAll()
    },
    [],
  )

  return {
    speak,
    cancel,
    isSpeaking,
    level,
    isSupported: speechOutput.isSupported(),
  }
}
