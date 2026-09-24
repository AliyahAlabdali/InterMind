import type { ReactNode } from "react"
import { motion } from "motion/react"
import { rise } from "../../design/motion"

interface PageIntroProps {
  /** Small context line above the title. Optional, and usually unnecessary. */
  kicker?: ReactNode
  title: ReactNode
  /** One sentence saying what this page is for. */
  lede?: ReactNode
  /** The page's primary action, and at most one secondary. */
  actions?: ReactNode
  /** Facts that belong with the title rather than in the body. */
  meta?: ReactNode
}

/**
 * How every workspace page begins.
 *
 * Left-aligned, on a controlled measure, with the primary action on the same baseline as the
 * title. Consistent enough that "where am I / what do I do here" is answered in the same place
 * on every page, and small enough that it never becomes the page's subject: internal titles are
 * labels, not headlines.
 */
export function PageIntro({ kicker, title, lede, actions, meta }: PageIntroProps) {
  return (
    <motion.header variants={rise} className="flex flex-col gap-5">
      <div className="flex flex-wrap items-end justify-between gap-x-8 gap-y-4">
        <div className="min-w-0">
          {kicker && <p className="type-data mb-2 text-fg-muted">{kicker}</p>}
          <h1 className="type-page text-balance text-fg">{title}</h1>
          {lede && <p className="type-copy mt-3 text-fg-soft">{lede}</p>}
        </div>
        {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
      </div>
      {meta}
    </motion.header>
  )
}
