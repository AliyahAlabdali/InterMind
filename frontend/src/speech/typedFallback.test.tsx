import { act, renderHook, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { useSpeechInput } from "./useSpeechInput"
import { browserSpeechInput } from "./browserSpeech"
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
 * Typing is the guaranteed input path: voice is an enhancement that must never be able to block
 * a candidate from answering. These cover the conditions under which the interview falls back
 * to typing.
 */
describe("typed fallback", () => {
  beforeEach(() => {
    vi.spyOn(console, "log").mockImplementation(() => {})
  })

  afterEach(() => {
    uninstallFakeRecognition()
    vi.restoreAllMocks()
  })

  it("reports voice as unsupported when the browser has no SpeechRecognition at all", () => {
    uninstallFakeRecognition()
    expect(browserSpeechInput.isSupported()).toBe(false)

    const view = renderHook(() => useSpeechInput({ onFinal: vi.fn() }))
    expect(view.result.current.isSupported).toBe(false)
    // The interview renders the typing-only hint in this case rather than a dead button.
    expect(view.result.current.isRecording).toBe(false)
  })

  it("leaves the answer under the candidate's control after a fatal voice failure", async () => {
    installFakeRecognition()
    const onFinal = vi.fn()
    const view = renderHook(() => useSpeechInput({ onFinal }))

    await act(async () => {
      void view.result.current.start()
      await Promise.resolve()
      FakeSpeechRecognition.latest().fireError("not-allowed")
    })

    await waitFor(() => expect(view.result.current.isUnavailable).toBe(true))
    // Nothing was written into the answer, and no further sessions were attempted - the
    // candidate simply carries on typing.
    expect(onFinal).not.toHaveBeenCalled()
    expect(FakeSpeechRecognition.instances).toHaveLength(1)
    expect(view.result.current.notice).toMatch(/continue by typing/i)
  })

  it("hands dictated text to the caller so it can be merged with typed text", async () => {
    installFakeRecognition()
    const onFinal = vi.fn()
    const view = renderHook(() => useSpeechInput({ onFinal }))

    await act(async () => {
      void view.result.current.start()
      await Promise.resolve()
      FakeSpeechRecognition.latest().fireStart()
    })
    await waitFor(() => expect(view.result.current.status).toBe("listening"))

    act(() => FakeSpeechRecognition.latest().fireResult("dictated sentence", true))

    // The hook never owns the answer text - it only reports finals, so typed content the
    // candidate already wrote is never overwritten.
    await waitFor(() => expect(onFinal).toHaveBeenCalledWith("dictated sentence"))
  })
})
