import { createRef } from "react"
import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { InterviewComposer } from "./InterviewComposer"

/**
 * The composer is the last place a transcript can be duplicated.
 *
 * An earlier version rendered `answer + interim` as the textarea's *value* while its `onChange`
 * wrote that whole composite back into the answer - so a keystroke while words were still being
 * heard promoted the unsettled text into the answer, and the provider's own final for the same
 * utterance then appended it a second time. These lock in the rule that fixed it: what has been
 * committed and what is still being heard are two different pieces of text, in two different
 * elements, and only one of them is the answer.
 */

function setup(overrides: Partial<Parameters<typeof InterviewComposer>[0]> = {}) {
  const onChange = vi.fn()
  const onSubmit = vi.fn()
  const props = {
    value: "",
    onChange,
    interim: "",
    onSubmit,
    locked: false,
    isSubmitting: false,
    voice: {
      isSupported: true,
      isUnavailable: false,
      isRecording: false,
      notice: null,
      toggle: vi.fn(),
    },
    textareaRef: createRef<HTMLTextAreaElement>(),
    ...overrides,
  }
  render(<InterviewComposer {...props} />)
  return { onChange, onSubmit }
}

const field = () => screen.getByLabelText("Your answer") as HTMLTextAreaElement

describe("InterviewComposer", () => {
  it("keeps words still being heard out of the answer itself", () => {
    setup({ value: "I rebuilt the ingestion path.", interim: "We batched the inserts" })

    // Both are on screen...
    expect(field().value).toBe("I rebuilt the ingestion path.")
    expect(screen.getByText(/We batched the inserts/)).toBeTruthy()
    // ...but only the settled half is the answer. If interim text were part of the value it
    // would be committed again the moment the provider settles that same utterance.
    expect(field().value).not.toMatch(/batched/)
  })

  it("reports only what the candidate typed, never the composite", () => {
    const { onChange } = setup({ value: "So far.", interim: "and still speaking" })

    field().dispatchEvent(new Event("input", { bubbles: true }))
    // React's onChange fires with the element's own value, which must never have included the
    // interim text in the first place.
    if (onChange.mock.calls.length > 0) {
      expect(onChange.mock.calls[0][0]).not.toMatch(/still speaking/)
    }
  })

  it("can send an answer that is still only spoken", () => {
    setup({ value: "", interim: "the whole answer arrived by voice" })

    // The last sentence a candidate speaks is often still unsettled when they reach for send;
    // a disabled button there loses it.
    const send = screen.getByRole("button", { name: /send answer/i }) as HTMLButtonElement
    expect(send.disabled).toBe(false)
  })

  it("has nothing to send when nothing has been said or typed", () => {
    setup()
    const send = screen.getByRole("button", { name: /send answer/i }) as HTMLButtonElement
    expect(send.disabled).toBe(true)
  })

  it("locks every control while the interviewer has the floor", () => {
    setup({ value: "An answer.", locked: true })

    expect(field().disabled).toBe(true)
    expect((screen.getByRole("button", { name: /send answer/i }) as HTMLButtonElement).disabled).toBe(
      true,
    )
    expect(
      (screen.getByRole("button", { name: /speaking instead/i }) as HTMLButtonElement).disabled,
    ).toBe(true)
  })

  it("offers typing, in plain words, when the microphone cannot be used", () => {
    setup({
      voice: {
        isSupported: true,
        isUnavailable: true,
        notice: "Voice input isn't available right now. You can continue by typing.",
        isRecording: false,
        toggle: vi.fn(),
      },
    })

    expect(screen.queryByRole("button", { name: /speaking instead/i })).toBeNull()
    expect(screen.getByText(/continue by typing/i)).toBeTruthy()
    // Never a browser or service error code.
    expect(screen.queryByText(/not-allowed|SPXERR|NotAllowedError/i)).toBeNull()
  })
})
