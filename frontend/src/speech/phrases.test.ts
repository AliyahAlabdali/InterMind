import { describe, expect, it } from "vitest"
import { BASELINE_TECHNICAL_PHRASES, MAX_PHRASES, buildPhraseList, phraseVariants } from "./phrases"

/**
 * The phrase list is a bias, not a filter, so what matters is that the terms most likely to be
 * misheard in *this* interview are present and that the list stays small enough to be useful.
 */
describe("phraseVariants", () => {
  it("keeps a plain target name as-is", () => {
    expect(phraseVariants("Computer Vision")).toEqual(["Computer Vision"])
  })

  it("splits a parenthesised abbreviation into both spoken forms", () => {
    // Plans name this target formally; candidates say one form or the other, and biasing only
    // the long form leaves "NLP" to be decoded as ordinary English.
    expect(phraseVariants("Natural Language Processing (NLP)")).toEqual([
      "Natural Language Processing",
      "NLP",
    ])
  })

  it("ignores blank targets", () => {
    expect(phraseVariants("   ")).toEqual([])
  })
})

describe("buildPhraseList", () => {
  it("covers every term the QA reproduction got wrong", () => {
    const phrases = buildPhraseList([
      "Python",
      "Computer Vision",
      "Natural Language Processing (NLP)",
    ])

    // The measured failures: Python -> "poison", PyTorch -> "Pie Charts",
    // "computer vision project" -> "computer which I'm projects".
    for (const required of [
      "Python",
      "PyTorch",
      "Computer Vision",
      "Natural Language Processing",
      "NLP",
      "machine learning",
      "object detection",
      "Transformer",
      "Transformer encoder",
      "FastAPI",
      "OpenCV",
      "ONNX",
    ]) {
      expect(phrases.map((p) => p.toLowerCase())).toContain(required.toLowerCase())
    }
  })

  it("puts this interview's own targets ahead of the generic baseline", () => {
    const phrases = buildPhraseList(["Rust", "Kubernetes"])
    expect(phrases.slice(0, 2)).toEqual(["Rust", "Kubernetes"])
  })

  it("keeps the plan's spelling when a target repeats a baseline term", () => {
    const phrases = buildPhraseList(["Computer Vision"])
    expect(phrases).toContain("Computer Vision")
    expect(phrases).not.toContain("computer vision")
  })

  it("never repeats a phrase, whatever the casing", () => {
    const phrases = buildPhraseList(["python", "PYTHON", "Python"])
    const lowered = phrases.map((phrase) => phrase.toLowerCase())
    expect(new Set(lowered).size).toBe(lowered.length)
  })

  it("stays bounded, because every entry competes with ordinary English", () => {
    const manyTargets = Array.from({ length: 400 }, (_, i) => `Target ${i}`)
    expect(buildPhraseList(manyTargets)).toHaveLength(MAX_PHRASES)
  })

  it("falls back to the baseline when the plan has not loaded yet", () => {
    expect(buildPhraseList([])).toEqual([...BASELINE_TECHNICAL_PHRASES])
  })
})
