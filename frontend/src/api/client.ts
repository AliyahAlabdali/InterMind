/**
 * Same-origin by default: the dev server proxies `/api` to the backend (see `vite.config.ts`),
 * and a production deployment is expected to serve the app and its API from one origin. That is
 * what lets recruiter auth use a `SameSite=Strict` session cookie.
 */
const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "/api"

/**
 * There is deliberately **no recruiter credential in this file, and none anywhere in browser
 * code.**
 *
 * It used to live here, read from `VITE_RECRUITER_ACCESS_TOKEN`, which Vite inlines into the
 * production bundle - so the shared recruiter secret was readable in `dist/assets/*.js` by
 * anyone who loaded the site, including every candidate. Recruiter requests now authenticate
 * with an `HttpOnly` session cookie that the browser cannot read and that carries no copy of
 * the underlying credential. See `app/api/recruiter_session.py`.
 *
 * `token` below is for **candidate** access tokens only - a per-interview credential the
 * candidate legitimately holds, in their own link.
 */
export interface RequestOptions {
  /** `Authorization: Bearer <token>`: a candidate's own per-interview access token. Never a
   * recruiter credential - recruiters authenticate by session cookie. */
  token?: string
}

export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = "ApiError"
    this.status = status
  }
}

async function parseErrorDetail(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown }
    if (typeof body.detail === "string") return body.detail
    if (Array.isArray(body.detail)) {
      // FastAPI validation errors: [{ loc, msg, type }, ...]
      const messages = body.detail
        .map((item) => (item && typeof item === "object" && "msg" in item ? String(item.msg) : null))
        .filter((msg): msg is string => Boolean(msg))
      if (messages.length > 0) return messages.join("; ")
    }
  } catch {
    // Response had no JSON body; fall through to the generic message below.
  }
  return `Request failed with status ${response.status}`
}

async function request<T>(path: string, init?: RequestInit, token?: string): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${BASE_URL}${path}`, {
      ...init,
      // Sends the recruiter session cookie on same-origin requests, and nothing at all
      // cross-origin - which is the intended behaviour, not a limitation.
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...init?.headers,
      },
    })
  } catch {
    throw new ApiError(0, "Could not reach the server. Is the backend running?")
  }

  if (!response.ok) {
    const detail = await parseErrorDetail(response)
    throw new ApiError(response.status, detail)
  }

  if (response.status === 204) {
    return undefined as T
  }

  return (await response.json()) as T
}

export function apiGet<T>(path: string, options?: RequestOptions): Promise<T> {
  return request<T>(path, { method: "GET" }, options?.token)
}

export function apiPost<T>(path: string, body?: unknown, options?: RequestOptions): Promise<T> {
  return request<T>(
    path,
    {
      method: "POST",
      body: body === undefined ? undefined : JSON.stringify(body),
    },
    options?.token,
  )
}
