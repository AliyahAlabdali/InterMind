import type { AnswerEvidenceType, EvidenceStrength } from "../types"

/**
 * What kind of evidence an assessment holds.
 *
 * The report has to keep four things visibly apart: something the candidate *demonstrated*,
 * something they only *claimed*, something they said they *lack*, and something the interview
 * never established either way. The last one especially - an unassessed requirement must never
 * look like a failed one.
 *
 * Derived from the backend's own `evidence_type`, falling back to the score-derived strength
 * band only when no type was recorded. Nothing here invents a state the API does not report.
 */
export type EvidenceKind =
  | "demonstrated"
  | "partial"
  | "claimed"
  | "lack"
  | "contradictory"
  | "none"

export function evidenceKind(
  evidenceType: AnswerEvidenceType | null,
  strength: EvidenceStrength,
): EvidenceKind {
  if (strength === "not_assessed") return "none"
  switch (evidenceType) {
    case "demonstrated":
      return "demonstrated"
    case "partial":
      return "partial"
    case "claimed_unverified":
      return "claimed"
    case "explicit_lack":
      return "lack"
    case "contradictory":
      return "contradictory"
    case "insufficient":
      return "none"
    default:
      return strength === "strong" ? "demonstrated" : strength === "moderate" ? "partial" : "none"
  }
}
