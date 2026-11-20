import { useEffect, useState } from 'react'

export const money = (n: number | null | undefined) => (n == null ? '-' : Number(n).toFixed(2))

/** Loads data on mount / when deps change; shows loading and error states. */
export function useFetch<T>(load: () => Promise<T>, deps: unknown[]) {
  const [state, setState] = useState<{ data?: T; error?: string; loading: boolean }>({ loading: true })
  const [tick, setTick] = useState(0)
  useEffect(() => {
    let live = true
    setState((s) => ({ ...s, loading: true, error: undefined }))
    load().then(
      (data) => live && setState({ data, loading: false }),
      (e: Error) => live && setState({ error: e.message, loading: false }),
    )
    return () => {
      live = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick])
  return { ...state, reload: () => setTick((t) => t + 1) }
}
