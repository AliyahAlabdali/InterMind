/**
 * Speech provider contracts.
 *
 * The UI talks to these interfaces only - never to `webkitSpeechRecognition` or
 * `speechSynthesis` directly. That boundary is the whole point: browser STT is the MVP, and
 * replacing it with backend Whisper later should mean writing one new provider and changing one
 * line of wiring, not touching the interview screen.
 */

export type SpeechInputErrorKind =
  | "unsupported"
  | "permission-denied"
  | "no-speech"
  | "network"
  | "unknown"

export interface SpeechInputError {
  kind: SpeechInputErrorKind
  /** Candidate-facing wording. Never a raw browser error code - see the interview UI. */
  message: string
  /**
   * Whether the session can be recovered by starting again.
   *
   * Non-fatal covers the things browser STT does routinely and recoverably: a silence timeout,
   * a dropped connection, an aborted turn. Fatal means retrying is pointless and would spin -
   * permission refused, or no usable capture device. Providers classify their own errors, so
   * the resilience policy in `useSpeechInput` stays provider-agnostic.
   */
  fatal: boolean
}

export interface SpeechInputHandlers {
  /** Interim text, may be revised. Shown to the candidate as they speak. */
  onPartial: (text: string) => void
  /** Settled text for an utterance. Appended to the answer. */
  onFinal: (text: string) => void
  onError: (error: SpeechInputError) => void
  /** Optional live mic amplitude 0..1, when the provider can measure it. */
  onLevel?: (level: number) => void
  /** The provider stopped on its own (silence timeout, end of stream). */
  onEnd?: () => void
}

export interface SpeechInputSession {
  stop: () => void
}

/**
 * What a provider needs to know about *this* interview in order to authenticate.
 *
 * The browser provider ignores it entirely; the Azure provider uses it to ask our backend for a
 * short-lived Speech token scoped to this interview. Optional so the interface stays
 * backwards-compatible with providers that need no credential at all.
 */
export interface SpeechInputContext {
  interviewId?: string
  /** The candidate's own interview access token, used to authorize the token request. */
  accessToken?: string
  /**
   * Technical terms to bias recognition toward, built from this interview's coverage targets
   * (see `./phrases`). Providers that cannot bias their decoder ignore it - Chrome's Web Speech
   * API has no working equivalent, which is part of why it is not the production provider.
   */
  phrases?: readonly string[]
}

export interface SpeechInputProvider {
  /** Stable id, for logging and for telling providers apart in devtools. */
  readonly id: string
  /** Whether this provider can run in the current browser/session. */
  isSupported: () => boolean
  /**
   * Begin capturing. Implementations must resolve only once capture has actually started, so
   * the UI's "recording" state never lies.
   */
  start: (
    handlers: SpeechInputHandlers,
    context?: SpeechInputContext,
  ) => Promise<SpeechInputSession>
}

export interface SpeechOutputHandlers {
  onStart?: () => void
  onEnd?: () => void
  onError?: () => void
  /**
   * Speech envelope 0..1. Browser synthesis exposes no true amplitude, so a provider may
   * derive this from real progress events (word boundaries) - it is always tied to actual
   * speech, never a free-running animation.
   */
  onLevel?: (level: number) => void
}

export interface SpeechOutputSession {
  cancel: () => void
}

export interface SpeechOutputProvider {
  readonly id: string
  isSupported: () => boolean
  speak: (text: string, handlers: SpeechOutputHandlers) => SpeechOutputSession
  cancelAll: () => void
}
