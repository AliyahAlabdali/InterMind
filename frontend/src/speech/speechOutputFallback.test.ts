/**
 * Narration must degrade, never disappear.
 *
 * Two layers protect the candidate's experience: Azure narration falls back to browser
 * synthesis for that question, and if both fail the interview carries on silently with the
 * question on screen. Neither layer may ever leave the UI believing it is still speaking.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { act, renderHook } from "@testing-library/react"
import { withBrowserFallback, useSpeechOutput } from "./index"
import { browserSpeechOutput } from "./browserSpeech"
import type { SpeechOutputHandlers, SpeechOutputProvider } from "./types"

const CONTEXT = { interviewId: "interview-1", accessToken: "candidate-token-value" }

/** A primary provider whose behaviour each test chooses. */
function primary(behaviour: "succeeds" | "fails"): SpeechOutputProvider & { calls: string[] } {
  const calls: string[] = []
  return {
    calls,
    id: "fake-primary",
    isSupported: () => true,
    speak(text: string, handlers: SpeechOutputHandlers) {
      calls.push(text)
      if (behaviour === "fails") handlers.onError?.()
      else handlers.onStart?.()
      return { cancel: vi.fn() }
    },
    cancelAll: vi.fn(),
  }
}

describe("falling back when Azure narration fails", () => {
  beforeEach(() => {
    vi.spyOn(browserSpeechOutput, "speak").mockReturnValue({ cancel: vi.fn() })
    vi.spyOn(browserSpeechOutput, "isSupported").mockReturnValue(true)
  })
  afterEach(() => vi.restoreAllMocks())

  it("reads the question with browser synthesis when Azure cannot", () => {
    const provider = withBrowserFallback(primary("fails"))

    provider.speak("Tell me about a system you designed.", {}, CONTEXT)

    expect(browserSpeechOutput.speak).toHaveBeenCalledOnce()
    expect(vi.mocked(browserSpeechOutput.speak).mock.calls[0][0]).toBe(
      "Tell me about a system you designed.",
    )
  })

  it("does not fall back when Azure succeeds", () => {
    const provider = withBrowserFallback(primary("succeeds"))

    provider.speak("A question.", {}, CONTEXT)

    expect(browserSpeechOutput.speak).not.toHaveBeenCalled()
  })

  it("surfaces an error only once both layers have failed", () => {
    const onError = vi.fn()
    vi.mocked(browserSpeechOutput.speak).mockImplementation((_text, handlers) => {
      handlers.onError?.()
      return { cancel: vi.fn() }
    })

    withBrowserFallback(primary("fails")).speak("A question.", { onError }, CONTEXT)

    // Exactly once: the fallback's own failure must not re-enter the fallback and loop.
    expect(onError).toHaveBeenCalledTimes(1)
  })

  it("skips Azure entirely when there is no interview credential", () => {
    const provider = withBrowserFallback(primary("succeeds"))

    provider.speak("A question.", {}, undefined)

    expect(browserSpeechOutput.speak).toHaveBeenCalledOnce()
  })

  it("does not fall back for a question the candidate has already moved past", () => {
    let captured: SpeechOutputHandlers | null = null
    const slow: SpeechOutputProvider = {
      id: "slow",
      isSupported: () => true,
      speak(_text, handlers) {
        captured = handlers
        return { cancel: vi.fn() }
      },
      cancelAll: vi.fn(),
    }

    const session = withBrowserFallback(slow).speak("Stale question.", {}, CONTEXT)
    session.cancel()
    // Azure reports its failure only after the question changed; the stale question must stay
    // silent rather than being read by the fallback over the top of the new one.
    captured!.onError?.()

    expect(browserSpeechOutput.speak).not.toHaveBeenCalled()
  })
})

describe("the interview never gets stuck mid-sentence", () => {
  it("retires the pending provider on timeout and ignores its late callbacks", () => {
    vi.spyOn(browserSpeechOutput, "cancelAll").mockImplementation(() => {})
    let pending: SpeechOutputHandlers | undefined
    const cancel = vi.fn()
    vi.spyOn(browserSpeechOutput, "isSupported").mockReturnValue(true)
    vi.spyOn(browserSpeechOutput, "speak").mockImplementation((_text, handlers) => {
      pending = handlers
      return { cancel }
    })
    const { result, unmount } = renderHook(() => useSpeechOutput())
    act(() => result.current.speak("Old question"))
    act(() => vi.advanceTimersByTime(8000))
    expect(cancel).toHaveBeenCalledOnce()
    act(() => { pending?.onStart?.(); pending?.onLevel?.(.9) })
    expect(result.current.isSpeaking).toBe(false)
    expect(result.current.level).toBe(0)
    act(() => result.current.speak("New question"))
    unmount()
    expect(cancel).toHaveBeenCalledTimes(2)
  })
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it("clears isSpeaking when narration silently never starts", () => {
    // WebKit's silent drop: no sound, no `end`, no `error`. Before the watchdog this left the
    // interviewer permanently lit as speaking.
    vi.spyOn(browserSpeechOutput, "isSupported").mockReturnValue(true)
    vi.spyOn(browserSpeechOutput, "speak").mockReturnValue({ cancel: vi.fn() })

    const { result } = renderHook(() => useSpeechOutput())
    act(() => result.current.speak("A question."))
    expect(result.current.isSpeaking).toBe(true)

    act(() => {
      vi.advanceTimersByTime(10_000)
    })
    expect(result.current.isSpeaking).toBe(false)
  })

  it("clears isSpeaking when narration reports a failure", () => {
    vi.spyOn(browserSpeechOutput, "isSupported").mockReturnValue(true)
    vi.spyOn(browserSpeechOutput, "speak").mockImplementation((_text, handlers) => {
      handlers.onError?.()
      return { cancel: vi.fn() }
    })

    const { result } = renderHook(() => useSpeechOutput())
    act(() => result.current.speak("A question."))

    expect(result.current.isSpeaking).toBe(false)
  })

  it("cancels the previous question's audio before starting the next", () => {
    const cancel = vi.fn()
    vi.spyOn(browserSpeechOutput, "isSupported").mockReturnValue(true)
    vi.spyOn(browserSpeechOutput, "speak").mockReturnValue({ cancel })

    const { result } = renderHook(() => useSpeechOutput())
    act(() => result.current.speak("First question."))
    act(() => result.current.speak("Second question."))

    // Otherwise the candidate hears two questions at once when the interview advances.
    expect(cancel).toHaveBeenCalled()
  })

  it("survives a provider that throws instead of reporting an error", () => {
    // Narration is started from a render effect, so an exception here would unmount the
    // interview screen and take the question with it. It must cost the voice and nothing else.
    vi.spyOn(browserSpeechOutput, "isSupported").mockReturnValue(true)
    vi.spyOn(browserSpeechOutput, "speak").mockImplementation(() => {
      throw new Error("no audio output available")
    })

    const { result } = renderHook(() => useSpeechOutput())

    expect(() => act(() => result.current.speak("A question."))).not.toThrow()
    expect(result.current.isSpeaking).toBe(false)
  })

  it("does nothing at all for empty text", () => {
    const speak = vi.spyOn(browserSpeechOutput, "speak")
    vi.spyOn(browserSpeechOutput, "isSupported").mockReturnValue(true)

    const { result } = renderHook(() => useSpeechOutput())
    act(() => result.current.speak("   "))

    expect(speak).not.toHaveBeenCalled()
    expect(result.current.isSpeaking).toBe(false)
  })
})
