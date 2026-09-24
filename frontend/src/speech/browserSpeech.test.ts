import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { browserSpeechInput, browserSpeechOutput, pickEnglishVoice, toInputError } from "./browserSpeech"
import {
  FakeSpeechRecognition,
  installFakeRecognition,
  installFakeSynthesis,
  makeVoice,
  uninstallFakeRecognition,
} from "./testDoubles"
import type { SpeechInputError, SpeechInputHandlers } from "./types"

function handlers(overrides: Partial<SpeechInputHandlers> = {}): SpeechInputHandlers {
  return {
    onPartial: vi.fn(),
    onFinal: vi.fn(),
    onError: vi.fn(),
    onEnd: vi.fn(),
    ...overrides,
  }
}

describe("browserSpeechInput.start lifecycle", () => {
  beforeEach(() => {
    installFakeRecognition()
    vi.spyOn(console, "log").mockImplementation(() => {})
  })

  afterEach(() => {
    uninstallFakeRecognition()
    vi.restoreAllMocks()
  })

  it("resolves once the recognition session actually starts", async () => {
    const promise = browserSpeechInput.start(handlers())
    const recognition = FakeSpeechRecognition.latest()

    expect(recognition.startCalls).toBe(1)
    recognition.fireStart()

    await expect(promise).resolves.toMatchObject({ stop: expect.any(Function) })
  })

  it("applies the configuration the interview needs", async () => {
    const promise = browserSpeechInput.start(handlers())
    const recognition = FakeSpeechRecognition.latest()
    recognition.fireStart()
    await promise

    expect(recognition.lang).toBe("en-US")
    expect(recognition.continuous).toBe(true)
    expect(recognition.interimResults).toBe(true)
    expect(recognition.maxAlternatives).toBe(1)
  })

  it("rejects immediately when an error arrives before start, carrying the real reason", async () => {
    const promise = browserSpeechInput.start(handlers())
    const recognition = FakeSpeechRecognition.latest()

    recognition.fireError("not-allowed")

    // The regression this covers: the old implementation hung for 5s and then reported a
    // misleading "browser unsupported" instead of the actual permission failure.
    await expect(promise).rejects.toMatchObject({ kind: "permission-denied", fatal: true })
  })

  it("rejects immediately when the session ends before it ever started", async () => {
    const promise = browserSpeechInput.start(handlers())
    const recognition = FakeSpeechRecognition.latest()

    recognition.fireEnd()

    await expect(promise).rejects.toMatchObject({ fatal: true })
  })

  it("does not reject after a successful start - errors go to the handler instead", async () => {
    const onError = vi.fn()
    const promise = browserSpeechInput.start(handlers({ onError }))
    const recognition = FakeSpeechRecognition.latest()
    recognition.fireStart()
    await promise

    recognition.fireError("no-speech")

    expect(onError).toHaveBeenCalledWith(expect.objectContaining({ kind: "no-speech", fatal: false }))
  })

  it("delivers interim results before they are final", async () => {
    const onPartial = vi.fn()
    const onFinal = vi.fn()
    const promise = browserSpeechInput.start(handlers({ onPartial, onFinal }))
    const recognition = FakeSpeechRecognition.latest()
    recognition.fireStart()
    await promise

    recognition.fireResult("I designed a billing", false)
    expect(onPartial).toHaveBeenCalledWith("I designed a billing")
    expect(onFinal).not.toHaveBeenCalled()

    recognition.fireResult("I designed a billing service", true)
    expect(onFinal).toHaveBeenCalledWith("I designed a billing service")
  })
})

describe("toInputError classification", () => {
  it.each([
    ["not-allowed", true],
    ["service-not-allowed", true],
    ["audio-capture", true],
  ])("treats %s as fatal", (code, fatal) => {
    expect(toInputError(code).fatal).toBe(fatal)
  })

  it.each([["no-speech"], ["network"], ["aborted"], ["something-unknown"]])(
    "treats %s as recoverable",
    (code) => {
      expect(toInputError(code).fatal).toBe(false)
    },
  )

  it("never exposes a raw browser error code to the candidate", () => {
    for (const code of ["not-allowed", "audio-capture", "no-speech", "network", "aborted"]) {
      const error: SpeechInputError = toInputError(code)
      expect(error.message).not.toContain(code)
      expect(error.message.length).toBeGreaterThan(0)
    }
  })
})

