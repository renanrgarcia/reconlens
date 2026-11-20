import type { ReactNode } from 'react'
import { money } from './lib'


/** Score bar with a marker at the match threshold. */
export function ScoreBar({ score, threshold }: { score: number; threshold: number }) {
  const ok = score >= threshold
  return (
    <span className="scorebar" title={`score ${score.toFixed(3)} vs threshold ${threshold}`}>
      <span className="track">
        <span className={ok ? 'fill ok' : 'fill low'} style={{ width: `${Math.max(0, Math.min(1, score)) * 100}%` }} />
        <span className="threshold" style={{ left: `${threshold * 100}%` }} />
      </span>
      <span className="num">{score.toFixed(3)}</span>
      <span className="sr-only">{ok ? 'above threshold' : 'below threshold'}</span>
    </span>
  )
}

export const Badge = ({ method }: { method: string | null }) =>
  method ? <span className={`badge ${method}`}>{method}</span> : null

/** Difference = reported - expected (computed by the worker); highlighted when non-zero. */
export function Diff({ value }: { value: number }) {
  return <td className={`num ${Number(value) !== 0 ? 'diff' : ''}`}>{money(value)}</td>
}

export const Status = ({ loading, error, children }: { loading: boolean; error?: string; children: ReactNode }) =>
  error ? <p className="error">{error}</p> : loading ? <p className="muted">Loading...</p> : <>{children}</>
