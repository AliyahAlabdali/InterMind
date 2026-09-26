import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

/**
 * The Azure SDK is mocked at the module boundary: these tests must never require an Azure
 * subscription, a microphone, or a network. What they verify is the contract this provider
 * exposes to the rest of InterMind - transcript semantics, lifecycle, and that no Azure detail
 * ever escapes into candidate-facing text.
 */

const startContinuousRecognitionAsync = vi.fn()
const stopContinuousRecognitionAsync = vi.fn()
const close = vi.fn()

/** Captures the recognizer the provider builds so tests can fire SDK events at it. */
interface FakeRecognizer {
  recognizing?: (sender: unknown, event: unknown) => void
  recognized?: (sender: unknown, event: unknown) => void
  canceled?: (sender: unknown, event: unknown) => void
  sessionStopped?: (sender: unknown, event: unknown) => void
  startContinuousRecognitionAsync: typeof startContinuousRecognitionAsync
  stopContinuousRecognitionAsync: typeof stopContinuousRecognitionAsync
  close: typeof close
}

let lastRecognizer: FakeRecognizer | null = null
let micThrows = false
/** Every phrase biased onto the recognizer built by the most recent `start()`. */
let addedPhrases: string[] = []
/** Set to make the SDK refuse to build a phrase list, as an older SDK or a locale might. */
let phraseListThrows = false
/** The config object the provider configured, so its settings can be asserted on. */
let lastSpeechConfig: {
  speechRecognitionLanguage: string
  authorizationToken?: string
  outputFormat?: unknown
} | null = null

function newConfig() {
  lastSpeechConfig = {
    speechRecognitionLanguage: "",
    authorizationToken: "",
    close: vi.fn(),
  } as typeof lastSpeechConfig
  return lastSpeechConfig
}

const fromAuthorizationToken = vi.fn(() => newConfig())
/** The managed-identity path: an Entra token is only accepted at the resource's custom domain,
 * so the provider must build the config from a host rather than a region. */
const fromHost = vi.fn(() => newConfig())

vi.mock("microsoft-cognitiveservices-speech-sdk", () => ({
  SpeechConfig: {
    fromAuthorizationToken: (...args: unknown[]) => fromAuthorizationToken(...(args as [])),
    fromHost: (...args: unknown[]) => fromHost(...(args as [])),
  },
  AudioConfig: {
    fromDefaultMicrophoneInput: () => {
      if (micThrows) throw new Error("microphone not available")
      return {}
    },
  },
  SpeechRecognizer: class {
    startContinuousRecognitionAsync = startContinuousRecognitionAsync
    stopContinuousRecognitionAsync = stopContinuousRecognitionAsync
    close = close
    constructor() {
      lastRecognizer = this as unknown as FakeRecognizer
    }
  },
  PhraseListGrammar: {
    fromRecognizer: () => {
      if (phraseListThrows) throw new Error("phrase list unsupported")
      return { addPhrase: (phrase: string) => addedPhrases.push(phrase) }
    },
  },
  OutputFormat: { Simple: 0, Detailed: 1 },
  ResultReason: { NoMatch: 0, RecognizingSpeech: 2, RecognizedSpeech: 3 },
  CancellationReason: { Error: 0, EndOfStream: 1 },
}))

const getSpeechToken = vi.fn()
vi.mock("../api/speech", () => ({ getSpeechToken: (...a: unknown[]) => getSpeechToken(...a) }))

const { azureSpeechInput, classifyCancellation } = await import("./azureSpeech")

const CONTEXT = { interviewId: "interview-1", accessToken: "candidate-token" }

function handlers() {
  return {
    onPartial: vi.fn(),
    onFinal: vi.fn(),
    onError: vi.fn(),
    onEnd: vi.fn(),
  }
}

/** Drives the SDK's success callback so `start()` resolves. */
function resolveStart() {
  startContinuousRecognitionAsync.mockImplementation((ok: () => void) => ok())
}

