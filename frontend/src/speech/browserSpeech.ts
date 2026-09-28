import { micPermissionState, speechEnvironmentReport, speechLog } from "./debugLog"
import type {
  SpeechInputError,
  SpeechInputHandlers,
  SpeechInputProvider,
  SpeechInputSession,
  SpeechOutputHandlers,
  SpeechOutputProvider,
  SpeechOutputSession,
} from "./types"

/**
 * Browser-native speech providers (the MVP implementations).
 *
 * Kept behind the provider interfaces in ./types so the interview UI never learns that STT
 * happens to be `webkitSpeechRecognition` today. A backend Whisper provider would implement the
 * same two interfaces - record with MediaRecorder, POST the blob, emit `onFinal` - and drop in
 * at the wiring point in ./index.ts.
 */

/* --- Minimal ambient types --------------------------------------------------------------
   The Web Speech API is still not in the standard DOM lib, so the shapes this file actually
   uses are declared here rather than pulling in a dependency for two interfaces. */
interface SpeechRecognitionAlternativeLike {
  transcript: string
}
interface SpeechRecognitionResultLike {
  isFinal: boolean
  0: SpeechRecognitionAlternativeLike
}
interface SpeechRecognitionEventLike {
  resultIndex: number
  results: { length: number; [index: number]: SpeechRecognitionResultLike }
}
interface SpeechRecognitionErrorEventLike {
  error: string
  message?: string
}
interface SpeechRecognitionLike {
  continuous: boolean
  interimResults: boolean
  maxAlternatives: number
  lang: string
  start: () => void
  stop: () => void
  abort: () => void
  onresult: ((event: SpeechRecognitionEventLike) => void) | null
  onerror: ((event: SpeechRecognitionErrorEventLike) => void) | null
  onend: (() => void) | null
  onstart: (() => void) | null
  onaudiostart: (() => void) | null
  onaudioend: (() => void) | null
  onsoundstart: (() => void) | null
  onsoundend: (() => void) | null
  onspeechstart: (() => void) | null
  onspeechend: (() => void) | null
  onnomatch: (() => void) | null
}
type SpeechRecognitionCtor = new () => SpeechRecognitionLike

function getRecognitionCtor(): SpeechRecognitionCtor | null {
  if (typeof window === "undefined") return null
  const w = window as unknown as {
    SpeechRecognition?: SpeechRecognitionCtor
    webkitSpeechRecognition?: SpeechRecognitionCtor
  }
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null
}

/**
 * Classify a Web Speech error code.
 *
 * Only three codes are genuinely unrecoverable: the user (or policy) refused the microphone,
 * or there is no usable capture device. Everything else - a silence timeout, a dropped
 * connection to the speech service, an aborted turn - is routine for this API and is recovered
 * by starting a new session.
 */
export function toInputError(code: string): SpeechInputError {
  switch (code) {
    case "not-allowed":
    case "service-not-allowed":
      return {
        kind: "permission-denied",
        message: "Voice input isn't available right now. You can continue by typing.",
        fatal: true,
      }
    case "audio-capture":
      return {
        kind: "unsupported",
        message: "No microphone was found. You can continue by typing.",
        fatal: true,
      }
    case "no-speech":
      return { kind: "no-speech", message: "Still listening…", fatal: false }
    case "network":
      return { kind: "network", message: "Reconnecting…", fatal: false }
    default:
      return { kind: "unknown", message: "Still listening…", fatal: false }
  }
}