describe("pickEnglishVoice", () => {
  it("never selects a non-English voice, even when it is the platform default", () => {
    const voices = [
      makeVoice("Microsoft Naayf - Arabic (Saudi)", "ar-SA", { default: true }),
      makeVoice("Microsoft David - English (United States)", "en-US"),
    ]
    expect(pickEnglishVoice(voices)?.lang).toBe("en-US")
  })

  it("prefers en-US over other English variants", () => {
    const voices = [makeVoice("Aussie", "en-AU"), makeVoice("American", "en-US")]
    expect(pickEnglishVoice(voices)?.name).toBe("American")
  })

  it("prefers a network (neural) voice over a local one", () => {
    const voices = [
      makeVoice("Microsoft David - English (United States)", "en-US", { localService: true }),
      makeVoice("Google US English", "en-US", { localService: false }),
    ]
    expect(pickEnglishVoice(voices)?.name).toBe("Google US English")
  })

  it("is deterministic when voices tie", () => {
    const voices = [
      makeVoice("Microsoft Zira - English (United States)", "en-US"),
      makeVoice("Microsoft David - English (United States)", "en-US"),
      makeVoice("Microsoft Mark - English (United States)", "en-US"),
    ]
    const first = pickEnglishVoice([...voices])?.name
    const again = pickEnglishVoice([...voices].reverse())?.name
    expect(first).toBe(again)
    expect(first).toBe("Microsoft David - English (United States)")
  })

  it("handles underscore locale forms", () => {
    expect(pickEnglishVoice([makeVoice("Odd", "en_US")])?.name).toBe("Odd")
  })

  it("returns null when no English voice exists at all", () => {
    expect(pickEnglishVoice([makeVoice("Naayf", "ar-SA", { default: true })])).toBeNull()
  })
})

describe("browserSpeechOutput", () => {
  beforeEach(() => {
    vi.spyOn(console, "log").mockImplementation(() => {})
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it("speaks English questions with an English voice and en-US lang", async () => {
    const synth = installFakeSynthesis([
      makeVoice("Microsoft Naayf - Arabic (Saudi)", "ar-SA", { default: true }),
      makeVoice("Microsoft David - English (United States)", "en-US"),
    ])

    browserSpeechOutput.speak("Tell me about a backend system you designed.", {})
    await vi.waitFor(() => expect(synth.spoken).toHaveLength(1))

    const utterance = synth.spoken[0]
    expect(utterance.lang).toBe("en-US")
    expect(utterance.voice?.lang).toBe("en-US")
    expect(utterance.voice?.name).not.toContain("Arabic")
  })

  it("waits for voiceschanged when the list is not ready yet", async () => {
    const synth = installFakeSynthesis([])

    browserSpeechOutput.speak("A question.", {})
    // Nothing spoken yet: the voice list is still empty.
    expect(synth.spoken).toHaveLength(0)

    synth.setVoicesLater([
      makeVoice("Microsoft Naayf - Arabic (Saudi)", "ar-SA", { default: true }),
      makeVoice("Google US English", "en-US", { localService: false }),
    ])

    await vi.waitFor(() => expect(synth.spoken).toHaveLength(1))
    expect(synth.spoken[0].voice?.name).toBe("Google US English")
  })

  it("still speaks when the platform offers no English voice", async () => {
    const synth = installFakeSynthesis([makeVoice("Naayf", "ar-SA", { default: true })])

    browserSpeechOutput.speak("A question.", {})
    await vi.waitFor(() => expect(synth.spoken).toHaveLength(1))

    // No English voice to pick, but the utterance still declares English so the platform can
    // do the best it can, rather than reading English with an Arabic voice by default.
    expect(synth.spoken[0].voice).toBeNull()
    expect(synth.spoken[0].lang).toBe("en-US")
  })
})
