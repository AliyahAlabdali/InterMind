import { useCallback, useEffect, useRef, useState } from "react"
import { speechOutput } from "./index"
import type { SpeechOutputSession } from "./types"

/**
 * Speaks text through whichever output provider is wired in, exposing just what the UI needs:
 * whether it's speaking, and the live envelope that drives the interviewer's ripple and the
 * waveform bars.
 */
export function useSpeechOutput() {
  const [isSpeaking, setIsSpeaking] = useState(false)
  const [level, setLevel] = useState(0)
  const sessionRef = useRef<SpeechOutputSession | null>(null)

  const cancel = useCallback(() => {
    sessionRef.current?.cancel()
    sessionRef.current = null
    setIsSpeaking(false)
    setLevel(0)
  }, [])

  const speak = useCallback(
    (text: string) => {
      if (!text.trim() || !speechOutput.isSupported()) return
      sessionRef.current?.cancel()
      setIsSpeaking(true)
      sessionRef.current = speechOutput.speak(text, {
        onEnd: () => {
          setIsSpeaking(false)
          setLevel(0)
          sessionRef.current = null
        },
        onError: () => {
          setIsSpeaking(false)
          setLevel(0)
          sessionRef.current = null
        },
        onLevel: setLevel,
      })
    },
    [],
  )

  // Never let a question keep talking after the candidate has navigated away.
  useEffect(() => () => speechOutput.cancelAll(), [])

  return {
    speak,
    cancel,
    isSpeaking,
    level,
    isSupported: speechOutput.isSupported(),
  }
}
