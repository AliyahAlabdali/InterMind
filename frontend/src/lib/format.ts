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

const RECOMMENDATION_LABELS: Record<Recommendation, string> = {
  strong_hire: "Strong Hire",
  hire: "Hire",
  consider: "Consider",
  no_hire: "No Hire",
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
