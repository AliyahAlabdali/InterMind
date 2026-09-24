import { act, renderHook, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { FINAL_RESULT_GRACE_MS, useSpeechInput } from "./useSpeechInput"
import {
  FakeSpeechRecognition,
  installFakeRecognition,
  uninstallFakeRecognition,
} from "./testDoubles"

/**
 * Regression: the submitted answer must be the *finalised* transcript, not the interim draft.
 *
 * The candidate spoke:
 *   "I worked on a computer vision project using Python and PyTorch to train an object
 *    detection model."
 *
 * The recogniser's interim hypothesis for that sentence is un-rescored, unpunctuated and
 * un-normalized; its final is none of those things. Because submitting read `voice.partial`
 * straight out of the composer and the provider discarded any final that settled after `stop()`,
 * the interim was what reached evaluation - every single time, for the last sentence of every
 * spoken answer.
 *
 * The fix is a short grace window on stop. The property these tests defend is narrow and
 * two-sided: the final wins when it exists, and the words reach the answer *exactly once*
 * either way. The second half is the transcript-duplication bug this must not reopen, and it is
 * why `stopAndCollect` returns the text to the caller instead of pushing it through `onFinal`.
 */

vi.mock("./index", async () => {
  const { browserSpeechInput } = await import("./browserSpeech")
  return { speechInput: browserSpeechInput }
})

const SPOKEN_INTERIM = "I worked on a computer vision project using Python and PyTorch"
const SPOKEN_FINAL =
  "I worked on a computer vision project using Python and PyTorch to train an object detection model."

/**
 * A stand-in for the interview composer, which is the thing that actually has the duplication
 * bug to avoid: it accumulates committed finals and appends whatever `stopAndCollect` returns.
 */
function composer() {
  let answer = ""
  return {
    onFinal: (text: string) => {
      answer = (answer ? `${answer} ${text}` : text).trim()
    },
    /** Exactly what `handleSubmit` composes and sends to evaluation. */
    submitted: (collected: string) => [answer, collected].filter(Boolean).join(" ").trim(),
  }
}

async function listening(onFinal: (text: string) => void) {
  const view = renderHook(() => useSpeechInput({ onFinal }))
  await act(async () => {
    void view.result.current.start()
    await Promise.resolve()
    FakeSpeechRecognition.latest().fireStart()
  })
  await waitFor(() => expect(view.result.current.status).toBe("listening"))
  return view
}

describe("final result is preferred over the interim draft", () => {
  beforeEach(() => {
    installFakeRecognition()
    vi.spyOn(console, "log").mockImplementation(() => {})
  })

  afterEach(() => {
    uninstallFakeRecognition()
    vi.restoreAllMocks()
  })

  it("submits the final when it settled before the candidate pressed submit", async () => {
    const c = composer()
    const view = await listening(c.onFinal)
    const recognition = FakeSpeechRecognition.latest()

    act(() => recognition.fireResult(SPOKEN_INTERIM, false))
    act(() => recognition.fireResult(SPOKEN_FINAL, true))

    let collected = ""
    await act(async () => {
      collected = await view.result.current.stopAndCollect()
    })

    // Already committed through `onFinal`, so there is nothing left to collect.
    expect(collected).toBe("")
    expect(c.submitted(collected)).toBe(SPOKEN_FINAL)
  })

  it("submits the final when it settles just after submit, inside the grace window", async () => {
    const c = composer()
    const view = await listening(c.onFinal)
    const recognition = FakeSpeechRecognition.latest()

    act(() => recognition.fireResult(SPOKEN_INTERIM, false))

    // The real sequence: the candidate presses submit mid-sentence and Azure settles the
    // utterance a moment later. This is the case that produced "poison" and "Pie Charts".
    let collected = ""
    await act(async () => {
      const pending = view.result.current.stopAndCollect()
      recognition.fireResult(SPOKEN_FINAL, true)
      collected = await pending
    })

    expect(collected).toBe(SPOKEN_FINAL)
    expect(c.submitted(collected)).toBe(SPOKEN_FINAL)
    // The interim must not also be appended - that is the duplication bug.
    expect(c.submitted(collected)).not.toContain(SPOKEN_INTERIM + " " + SPOKEN_FINAL)
  })

  it("falls back to the interim when no final ever arrives", async () => {
    const c = composer()
    const view = await listening(c.onFinal)

    act(() => FakeSpeechRecognition.latest().fireResult(SPOKEN_INTERIM, false))

    let collected = ""
    await act(async () => {
      collected = await view.result.current.stopAndCollect()
    })

    // Nothing is lost when the recogniser never settles: the candidate's words still count.
    expect(collected).toBe(SPOKEN_INTERIM)
    expect(c.submitted(collected)).toBe(SPOKEN_INTERIM)
  })

  it("resolves as soon as the session closes, without waiting out the full window", async () => {
    const c = composer()
    const view = await listening(c.onFinal)
    const recognition = FakeSpeechRecognition.latest()

    act(() => recognition.fireResult(SPOKEN_INTERIM, false))

    const startedAt = Date.now()
    let collected = ""
    await act(async () => {
      const pending = view.result.current.stopAndCollect()
      // The provider reports the session closed: no final is coming, so there is nothing left
      // to wait for and the candidate should not be made to.
      recognition.fireEnd()
      collected = await pending
    })

    expect(collected).toBe(SPOKEN_INTERIM)
    expect(Date.now() - startedAt).toBeLessThan(FINAL_RESULT_GRACE_MS)
  })

  it("commits the spoken words exactly once when both an interim and a final exist", async () => {
    const onFinal = vi.fn()
    const view = await listening(onFinal)
    const recognition = FakeSpeechRecognition.latest()

    act(() => recognition.fireResult(SPOKEN_INTERIM, false))

    let collected = ""
    await act(async () => {
      const pending = view.result.current.stopAndCollect()
      recognition.fireResult(SPOKEN_FINAL, true)
      collected = await pending
    })

    // The collected final went to the caller, never through `onFinal`: returning the text is
    // what makes committing it twice structurally impossible rather than merely guarded.
    expect(onFinal).not.toHaveBeenCalled()
    expect(collected).toBe(SPOKEN_FINAL)
    expect(view.result.current.partial).toBe("")
  })

  it("ignores a second final that arrives after the window has already closed", async () => {
    const onFinal = vi.fn()
    const view = await listening(onFinal)
    const recognition = FakeSpeechRecognition.latest()

    act(() => recognition.fireResult(SPOKEN_INTERIM, false))
    await act(async () => {
      const pending = view.result.current.stopAndCollect()
      recognition.fireResult(SPOKEN_FINAL, true)
      await pending
    })

    act(() => recognition.fireResult("a straggling extra result", true))
    act(() => recognition.fireEnd())

    await new Promise((resolve) => setTimeout(resolve, 50))
    expect(onFinal).not.toHaveBeenCalled()
    // No restart: the candidate stopped, so the microphone stays closed.
    expect(FakeSpeechRecognition.instances).toHaveLength(1)
  })

  it("returns the draft without waiting when the microphone is already closed", async () => {
    const view = renderHook(() => useSpeechInput({ onFinal: vi.fn() }))

    // Submitting a typed answer with no recording session open must not stall on a timer.
    let collected = "unset"
    await act(async () => {
      collected = await view.result.current.stopAndCollect()
    })

    expect(collected).toBe("")
  })

  it("settles a pending collect when the candidate closes the microphone mid-window", async () => {
    const view = await listening(vi.fn())
    act(() => FakeSpeechRecognition.latest().fireResult(SPOKEN_INTERIM, false))

    let collected = ""
    await act(async () => {
      const pending = view.result.current.stopAndCollect()
      // A pending promise must never be left unresolved: the submit path awaits it.
      view.result.current.stop()
      collected = await pending
    })

    expect(collected).toBe(SPOKEN_INTERIM)
  })
})
