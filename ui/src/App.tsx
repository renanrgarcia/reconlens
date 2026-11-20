import { useState } from 'react'
import { api, type Health } from './api'
import { useFetch } from './lib'
import { Batches, Catalog, Lines, Playground } from './pages'

const TABS = ['Batches', 'Lines', 'Match playground', 'Catalog'] as const

export default function App() {
  const [tab, setTab] = useState<(typeof TABS)[number]>('Batches')
  const [prefill, setPrefill] = useState('')
  const health = useFetch(() => api<Health>('/health'), [])

  return (
    <main>
      <header>
        <h1>ReconLens</h1>
        <span className={`badge ${health.data?.status === 'ok' ? 'ean_exact' : 'none'}`}>
          {health.data ? `${health.data.status} / db ${health.data.db}` : health.error ? 'api down' : '...'}
        </span>
        {health.data && <span className="muted">embedding: {health.data.embedding_model}</span>}
      </header>
      <nav>
        {TABS.map((t) => (
          <button key={t} className={t === tab ? 'active' : ''} onClick={() => setTab(t)}>{t}</button>
        ))}
      </nav>
      {tab === 'Batches' && <Batches />}
      {tab === 'Lines' && <Lines onOpen={(text) => { setPrefill(text); setTab('Match playground') }} />}
      {tab === 'Match playground' && <Playground key={prefill} initialText={prefill} />}
      {tab === 'Catalog' && <Catalog />}
    </main>
  )
}
