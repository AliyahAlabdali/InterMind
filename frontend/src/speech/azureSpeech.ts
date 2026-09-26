import { getSpeechToken } from "../api/speech"
import { speechLog } from "./debugLog"
import type {
  SpeechInputContext,
  SpeechInputError,
  SpeechInputHandlers,
  SpeechInputProvider,
  SpeechInputSession,
} from "./types"

/**
 * Azure AI Speech continuous recognition - the production STT provider.
 *
 * Replaces the browser's Web Speech API, which in real Chrome repeatedly opened the microphone,
 * detected no sound at all (`audiostart` with no `soundstart`) and timed out with `no-speech`.
 *
 * Credentials never touch this file. The browser is given a short-lived authorization token
 * minted by our own backend (`GET /interviews/{id}/speech-token`), which is the documented
 * browser-SDK path. The Azure resource key stays server-side - in production no key exists at
 * all, because the backend authenticates to Azure with its managed identity. A token lasts ~10
 * minutes and one is fetched per recording session, which is far shorter than a single answer,
 * so no refresh logic is needed inside a session.
 */

/** Candidate-facing wording only. Azure's own reasons/codes never reach the interview UI. */
function friendlyError(
  kind: SpeechInputError["kind"],
  message: string,
  fatal: boolean,
): SpeechInputError {
  return { kind, message, fatal }
}

const ERRORS = {
  microphone: friendlyError(
    "permission-denied",
    "Microphone access is required for voice answers. You can continue by typing.",
    true,
  ),
  auth: friendlyError(
    "unknown",
    "Voice input is temporarily unavailable. You can continue by typing.",
    true,
  ),
  connection: friendlyError("network", "We lost the speech connection. Please try again.", false),
  unavailable: friendlyError(
    "network",
    "Voice input is temporarily unavailable. You can continue by typing.",
    true,
  ),
} as const

/**
 * Map an Azure cancellation onto the provider-agnostic error contract.
 *
 * The distinction that matters downstream is `fatal`: the hook restarts non-fatal sessions and
 * stops for fatal ones. A dropped connection is worth retrying; a refused microphone or a
 * rejected token is not, and retrying would just spin.
 */
export function classifyCancellation(
  errorCode: number | undefined,
  errorDetails: string | undefined,
): SpeechInputError {
  const details = (errorDetails ?? "").toLowerCase()

  // Matched on substrings rather than numeric codes: the SDK's CancellationErrorCode values
  // have shifted between major versions, while these phrases have been stable.
  if (details.includes("microphone") || details.includes("permission") || details.includes("notallowed")) {
    return ERRORS.microphone
  }
  if (
    details.includes("401") ||
    details.includes("403") ||
    details.includes("forbidden") ||
    details.includes("unauthorized") ||
    details.includes("authentication")
  ) {
    return ERRORS.auth
  }
  if (details.includes("connection") || details.includes("websocket") || details.includes("timeout")) {
    return ERRORS.connection
  }
  if (errorCode === undefined) return ERRORS.connection
  return ERRORS.unavailable
}

