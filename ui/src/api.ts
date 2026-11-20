export type Batch = { batch_id: string; line_count: number; matched: number; unmatched: number; run_status: string | null }
export type ReportRow = {
  store_cnpj: string
  line_count: number
  unmatched_count: number
  reported_total: number
  expected_total: number
  difference: number
  mismatched_lines: number
}
export type Line = {
  id: number
  store_cnpj: string
  raw_product: string
  quantity: number
  amount: number
  sku: string | null
  name: string | null
  unit_price: number | null
  expected_amount: number | null
  score: number | null
  method: string | null
}
export type LinesPage = { total: number; limit: number; offset: number; threshold: number; items: Line[] }
export type Candidate = { catalog_id: number; sku: string; name: string; brand: string; score: number; method: string }
export type MatchResult = { query: string; embedding_model: string; threshold: number; best: Candidate | null; candidates: Candidate[] }
export type CatalogRow = { id: number; sku: string; name: string; brand: string; ean: string; unit_price: number; active: boolean }
export type Health = { status: string; db: string; embedding_model: string }

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, init)
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`)
  return res.json() as Promise<T>
}

export const post = <T,>(path: string, body?: unknown, headers: Record<string, string> = {}) =>
  api<T>(path, {
    method: 'POST',
    headers: { 'content-type': 'application/json', ...headers },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
