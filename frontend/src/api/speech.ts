import { apiGet } from "./client"

/** What the backend returns for a speech session. Never contains an Azure key - see
 * `app.services.speech_token`.
 *
 * `host` and `region` are two different ways of naming where to connect, and exactly one is
 * populated. A managed-identity (Entra) token is only accepted at the Speech resource's
 * custom-domain `host`; a key-issued token is regional. Prefer `host` - see `azureSpeech.ts`. */
export interface SpeechTokenResponse {
  token: string
  region?: string | null
  host?: string | null
  language: string
  expires_in_seconds: number
}

/**
 * Ask the backend to mint a short-lived Azure Speech authorization token for this interview.
 *
 * Interview-scoped on purpose: it reuses the candidate access boundary rather than introducing
 * a second auth path, so a candidate can only obtain a token for their own interview.
 */
export function getSpeechToken(
  interviewId: string,
  candidateToken: string,
): Promise<SpeechTokenResponse> {
  return apiGet<SpeechTokenResponse>(
    `/interviews/${encodeURIComponent(interviewId)}/speech-token`,
    { token: candidateToken },
  )
}