export const azureSpeechInput: SpeechInputProvider = {
  id: "azure-speech",

  isSupported() {
    // The SDK needs a secure context and microphone capture; everything else it needs is
    // fetched at start time.
    return (
      typeof window !== "undefined" &&
      typeof navigator !== "undefined" &&
      Boolean(navigator.mediaDevices?.getUserMedia)
    )
  },

  async start(
    handlers: SpeechInputHandlers,
    context?: SpeechInputContext,
  ): Promise<SpeechInputSession> {
    if (!context?.interviewId || !context.accessToken) {
      // A programming error rather than a runtime condition - the interview always knows both.
      throw ERRORS.auth
    }

    let credentials
    try {
      credentials = await getSpeechToken(context.interviewId, context.accessToken)
    } catch (error) {
      speechLog("react", "azure token request failed", (error as Error)?.message)
      throw ERRORS.unavailable
    }

    // Loaded on demand: the SDK is ~76KB gzipped and most of the product never records audio,
    // so it stays out of the main bundle (same approach as the 3D interviewer's three.js).
    const {
      AudioConfig,
      CancellationReason,
      OutputFormat,
      PhraseListGrammar,
      ResultReason,
      SpeechConfig,
      SpeechRecognizer,
    } = await import("microsoft-cognitiveservices-speech-sdk")

    // Where to connect is the backend's decision, not this file's, and the two credential
    // shapes are not interchangeable: an Entra (managed-identity) token is only accepted at the
    // resource's own custom-domain host, while a key-issued token is regional. So `host` wins
    // when present, and `fromAuthorizationToken` - which targets the regional endpoint - is the
    // fallback for the key path used in local development.
    let speechConfig
    if (credentials.host) {
      speechConfig = SpeechConfig.fromHost(new URL(`wss://${credentials.host}`))
      speechConfig.authorizationToken = credentials.token
    } else if (credentials.region) {
      speechConfig = SpeechConfig.fromAuthorizationToken(credentials.token, credentials.region)
    } else {
      // A backend that returned neither is misconfigured; there is nothing to connect to and no
      // retry would help, so this is surfaced the same way an unreachable service would be.
      speechLog("react", "azure token response named neither host nor region")
      throw ERRORS.unavailable
    }
    speechConfig.speechRecognitionLanguage = credentials.language
    // Diagnostics only. Detailed adds per-result confidence and an N-best list to the SDK's own
    // result object; `result.text` - the only thing this provider reads - is unchanged, so the
    // transcript the candidate sees is exactly what Simple would have produced. This exists so
    // the next recognition-quality question can be measured instead of guessed at.
    speechConfig.outputFormat = OutputFormat.Detailed

    let audioConfig
    try {
      audioConfig = AudioConfig.fromDefaultMicrophoneInput()
    } catch {
      speechConfig.close()
      throw ERRORS.microphone
    }

    const recognizer = new SpeechRecognizer(speechConfig, audioConfig)

    // Bias the decoder toward this interview's own vocabulary before recognition starts. Must be
    // attached to the recognizer rather than the config - the grammar is per-recognizer state.
    // Best-effort: a failure here costs accuracy on technical terms, which is a far smaller
    // problem than refusing to record at all, so it never fails the session.
    if (context.phrases?.length) {
      try {
        const grammar = PhraseListGrammar.fromRecognizer(recognizer)
        for (const phrase of context.phrases) grammar.addPhrase(phrase)
        if (import.meta.env.DEV) {
          speechLog("config", "azure phrase list attached", { count: context.phrases.length })
        }
      } catch (error) {
        speechLog("config", "azure phrase list unavailable", (error as Error)?.message)
      }
    }

    let stopped = false
    let ended = false
    /**
     * Set by the caller's `stop()`, as distinct from `ended`.
     *
     * The utterance in flight when the microphone closes is the last thing the candidate said,
     * and Azure settles it a moment *after* `stop()` - with punctuation, inverse text
     * normalization and a full rescoring pass that the interim hypothesis has not had. This
     * provider used to set `ended` in `stop()` and discard that result, so the last sentence of
     * every spoken answer was submitted as an unrescored interim. It is delivered now; deciding
     * whether to use it is `useSpeechInput`'s job, and it takes exactly one of the two.
     */
    let stopping = false

    function dispose() {
      if (stopped) return
      stopped = true
      // Release the microphone and the websocket. Without this the capture indicator stays on
      // after the candidate stops.
      try {
        recognizer.close()
      } catch {
        /* already closed */
      }
    }

    /**
     * Announce the end of this session exactly once.
     *
     * Azure routinely fires *both* `canceled` and `sessionStopped` for a single session ending
     * (an error cancels the stream, then the session closes behind it). Reporting each of them
     * as an end told `useSpeechInput` the session had died twice, and it scheduled two
     * restarts - so two recognizers ended up holding the microphone at once and every
     * subsequent utterance was transcribed, and appended to the answer, twice. A session ends
     * once; the SDK's event count is an implementation detail that must not leak upward.
     */
    function reportEnd() {
      if (ended) return
      ended = true
      handlers.onEnd?.()
    }

    recognizer.recognizing = (_sender, event) => {
      // Interim text after `stop()` would only revise a display the candidate is no longer
      // watching, and could regress the fallback text below what was already heard.
      if (ended || stopping) return
      // Interim hypothesis - revised as the candidate keeps speaking. Never appended to the
      // answer; only `recognized` text is committed, which is what stops duplication.
      if (event.result.text) handlers.onPartial(event.result.text)
    }

    recognizer.recognized = (_sender, event) => {
      // `ended` means the session is genuinely over (cancelled, or closed by the service) and
      // the caller has moved on. `stopping` does not: a final settled just after `stop()` is
      // the best transcript of the last thing the candidate said, and is delivered.
      if (ended) return
      if (event.result.reason === ResultReason.RecognizedSpeech && event.result.text) {
        handlers.onFinal(event.result.text)
      }
      // ResultReason.NoMatch is silence or unintelligible audio - not an error, and not text.
    }

    recognizer.canceled = (_sender, event) => {
      const isError = event.reason === CancellationReason.Error
      if (import.meta.env.DEV) {
        speechLog("recognition", "azure canceled", {
          reason: event.reason,
          errorCode: event.errorCode,
          // Logged in development only, and never shown to the candidate.
          errorDetails: event.errorDetails,
        })
      }
      if (isError && !ended) {
        handlers.onError(classifyCancellation(event.errorCode, event.errorDetails))
      }
      dispose()
      reportEnd()
    }

    recognizer.sessionStopped = () => {
      if (import.meta.env.DEV) speechLog("recognition", "azure sessionStopped")
      dispose()
      reportEnd()
    }

    await new Promise<void>((resolve, reject) => {
      recognizer.startContinuousRecognitionAsync(
        () => {
          if (import.meta.env.DEV) speechLog("recognition", "azure recognition started")
          resolve()
        },
        (error: string) => {
          if (import.meta.env.DEV) speechLog("recognition", "azure start failed", error)
          dispose()
          // A failure this early is almost always the microphone or the token; both are fatal.
          const lowered = (error ?? "").toLowerCase()
          reject(lowered.includes("microphone") ? ERRORS.microphone : ERRORS.unavailable)
        },
      )
    })

    return {
      stop() {
        if (stopped) return
        // Deliberately does *not* set `ended`: see `stopping` above. The caller opens a short
        // grace window for the settling final and commits either it or the interim, never both.
        stopping = true
        recognizer.stopContinuousRecognitionAsync(
          () => dispose(),
          () => dispose(),
        )
      },
    }
  },
}