export const browserSpeechInput: SpeechInputProvider = {
  id: "browser-web-speech",

  isSupported() {
    return getRecognitionCtor() !== null
  },

  async start(handlers: SpeechInputHandlers): Promise<SpeechInputSession> {
    const Ctor = getRecognitionCtor()
    if (!Ctor) {
      throw Object.assign(new Error("Speech recognition is unavailable"), {
        kind: "unsupported" as const,
      })
    }

    const recognition = new Ctor()
    recognition.continuous = true
    recognition.interimResults = true
    recognition.maxAlternatives = 1
    // Questions are asked in English, so recognise English rather than whatever the OS locale
    // happens to be - the same reasoning as the TTS voice selection below.
    recognition.lang = "en-US"

    if (import.meta.env.DEV) {
      speechLog("config", "applied", {
        ...speechEnvironmentReport(),
        lang: recognition.lang,
        continuous: recognition.continuous,
        interimResults: recognition.interimResults,
        maxAlternatives: recognition.maxAlternatives,
      })
      void micPermissionState().then((state) => speechLog("config", "micPermission", state))
      recognition.onaudiostart = () => speechLog("recognition", "audiostart")
      recognition.onsoundstart = () => speechLog("recognition", "soundstart")
      recognition.onspeechstart = () => speechLog("recognition", "speechstart")
      recognition.onspeechend = () => speechLog("recognition", "speechend")
      recognition.onsoundend = () => speechLog("recognition", "soundend")
      recognition.onaudioend = () => speechLog("recognition", "audioend")
      recognition.onnomatch = () => speechLog("recognition", "nomatch")
    }

    // `started` gates the start promise: until the session is confirmed live, an error or end
    // must reject it rather than leave the caller hanging until a timeout (the bug that made a
    // denied microphone surface 5s later as a false "browser unsupported").
    let started = false
    let settle: { resolve: () => void; reject: (error: unknown) => void } | null = null

    recognition.onresult = (event) => {
      if (import.meta.env.DEV) {
        speechLog("recognition", "result", {
          resultIndex: event.resultIndex,
          isFinal: event.results[event.resultIndex]?.isFinal,
        })
      }
      // Only walk results from `resultIndex` forward: everything before it was already
      // delivered on a previous event, and re-emitting it would duplicate the answer text.
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        const result = event.results[i]
        const text = result[0]?.transcript ?? ""
        if (!text) continue
        if (result.isFinal) handlers.onFinal(text.trim())
        else handlers.onPartial(text.trim())
      }
    }

    recognition.onerror = (event) => {
      if (import.meta.env.DEV) {
        speechLog("recognition", "error", { error: event.error, message: event.message })
      }
      const inputError = toInputError(event.error)
      if (!started && settle) {
        // Failed before it ever ran: reject now, with the real reason.
        const pending = settle
        settle = null
        pending.reject(inputError)
        return
      }
      handlers.onError(inputError)
    }

    recognition.onend = () => {
      if (import.meta.env.DEV) speechLog("recognition", "end")
      if (!started && settle) {
        const pending = settle
        settle = null
        pending.reject({
          kind: "unknown",
          message: "Voice input isn't available right now. You can continue by typing.",
          fatal: true,
        } satisfies SpeechInputError)
        return
      }
      handlers.onEnd?.()
    }

    await new Promise<void>((resolve, reject) => {
      settle = { resolve, reject }
      const timeout = window.setTimeout(() => {
        if (!settle) return
        settle = null
        reject({
          kind: "unknown",
          message: "Voice input isn't available right now. You can continue by typing.",
          fatal: true,
        } satisfies SpeechInputError)
      }, 5000)

      recognition.onstart = () => {
        if (import.meta.env.DEV) speechLog("recognition", "start")
        started = true
        window.clearTimeout(timeout)
        if (!settle) return
        const pending = settle
        settle = null
        pending.resolve()
      }

      try {
        if (import.meta.env.DEV) speechLog("recognition", "start()")
        recognition.start()
      } catch (error) {
        window.clearTimeout(timeout)
        if (!settle) return
        const pending = settle
        settle = null
        pending.reject(error)
      }
    })

    return {
      stop() {
        if (import.meta.env.DEV) speechLog("recognition", "stop() called by app")
        try {
          recognition.stop()
        } catch {
          recognition.abort()
        }
      },
    }
  },
}

/* --- TTS voice selection ------------------------------------------------------------------
   Interview questions are English. Left to itself the platform picks its *default* voice,
   which on a machine whose OS locale is not English can be a non-English voice reading English
   text (observed: "Microsoft Naayf - Arabic (Saudi)"). Selection is therefore explicit,
   deterministic, and never hard-codes a voice name - it scores whatever the platform offers. */

