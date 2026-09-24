/**
 * TEMPORARY development-only instrumentation for the speech layer.
 *
 * Added to diagnose "microphone opens for ~1s then closes with no transcript". It records every
 * SpeechRecognition lifecycle event with millisecond deltas, plus the config actually applied
 * and the React state transitions around it.
 *
 * Entirely inert in production builds (`import.meta.env.DEV` guard) and safe to delete once the
 * root cause is fixed - nothing outside this file's own callers depends on it.
 *
 * In the browser console:
 *   __intermindSpeech.dump()     table of the event trace
 *   __intermindSpeech.env()      capability / permission / origin report
 *   __intermindSpeech.voices()   available TTS voices and which one is default
 *   __intermindSpeech.clear()
 */

export const SPEECH_DEBUG = import.meta.env.DEV

interface SpeechLogEntry {
  t: number
  /** Wall clock, so restart cycles can be told apart from one another. */
  clock: string
  sinceStart: number
  sincePrev: number
  source: "recognition" | "react" | "config" | "tts" | "ui"
  event: string
  detail?: unknown
}

const entries: SpeechLogEntry[] = []
let sessionStart = 0
let prev = 0

export function speechLog(
  source: SpeechLogEntry["source"],
  event: string,
  detail?: unknown,
): void {
  if (!SPEECH_DEBUG) return
  const now = performance.now()
  if (event === "start()" || sessionStart === 0) {
    sessionStart = now
    prev = now
  }
  const entry: SpeechLogEntry = {
    t: Math.round(now),
    clock: new Date().toISOString().slice(11, 23),
    sinceStart: Math.round(now - sessionStart),
    sincePrev: Math.round(now - prev),
    source,
    event,
    detail,
  }
  prev = now
  entries.push(entry)
  // eslint-disable-next-line no-console
  console.log(
    `%c[speech:${source}] +${entry.sinceStart}ms (Δ${entry.sincePrev}ms) ${event}`,
    "color:#6d4aff",
    detail ?? "",
  )
}

export function speechEnvironmentReport() {
  const w = window as unknown as Record<string, unknown>
  return {
    hasSpeechRecognition: "SpeechRecognition" in window,
    hasWebkitSpeechRecognition: "webkitSpeechRecognition" in window,
    constructorUsed: w.SpeechRecognition
      ? "SpeechRecognition"
      : w.webkitSpeechRecognition
        ? "webkitSpeechRecognition"
        : "none",
    hasSpeechSynthesis: "speechSynthesis" in window,
    isSecureContext: window.isSecureContext,
    origin: window.location.origin,
    protocol: window.location.protocol,
    navigatorLanguage: navigator.language,
    userAgent: navigator.userAgent,
    online: navigator.onLine,
  }
}

/** Microphone permission, when the browser exposes the Permissions API for it. */
export async function micPermissionState(): Promise<string> {
  try {
    const status = await navigator.permissions.query({
      name: "microphone" as PermissionName,
    })
    return status.state
  } catch (error) {
    return `unavailable (${(error as Error).message})`
  }
}

function voicesReport() {
  const voices = window.speechSynthesis?.getVoices() ?? []
  return voices.map((v) => ({
    name: v.name,
    lang: v.lang,
    localService: v.localService,
    default: v.default,
  }))
}

if (SPEECH_DEBUG && typeof window !== "undefined") {
  Object.assign(window, {
    __intermindSpeech: {
      dump: () => {
        // eslint-disable-next-line no-console
        console.table(entries)
        return entries
      },
      /** Copy-pasteable plain-text trace - console.table truncates the detail objects. */
      trace: () => {
        const text = entries
          .map(
            (e) =>
              `${e.clock} +${String(e.sinceStart).padStart(5)}ms [${e.source}] ${e.event}` +
              (e.detail !== undefined ? ` ${JSON.stringify(e.detail)}` : ""),
          )
          .join("\n")
        // eslint-disable-next-line no-console
        console.log(text)
        return text
      },
      /** Summary of whether transcripts ever existed, and where they got to. */
      summary: () => {
        const of = (source: string, event: string) =>
          entries.filter((e) => e.source === source && e.event.startsWith(event))
        const report = {
          recognitionResults: of("recognition", "result").length,
          hookPartials: of("react", "onPartial").length,
          hookFinals: of("react", "onFinal").length,
          uiRenderedTranscript: of("ui", "textarea").filter((e) => Boolean(e.detail)).length,
          errors: of("recognition", "error").map((e) => e.detail),
          restarts: of("react", "end - unexpected").length,
          endedUnavailable: of("react", "end - restart budget").length > 0,
        }
        // eslint-disable-next-line no-console
        console.table(report)
        return report
      },
      entries: () => entries,
      clear: () => {
        entries.length = 0
        sessionStart = 0
        prev = 0
      },
      env: async () => {
        const report = { ...speechEnvironmentReport(), micPermission: await micPermissionState() }
        // eslint-disable-next-line no-console
        console.table(report)
        return report
      },
      voices: () => {
        const list = voicesReport()
        // eslint-disable-next-line no-console
        console.table(list)
        return list
      },
    },
  })
}