describe("azureSpeechInput", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    lastRecognizer = null
    lastSpeechConfig = null
    micThrows = false
    addedPhrases = []
    phraseListThrows = false
    vi.spyOn(console, "log").mockImplementation(() => {})
    getSpeechToken.mockResolvedValue({
      token: "short-lived-token",
      region: "westeurope",
      language: "en-US",
      expires_in_seconds: 540,
    })
    resolveStart()
  })

  afterEach(() => vi.restoreAllMocks())

  it("initializes from a backend-issued token, never a subscription key", async () => {
    await azureSpeechInput.start(handlers(), CONTEXT)

    expect(getSpeechToken).toHaveBeenCalledWith("interview-1", "candidate-token")
    expect(fromAuthorizationToken).toHaveBeenCalledWith("short-lived-token", "westeurope")
  })

  describe("connection target", () => {
    /**
     * The backend decides where the browser connects, because the two credentials are not
     * interchangeable at the network level: a managed-identity (Entra) token is only accepted at
     * the Speech resource's custom-domain host, while a key-issued token is regional. Sending an
     * Entra token to the regional endpoint fails to connect, so which factory is used is a
     * correctness property, not a style choice.
     */
    it("connects to the custom domain when the backend names a host", async () => {
      getSpeechToken.mockResolvedValue({
        token: "aad#/subscriptions/0000/resourceGroups/rg/providers/x#entra-token",
        region: null,
        host: "intermind-speech-aliyah.cognitiveservices.azure.com",
        language: "en-US",
        expires_in_seconds: 540,
      })

      await azureSpeechInput.start(handlers(), CONTEXT)

      expect(fromHost).toHaveBeenCalledTimes(1)
      const [hostUrl] = fromHost.mock.calls[0] as unknown as [URL]
      expect(hostUrl.toString()).toBe(
        "wss://intermind-speech-aliyah.cognitiveservices.azure.com/",
      )
      // fromHost takes no token, so the authorization token has to be set on the config.
      expect(lastSpeechConfig?.authorizationToken).toBe(
        "aad#/subscriptions/0000/resourceGroups/rg/providers/x#entra-token",
      )
      expect(fromAuthorizationToken).not.toHaveBeenCalled()
    })

    it("prefers the host over a region when the backend sends both", async () => {
      getSpeechToken.mockResolvedValue({
        token: "aad#resource#entra-token",
        region: "eastus",
        host: "intermind-speech-aliyah.cognitiveservices.azure.com",
        language: "en-US",
        expires_in_seconds: 540,
      })

      await azureSpeechInput.start(handlers(), CONTEXT)

      expect(fromHost).toHaveBeenCalledTimes(1)
      expect(fromAuthorizationToken).not.toHaveBeenCalled()
    })

    it("falls back to the region for the key-based local-development path", async () => {
      // Exactly what the backend returns with AZURE_SPEECH_KEY set and no resource id.
      getSpeechToken.mockResolvedValue({
        token: "short-lived-token",
        region: "westeurope",
        host: null,
        language: "en-US",
        expires_in_seconds: 540,
      })

      await azureSpeechInput.start(handlers(), CONTEXT)

      expect(fromAuthorizationToken).toHaveBeenCalledWith("short-lived-token", "westeurope")
      expect(fromHost).not.toHaveBeenCalled()
    })

    it("fails cleanly when the backend names neither, leaving typing available", async () => {
      getSpeechToken.mockResolvedValue({
        token: "a-token-with-nowhere-to-go",
        region: null,
        host: null,
        language: "en-US",
        expires_in_seconds: 540,
      })

      await expect(azureSpeechInput.start(handlers(), CONTEXT)).rejects.toMatchObject({
        fatal: true,
        message: expect.stringContaining("continue by typing"),
      })
      expect(fromHost).not.toHaveBeenCalled()
      expect(fromAuthorizationToken).not.toHaveBeenCalled()
    })
  })

  it("resolves only once recognition has actually started", async () => {
    let started = false
    startContinuousRecognitionAsync.mockImplementation((ok: () => void) => {
      setTimeout(() => {
        started = true
        ok()
      }, 5)
    })

    await azureSpeechInput.start(handlers(), CONTEXT)
    expect(started).toBe(true)
  })

  it("delivers interim text as partial, not final", async () => {
    const h = handlers()
    await azureSpeechInput.start(h, CONTEXT)

    lastRecognizer?.recognizing?.(null, { result: { text: "I designed a billing" } })

    expect(h.onPartial).toHaveBeenCalledWith("I designed a billing")
    expect(h.onFinal).not.toHaveBeenCalled()
  })

  it("delivers recognized text as final", async () => {
    const h = handlers()
    await azureSpeechInput.start(h, CONTEXT)

    lastRecognizer?.recognized?.(null, { result: { reason: 3, text: "I designed a billing service" } })

    expect(h.onFinal).toHaveBeenCalledWith("I designed a billing service")
  })

  it("accumulates multiple final segments without duplicating interim text", async () => {
    const h = handlers()
    await azureSpeechInput.start(h, CONTEXT)

    lastRecognizer?.recognizing?.(null, { result: { text: "first part" } })
    lastRecognizer?.recognized?.(null, { result: { reason: 3, text: "first part complete" } })
    lastRecognizer?.recognizing?.(null, { result: { text: "second" } })
    lastRecognizer?.recognized?.(null, { result: { reason: 3, text: "second part complete" } })

    // Only finals reach the answer - interim hypotheses are display-only, which is what stops
    // the same words being appended twice.
    expect(h.onFinal.mock.calls.map((call) => call[0])).toEqual([
      "first part complete",
      "second part complete",
    ])
  })

  it("ignores NoMatch results, which are silence rather than transcript", async () => {
    const h = handlers()
    await azureSpeechInput.start(h, CONTEXT)

    lastRecognizer?.recognized?.(null, { result: { reason: 0, text: "" } })

    expect(h.onFinal).not.toHaveBeenCalled()
    expect(h.onError).not.toHaveBeenCalled()
  })

  it("releases the microphone on a clean stop", async () => {
    stopContinuousRecognitionAsync.mockImplementation((ok: () => void) => ok())
    const session = await azureSpeechInput.start(handlers(), CONTEXT)

    session.stop()

    expect(stopContinuousRecognitionAsync).toHaveBeenCalled()
    expect(close).toHaveBeenCalled()
  })

  it("reports a session the service closed as an end, not an error", async () => {
    const h = handlers()
    await azureSpeechInput.start(h, CONTEXT)

    lastRecognizer?.sessionStopped?.(null, {})

    expect(h.onEnd).toHaveBeenCalled()
    expect(h.onError).not.toHaveBeenCalled()
  })

  it("surfaces a cancellation as a friendly error and ends the session", async () => {
    const h = handlers()
    await azureSpeechInput.start(h, CONTEXT)

    lastRecognizer?.canceled?.(null, {
      reason: 0,
      errorCode: 7,
      errorDetails: "Websocket connection closed unexpectedly",
    })

    expect(h.onError).toHaveBeenCalledTimes(1)
    const error = h.onError.mock.calls[0][0]
    expect(error.message).not.toMatch(/websocket/i)
    expect(error.message).not.toMatch(/CancellationReason/i)
    expect(h.onEnd).toHaveBeenCalled()
  })

  it("reports one end when the service both cancels and stops the same session", async () => {
    const h = handlers()
    await azureSpeechInput.start(h, CONTEXT)

    // The real sequence when a connection drops: the stream is cancelled, then the session
    // closes behind it. Reporting both as an end made the hook restart twice, leaving two
    // recognizers on one microphone and duplicating every later utterance.
    lastRecognizer?.canceled?.(null, {
      reason: 0,
      errorCode: 7,
      errorDetails: "Connection was closed by the remote host",
    })
    lastRecognizer?.sessionStopped?.(null, {})

    expect(h.onEnd).toHaveBeenCalledTimes(1)
    expect(h.onError).toHaveBeenCalledTimes(1)
  })

  it("ignores transcript that arrives after the session has ended", async () => {
    const h = handlers()
    await azureSpeechInput.start(h, CONTEXT)

    lastRecognizer?.sessionStopped?.(null, {})
    lastRecognizer?.recognized?.(null, { result: { reason: 3, text: "trailing words" } })
    lastRecognizer?.recognizing?.(null, { result: { text: "trailing" } })

    expect(h.onFinal).not.toHaveBeenCalled()
    expect(h.onPartial).not.toHaveBeenCalled()
  })

  it("delivers the final that settles just after the caller stopped the session", async () => {
    stopContinuousRecognitionAsync.mockImplementation((ok: () => void) => ok())
    const h = handlers()
    const session = await azureSpeechInput.start(h, CONTEXT)

    session.stop()
    // Azure settles the utterance that was in flight when stop() was called, and that result -
    // rescored, punctuated, normalized - is the best record of the candidate's last sentence.
    // This provider used to drop it, which is why answers were submitted from the interim.
    // Delivering it is safe because `useSpeechInput` commits either it or the interim, never
    // both; see the grace-window tests in useSpeechInput.test.tsx.
    lastRecognizer?.recognized?.(null, { result: { reason: 3, text: "the last thing I said." } })

    expect(h.onFinal).toHaveBeenCalledWith("the last thing I said.")
  })

  it("stops revising the interim draft once the caller has stopped", async () => {
    stopContinuousRecognitionAsync.mockImplementation((ok: () => void) => ok())
    const h = handlers()
    const session = await azureSpeechInput.start(h, CONTEXT)

    session.stop()
    // A late hypothesis can only revise a display nobody is watching, and could regress the
    // fallback text below what was already heard.
    lastRecognizer?.recognizing?.(null, { result: { text: "the last thing" } })

    expect(h.onPartial).not.toHaveBeenCalled()
  })

  it("still ignores everything once the session is genuinely over", async () => {
    const h = handlers()
    await azureSpeechInput.start(h, CONTEXT)

    // `sessionStopped` is the service closing the stream, not the caller pausing it: nothing
    // after it belongs to the answer.
    lastRecognizer?.sessionStopped?.(null, {})
    lastRecognizer?.recognized?.(null, { result: { reason: 3, text: "trailing words" } })

    expect(h.onFinal).not.toHaveBeenCalled()
  })

  /* --- Technical vocabulary biasing --------------------------------------------------- */

  it("biases the recognizer with the interview's own technical phrases", async () => {
    await azureSpeechInput.start(handlers(), {
      ...CONTEXT,
      phrases: ["Python", "PyTorch", "Computer Vision"],
    })

    expect(addedPhrases).toEqual(["Python", "PyTorch", "Computer Vision"])
  })

  it("records no phrases when the interview supplies none", async () => {
    await azureSpeechInput.start(handlers(), CONTEXT)
    expect(addedPhrases).toEqual([])
  })

  it("still records when the phrase list cannot be built", async () => {
    phraseListThrows = true
    const h = handlers()

    // Losing accuracy on technical terms is a far smaller problem than refusing to record, so
    // biasing is best-effort and never fails the session.
    const session = await azureSpeechInput.start(h, { ...CONTEXT, phrases: ["PyTorch"] })
    lastRecognizer?.recognized?.(null, { result: { reason: 3, text: "an answer" } })

    expect(h.onFinal).toHaveBeenCalledWith("an answer")
    expect(h.onError).not.toHaveBeenCalled()
    expect(session).toBeDefined()
  })

  it("requests detailed output so confidence and alternatives can be measured", async () => {
    await azureSpeechInput.start(handlers(), CONTEXT)

    // Internal/diagnostic only - the provider still reads `result.text`, so the candidate-facing
    // transcript is unchanged by this.
    expect(lastSpeechConfig?.outputFormat).toBe(1)
  })

  it("fails fast and fatally when the backend will not issue a token", async () => {
    getSpeechToken.mockRejectedValue(new Error("503 Service Unavailable"))

    await expect(azureSpeechInput.start(handlers(), CONTEXT)).rejects.toMatchObject({
      fatal: true,
      message: expect.stringMatching(/continue by typing/i),
    })
  })

  it("fails fatally when the microphone cannot be opened", async () => {
    micThrows = true

    await expect(azureSpeechInput.start(handlers(), CONTEXT)).rejects.toMatchObject({
      kind: "permission-denied",
      fatal: true,
    })
  })

  it("fails when no interview context is supplied", async () => {
    await expect(azureSpeechInput.start(handlers())).rejects.toMatchObject({ fatal: true })
    expect(getSpeechToken).not.toHaveBeenCalled()
  })

  it("rejects when the SDK cannot start recognition at all", async () => {
    startContinuousRecognitionAsync.mockImplementation(
      (_ok: () => void, fail: (e: string) => void) => fail("Microphone initialization failed"),
    )

    await expect(azureSpeechInput.start(handlers(), CONTEXT)).rejects.toMatchObject({
      kind: "permission-denied",
      fatal: true,
    })
  })
})

describe("classifyCancellation", () => {
  it.each([
    ["Microphone permission was denied", "permission-denied", true],
    ["WebSocket upgrade failed with 401 Unauthorized", "unknown", true],
    ["Authentication error while connecting", "unknown", true],
    ["Connection was closed by the remote host", "network", false],
  ])("classifies %s", (details, kind, fatal) => {
    const error = classifyCancellation(4, details)
    expect(error.kind).toBe(kind)
    expect(error.fatal).toBe(fatal)
  })

  it("never returns raw Azure detail in the candidate-facing message", () => {
    const details = "SPXERR_CONNECTION_FAILURE websocket error code 1006"
    expect(classifyCancellation(7, details).message).not.toContain("SPXERR")
  })

  it("treats a connection loss as recoverable so the session can restart", () => {
    expect(classifyCancellation(7, "Connection failed").fatal).toBe(false)
  })
})
