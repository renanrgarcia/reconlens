import { useState } from 'react'
import {
  api, post, type Batch, type CatalogRow, type LinesPage, type MatchResult, type ReportRow,
} from './api'
import { Badge, Diff, ScoreBar, Status } from './components'
import { money, useFetch } from './lib'

export function Batches() {
  const [selected, setSelected] = useState<string | null>(null)
  const batches = useFetch(() => api<Batch[]>('/batches'), [])
  const report = useFetch(() => (selected ? api<ReportRow[]>(`/reports/${selected}`) : Promise.resolve([])), [selected])
  const [msg, setMsg] = useState('')

  async function rerun() {
    setMsg('Running...')
    try {
      const r = await post<{ matched: number; unmatched: number }>(`/reconcile/${selected}`, undefined, {
        'Idempotency-Key': crypto.randomUUID(),
      })
      setMsg(`Matched ${r.matched}, unmatched ${r.unmatched}`)
      batches.reload()
    } catch (e) {
      setMsg((e as Error).message)
    }
  }

  return (
    <>
      <Status loading={batches.loading} error={batches.error}>
        <table>
          <thead>
            <tr><th>Batch</th><th className="num">Lines</th><th className="num">Matched</th><th className="num">Unmatched</th><th>Run</th></tr>
          </thead>
          <tbody>
            {batches.data?.map((b) => (
              <tr key={b.batch_id} className={`click ${b.batch_id === selected ? 'sel' : ''}`} onClick={() => setSelected(b.batch_id)}>
                <td>{b.batch_id}</td><td className="num">{b.line_count}</td><td className="num">{b.matched}</td>
                <td className="num">{b.unmatched}</td><td>{b.run_status ?? '-'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Status>
      {selected && (
        <section>
          <h2>
            Report {selected}{' '}
            <button
              onClick={rerun}
              title="Re-runs matching only (match_results). Totals are owned by the .NET worker and are not recomputed here."
            >
              Re-run matching
            </button>{' '}
            <span className="muted">{msg}</span>
          </h2>
          <Status loading={report.loading} error={report.error}>
            {report.data?.length ? (
              <table>
                <thead>
                  <tr><th>Store</th><th className="num">Reported</th><th className="num">Expected</th><th className="num">Difference</th><th className="num">Mismatched</th><th className="num">Unmatched</th></tr>
                </thead>
                <tbody>
                  {report.data.map((r) => (
                    <tr key={r.store_cnpj}>
                      <td>{r.store_cnpj}</td><td className="num">{money(r.reported_total)}</td>
                      <td className="num">{money(r.expected_total)}</td><Diff value={r.difference} />
                      <td className="num">{r.mismatched_lines}</td><td className="num">{r.unmatched_count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <p className="muted">No report yet (the worker has not reconciled this batch).</p>
            )}
          </Status>
        </section>
      )}
    </>
  )
}

const PAGE = 25

export function Lines({ onOpen }: { onOpen: (text: string) => void }) {
  const batches = useFetch(() => api<Batch[]>('/batches'), [])
  const [batch, setBatch] = useState('')
  const [status, setStatus] = useState('all')
  const [store, setStore] = useState('')
  const [offset, setOffset] = useState(0)
  const current = batch || batches.data?.[0]?.batch_id || ''
  const reports = useFetch(() => (current ? api<ReportRow[]>(`/reports/${current}`) : Promise.resolve([])), [current])
  const lines = useFetch(
    () =>
      current
        ? api<LinesPage>(`/lines/${current}?status=${status}&store_cnpj=${store}&limit=${PAGE}&offset=${offset}`)
        : Promise.resolve(null),
    [current, status, store, offset],
  )
  const page = lines.data

  return (
    <>
      <div className="filters">
        <label>Batch <select value={current} onChange={(e) => { setBatch(e.target.value); setStore(''); setOffset(0) }}>
          {batches.data?.map((b) => <option key={b.batch_id}>{b.batch_id}</option>)}
        </select></label>
        <label>Status <select value={status} onChange={(e) => { setStatus(e.target.value); setOffset(0) }}>
          <option>all</option><option>matched</option><option>unmatched</option>
        </select></label>
        <label>Store <select value={store} onChange={(e) => { setStore(e.target.value); setOffset(0) }}>
          <option value="">all</option>
          {reports.data?.map((r) => <option key={r.store_cnpj}>{r.store_cnpj}</option>)}
        </select></label>
      </div>
      <Status loading={lines.loading} error={lines.error}>
        {page && (
          <>
            <table>
              <thead>
                <tr><th>Raw product</th><th>Matched</th><th>Score (| = threshold {page.threshold})</th><th>Method</th><th className="num">Qty</th><th className="num">Unit price</th><th className="num">Qty x price (expected)</th><th className="num">Reported</th></tr>
              </thead>
              <tbody>
                {page.items.map((l) => (
                  <tr key={l.id} className="click" onClick={() => onOpen(l.raw_product)} title="Open in Match playground">
                    <td>{l.raw_product}</td>
                    <td>{l.sku ? `${l.sku} ${l.name}` : <span className="muted">unmatched</span>}</td>
                    <td>{l.score != null && <ScoreBar score={l.score} threshold={page.threshold} />}</td>
                    <td><Badge method={l.method} /></td>
                    <td className="num">{l.quantity}</td><td className="num">{money(l.unit_price)}</td>
                    <td className="num">{money(l.expected_amount)}</td><td className="num">{money(l.amount)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="pager">
              <button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>Prev</button>{' '}
              {page.total ? offset + 1 : 0}-{Math.min(offset + PAGE, page.total)} of {page.total}{' '}
              <button disabled={offset + PAGE >= page.total} onClick={() => setOffset(offset + PAGE)}>Next</button>
            </p>
          </>
        )}
      </Status>
    </>
  )
}

export function Playground({ initialText }: { initialText: string }) {
  const [text, setText] = useState(initialText)
  const [topK, setTopK] = useState(5)
  const [brand, setBrand] = useState('')
  const [result, setResult] = useState<MatchResult | null>(null)
  const [error, setError] = useState('')

  async function run(e?: { preventDefault(): void }) {
    e?.preventDefault()
    setError('')
    try {
      setResult(await post<MatchResult>('/match', { text, top_k: topK, brand: brand || null }))
    } catch (err) {
      setError((err as Error).message)
    }
  }

  return (
    <>
      <form onSubmit={run} className="filters">
        <input aria-label="Text" className="wide" value={text} onChange={(e) => setText(e.target.value)} placeholder="DIPIR 500 CPR" />
        <label>top_k <input type="number" min={1} max={20} value={topK} onChange={(e) => setTopK(Number(e.target.value))} /></label>
        <input aria-label="Brand" value={brand} onChange={(e) => setBrand(e.target.value)} placeholder="brand (optional)" />
        <button type="submit" disabled={!text.trim()}>Match</button>
      </form>
      {error && <p className="error">{error}</p>}
      {result && (
        <>
          <p className="muted">
            embedding_model <b>{result.embedding_model}</b>, threshold <b>{result.threshold}</b>,{' '}
            best: <b>{result.best ? `${result.best.sku} (${result.best.method})` : 'none above threshold'}</b>
          </p>
          <table>
            <thead><tr><th>SKU</th><th>Name</th><th>Brand</th><th>Score</th><th>Method</th></tr></thead>
            <tbody>
              {result.candidates.map((c) => (
                <tr key={c.catalog_id}>
                  <td>{c.sku}</td><td>{c.name}</td><td>{c.brand}</td>
                  <td><ScoreBar score={c.score} threshold={result.threshold} /></td><td><Badge method={c.method} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </>
  )
}

export function Catalog() {
  const [q, setQ] = useState('')
  const rows = useFetch(() => api<CatalogRow[]>(`/catalog?q=${encodeURIComponent(q)}&limit=100`), [q])
  return (
    <>
      <div className="filters"><input aria-label="Search" className="wide" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search name, SKU or brand" /></div>
      <Status loading={rows.loading} error={rows.error}>
        <table>
          <thead><tr><th>SKU</th><th>Name</th><th>Brand</th><th>EAN</th><th className="num">Unit price</th></tr></thead>
          <tbody>
            {rows.data?.map((r) => (
              <tr key={r.id}><td>{r.sku}</td><td>{r.name}</td><td>{r.brand}</td><td>{r.ean}</td><td className="num">{money(r.unit_price)}</td></tr>
            ))}
          </tbody>
        </table>
      </Status>
    </>
  )
}
