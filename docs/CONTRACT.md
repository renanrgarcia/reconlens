# ReconLens — fixed contract

Study project (sales reconciliation). Python API and .NET worker are built against this file. Change it only deliberately.

## Layout
```
docker-compose.yml        db, seed (one-shot), api, worker, ui
.env.example              never commit .env
db/init/001_schema.sql    mounted into /docker-entrypoint-initdb.d
data/catalog.csv          generated once, committed (~200 rows)
data/sales.csv            generated once, committed (~1000 rows)
data/golden.csv           ~50 labelled pairs, committed
api/                      Python 3.12, uv, package `reconlens`, FastAPI
worker/                   .NET 10 Worker Service + worker tests
ui/                       Vite + React + TypeScript management UI (nginx in compose, port 5173)
databricks/               optional: Delta DDL + MERGE notes
.github/workflows/ci.yml
```

## Database (Postgres 16 + pgvector, image `pgvector/pgvector:pg16`)
```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE catalog (
  id              serial PRIMARY KEY,
  sku             text UNIQUE NOT NULL,
  name            text NOT NULL,          -- clean canonical name, e.g. "DIPIRONA SODICA 500MG 10 COMPRIMIDOS"
  brand           text NOT NULL,          -- lab/manufacturer
  ean             text UNIQUE NOT NULL,   -- 13 digits
  unit_price      numeric(12,2) NOT NULL,
  active          boolean NOT NULL DEFAULT true,
  embedding       vector(1536),
  embedding_model text                    -- e.g. 'local-hash-v1' or 'text-embedding-3-small'
);
CREATE INDEX catalog_embedding_hnsw ON catalog USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);

CREATE TABLE sales_lines (
  id              bigserial PRIMARY KEY,
  batch_id        text NOT NULL,
  source_line_id  text NOT NULL,          -- stable id from the source system
  store_cnpj      text NOT NULL,          -- 14 digits
  sale_date       date NOT NULL,
  raw_product     text NOT NULL,          -- messy free text
  quantity        integer NOT NULL,
  amount          numeric(12,2) NOT NULL, -- reported line total
  UNIQUE (batch_id, source_line_id)
);

CREATE TABLE match_results (
  sales_line_id   bigint PRIMARY KEY REFERENCES sales_lines(id),
  batch_id        text NOT NULL,
  catalog_id      integer REFERENCES catalog(id),  -- NULL when below threshold
  score           double precision NOT NULL,
  method          text NOT NULL,                   -- 'ean_exact' | 'vector' | 'none'
  embedding_model text NOT NULL,
  matched_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE api_idempotency (
  idempotency_key text PRIMARY KEY,
  response        jsonb NOT NULL,
  created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE reconciliation_runs (
  idempotency_key text PRIMARY KEY,       -- sha256(batch_id + '|' + content hash of the batch lines)
  batch_id        text NOT NULL,
  status          text NOT NULL,          -- 'running' | 'completed' | 'failed'
  started_at      timestamptz NOT NULL DEFAULT now(),
  completed_at    timestamptz
);

CREATE TABLE reconciliation_report (
  batch_id            text NOT NULL,
  store_cnpj          text NOT NULL,
  line_count          integer NOT NULL,
  unmatched_count     integer NOT NULL,
  reported_total      numeric(14,2) NOT NULL,   -- sum(amount) all lines
  expected_total      numeric(14,2) NOT NULL,   -- sum(quantity * catalog.unit_price) matched lines
  matched_reported    numeric(14,2) NOT NULL,   -- sum(amount) matched lines
  unmatched_amount    numeric(14,2) NOT NULL,   -- sum(amount) unmatched lines
  difference          numeric(14,2) NOT NULL,   -- matched_reported - expected_total
  mismatched_lines    integer NOT NULL,         -- matched lines with |amount - qty*price| > 0.01
  computed_at         timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (batch_id, store_cnpj)
);
```

## CSV formats (header row, comma, UTF-8)
- `data/catalog.csv`: `sku,name,brand,ean,unit_price`
- `data/sales.csv`: `batch_id,source_line_id,store_cnpj,sale_date,raw_product,quantity,amount,true_sku`
  (`true_sku` empty when the product is not in the catalog; ground truth for study only, the worker ignores it)
