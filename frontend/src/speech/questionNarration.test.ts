/**
 * Regression tests for the cross-browser question-narration failures found in production.
 *
 * Three distinct symptoms, all from one architecture that let each browser choose the
 * interviewer's voice from its own catalogue:
 *
 * 1. Windows Edge read questions in Microsoft's **children's** voice (`Ana`), because Edge's
 *    neural catalogue is a dozen voices that all scored identically and "Ana" sorts first.
 * 2. iPhone and iPad produced **no audio at all**: narration is triggered by a React effect when
 *    the question arrives, which is outside any user gesture, and WebKit drops such speech
 *    silently.
 * 3. iOS would also have chosen a **male** voice (`Aaron`) for the same alphabetical reason,
 *    even once it could be heard.
 *
 * These tests assert the externally meaningful outcome - which voice a real platform catalogue
 * yields, and that narration survives failure - rather than the shape of the scoring function.
 */

import { beforeEach, describe, expect, it, vi } from "vitest"
import { browserSpeechOutput, pickEnglishVoice } from "./browserSpeech"
import { INTERVIEWER_VOICE } from "./azureSpeechOutput"
import { installFakeSynthesis, makeVoice } from "./testDoubles"

/** Windows Edge: Microsoft's cloud "Online (Natural)" catalogue plus the legacy local voices. */
const EDGE_WINDOWS = [
  makeVoice("Microsoft David - English (United States)", "en-US", { localService: true }),
  makeVoice("Microsoft Zira - English (United States)", "en-US", { localService: true }),
  makeVoice("Microsoft Mark - English (United States)", "en-US", { localService: true }),
  ...[
    "Ana",
    "Andrew",
    "Aria",
    "Ava",
    "Brian",
    "Christopher",
    "Emma",
    "Eric",
    "Guy",
    "Jenny",
    "Michelle",
    "Roger",
    "Steffan",
  ].map((given) =>
    makeVoice(`Microsoft ${given} Online (Natural) - English (United States)`, "en-US", {
      localService: false,
    }),
  ),
]

/** Windows Chrome: no Online (Natural) catalogue at all. */
const CHROME_WINDOWS = [
  makeVoice("Microsoft David - English (United States)", "en-US", { localService: true }),
  makeVoice("Microsoft Zira - English (United States)", "en-US", { localService: true }),
  makeVoice("Google US English", "en-US", { localService: false }),
  makeVoice("Google UK English Female", "en-GB", { localService: false }),
  makeVoice("Google UK English Male", "en-GB", { localService: false }),
]

/** iPhone / iPad: everything is local, so the network tier never breaks a tie. */
const IOS_SAFARI = [
  makeVoice("Aaron", "en-US", { localService: true }),
  makeVoice("Fred", "en-US", { localService: true }),
  makeVoice("Nicky", "en-US", { localService: true }),
  makeVoice("Samantha", "en-US", { localService: true, default: true }),
  makeVoice("Karen", "en-AU", { localService: true }),
  makeVoice("Daniel", "en-GB", { localService: true }),
]

describe("fallback voice selection on real platform catalogues", () => {
  it("never reads an interview question in Microsoft's children's voice on Edge", () => {
    const picked = pickEnglishVoice([...EDGE_WINDOWS])

    expect(picked?.name).not.toContain("Ana Online")
    expect(picked?.name).toBe("Microsoft Aria Online (Natural) - English (United States)")
  })

  it("still avoids the child voice however the platform orders its catalogue", () => {
    const reversed = pickEnglishVoice([...EDGE_WINDOWS].reverse())
    const shuffled = pickEnglishVoice([EDGE_WINDOWS[3], ...EDGE_WINDOWS.slice(4), ...EDGE_WINDOWS.slice(0, 3)])

    expect(reversed?.name).not.toContain("Ana Online")
    expect(shuffled?.name).not.toContain("Ana Online")
    expect(reversed?.name).toBe(shuffled?.name)
  })

  it("picks an adult female voice on iOS rather than the alphabetically first one", () => {
    const picked = pickEnglishVoice([...IOS_SAFARI])

    expect(picked?.name).not.toBe("Aaron")
    expect(picked?.name).toBe("Samantha")
  })

  it("keeps choosing a normal adult voice on Chrome", () => {
    expect(pickEnglishVoice([...CHROME_WINDOWS])?.name).toBe("Google US English")
  })

  it("selects a child voice only when the platform offers nothing else in English", () => {
    const onlyChild = [
      makeVoice("Microsoft Ana Online (Natural) - English (United States)", "en-US", {
        localService: false,
      }),
    ]
    // Better than silence: the question is still read, just not by the voice we would choose.
    expect(pickEnglishVoice(onlyChild)?.name).toContain("Ana")
  })
})

describe("fallback speaks without waiting on a promise when voices are ready", () => {
  beforeEach(() => {
    vi.spyOn(console, "log").mockImplementation(() => {})
  })

  it("queues the utterance synchronously, which is what WebKit requires", () => {
    const synth = installFakeSynthesis(IOS_SAFARI)

    browserSpeechOutput.speak("Tell me about a system you designed.", {})

    // No `await`, no tick: if this were still routed through a promise continuation the
    // utterance would be queued too late for iOS to allow it, which is why narration was silent.
    expect(synth.spoken).toHaveLength(1)
    expect(synth.spoken[0].voice?.name).toBe("Samantha")
  })
})

describe("the pinned Azure interviewer voice", () => {
  it("is a professional adult female neural voice, named explicitly", () => {
    // Pinned rather than discovered: this constant is the reason every candidate hears the same
    // interviewer regardless of browser or device.
    expect(INTERVIEWER_VOICE).toBe("en-US-AriaNeural")
  })
})
