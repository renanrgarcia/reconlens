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
