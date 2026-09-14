import { useCallback, useEffect, useState } from "react"
import { ApiError } from "../api/client"

interface AsyncDataState<T> {
  data: T | null
  error: string | null
  isLoading: boolean
  refetch: () => void
}

/**
 * `enabled: false` skips fetching entirely (e.g. while a dependency this fetcher needs, such
 * as an id from another in-flight request, is not yet available) without reporting an error.
 */
export function useAsyncData<T>(
  fetcher: () => Promise<T>,
  deps: unknown[],
  enabled = true,
): AsyncDataState<T> {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(enabled)
  const [version, setVersion] = useState(0)

  const load = useCallback(() => {
    if (!enabled) {
      setIsLoading(false)
      return
    }

    let cancelled = false
    setIsLoading(true)
    setError(null)

    fetcher()
      .then((result) => {
        if (!cancelled) setData(result)
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : "Something went wrong.")
        }
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false)
      })

    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, ...deps, version])

  useEffect(() => load(), [load])

  const refetch = useCallback(() => setVersion((v) => v + 1), [])

  return { data, error, isLoading, refetch }
}
