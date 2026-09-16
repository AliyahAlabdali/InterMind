import type {
  EvidenceSource,
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

const SOURCE_LABELS: Record<EvidenceSource, string> = {
  jobspec: "Job description",
  onet: "O*NET",
  both: "Job description + O*NET",
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

export function formatSource(value: EvidenceSource): string {
  return SOURCE_LABELS[value] ?? value
}

export function formatRecommendation(value: Recommendation): string {
  return RECOMMENDATION_LABELS[value] ?? value
}

export function formatEvidenceStrength(value: EvidenceStrength): string {
  return EVIDENCE_STRENGTH_LABELS[value] ?? value
}

export function formatPercent(value: number | null, fractionDigits = 0): string {
  if (value === null) return "N/A"
  return `${(value * 100).toFixed(fractionDigits)}%`
}

export function formatDate(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  })
}
