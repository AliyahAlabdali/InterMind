/**
 * Azure question narration: credential handling, token reuse, and failing safely.
 *
 * The security property under test is the same one the input provider has always had: the
 * browser is given a short-lived, interview-scoped authorization token and never an Azure key,
 * and that token is never written anywhere it could outlive the page or be read back.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

const getSpeechToken = vi.fn()
vi.mock("../api/speech", () => ({ getSpeechToken: (...args: unknown[]) => getSpeechToken(...args) }))

// A synthesizer that hands back bytes, and records the config it was built with.
const synthesized: Array<{ text: string; voice: string; format: number }> = []
let synthesisShouldFail = false

class FakeSpeechConfig {
  authorizationToken = ""
  speechSynthesisVoiceName = ""
  speechSynthesisOutputFormat = -1
  static fromHost = vi.fn(() => new FakeSpeechConfig())
  static fromAuthorizationToken = vi.fn(() => new FakeSpeechConfig())
}

class FakeSynthesizer {
  private config: FakeSpeechConfig
  constructor(config: FakeSpeechConfig) {
    this.config = config
  }
  speakTextAsync(
    text: string,
    done: (result: unknown) => void,
    fail: (error: string) => void,
  ) {
    if (synthesisShouldFail) {
      fail("synthesis refused")
      return
    }
    synthesized.push({
      text,
      voice: this.config.speechSynthesisVoiceName,
      format: this.config.speechSynthesisOutputFormat,
    })
    done({ reason: 8, audioData: new ArrayBuffer(16), errorDetails: "" })
  }
  close() {}
}

vi.mock("microsoft-cognitiveservices-speech-sdk", () => ({
  SpeechConfig: FakeSpeechConfig,
  SpeechSynthesizer: FakeSynthesizer,
  ResultReason: { SynthesizingAudioCompleted: 8 },
}))

import { azureSpeechOutput, clearSpeechTokenCache, INTERVIEWER_VOICE } from "./azureSpeechOutput"
import { resetAudioUnlockForTests } from "./audioUnlock"

const CONTEXT = { interviewId: "interview-1", accessToken: "candidate-token-value" }

const TOKEN = {
  token: "azure-authorization-token-value",
  host: "intermind-speech.cognitiveservices.azure.com",
  region: null,
  language: "en-US",
  expires_in_seconds: 540,
}

/** Minimal HTMLAudioElement stand-in: jsdom cannot decode or play real audio. */
class FakeAudio {
  src = ""
  muted = false
  currentTime = 0
  paused = true
  ended = false
  preload = ""
  onended: (() => void) | null = null
  onerror: (() => void) | null = null
  play = vi.fn(async () => {
    this.paused = false
  })
  pause = vi.fn(() => {
    this.paused = true
  })
  setAttribute() {}
}

let audio: FakeAudio
let originalCreateObjectURL: typeof URL.createObjectURL
let originalRevokeObjectURL: typeof URL.revokeObjectURL

beforeEach(() => {
  synthesized.length = 0
  synthesisShouldFail = false
  getSpeechToken.mockReset()
  getSpeechToken.mockResolvedValue({ ...TOKEN })
  clearSpeechTokenCache()
  resetAudioUnlockForTests()
  audio = new FakeAudio()
  // A plain function, not an arrow: the provider calls `new Audio()`, and returning an object
  // from a constructor is what hands back this one shared fake.
  vi.stubGlobal(
    "Audio",
    function FakeAudioCtor() {
      return audio
    } as unknown as typeof Audio,
  )
  // Patch only the two statics. Replacing `URL` wholesale would break `new URL(...)`, which the
  // provider uses to address the Speech resource's custom domain.
  originalCreateObjectURL = URL.createObjectURL
  originalRevokeObjectURL = URL.revokeObjectURL
  URL.createObjectURL = vi.fn(() => "blob:narration")
  URL.revokeObjectURL = vi.fn()
  vi.spyOn(console, "log").mockImplementation(() => {})
})

