import { useState } from "react"
import { motion } from "motion/react"
import { ChevronDown } from "lucide-react"
import { transition } from "../../design/motion"
import { formatCategory } from "../../lib/format"
import { EvidenceMark } from "./EvidenceMark"
import { evidenceKind } from "../../lib/evidence"
import type { QuestionEvaluationSummary } from "../../types"

const DECISION_NOTE = {
  advance: "Moved on after this.",
  follow_up: "Went deeper on this.",
} as const

/**
 * The interview record: what was asked, what was said, in order.
 *
 * Everything above it in the report is a reading of this, so it stays available in full while
 * staying out of the way - hairline-ruled disclosure rows rather than a stack of bordered
 * cards, which is what made the old version read as the page's main content instead of its
 * appendix.
 *
 * Not every row is a question. A target established from an answer to a *different* question
 * appears here too, because it is part of the record and its evidence has to be readable - but
 * it was never asked, so it takes no position in the numbering and its panel says where the
 * words came from. Numbering it and heading it "InterMind asked" (which is what this used to
 * do) described the interview as having asked something it never asked.
 */
export function QuestionEvaluationList({ items }: { items: QuestionEvaluationSummary[] }) {
  const [openId, setOpenId] = useState<string | null>(null)
  if (items.length === 0) return null

  // Positions count asked questions only, so the numbers here match the count above the list
  // and stay stable whether or not cross-target evidence turned up between them.
  const askedPosition = (index: number) =>
    items.slice(0, index + 1).filter((item) => item.assessment_method !== "cross_target").length

  return (
    <ol className="border-t border-hair">
      {items.map((item, index) => {
        const open = openId === item.question_id
        const panelId = `turn-${item.question_id}`
        const crossTarget = item.assessment_method === "cross_target"
        const position = crossTarget ? null : askedPosition(index)
        return (
          <li key={item.question_id} className="border-b border-hair">
            <button
              type="button"
              onClick={() => setOpenId(open ? null : item.question_id)}
              aria-expanded={open}
              aria-controls={panelId}
              className="flex min-h-[52px] w-full items-center gap-3 py-3.5 text-left transition-colors duration-200 hover:bg-fg/[0.05]"
            >
              <span className="type-data type-numeric w-5 shrink-0 text-fg-muted">
                {position ?? (
                  <span aria-label="Not asked directly" title="Not asked directly">
                    &middot;
                  </span>
                )}
              </span>
              <span className="min-w-0 flex-1 truncate text-[0.9375rem] text-fg">
                {item.target}
              </span>
              <span className="type-data hidden shrink-0 text-fg-muted sm:block">
                {formatCategory(item.category)}
              </span>
              <EvidenceMark kind={evidenceKind(item.evidence_type, item.evidence_strength)} />
              <ChevronDown
                size={15}
                aria-hidden="true"
                className={`shrink-0 text-fg-muted transition-transform duration-200 ${open ? "rotate-180" : ""}`}
              />
            </button>

            {open && (
              <motion.div
                id={panelId}
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: "auto" }}
                transition={transition.state}
                className="overflow-hidden"
              >
                <div className="flex flex-col gap-4 pb-6 pl-9 pr-1 pt-1">
                  {crossTarget ? (
                    // No question to show: the backend's placeholder text for these rows said
                    // the same thing this heading now says, so printing both was the
                    // contradiction - a row headed "InterMind asked" whose body read "not
                    // asked directly".
                    <div>
                      <h4 className="type-data font-medium text-fg-muted">Not asked directly</h4>
                      <p className="mt-1.5 text-[0.9375rem] leading-relaxed text-fg">
                        InterMind established this from what the candidate said while answering
                        a different question.
                      </p>
                    </div>
                  ) : (
                    <div>
                      <h4 className="type-data font-medium text-fg-muted">InterMind asked</h4>
                      <p className="mt-1.5 text-[0.9375rem] leading-relaxed text-fg">
                        {item.question}
                      </p>
                    </div>
                  )}

                  <div>
                    <h4 className="type-data font-medium text-fg-muted">
                      {crossTarget ? "What they said" : "They answered"}
                    </h4>
                    <p className="mt-1.5 whitespace-pre-wrap text-[0.9375rem] leading-relaxed text-fg-soft">
                      {item.candidate_answer}
                    </p>
                  </div>

                  <p className="type-data text-fg-muted">
                    {item.evidence_label}
                    {item.decision && ` · ${DECISION_NOTE[item.decision]}`}
                  </p>
                </div>
              </motion.div>
            )}
          </li>
        )
      })}
    </ol>
  )
}
