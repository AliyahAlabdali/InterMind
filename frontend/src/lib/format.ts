import type {
  EvidenceStrength,
  QuestionCategory,
  Recommendation,
  Seniority,
} from "../types"

const SENIORITY_LABELS: Record<Seniority, string> = {
  intern: "Intern",
  junior: "Junior",
  mid: "Mid-level",
  senior: "Senior",
  lead: "Lead",
  principal: "Principal",
  unknown: "Unspecified",
}

const CATEGORY_LABELS: Record<QuestionCategory, string> = {
  competency: "Competency",
  technology: "Technology",
  task: "Task",
}

/**
 * What the interview evidence came to, not a hiring decision. The stored enum keeps its original
 * names (`strong_hire` and friends are the persisted, deterministic bands of `overall_score` -
 * see `derive_recommendation`), and only the words a recruiter reads change: InterMind assesses
 * evidence for a person to act on, and a label that reads as a verdict contradicts the notice
 * every candidate is shown before they start.
 */
const RECOMMENDATION_LABELS: Record<Recommendation, string> = {
  strong_hire: "Strong evidence",
  hire: "Good evidence",
  consider: "Mixed evidence",
  no_hire: "Limited evidence",
}

const EVIDENCE_STRENGTH_LABELS: Record<EvidenceStrength, string> = {
  strong: "Strong evidence",
  moderate: "Moderate evidence",
  limited: "Limited evidence",
  insufficient: "Insufficient evidence",
  not_assessed: "Not assessed",
}

export function formatSeniority(value: Seniority): string {
  return SENIORITY_LABELS[value] ?? value
}

export function formatCategory(value: QuestionCategory): string {
  return CATEGORY_LABELS[value] ?? value
}

export function formatRecommendation(value: Recommendation): string {
  return RECOMMENDATION_LABELS[value] ?? value
}

export function formatEvidenceStrength(value: EvidenceStrength): string {
  return EVIDENCE_STRENGTH_LABELS[value] ?? value
}