afterEach(() => {
  URL.createObjectURL = originalCreateObjectURL
  URL.revokeObjectURL = originalRevokeObjectURL
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

/** Wait for the provider's internal async work to settle. */
const settle = () => new Promise((resolve) => setTimeout(resolve, 0))

describe("azure narration", () => {
  it("synthesizes with the pinned adult female voice, not a browser-chosen one", async () => {
    azureSpeechOutput.speak("Tell me about a system you designed.", {}, CONTEXT)
    await settle()

    expect(synthesized).toHaveLength(1)
    expect(synthesized[0].voice).toBe(INTERVIEWER_VOICE)
    expect(synthesized[0].text).toBe("Tell me about a system you designed.")
  })

  it("authorizes with this interview's own token from our backend", async () => {
    azureSpeechOutput.speak("A question.", {}, CONTEXT)
    await settle()

    expect(getSpeechToken).toHaveBeenCalledWith("interview-1", "candidate-token-value")
  })

  it("reuses one token across questions instead of minting one per question", async () => {
    azureSpeechOutput.speak("First question.", {}, CONTEXT)
    await settle()
    azureSpeechOutput.speak("Second question.", {}, CONTEXT)
    await settle()
    azureSpeechOutput.speak("Third question.", {}, CONTEXT)
    await settle()

    expect(synthesized).toHaveLength(3)
    expect(getSpeechToken).toHaveBeenCalledTimes(1)
  })

  it("mints a fresh token once the cached one is close to expiring", async () => {
    getSpeechToken.mockResolvedValue({ ...TOKEN, expires_in_seconds: 30 })

    azureSpeechOutput.speak("First question.", {}, CONTEXT)
    await settle()
    // 30s life minus the 60s safety margin means it was never usable a second time.
    azureSpeechOutput.speak("Second question.", {}, CONTEXT)
    await settle()

    expect(getSpeechToken).toHaveBeenCalledTimes(2)
  })

  it("never stores a speech token anywhere that outlives the page", async () => {
    azureSpeechOutput.speak("A question.", {}, CONTEXT)
    await settle()

    const persisted = [
      ...Object.values(window.localStorage),
      ...Object.values(window.sessionStorage),
      window.document.cookie,
    ].join(" ")
    expect(persisted).not.toContain(TOKEN.token)
    expect(persisted).not.toContain(CONTEXT.accessToken)
  })

  it("never logs the speech token or the candidate's access token", async () => {
    const log = vi.spyOn(console, "log").mockImplementation(() => {})
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {})
    const error = vi.spyOn(console, "error").mockImplementation(() => {})

    synthesisShouldFail = true
    azureSpeechOutput.speak("A question.", { onError: () => {} }, CONTEXT)
    await settle()

    const written = [...log.mock.calls, ...warn.mock.calls, ...error.mock.calls]
      .flat()
      .map((entry) => (typeof entry === "string" ? entry : JSON.stringify(entry)))
      .join(" ")
    expect(written).not.toContain(TOKEN.token)
    expect(written).not.toContain(CONTEXT.accessToken)
  })

  it("reports an error rather than throwing when synthesis fails", async () => {
    synthesisShouldFail = true
    const onError = vi.fn()

    azureSpeechOutput.speak("A question.", { onError }, CONTEXT)
    await settle()

    expect(onError).toHaveBeenCalled()
  })

  it("discards a token that failed, so one bad token cannot break every later question", async () => {
    synthesisShouldFail = true
    azureSpeechOutput.speak("First question.", { onError: () => {} }, CONTEXT)
    await settle()

    synthesisShouldFail = false
    azureSpeechOutput.speak("Second question.", {}, CONTEXT)
    await settle()

    expect(getSpeechToken).toHaveBeenCalledTimes(2)
    expect(synthesized).toHaveLength(1)
  })

  it("errors immediately when there is no interview credential to authorize with", () => {
    const onError = vi.fn()

    azureSpeechOutput.speak("A question.", { onError }, { interviewId: "interview-1" })

    expect(onError).toHaveBeenCalled()
    expect(getSpeechToken).not.toHaveBeenCalled()
  })

  it("stops playback and reports nothing further once cancelled", async () => {
    const onEnd = vi.fn()
    const session = azureSpeechOutput.speak("A question.", { onEnd }, CONTEXT)
    session.cancel()
    await settle()

    expect(audio.pause).toHaveBeenCalled()
    expect(onEnd).not.toHaveBeenCalled()
  })
})
