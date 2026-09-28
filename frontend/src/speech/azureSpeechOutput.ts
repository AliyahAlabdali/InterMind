import { getSpeechToken, type SpeechTokenResponse } from "../api/speech"
import { getNarrationAudio } from "./audioUnlock"
import { speechLog } from "./debugLog"
import type {
  SpeechOutputContext,
  SpeechOutputHandlers,
  SpeechOutputProvider,
  SpeechOutputSession,
} from "./types"

/**
 * Azure AI Speech synthesis - the production voice for reading interview questions aloud.
 *
 * Why not the browser
 * -------------------
 * `speechSynthesis` reads from whatever voice catalogue the browser happens to ship, and those
 * catalogues disagree badly. The same code picked a normal adult voice in Chrome, Microsoft's
 * **children's** voice in Edge (its neural catalogue's alphabetically first entry), a male voice
 * on iOS, and produced no audio at all on iPhone and iPad. A product whose premise is an
 * autonomous interviewer cannot have its interviewer's voice decided by the user's browser.
 *
 * Naming the voice server-side removes the whole class of problem: every candidate hears the
 * same person. The browser path is kept as a fallback (see `./browserSpeech`), hardened so that
 * when it does run it still picks an adult voice.
 *
 * Credentials
 * -----------
 * Identical to the input provider and deliberately so: the browser never sees an Azure key. It
 * receives a short-lived authorization token minted by our own backend at
 * `GET /interviews/{id}/speech-token`, which is candidate-authorized and interview-scoped. In
 * production no key exists at all - the backend authenticates with its managed identity.
 *
 * Nothing here logs the token, the authorization header, or the candidate's access token.
 */

/**
 * The interviewer's voice. Pinned on purpose: this is the one decision that makes the product
 * sound the same everywhere, so it is a constant rather than anything discovered at runtime.
 * Aria is Microsoft's professional adult female en-US neural voice.
 */
export const INTERVIEWER_VOICE = "en-US-AriaNeural"

/**
 * MP3 rather than PCM/WAV. Every target decodes it, including iOS, and a question is a few
 * seconds of speech, so the smaller payload reaches the candidate sooner.
 */
const OUTPUT_FORMAT_MP3 = 6 // SpeechSynthesisOutputFormat.Audio24Khz48KBitRateMonoMp3

/**
 * How early to treat a cached token as expired. Azure issues ~10-minute tokens; the backend
 * reports the usable life it wants us to assume. Retiring one a minute early means a long
 * question never starts synthesising against a token that dies mid-request.
 */
const TOKEN_SAFETY_MARGIN_SECONDS = 60

interface CachedToken {
  credentials: SpeechTokenResponse
  /** `Date.now()` after which this token must not be used again. */
  expiresAt: number
  interviewId: string
}

/**
 * In-memory only, for the lifetime of the page.
 *
 * Deliberately not `localStorage`/`sessionStorage`: this is a credential, and persisting it
 * would outlive the interview and survive in a place other scripts on the origin can read.
 */
let cached: CachedToken | null = null

/** Test seam, and what a failed request uses to make sure a bad token is never reused. */
export function clearSpeechTokenCache(): void {
  cached = null
}

async function credentialsFor(context: SpeechOutputContext): Promise<SpeechTokenResponse> {
  const { interviewId, accessToken } = context
  if (!interviewId || !accessToken) {
    throw new Error("speech output requires an interview id and access token")
  }

  if (cached && cached.interviewId === interviewId && Date.now() < cached.expiresAt) {
    return cached.credentials
  }

  const credentials = await getSpeechToken(interviewId, accessToken)
  const lifetime = Math.max(0, credentials.expires_in_seconds - TOKEN_SAFETY_MARGIN_SECONDS)
  cached = {
    credentials,
    expiresAt: Date.now() + lifetime * 1000,
    interviewId,
  }
  return credentials
}

/**
 * Build a `SpeechConfig` from whichever credential shape the backend returned.
 *
 * The two are not interchangeable, for the same reason they are not on the input side: an Entra
 * (managed-identity) token is only accepted at the Speech resource's own custom-domain host,
 * while a key-issued token is regional. `host` therefore wins when present.
 *
 * `fromHost` rather than the input provider's `fromEndpoint`: synthesis has no equivalent of the
 * recognition endpoint-version problem that forced `fromEndpoint` there, and `fromHost` lets the
 * SDK derive the right synthesis path for a custom domain itself.
 */
async function buildConfig(credentials: SpeechTokenResponse) {
  const { SpeechConfig } = await import("microsoft-cognitiveservices-speech-sdk")

  let config
  if (credentials.host) {
    config = SpeechConfig.fromHost(new URL(`https://${credentials.host}`))
    config.authorizationToken = credentials.token
  } else if (credentials.region) {
    config = SpeechConfig.fromAuthorizationToken(credentials.token, credentials.region)
  } else {
    throw new Error("speech token response named neither host nor region")
  }

  config.speechSynthesisVoiceName = INTERVIEWER_VOICE
  config.speechSynthesisOutputFormat = OUTPUT_FORMAT_MP3
  return config
}

