import { afterEach, expect, it, vi } from "vitest"
import { submitAnswer } from "./interviews"

afterEach(() => vi.restoreAllMocks())

it("sends the observed turn identity with the candidate's answer", async () => {
  const fetch = vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response("{}", { status: 200, headers: { "Content-Type": "application/json" } }),
  )
  await submitAnswer("interview-1", "My answer", "test-candidate", "1".repeat(32))
  const [url, init] = fetch.mock.calls[0]
  expect(url).toBe("/api/interviews/interview-1/answers")
  expect(JSON.parse(String(init?.body))).toEqual({ answer: "My answer", turn_id: "1".repeat(32) })
  const headers = (init?.headers ?? {}) as Record<string, string>
  expect(headers.Authorization).toBe("Bearer test-candidate")
})
