import { useState } from "react"
import { motion } from "motion/react"
import { ChevronDown } from "lucide-react"
import { rise, transition } from "../../design/motion"
import { formatCategory, formatEvidenceStrength } from "../../lib/format"
import { EvidenceMark } from "./EvidenceMark"
import { evidenceKind } from "../../lib/evidence"
import type { CompetencyAssessment } from "../../types"

const METHOD_NOTE = {
  direct: "A question was asked about this directly.",
  cross_target: "Established while the candidate was answering about something else.",
} as const

const METHOD_LABEL = {
  direct: "Asked directly",
  cross_target: "Came up in another answer",
} as const

/**
 * One requirement, and what the interview established about it.
 *
 * A row rather than a card, and closed until asked: a report with fourteen expanded panels is
 * unreadable, while a scannable column of requirements with their evidence state beside them
 * can be read in one pass and opened where it matters.
 *
 * Two things are deliberately kept apart. *How* the evidence was gathered - directly, or picked
 * up while the candidate was talking about something else - is provenance, and it is never
 * styled as a judgement. *What it shows* is the evidence state, and that is what the glyph and
 * the label carry.
 */
export function EvidenceTarget({ assessment }: { assessment: CompetencyAssessment }) {
  const [open, setOpen] = useState(false)
  const kind = evidenceKind(assessment.evidence_type, assessment.evidence_strength)
  const label = assessment.evidence_label || formatEvidenceStrength(assessment.evidence_strength)
  const panelId = `evidence-${assessment.category}-${assessment.name.replace(/\s+/g, "-")}`

  const hasDetail =
    assessment.evidence.length > 0 ||
    assessment.strengths.length > 0 ||
    assessment.weaknesses.length > 0

  return (
    <motion.li variants={rise} className="border-b border-hair last:border-0">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        aria-controls={panelId}
        disabled={!hasDetail}
        className="flex min-h-[52px] w-full items-center gap-3 py-3.5 text-left transition-colors duration-200 hover:bg-fg/[0.05] disabled:cursor-default disabled:hover:bg-transparent"
      >
        <EvidenceMark kind={kind} />

        {/* Flex rather than a grid: below `sm` the grid's auto-placement put the chevron in
            the first cell and right-aligned the requirement name. A row that reads
            mark / name / state left to right at every width is worth more than column
            alignment that only exists on one of them. */}
        <span className="min-w-0 flex-1">
          <span className="block truncate text-[0.9375rem] text-fg">{assessment.name}</span>
          <span className="type-data mt-0.5 block text-fg-soft sm:hidden">{label}</span>
        </span>

        <span className="type-data hidden w-24 shrink-0 text-fg-muted md:block">
          {formatCategory(assessment.category)}
        </span>

        <span className="type-data hidden w-40 shrink-0 text-fg-soft sm:block">{label}</span>

        {hasDetail ? (
          <ChevronDown
            size={15}
            aria-hidden="true"
            className={`shrink-0 text-fg-muted transition-transform duration-200 ${
              open ? "rotate-180" : ""
            }`}
          />
        ) : (
          <span aria-hidden="true" className="w-[15px] shrink-0" />
        )}
      </button>

      {open && hasDetail && (
        <motion.div
          id={panelId}
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: "auto" }}
          transition={transition.state}
          className="overflow-hidden"
        >
          <div className="flex flex-col gap-5 pb-6 pl-6 pr-1 pt-1 sm:pl-7">
            {assessment.evidence.length > 0 && (
              <div>
                <h4 className="type-data font-medium text-fg">What they said</h4>
                <div className="mt-2 flex flex-col gap-2">
                  {assessment.evidence.map((quote, index) => (
                    <blockquote
                      key={index}
                      className="border-l-2 border-accent/30 pl-3.5 text-sm leading-relaxed text-fg-soft"
                    >
                      {quote}
                    </blockquote>
                  ))}
                </div>
              </div>
            )}

            {assessment.strengths.length > 0 && (
              <div>
                <h4 className="type-data font-medium text-fg">What that shows</h4>
                <ul className="mt-2 flex flex-col gap-1.5">
                  {assessment.strengths.map((item, index) => (
                    <li key={index} className="text-sm leading-relaxed text-fg-soft">
                      {item}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {assessment.weaknesses.length > 0 && (
              <div>
                <h4 className="type-data font-medium text-fg">Left open</h4>
                <ul className="mt-2 flex flex-col gap-1.5">
                  {assessment.weaknesses.map((item, index) => (
                    <li key={index} className="text-sm leading-relaxed text-fg-soft">
                      {item}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {assessment.score !== null && (
              <p className="type-data text-fg-muted">
                <span className="text-fg">{METHOD_LABEL[assessment.assessment_method]}.</span>{" "}
                {METHOD_NOTE[assessment.assessment_method]}
              </p>
            )}
          </div>
        </motion.div>
      )}
    </motion.li>
  )
}
