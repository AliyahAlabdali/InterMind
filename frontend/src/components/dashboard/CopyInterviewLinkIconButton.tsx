import { useState } from "react"
import { IconButton } from "../ui/IconButton"
import { CopyIcon, CheckIcon } from "../ui/icons"
import { candidateLink } from "../../lib/candidateLink"

interface CopyInterviewLinkIconButtonProps {
  interviewId: string
  accessToken: string
}

/** The persistent, always-available way to recover a candidate's interview link from the
 * candidate table - not just a one-time thing shown in the creation dialog. Builds the link
 * from the same stable token the dialog used; never mints or requests a new one. */
export function CopyInterviewLinkIconButton({ interviewId, accessToken }: CopyInterviewLinkIconButtonProps) {
  const [copied, setCopied] = useState(false)

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(candidateLink(interviewId, accessToken))
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1600)
    } catch {
      // Clipboard API unavailable/denied - nothing to fall back to in an icon-only control;
      // the full-link copy button in the creation dialog still works via its own text.
    }
  }

  return (
    <IconButton
      label={copied ? "Copied" : "Copy interview link"}
      icon={copied ? <CheckIcon /> : <CopyIcon />}
      tone={copied ? "success" : "default"}
      onClick={handleCopy}
    />
  )
}