- `data/golden.csv`: `raw_product,expected_sku` (`expected_sku` empty = should NOT match anything)

`batch_id` format: `YYYY-MM-DD` (one batch per sale day, ~5 batches).

## API (FastAPI, port 8000)
- `GET /health` → `200 {"status":"ok","db":"ok","embedding_model":"local-hash-v1"}`
- `POST /match` body `{"text": str, "top_k": int = 5, "brand": str | null}` →
  `{"query": str, "embedding_model": str, "threshold": float, "best": Candidate | null, "candidates": [Candidate]}`
  `Candidate = {"catalog_id": int, "sku": str, "name": str, "brand": str, "score": float, "method": "ean_exact"|"vector"}`
  `best` = first candidate with score >= threshold, else null. Response carries NO prices.
- `POST /reconcile/{batch_id}` header `Idempotency-Key` (optional) →
  matches every `sales_lines` row of the batch, upserts `match_results`, returns
  `{"batch_id": str, "lines": int, "matched": int, "unmatched": int, "embedding_model": str, "threshold": float}`.
  Same key again → stored response replayed from `api_idempotency`, no re-work. 404 if the batch has no lines.

Read-only endpoints for the UI (no money computed in Python; report numbers come from `reconciliation_report`, written by the worker):
- `GET /batches` → `[{"batch_id", "line_count", "matched", "unmatched", "run_status": str | null}]` (`run_status` from the latest `reconciliation_runs` row).
- `GET /reports/{batch_id}` → `reconciliation_report` rows for the batch (`[]` when the worker has not run it).
- `GET /lines/{batch_id}?status=all|matched|unmatched&store_cnpj=&limit=50&offset=0` →
  `{"total", "limit", "offset", "threshold", "items": [{"id","source_line_id","store_cnpj","sale_date","raw_product","quantity","amount","sku","name","unit_price","expected_amount","score","method"}]}`;
  catalog/match fields are null for unmatched lines. `expected_amount` = `quantity * catalog.unit_price` read in SQL, display only (the worker's report is the source of truth). `limit` 1..500.
- `GET /catalog?q=&limit=50` → `[{"id","sku","name","brand","ean","unit_price","active","embedding_model"}]`, no embeddings; `q` is an ILIKE on name, sku and brand.

The UI calls everything under `/api` (Vite dev proxy and nginx strip the prefix and forward to the API).

Hybrid query: (1) if the text contains a 13-digit EAN equal to `catalog.ean` → score 1.0, method `ean_exact`;
(2) else cosine `1 - (embedding <=> :q)` with exact filters `active = true AND embedding_model = :current_model`
(+ `brand = :brand` when given), ORDER BY distance LIMIT top_k. Threshold from env `MATCH_THRESHOLD`.

## Embeddings
- Azure OpenAI `text-embedding-3-small` (1536 dims) when `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`,
  `AZURE_OPENAI_EMBEDDING_DEPLOYMENT` are set.
- Otherwise `local-hash-v1`: deterministic, offline, no torch — normalized text (lowercase, strip accents,
  abbreviation map), word tokens + char 3-grams, signed feature hashing into 1536 dims, L2-normalized.
- Seed refuses to mix models: rows with a different `embedding_model` get re-embedded (`--reembed`).

## Worker (.NET 10)
Env: `DATABASE_URL` (Npgsql conn string), `API_BASE_URL`, `SALES_SOURCE` = `csv` (default) | `databricks`,
`SALES_CSV_PATH`, `SCHEDULE_SECONDS` (default 300), `DATABRICKS_HOST`, `DATABRICKS_TOKEN`, `DATABRICKS_WAREHOUSE_ID`.
Per tick, per batch: compute idempotency key → skip if a `completed` run exists → insert lines
(`ON CONFLICT DO NOTHING`) → `POST /reconcile/{batch}` with `Idempotency-Key` (Polly retry, exp. backoff + jitter)
→ read match_results JOIN catalog → compute report in C# `decimal` → upsert `reconciliation_report` → mark completed.
Money is computed only here, from `catalog.unit_price` and `sales_lines.amount`.