const SPEECH_LANG = "en-US"

function normalizeLang(lang: string): string {
  return lang.replace("_", "-").toLowerCase()
}

/**
 * Adult voices known to be appropriate for an interviewer, best first.
 *
 * Deliberately short. This is not a browser-detection table and must not grow into one: it is a
 * preference list, and a platform offering none of these still gets a sensible voice from the
 * generic scoring below. The entries are the standard adult female en-* voices across the
 * platforms InterMind actually targets - Microsoft neural (Edge), Apple (macOS/iOS), and Chrome.
 */
const PREFERRED_ADULT_VOICES = [
  "aria",
  "jenny",
  "michelle",
  "emma",
  "ava",
  "samantha",
  "google us english",
  "zira",
] as const

/**
 * Voices that must not read an interview question.
 *
 * `ana` is Microsoft's **children's** voice (`en-US-AnaNeural`), and it is the reason this list
 * exists: Edge exposes a dozen en-US neural voices that all score identically, and "Ana" happens
 * to sort first alphabetically, so a purely alphabetical tie-break handed a professional
 * interview to a cartoon child voice. `junior` is Apple's equivalent.
 */
const AVOIDED_VOICES = ["ana", "junior"] as const

/** Whole-word match, so "Ana" never matches "Ananya" and "ava" never matches "Avatar". */
function mentions(voiceName: string, term: string): boolean {
  const name = voiceName.toLowerCase()
  if (term.includes(" ")) return name.includes(term)
  return new RegExp(`(^|[^a-z])${term}([^a-z]|$)`).test(name)
}

/**
 * Deterministic ranking, in priority order:
 *
 * 1. never a known child voice (see `AVOIDED_VOICES`);
 * 2. a known adult voice, earlier in `PREFERRED_ADULT_VOICES` beating later;
 * 3. exact en-US over other English variants;
 * 4. a network/neural voice over a local one (they sound markedly better);
 * 5. alphabetically, so the same machine always picks the same voice.
 *
 * Steps 1 and 2 are the whole fix. Everything else is the original ranking, which was right
 * about *quality* tiers and wrong only in what it did when they tied - and on a modern neural
 * catalogue, they tie constantly.
 *
 * Preference outranks locale on purpose: an adult en-GB voice is a better interviewer than a
 * child en-US one, and voice suitability is what this function is actually for.
 */
export function pickEnglishVoice(
  voices: SpeechSynthesisVoice[],
): SpeechSynthesisVoice | null {
  const english = voices.filter((voice) => normalizeLang(voice.lang).startsWith("en"))
  if (english.length === 0) return null

  const scored = english.map((voice) => {
    const lang = normalizeLang(voice.lang)
    let score = 0

    // Large enough to lose to anything else that is remotely suitable, but still selectable:
    // a child voice reading the question beats silence if the platform offers nothing else.
    if (AVOIDED_VOICES.some((term) => mentions(voice.name, term))) score -= 1000

    const preference = PREFERRED_ADULT_VOICES.findIndex((term) => mentions(voice.name, term))
    if (preference >= 0) score += 200 - preference

    if (lang === "en-us") score += 100
    else if (lang.startsWith("en-")) score += 50
    // Network voices are the neural ones; local voices are the older SAPI-era engines.
    if (!voice.localService) score += 25
    return { voice, score }
  })

  scored.sort((a, b) => b.score - a.score || a.voice.name.localeCompare(b.voice.name))
  return scored[0].voice
}

/**
 * Chrome populates the voice list asynchronously - the first `getVoices()` call commonly
 * returns []. Resolves as soon as voices exist, or gives up so speech still happens with the
 * platform default rather than never happening at all.
 */
