import { act, renderHook, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { useSpeechInput } from "./useSpeechInput"
import {
  FakeSpeechRecognition,
  installFakeRecognition,
  uninstallFakeRecognition,
} from "./testDoubles"

/**
 * The hook is provider-agnostic by design, and these tests exercise it through the browser
 * provider's fake recogniser. Pinned explicitly rather than inherited from the environment: the
 * configured `VITE_SPEECH_PROVIDER` is `azure` in this project, and letting it decide what is
 * under test is how these silently stopped testing anything.
 */
vi.mock("./index", async () => {
  const { browserSpeechInput } = await import("./browserSpeech")
  return { speechInput: browserSpeechInput }
})

/**
 * These cover the resilience policy that fixes the reported bug: the microphone turning itself
 * off about a second after being pressed, because every `end` was treated as "the candidate
 * finished speaking".
 */

async function startListening(onFinal = vi.fn()) {
  const view = renderHook(() => useSpeechInput({ onFinal }))

  await act(async () => {
    void view.result.current.start()
    // The provider resolves only on `start`, so the fake has to confirm the session is live.
    await Promise.resolve()
    FakeSpeechRecognition.latest().fireStart()
  })

  await waitFor(() => expect(view.result.current.status).toBe("listening"))
  return { view, onFinal }
}

describe("useSpeechInput", () => {
  beforeEach(() => {
    installFakeRecognition()
    vi.spyOn(console, "log").mockImplementation(() => {})
  })

  afterEach(() => {
    uninstallFakeRecognition()
    vi.restoreAllMocks()
  })

  it("reports listening once the session is live", async () => {
    const { view } = await startListening()
    expect(view.result.current.isRecording).toBe(true)
    expect(view.result.current.isUnavailable).toBe(false)
  })

  it("does not restart after the candidate explicitly stops", async () => {
    const { view } = await startListening()
    const recognition = FakeSpeechRecognition.latest()

    act(() => view.result.current.stop())
    act(() => recognition.fireEnd())

    await waitFor(() => expect(view.result.current.status).toBe("idle"))
    // One instance only: no new session was opened.
    expect(FakeSpeechRecognition.instances).toHaveLength(1)
    expect(recognition.stopCalls).toBe(1)
  })

  it("restarts automatically when Chrome ends the session unexpectedly", async () => {
    const { view } = await startListening()

    act(() => FakeSpeechRecognition.latest().fireEnd())

    // Stays visually active - the candidate must not have to press the button again.
    await waitFor(() => expect(view.result.current.isRecording).toBe(true))
    expect(view.result.current.status).toBe("restarting")

    await waitFor(() => expect(FakeSpeechRecognition.instances).toHaveLength(2))
  })

  it("treats no-speech as recoverable and keeps listening", async () => {
    const { view } = await startListening()
    const recognition = FakeSpeechRecognition.latest()

    act(() => recognition.fireError("no-speech"))
    // A non-fatal error alone must not close the microphone.
    expect(view.result.current.isUnavailable).toBe(false)

    act(() => recognition.fireEnd())
    await waitFor(() => expect(FakeSpeechRecognition.instances).toHaveLength(2))
    expect(view.result.current.isRecording).toBe(true)
  })

  it.each([["not-allowed"], ["service-not-allowed"], ["audio-capture"]])(
    "does not restart after the fatal error %s",
    async (code) => {
      const { view } = await startListening()
      const recognition = FakeSpeechRecognition.latest()

      act(() => recognition.fireError(code))
      act(() => recognition.fireEnd())

      await waitFor(() => expect(view.result.current.isUnavailable).toBe(true))
      expect(FakeSpeechRecognition.instances).toHaveLength(1)
      expect(view.result.current.notice).toMatch(/continue by typing/i)
    },
  )

  it("stops restarting once repeated sessions produce no transcript at all", async () => {
    const { view } = await startListening()

    // Every restart ends immediately without a result - the case that would otherwise spin.
    for (let i = 0; i < 8; i += 1) {
      const recognition = FakeSpeechRecognition.latest()
      act(() => recognition.fireEnd())
      if (view.result.current.status === "unavailable") break
      await waitFor(() => expect(FakeSpeechRecognition.latest()).not.toBe(recognition))
      act(() => FakeSpeechRecognition.latest().fireStart())
    }

    await waitFor(() => expect(view.result.current.status).toBe("unavailable"))
    expect(FakeSpeechRecognition.instances.length).toBeLessThanOrEqual(6)
    expect(view.result.current.notice).toMatch(/continue by typing/i)
  })

  it("preserves interim transcript when the session ends before finalising it", async () => {
    const onFinal = vi.fn()
    const { view } = await startListening(onFinal)
    const recognition = FakeSpeechRecognition.latest()

    act(() => recognition.fireResult("I designed a billing service", false))
    expect(view.result.current.partial).toBe("I designed a billing service")

    // Chrome drops the session mid-sentence: the words must survive, not vanish.
    act(() => recognition.fireEnd())

    await waitFor(() => expect(onFinal).toHaveBeenCalledWith("I designed a billing service"))
    expect(view.result.current.partial).toBe("")
  })

  it("preserves interim transcript when the candidate stops mid-sentence", async () => {
    const onFinal = vi.fn()
    const { view } = await startListening(onFinal)
    const recognition = FakeSpeechRecognition.latest()

    act(() => recognition.fireResult("partial words", false))
    act(() => view.result.current.stop())

    await waitFor(() => expect(onFinal).toHaveBeenCalledWith("partial words"))
  })

  it("commits final transcript and clears the interim draft", async () => {
    const onFinal = vi.fn()
    const { view } = await startListening(onFinal)
    const recognition = FakeSpeechRecognition.latest()

    act(() => recognition.fireResult("a complete answer", true))

    await waitFor(() => expect(onFinal).toHaveBeenCalledWith("a complete answer"))
    expect(view.result.current.partial).toBe("")
    // A final result must not be double-counted when the session later ends.
    act(() => view.result.current.stop())
    expect(onFinal).toHaveBeenCalledTimes(1)
  })

  it("a transcript resets the restart budget, so a pausing candidate is never cut off", async () => {
    const { view } = await startListening()

    for (let i = 0; i < 6; i += 1) {
      const recognition = FakeSpeechRecognition.latest()
      act(() => recognition.fireResult("still talking", true))
      act(() => recognition.fireEnd())
      await waitFor(() => expect(FakeSpeechRecognition.latest()).not.toBe(recognition))
      act(() => FakeSpeechRecognition.latest().fireStart())
    }

    // `waitFor`, not a bare assertion: a session only counts as listening once the provider
    // has actually confirmed it, and that confirmation is a resolved promise. The point of the
    // test is that the budget never runs out, which `isUnavailable` is what proves.
    await waitFor(() => expect(view.result.current.status).toBe("listening"))
    expect(view.result.current.isUnavailable).toBe(false)
  })

  /* --- Transcript integrity ------------------------------------------------------------
     Every one of these is a way the same words used to reach the answer twice. */

  it("restarts once, not twice, when a provider reports the same ending twice", async () => {
    const { view } = await startListening()
    const recognition = FakeSpeechRecognition.latest()

    // Azure does exactly this: `canceled` and `sessionStopped` for one session ending. Two
    // restarts meant two recognizers on one microphone, and every later utterance arriving -
    // and being appended - twice.
    act(() => recognition.fireEnd())
    act(() => recognition.fireEnd())

    await waitFor(() => expect(FakeSpeechRecognition.instances).toHaveLength(2))
    // Give any second restart timer the chance to fire before concluding there wasn't one.
    await new Promise((resolve) => setTimeout(resolve, 400))
    expect(FakeSpeechRecognition.instances).toHaveLength(2)
    expect(view.result.current.isRecording).toBe(true)
  })

  it("never lets two recognition sessions hold the microphone at once", async () => {
    const { view } = await startListening()
    const first = FakeSpeechRecognition.latest()

    // A second start while one is live (a stray restart, a double press).
    await act(async () => {
      void view.result.current.start()
      await Promise.resolve()
    })

    // Either no second session was opened, or the first was closed as the second opened.
    const opened = FakeSpeechRecognition.instances.length
    if (opened > 1) expect(first.stopCalls + first.abortCalls).toBeGreaterThan(0)
    expect(view.result.current.isUnavailable).toBe(false)
  })

  it("drops a final that arrives after the candidate has stopped", async () => {
    const onFinal = vi.fn()
    const { view } = await startListening(onFinal)
    const recognition = FakeSpeechRecognition.latest()

    act(() => recognition.fireResult("scaled the billing service", false))
    act(() => view.result.current.stop())
    // The interim words are committed once, by the flush.
    await waitFor(() => expect(onFinal).toHaveBeenCalledTimes(1))

    // The provider settles the same utterance a moment later, as Azure does after `stop()`.
    act(() => recognition.fireResult("scaled the billing service.", true))
    act(() => recognition.fireEnd())

    await new Promise((resolve) => setTimeout(resolve, 50))
    expect(onFinal).toHaveBeenCalledTimes(1)
    expect(FakeSpeechRecognition.instances).toHaveLength(1)
  })

  it("discards the interim draft when the caller has already taken it", async () => {
    const onFinal = vi.fn()
    const { view } = await startListening(onFinal)

    act(() => FakeSpeechRecognition.latest().fireResult("half a sentence", false))
    // What submitting an answer does: the composer already holds these words.
    act(() => view.result.current.stop({ discardPartial: true }))

    await waitFor(() => expect(view.result.current.partial).toBe(""))
    expect(onFinal).not.toHaveBeenCalled()
  })

  it("surfaces a friendly message, never a raw error code, when start fails outright", async () => {
    const view = renderHook(() => useSpeechInput({ onFinal: vi.fn() }))

    await act(async () => {
      void view.result.current.start()
      await Promise.resolve()
      FakeSpeechRecognition.latest().fireError("not-allowed")
    })

    await waitFor(() => expect(view.result.current.status).toBe("unavailable"))
    expect(view.result.current.notice).toBe(
      "Voice input isn't available right now. You can continue by typing.",
    )
    expect(view.result.current.notice).not.toMatch(/not-allowed/)
  })
})
