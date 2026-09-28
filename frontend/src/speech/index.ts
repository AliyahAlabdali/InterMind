import { azureSpeechInput } from "./azureSpeech"
import { azureSpeechOutput } from "./azureSpeechOutput"
import { browserSpeechInput, browserSpeechOutput } from "./browserSpeech"
import type {
  SpeechInputProvider,
  SpeechOutputContext,
  SpeechOutputHandlers,
  SpeechOutputProvider,
  SpeechOutputSession,
} from "./types"

/**
 * The single wiring point for speech.
 *
 * ```
 * SpeechInputProvider                     SpeechOutputProvider
 * ├── azureSpeechInput   <- production    ├── azureSpeechOutput   <- production
 * └── browserSpeechInput <- dev/offline   └── browserSpeechOutput <- fallback
 * ```
 *
 * The two sides treat their fallback differently, on purpose. Input never silently downgrades:
 * a failing Azure recogniser means the candidate types, because quietly switching to the weaker
 * engine would hide a production misconfiguration. Output does fall back, because the
 * alternative is an interviewer that says nothing at all, and a differently-voiced question is
 * plainly better than a silent one.
 *
 * Azure is the production STT provider: the browser's Web Speech API proved unusable in real
 * Chrome (the microphone opened, no sound was ever detected, and every session timed out with
 * `no-speech`). The browser provider is kept because it needs no Azure subscription, which
 * makes local development and offline work possible - not as a silent fallback. If Azure is
 * selected and fails, the candidate is told voice is unavailable and keeps typing; we never
 * quietly downgrade to the weaker engine, because that would hide a production misconfiguration.
 *
 * Selection is build-time configuration, mirroring the backend's own SPEECH_PROVIDER (the
 * backend is what actually gates token issuance, so the two should agree).
 */
export type SpeechProviderName = "azure" | "browser" | "disabled"

function resolveProviderName(): SpeechProviderName {
  const configured = import.meta.env.VITE_SPEECH_PROVIDER as string | undefined
  if (configured === "azure" || configured === "browser" || configured === "disabled") {
    return configured
  }
  // Default to browser so a checkout with no configuration still runs locally.
  return "browser"
}

export const speechProviderName: SpeechProviderName = resolveProviderName()

/** Voice input is off entirely - the interview stays fully usable by typing. */
const disabledSpeechInput: SpeechInputProvider = {
  id: "disabled",
  isSupported: () => false,
  start: () => Promise.reject(new Error("Voice input is disabled in this deployment")),
}

function selectInputProvider(name: SpeechProviderName): SpeechInputProvider {
  switch (name) {
    case "azure":
      return azureSpeechInput
    case "browser":
      return browserSpeechInput
    case "disabled":
      return disabledSpeechInput
  }
}

export const speechInput: SpeechInputProvider = selectInputProvider(speechProviderName)

/**
 * Question narration: Azure first, browser synthesis as the safety net.
 *
 * The browser path alone could not give the product one interviewer. Each browser reads from its
 * own voice catalogue, and the same code chose a normal adult voice in Chrome, Microsoft's
 * children's voice in Edge, a male voice on iOS, and nothing audible at all on iPhone and iPad.
 * Naming the voice server-side is what makes every candidate hear the same person.
 *
 * The fallback is a real fallback, not a silent downgrade of a misconfiguration: it runs when
 * synthesis or playback actually fails for *this* question, and each question is retried against
 * Azure on its own. That differs deliberately from the input side, where falling back would hide
 * a broken deployment - here the alternative is an interviewer that says nothing, and a
 * differently-voiced question is plainly better than a silent one.
 *
 * Both layers are optional. If both fail the question is still on screen and the interview is
 * completely usable; narration is an enhancement and is never allowed to block anything.
 */
export function withBrowserFallback(primary: SpeechOutputProvider): SpeechOutputProvider {
  const active = new Set<() => void>()
  return {
    id: `${primary.id}+fallback`,

    // Supported if *either* layer can run, so a browser without `speechSynthesis` still gets
    // Azure narration and a browser where Azure cannot run still gets the fallback.
    isSupported: () => primary.isSupported() || browserSpeechOutput.isSupported(),

    speak(
      text: string,
      handlers: SpeechOutputHandlers,
      context?: SpeechOutputContext,
    ): SpeechOutputSession {
      // Nothing to authorize against means Azure cannot be tried at all; go straight to the
      // fallback rather than spending a failed request to discover it.
      if (!primary.isSupported() || !context?.interviewId || !context.accessToken) {
        return browserSpeechOutput.speak(text, handlers, context)
      }

      let fallback: SpeechOutputSession | null = null
      let cancelled = false
      let fellBack = false

      const session = primary.speak(
        text,
        {
          ...handlers,
          onError: () => {
            // One fallback attempt per question. Without this guard a fallback that also fails
            // would re-enter here and loop.
            if (cancelled || fellBack) return
            fellBack = true
            fallback = browserSpeechOutput.speak(text, handlers, context)
          },
        },
        context,
      )

      const cancel = () => {
        cancelled = true
        active.delete(cancel)
        session.cancel()
        fallback?.cancel()
      }
      active.add(cancel)
      return { cancel }
    },

    cancelAll() {
      for (const cancel of [...active]) cancel()
      primary.cancelAll()
      browserSpeechOutput.cancelAll()
    },
  }
}

/**
 * Selected the same way input is: build-time configuration mirroring the backend's own
 * SPEECH_PROVIDER. Only the `azure` deployment has a token endpoint to mint from, so the other
 * modes use browser synthesis directly.
 */
export const speechOutput: SpeechOutputProvider =
  speechProviderName === "azure" ? withBrowserFallback(azureSpeechOutput) : browserSpeechOutput

export * from "./types"
export { BASELINE_TECHNICAL_PHRASES, buildPhraseList, phraseVariants } from "./phrases"
export { useSpeechInput } from "./useSpeechInput"
export { useSpeechOutput } from "./useSpeechOutput"
export { unlockAudioPlayback } from "./audioUnlock"
export { INTERVIEWER_VOICE } from "./azureSpeechOutput"
