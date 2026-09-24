import { azureSpeechInput } from "./azureSpeech"
import { browserSpeechInput, browserSpeechOutput } from "./browserSpeech"
import type { SpeechInputProvider, SpeechOutputProvider } from "./types"

/**
 * The single wiring point for speech.
 *
 * ```
 * SpeechInputProvider
 * ├── AzureSpeechProvider    <- production
 * └── BrowserSpeechProvider  <- development / offline only
 * ```
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

/** Text-to-speech is unchanged - the browser synthesis path is working well. */
export const speechOutput: SpeechOutputProvider = browserSpeechOutput

export * from "./types"
export { BASELINE_TECHNICAL_PHRASES, buildPhraseList, phraseVariants } from "./phrases"
export { useSpeechInput } from "./useSpeechInput"
export { useSpeechOutput } from "./useSpeechOutput"
