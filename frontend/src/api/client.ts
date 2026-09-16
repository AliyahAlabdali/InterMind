const BASE_URL = import.meta.env.VITE_API_BASE_URL

/**
 * Milestone 4 recruiter access token (see `app.api.auth` on the backend) - a single shared
 * credential standing in for "is a recruiter", not a per-user login. Attached by every
 * recruiter-facing API call (jobs, plans, starting interviews, reports, candidate listings).
 * Real recruiter accounts/login are out of scope until Milestone 6-B; see that module's
 * docstring for the full rationale.
 */
export const RECRUITER_ACCESS_TOKEN: string = import.meta.env.VITE_RECRUITER_ACCESS_TOKEN ?? ""

export interface RequestOptions {
  /** `Authorization: Bearer <token>` to send - the recruiter token, or a candidate's own
   * per-interview access token. Omitted only for the (rare) unauthenticated endpoint. */
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
