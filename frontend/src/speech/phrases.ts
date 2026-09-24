/**
 * Technical vocabulary biasing for Azure recognition.
 *
 * Why this exists
 * ---------------
 * A general-purpose recogniser decodes with a general-purpose language model, and that model's
 * priors are wrong for an engineering interview. Measured on the real pipeline, "Python" came
 * back as "poison" (a near-minimal pair - the `/aI/`-`/OI/` diphthong and the `/T/`-`/z/`
 * fricative are exactly the cues a 16 kHz microphone conveys worst) and "PyTorch" as "Pie
 * Charts" (identical phonemes, different word boundary; "pie charts" is a far commoner English
 * bigram). Ordinary words in the same sentence - "to train an object detection model" - were
 * transcribed perfectly, which is what tells us the audio was never the problem.
 *
 * Azure's `PhraseListGrammar` is the documented fix: it re-weights the decoder toward terms we
 * know are likely *in this interview*, without retraining anything and without a Custom Speech
 * deployment.
 *
 * Where the terms come from
 * -------------------------
 * The interview plan's coverage targets, which already name exactly what this interview intends
 * to ask about ("Python", "Computer Vision", "Natural Language Processing (NLP)"). That is an
 * existing source of truth and this module does not introduce another one - the candidate screen
 * already fetches the plan to draw its progress rail, so the terms cost no extra request.
 *
 * `BASELINE_TECHNICAL_PHRASES` covers the rest: terms a candidate reaches for while *answering*
 * a question about something else. A Computer Vision target does not mention OpenCV or ONNX, but
 * an answer about it very likely will, and cross-target evidence means those answers are read
 * for other targets too.
 *
 * Bounded on purpose
 * ------------------
 * A phrase list is a bias, not a filter: every entry competes with ordinary English, so a large
 * or off-topic list makes recognition worse rather than better. Interview terms come first and
 * the whole list is capped, so a plan with many targets crowds out the generic baseline rather
 * than the reverse.
 */

/** Azure accepts far more, but a bias this size is already at the edge of useful. */
export const MAX_PHRASES = 100

/**
 * Cross-cutting engineering vocabulary, independent of any one job description.
 *
 * Kept deliberately short and restricted to terms that are (a) plausible in answers across many
 * roles and (b) known to decode badly as ordinary English. Anything role-specific belongs in the
 * plan's coverage targets, not here.
 */
export const BASELINE_TECHNICAL_PHRASES: readonly string[] = [
  // The measured failures from the QA reproduction.
  "Python",
  "PyTorch",
  "computer vision",
  "Natural Language Processing",
  "NLP",
  "object detection",
  // Adjacent terms an answer about any of the above is likely to reach for.
  "machine learning",
  "deep learning",
  "Transformer",
  "Transformer encoder",
  "TensorFlow",
  "OpenCV",
  "ONNX",
  "scikit-learn",
  "NumPy",
  "pandas",
  "Hugging Face",
  "fine-tuning",
  "embeddings",
  "inference",
  // Backend and platform terms, for the same reason.
  "FastAPI",
  "PostgreSQL",
  "Kubernetes",
  "Docker",
  "REST API",
  "CI/CD",
]

/**
 * Split a coverage-target name into the forms a candidate might actually say.
 *
 * Plans name targets formally - "Natural Language Processing (NLP)" - while candidates say one
 * or the other. Both are biased, because biasing only the full form leaves the abbreviation to
 * be decoded as ordinary English, which is where "NLP" becomes "an LP".
 */
export function phraseVariants(target: string): string[] {
  const trimmed = target.trim()
  if (!trimmed) return []

  const open = trimmed.indexOf("(")
  const close = trimmed.indexOf(")", open + 1)
  if (open === -1 || close === -1) return [trimmed]

  const head = trimmed.slice(0, open).trim()
  const abbreviation = trimmed.slice(open + 1, close).trim()
  return [head, abbreviation].filter(Boolean)
}

/**
 * The phrase list for one interview: its own targets first, then the shared baseline.
 *
 * Deduplicated case-insensitively while keeping the first spelling seen, so a plan that says
 * "Computer Vision" is biased with its own capitalisation rather than the baseline's.
 */
export function buildPhraseList(
  targetNames: readonly string[],
  baseline: readonly string[] = BASELINE_TECHNICAL_PHRASES,
): string[] {
  const seen = new Set<string>()
  const phrases: string[] = []

  for (const candidate of [...targetNames.flatMap(phraseVariants), ...baseline]) {
    const phrase = candidate.trim()
    if (!phrase) continue
    const key = phrase.toLowerCase()
    if (seen.has(key)) continue
    seen.add(key)
    phrases.push(phrase)
    if (phrases.length >= MAX_PHRASES) break
  }

  return phrases
}
