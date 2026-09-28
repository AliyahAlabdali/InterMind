/**
 * One-time audio unlock for WebKit, and the single `<audio>` element narration plays through.
 *
 * Why this exists
 * ---------------
 * iOS Safari (and therefore every browser on iOS, which all use WebKit) will only start audio
 * from inside a **synchronous call chain rooted at a user gesture**. A promise continuation, a
 * `setTimeout`, or an effect that runs when data arrives are all outside that chain, and WebKit
 * drops the playback *silently* - no exception, no `error` event, nothing to catch.
 *
 * Question narration is triggered by a React effect when the question text arrives from the
 * network, which is never inside a gesture. So narration could never start on iOS. The fix is
 * not to move narration into a tap - the interview is meant to read questions on its own - but
 * to spend one real gesture, once, priming the two things narration later needs:
 *
 * 1. a single `HTMLAudioElement`, played and immediately paused, which leaves it permanently
 *    allowed to play later without a gesture. Azure narration reuses *this same element*, which
 *    is the whole point: a freshly constructed `new Audio()` would be locked again.
 * 2. `speechSynthesis`, given an empty utterance, which unlocks the browser fallback path.
 *
 * The gesture used is the candidate pressing "Begin the interview", which already exists. No
 * extra screen, no extra button, and nothing audible is ever played to unlock: the priming
 * element is muted and is stopped in the same tick.
 *
 * This does not touch the microphone. Recording is authorised separately by `getUserMedia`,
 * which has its own permission prompt and its own gesture, and is unaffected by any of this.
 */

/** The one element all narration audio plays through, created lazily and then reused forever. */
let sharedElement: HTMLAudioElement | null = null
let unlocked = false

/**
 * A 1-sample silent WAV. Small enough to inline, and a real decodable file, which matters:
 * WebKit will not consider an element unlocked if the source never becomes playable.
 */
const SILENT_WAV =
  "data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAgD4AAAB9AAACABAAZGF0YQAAAAA="

/** The shared narration element, created on first use. */
export function getNarrationAudio(): HTMLAudioElement | null {
  if (typeof window === "undefined" || typeof Audio === "undefined") return null
  if (!sharedElement) {
    sharedElement = new Audio()
    sharedElement.preload = "auto"
    // Lets iOS play narration with the phone's ringer switch silenced, and keeps the page from
    // being treated as a background media session.
    sharedElement.setAttribute("playsinline", "")
  }
  return sharedElement
}

/** Whether {@link unlockAudioPlayback} has already run successfully. */
export function isAudioUnlocked(): boolean {
  return unlocked
}

/**
 * Prime audio output. **Must be called synchronously from inside a user-gesture handler** -
 * awaiting anything first defeats the entire purpose.
 *
 * Safe to call more than once; only the first call does work. Never throws: on a browser that
 * needs no unlocking this is a no-op, and on one that refuses, narration simply falls back to
 * text, which the interview is fully usable with.
 */
export function unlockAudioPlayback(): void {
  if (unlocked || typeof window === "undefined") return
  unlocked = true

  const element = getNarrationAudio()
  if (element) {
    try {
      element.muted = true
      element.src = SILENT_WAV
      // `play()` returns a promise, but the *call* is what must be inside the gesture, not its
      // resolution. Rejections are expected and ignored: a browser that refuses here would have
      // refused narration anyway, and the fallback path covers it.
      void element.play().then(
        () => {
          element.pause()
          element.currentTime = 0
          element.muted = false
        },
        () => {
          element.muted = false
        },
      )
    } catch {
      element.muted = false
    }
  }

  // Unlock the browser-synthesis fallback too. An empty utterance produces no sound and no
  // `start` event, but it is enough to satisfy WebKit's first-speak gesture requirement.
  try {
    if ("speechSynthesis" in window) {
      window.speechSynthesis.speak(new SpeechSynthesisUtterance(""))
    }
  } catch {
    // A browser without synthesis is fine; narration falls back to text.
  }
}

/** Test seam. Resets the module's one-time state so each test starts from a locked browser. */
export function resetAudioUnlockForTests(): void {
  sharedElement = null
  unlocked = false
}