/** Synthesize `text` to MP3 bytes. Never plays anything itself - see `speak`. */
async function synthesize(
  text: string, context: SpeechOutputContext, signal: AbortSignal,
): Promise<ArrayBuffer> {
  const credentials = await credentialsFor(context)
  signal.throwIfAborted()
  const config = await buildConfig(credentials)
  const { ResultReason, SpeechSynthesizer } = await import(
    "microsoft-cognitiveservices-speech-sdk"
  )

  // `null` audio config means "do not open a speaker": the SDK hands back the bytes instead.
  // That is what lets playback go through the element unlocked by the candidate's own tap,
  // which is the only way narration can start on iOS.
  signal.throwIfAborted()
  const synthesizer = new SpeechSynthesizer(config, null)
  let abort: (() => void) | undefined

  try {
    return await new Promise<ArrayBuffer>((resolve, reject) => {
      abort = () => reject(new Error("Synthesis retired"))
      signal.addEventListener("abort", abort, { once: true })
      synthesizer.speakTextAsync(
        text,
        (result) => {
          if (result.reason === ResultReason.SynthesizingAudioCompleted && result.audioData) {
            resolve(result.audioData)
          } else {
            // `errorDetails` can name the endpoint; it is not surfaced to the candidate and not
            // logged with the token, and the caller turns any rejection into the fallback.
            reject(new Error(result.errorDetails || "speech synthesis did not complete"))
          }
        },
        (error) => reject(new Error(String(error))),
      )
    })
  } finally {
    if (abort) signal.removeEventListener("abort", abort)
    synthesizer.close()
  }
}

const activeCancellations = new Set<() => void>()

export const azureSpeechOutput: SpeechOutputProvider = {
  id: "azure-speech-synthesis",

  isSupported() {
    return typeof window !== "undefined" && typeof Audio !== "undefined"
  },

  speak(
    text: string,
    handlers: SpeechOutputHandlers,
    context?: SpeechOutputContext,
  ): SpeechOutputSession {
    this.cancelAll()
    const element = getNarrationAudio()
    if (!element || !context?.interviewId || !context.accessToken) {
      handlers.onError?.()
      return { cancel: () => {} }
    }

    let cancelled = false
    const controller = new AbortController()
    let objectUrl: string | null = null
    let levelTimer = 0

    const releaseUrl = () => {
      if (objectUrl) {
        URL.revokeObjectURL(objectUrl)
        objectUrl = null
      }
    }

    const stopLevel = () => {
      if (levelTimer) {
        window.clearInterval(levelTimer)
        levelTimer = 0
      }
      handlers.onLevel?.(0)
    }

    const cancel = () => {
      if (cancelled) return
      cancelled = true
      activeCancellations.delete(cancel)
      controller.abort()
      stopLevel()
      element.onended = null
      element.onerror = null
      try {
        element.pause()
        element.currentTime = 0
      } catch {
        // An element that never got a source cannot be paused; nothing to clean up.
      }
      releaseUrl()
    }

    const finish = (ok: boolean) => {
      if (cancelled) return
      activeCancellations.delete(cancel)
      stopLevel()
      releaseUrl()
      if (ok) handlers.onEnd?.()
      else handlers.onError?.()
    }

    void (async () => {
      let audio: ArrayBuffer
      try {
        audio = await synthesize(text, context, controller.signal)
      } catch (error) {
        if (cancelled) return
        activeCancellations.delete(cancel)
        // A rejected token must never be reused, or every later question fails the same way.
        clearSpeechTokenCache()
        speechLog("tts", "azure synthesis failed", (error as Error)?.message)
        if (!cancelled) handlers.onError?.()
        return
      }
      if (cancelled) return

      objectUrl = URL.createObjectURL(new Blob([audio], { type: "audio/mpeg" }))
      element.onended = () => finish(true)
      element.onerror = () => finish(false)
      element.src = objectUrl

      try {
        await element.play()
      } catch {
        // Playback refused, almost always because the unlock never happened. The caller falls
        // back to browser synthesis, and the question text is on screen regardless.
        if (!cancelled) finish(false)
        return
      }
      if (cancelled) return

      handlers.onStart?.()
      // Azure returns finished audio rather than a stream, so there are no word-boundary events
      // to drive the envelope from. Playback progress is the honest signal available: the bars
      // move only while audio is actually playing, and stop the moment it does.
      levelTimer = window.setInterval(() => {
        if (element.paused || element.ended) return
        handlers.onLevel?.(0.45 + Math.random() * 0.35)
      }, 90)
    })()

    activeCancellations.add(cancel)
    return { cancel }
  },

  cancelAll() {
    for (const cancel of [...activeCancellations]) cancel()
    const element = getNarrationAudio()
    if (!element) return
    element.onended = null
    element.onerror = null
    try {
      element.pause()
      element.currentTime = 0
    } catch {
      // Same as above.
    }
  },
}
