import { useState } from "react"
import { motion } from "motion/react"
import { ChevronDown } from "lucide-react"
import { transition } from "../../design/motion"
import { formatCategory, formatSource } from "../../lib/format"
import type { CoverageTarget } from "../../types"

interface CoverageMapProps {
  targets: CoverageTarget[]
  /** Targets the interview has actually moved past. Omit before an interview has run. */
  assessedIds?: Set<string>
  /** The target being explored right now. */
  activeId?: string | null
}

type TargetState = "assessed" | "active" | "pending"

const STATE_LABEL: Record<TargetState, string> = {
  assessed: "Explored",
  active: "Exploring",
  pending: "Not yet",
}

function stateOf(
  target: CoverageTarget,
  assessedIds: Set<string> | undefined,
  activeId: string | null | undefined,
): TargetState {
  if (activeId === target.id) return "active"
  if (assessedIds?.has(target.id)) return "assessed"
  return "pending"
}

/**
 * The requirement map: what this interview is prepared to probe, and - once it is running -
 * what it has actually reached.
 *
 * Three decisions carry the design. Required and preferred are the top-level split, because
 * that is the distinction a recruiter acts on: a required gap matters, a preferred one usually
 * does not. Each requirement can be opened to show *why* InterMind thinks the job calls for it,
 * which is real plan data (`grounding`, `source`) rather than a decorative expander. And a
 * requirement the interview has not reached is drawn as absent, never as failed - an unexplored
 * area is a fact about the interview's length, not about the candidate.
 */
export function CoverageMap({ targets, assessedIds, activeId }: CoverageMapProps) {
  if (targets.length === 0) return null

  const required = targets.filter((t) => t.requirement_level === "required")
  const preferred = targets.filter((t) => t.requirement_level !== "required")
  const groups = [
    { label: "Required", hint: "The job asks for these.", items: required },
    { label: "Preferred", hint: "Good to have, not essential.", items: preferred },
  ].filter((group) => group.items.length > 0)

  const live = Boolean(assessedIds)
  const explored = assessedIds ? targets.filter((t) => assessedIds.has(t.id)).length : 0

  return (
    <div className="flex flex-col gap-10">
      {live && (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <span className="flex h-[5px] min-w-[10rem] flex-1 items-stretch gap-[3px]" aria-hidden="true">
            {targets.map((target) => {
              const state = stateOf(target, assessedIds, activeId)
              return (
                <span
                  key={target.id}
                  className={`min-w-[4px] flex-1 rounded-full ${
                    state === "assessed"
                      ? "bg-accent"
                      : state === "active"
                        ? "bg-accent/45"
                        : "bg-fg/10"
                  }`}
                />
              )
            })}
          </span>
          <p className="type-data shrink-0 text-fg-muted">
            {explored} of {targets.length} areas explored
          </p>
        </div>
      )}

      {groups.map((group) => (
        <section key={group.label}>
          <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1 border-b border-fg/15 pb-2">
            <h3 className="type-data font-medium text-fg">{group.label}</h3>
            <p className="type-data text-fg-muted">{group.hint}</p>
          </div>
          <ul>
            {group.items.map((target) => (
              <TargetRow
                key={target.id}
                target={target}
                state={stateOf(target, assessedIds, activeId)}
                showState={live}
              />
            ))}
          </ul>
        </section>
      ))}
    </div>
  )
}

function TargetRow({
  target,
  state,
  showState,
}: {
  target: CoverageTarget
  state: TargetState
  showState: boolean
}) {
  const [open, setOpen] = useState(false)
  const hasDetail = Boolean(target.grounding)
  const panelId = `coverage-${target.id}`

  const body = (
    <div className="flex w-full items-center gap-3 text-left">
      <Marker state={state} showState={showState} />

      <span
        className={`min-w-0 flex-1 truncate text-sm ${
          state === "pending" && showState ? "text-fg-muted" : "text-fg"
        }`}
      >
        {target.target}
      </span>

      <span className="type-data hidden w-24 shrink-0 text-fg-muted sm:block">
        {formatCategory(target.category)}
      </span>

      {showState && (
        <span
          className={`type-data shrink-0 ${state === "assessed" ? "text-accent" : "text-fg-muted"}`}
        >
          {STATE_LABEL[state]}
        </span>
      )}

      {hasDetail ? (
        <ChevronDown
          size={15}
          aria-hidden="true"
          className={`shrink-0 text-fg-muted transition-transform duration-200 ${open ? "rotate-180" : ""}`}
        />
      ) : (
        <span aria-hidden="true" className="w-[15px] shrink-0" />
      )}
    </div>
  )

  return (
    <li className="border-b border-hair last:border-0">
      {hasDetail ? (
        <button
          type="button"
          onClick={() => setOpen((value) => !value)}
          aria-expanded={open}
          aria-controls={panelId}
          className="flex min-h-[44px] w-full items-center py-2.5 transition-colors duration-200 hover:bg-fg/[0.02]"
        >
          {body}
        </button>
      ) : (
        <div className="flex min-h-[44px] w-full items-center py-2.5">{body}</div>
      )}

      {hasDetail && open && (
        <motion.div
          id={panelId}
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: "auto" }}
          transition={transition.state}
          className="overflow-hidden"
        >
          <div className="pb-4 pl-6 pr-2 sm:pl-7">
            <p className="type-copy text-sm text-fg-soft">{target.grounding}</p>
            <p className="type-data mt-2 text-fg-muted">
              Identified from {formatSource(target.source)}
            </p>
          </div>
        </motion.div>
      )}
    </li>
  )
}

/**
 * State as a shape first. Filled square for explored, ringed for in flight, hollow hairline for
 * not yet - legible without colour, and without implying that "not yet" is a failure.
 */
function Marker({ state, showState }: { state: TargetState; showState: boolean }) {
  if (!showState) {
    return <span aria-hidden="true" className="h-1.5 w-1.5 shrink-0 rounded-[1px] bg-fg/25" />
  }

  if (state === "assessed") {
    return (
      <motion.span
        aria-hidden="true"
        className="h-2 w-2 shrink-0 rounded-[2px] bg-accent"
        animate={{ scale: [1, 1.45, 1] }}
        transition={transition.emphasis}
      />
    )
  }

  if (state === "active") {
    return (
      <span
        aria-hidden="true"
        className="think-dot h-2 w-2 shrink-0 rounded-[2px] bg-accent/50 ring-2 ring-accent/25"
      />
    )
  }

  return (
    <span aria-hidden="true" className="h-2 w-2 shrink-0 rounded-[2px] border border-fg/25" />
  )
}