function loadVoices(timeoutMs = 1500): Promise<SpeechSynthesisVoice[]> {
  return new Promise((resolve) => {
    const synth = window.speechSynthesis
    const immediate = synth.getVoices()
    if (immediate.length > 0) {
      resolve(immediate)
      return
    }

    let settled = false
    const finish = () => {
      if (settled) return
      settled = true
      synth.removeEventListener("voiceschanged", finish)
      window.clearTimeout(timer)
      resolve(synth.getVoices())
    }

    const timer = window.setTimeout(finish, timeoutMs)
    synth.addEventListener("voiceschanged", finish)
  })
}

let outputGeneration = 0

export const browserSpeechOutput: SpeechOutputProvider = {
  id: "browser-speech-synthesis",

  isSupported() {
    return typeof window !== "undefined" && "speechSynthesis" in window
  },

  speak(text: string, handlers: SpeechOutputHandlers): SpeechOutputSession {
    this.cancelAll()
    const generation = outputGeneration
    if (!this.isSupported()) {
      handlers.onError?.()
      return { cancel: () => {} }
    }

    let cancelled = false
    let levelTimer = 0
    let envelope = 0

    // SpeechSynthesis exposes no audio amplitude, so the envelope is driven by real progress:
    // each word boundary re-energises it and it decays between words. The bars therefore track
    // actual speech, they are not a free-running animation.
    function pumpLevel() {
      if (cancelled || generation !== outputGeneration) return
      envelope *= 0.82
      handlers.onLevel?.(envelope)
      levelTimer = window.setTimeout(pumpLevel, 60)
    }

    function startWith(voices: SpeechSynthesisVoice[]) {
      if (cancelled || generation !== outputGeneration) return

      const utterance = new SpeechSynthesisUtterance(text)
      utterance.lang = SPEECH_LANG
      utterance.rate = 0.98
      utterance.pitch = 1

      const voice = pickEnglishVoice(voices)
      if (voice) utterance.voice = voice

      if (import.meta.env.DEV) {
        speechLog("tts", "voice selected", {
          selected: voice?.name ?? "(none - platform default)",
          selectedLang: voice?.lang ?? null,
          localService: voice?.localService ?? null,
          utteranceLang: utterance.lang,
          platformDefault: voices.find((v) => v.default)?.name ?? null,
          englishVoicesAvailable: voices.filter((v) => normalizeLang(v.lang).startsWith("en")).length,
          totalVoices: voices.length,
        })
      }

      utterance.onstart = () => {
        if (cancelled || generation !== outputGeneration) return
        handlers.onStart?.()
        pumpLevel()
      }
      utterance.onboundary = () => {
        if (cancelled || generation !== outputGeneration) return
        envelope = Math.min(1, 0.55 + Math.random() * 0.45)
      }
      utterance.onend = () => {
        if (cancelled || generation !== outputGeneration) return
        window.clearTimeout(levelTimer)
        handlers.onLevel?.(0)
        handlers.onEnd?.()
      }
      utterance.onerror = () => {
        if (cancelled || generation !== outputGeneration) return
        window.clearTimeout(levelTimer)
        handlers.onLevel?.(0)
        handlers.onError?.()
      }

      window.speechSynthesis.cancel()
      window.speechSynthesis.speak(utterance)
    }

    // Speak synchronously whenever the voice list is already populated.
    //
    // This is not a micro-optimisation. WebKit only starts speech from a synchronous call chain
    // rooted at a user gesture, and a promise continuation is outside that chain - so routing
    // every call through `loadVoices().then(...)` meant that on iOS the utterance was dropped
    // silently even when a gesture was present. iOS ships its voices with the OS, so this
    // branch is the one it takes. The asynchronous wait remains for Chrome, which genuinely
    // populates `getVoices()` late, and where no gesture is required in the first place.
    const ready = window.speechSynthesis.getVoices()
    if (ready.length > 0) startWith(ready)
    else void loadVoices().then(startWith)

    return {
      cancel() {
        cancelled = true
        window.clearTimeout(levelTimer)
        handlers.onLevel?.(0)
        window.speechSynthesis.cancel()
      },
    }
  },

  cancelAll() {
    outputGeneration += 1
    if (this.isSupported()) window.speechSynthesis.cancel()
  },
}
