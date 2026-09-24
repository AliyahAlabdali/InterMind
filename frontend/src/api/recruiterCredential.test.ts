import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { readFileSync, readdirSync, existsSync } from "node:fs"
import { join } from "node:path"

/**
 * Security regression: **no recruiter credential may reach the browser.**
 *
 * It used to. `VITE_RECRUITER_ACCESS_TOKEN` was read in `api/client.ts`, and Vite inlines
 * `VITE_`-prefixed variables into the bundle at build time - so the shared recruiter secret was
 * sitting in `dist/assets/*.js`, readable by anyone who loaded the site, including every
 * candidate. Recruiter requests now authenticate with an `HttpOnly` session cookie instead.
 *
 * These tests fail loudly if that regresses, in two independent ways: by source inspection, and
 * by searching the actual build output when one exists.
 */

const SRC = join(__dirname, "..")
const DIST_ASSETS = join(__dirname, "..", "..", "dist", "assets")

/** The development credential. Present here as the thing being searched *for*. */
const OLD_DEV_CREDENTIAL = "dev-recruiter-milestone-token-change-me"

function sourceFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = join(dir, entry.name)
    if (entry.isDirectory()) return sourceFiles(full)
    return /\.(ts|tsx)$/.test(entry.name) ? [full] : []
  })
}

describe("recruiter credential is not available to browser code", () => {
  it("no source file reads VITE_RECRUITER_ACCESS_TOKEN", () => {
    const offenders = sourceFiles(SRC).filter((file) => {
      if (file.endsWith("recruiterCredential.test.ts")) return false
      const text = readFileSync(file, "utf8")
      // Only actual reads count; the explanatory comment in `client.ts` naming the old variable
      // is documentation, not a credential.
      return /import\.meta\.env\.VITE_RECRUITER_ACCESS_TOKEN/.test(text)
    })

    expect(offenders).toEqual([])
  })

  it("no source file contains the development credential value", () => {
    const offenders = sourceFiles(SRC).filter(
      (file) =>
        !file.endsWith("recruiterCredential.test.ts") &&
        readFileSync(file, "utf8").includes(OLD_DEV_CREDENTIAL),
    )

    expect(offenders).toEqual([])
  })

  it("the api client exports no recruiter credential", async () => {
    const client = await import("./client")
    expect(Object.keys(client)).not.toContain("RECRUITER_ACCESS_TOKEN")
  })

  it("the built bundle contains no recruiter credential", () => {
    if (!existsSync(DIST_ASSETS)) {
      // A build has not been run in this checkout. The source-level tests above still hold, and
      // the build is checked explicitly in CI/verification.
      return
    }
    const offenders = readdirSync(DIST_ASSETS)
      .filter((name) => name.endsWith(".js"))
      .filter((name) => {
        const text = readFileSync(join(DIST_ASSETS, name), "utf8")
        return text.includes(OLD_DEV_CREDENTIAL) || text.includes("VITE_RECRUITER_ACCESS_TOKEN")
      })

    expect(offenders).toEqual([])
  })
})

describe("recruiter auth does not touch browser storage", () => {
  beforeEach(() => {
    vi.spyOn(Storage.prototype, "setItem")
  })
  afterEach(() => vi.restoreAllMocks())

  it("signing in writes no password to localStorage or sessionStorage", async () => {
    const { recruiterLogin } = await import("./auth")
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(
        new Response(JSON.stringify({ authenticated: true }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      )

    await recruiterLogin("recruiter@example.com", "a-password")

    // The password goes out in the request body and is never persisted anywhere.
    expect(Storage.prototype.setItem).not.toHaveBeenCalled()
    const [, init] = fetchMock.mock.calls[0]
    expect(JSON.parse(String(init?.body))).toEqual({
      email: "recruiter@example.com",
      password: "a-password",
    })
    // Cookies, not a bearer header: the browser has no recruiter token to send.
    expect((init?.headers as Record<string, string>)?.Authorization).toBeUndefined()
    expect(init?.credentials).toBe("same-origin")
  })

  it("recruiter API calls send no Authorization header", async () => {
    const { listJobs } = await import("./jobs")
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(
        new Response("[]", { status: 200, headers: { "Content-Type": "application/json" } }),
      )

    await listJobs()

    const [, init] = fetchMock.mock.calls[0]
    expect((init?.headers as Record<string, string>)?.Authorization).toBeUndefined()
    expect(init?.credentials).toBe("same-origin")
  })
})
