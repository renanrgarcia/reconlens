# ReconLens

Sales-line reconciliation for a pharmacy chain: messy point-of-sale text ("DIPIR 500 CPR") is matched
to a product catalog with pgvector, and a .NET worker computes per-store totals from the catalog prices.

**This is a weekend study project** built to practice (and talk about) AI agents, Docker, CI/CD and
.NET + Python integration. It uses synthetic data, was never deployed and is not production work.

## Quick start

Needs Docker. No `.env` is required; everything has a default.

```bash
docker compose up --build
```

Expected: `db` becomes healthy, `seed` prints `seeded 200/200 catalog rows (model=local-hash-v1)` and exits 0,
`api` becomes healthy, then `worker` logs one line per batch and store, for example:

```
Batch 2026-11-10 store 13356886000145: lines=26 unmatched=0 reported=3354.13 expected=3553.07 diff=-198.94 mismatched=2
```

5 batches x 8 stores = 40 report rows. On later ticks (every `SCHEDULE_SECONDS`, default 300) or after
`docker compose restart worker` it logs `Batch 2026-11-10: skipped, already reconciled`. The worker image
prints a harmless `libgssapi_krb5.so.2` message at start (Npgsql probing for Kerberos).

```bash
curl -s localhost:8000/health
# {"status":"ok","db":"ok","embedding_model":"local-hash-v1"}

curl -s -X POST localhost:8000/match -H 'content-type: application/json' \
  -d '{"text":"DIPIRONA SODICA 500MG 10 COMPRIMIDOS","top_k":2}'
# best.sku = SKU0073, score 0.961, method "vector"  (a 13-digit EAN in the text gives score 1.0, "ean_exact")

curl -s -X POST localhost:8000/reconcile/2026-11-10 -H 'Idempotency-Key: demo-1'
# {"batch_id":"2026-11-10","lines":196,"matched":...}; same key again replays the stored response

docker compose exec db psql -U postgres -c \
  "SELECT batch_id, store_cnpj, line_count, unmatched_count, reported_total, expected_total, difference FROM reconciliation_report ORDER BY 1,2 LIMIT 5"

docker compose down -v   # stop and drop the volume
```

Eval and agent (run from `api/`, with `uv`; the DB port 5432 is published by compose):

```bash
cd api && uv sync
uv run python evals/run_eval.py --api-url http://localhost:8000    # through the running API
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/postgres uv run python evals/run_eval.py   # direct
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/postgres uv run python -m reconlens.agent "DIPIR 500 CPR"
DATABASE_URL=... uv run pytest        # integration tests run when DATABASE_URL points at a seeded DB
cd ../worker && dotnet test           # Testcontainers starts its own pgvector
```

### Azure OpenAI and Databricks (optional)

`cp .env.example .env` and fill in the values; compose passes them through. Empty means the offline fallbacks.

- **Azure OpenAI**: set `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_EMBEDDING_DEPLOYMENT`
  (`text-embedding-3-small`) to switch embeddings; add `AZURE_OPENAI_CHAT_DEPLOYMENT` so the agent writes a real
  explanation instead of printing the raw tool output. After switching embedding model, re-seed
  (`docker compose run --rm seed python -m reconlens.seed --reembed`) and re-tune `MATCH_THRESHOLD`:
  the score scale differs from `local-hash-v1`.
- **Databricks**: set `SALES_SOURCE=databricks`, `DATABRICKS_HOST`, `DATABRICKS_TOKEN`, `DATABRICKS_WAREHOUSE_ID`
  and load the table as described in [databricks/README.md](databricks/README.md).

## Architecture

```mermaid
flowchart LR
  CSV[data/sales.csv] --> W
  DBX[Databricks sales_raw<br/>optional] --> W
  W[.NET worker<br/>batch key, retries,<br/>totals in decimal] -->|POST /reconcile/batch<br/>Idempotency-Key| API
  API[FastAPI matcher<br/>EAN + cosine] --> PG[(Postgres + pgvector)]
  W -->|lines, report| PG
  PG -->|match_results JOIN catalog.unit_price| W
  AG[Agent: Microsoft Agent Framework] -->|search_catalog tool| PG
  AZ[Azure OpenAI<br/>optional] -.embeddings / chat.-> API
  AZ -.chat.-> AG
```

Per tick, per batch, the worker: computes the batch idempotency key, skips it if a `completed` run exists,
inserts lines (`ON CONFLICT DO NOTHING`), calls the API, reads the matches joined to `catalog.unit_price`,
computes the report in C# `decimal`, upserts `reconciliation_report`, marks the run completed.
The fixed interface between the two halves is [docs/CONTRACT.md](docs/CONTRACT.md).

## Eval results

Golden set `data/golden.csv` (50 pairs: 42 positive, 8 negative), `MATCH_THRESHOLD=0.80`, `local-hash-v1`,
run against the compose stack (`run_eval.py --api-url http://localhost:8000`):

```
golden pairs: 50 (42 positive, 8 negative)
precision@1 (positives):          1.000
threshold:                        0.8
recall at threshold:              0.976
false-match rate (all rows):      0.000
false-match rate (negatives only): 0.000

threshold sweep:
  thr    recall  false_all  false_neg
  0.30   1.000   0.160      1.000
  0.40   1.000   0.160      1.000
  0.50   1.000   0.120      0.750
  0.60   1.000   0.080      0.500
  0.70   1.000   0.020      0.125
  0.75   1.000   0.000      0.000
  0.80   0.976   0.000      0.000
  0.85   0.952   0.000      0.000
  0.90   0.857   0.000      0.000
```

These numbers are optimistic, see the limits below. The threshold rationale (also checked on the 1000 sales
lines) is in the comment in [api/reconlens/config.py](api/reconlens/config.py).

## Repo layout

```
docker-compose.yml          db, seed (one-shot), api, worker
.github/workflows/ci.yml    python (ruff, pytest, eval), dotnet (build, format, test), docker (compose build)
db/init/001_schema.sql      pgvector schema, HNSW index
data/                       catalog.csv, sales.csv, golden.csv (synthetic, generated by api/reconlens/datagen.py)
api/reconlens/              main.py (FastAPI), matching.py, embeddings.py, seed.py, agent.py, config.py
api/evals/run_eval.py       golden-set metrics and threshold sweep
api/tests/                  unit + integration tests
worker/src/ReconLens.Worker .NET 10 worker (pipeline, calculator, Polly client, CSV/Databricks sources)
worker/tests/               xUnit + Testcontainers
databricks/                 Delta DDL and MERGE notes
docs/CONTRACT.md            schema, API and env contract
```

## Interview talking points

**HNSW vs IVFFlat** ([db/init/001_schema.sql](db/init/001_schema.sql))
The catalog index is HNSW (`m=16, ef_construction=64`). HNSW is a layered graph: better recall/latency
trade-off and no training step, but slower to build and more memory. IVFFlat clusters vectors into `lists`
and scans `probes` of them: fast build, small, but it needs data present before building (centroids come from
it), and recall drops as data drifts, so it needs periodic rebuilds. HNSW handles inserts and updates
incrementally. Query-time knobs: `hnsw.ef_search` (default 40, raise for recall) vs `ivfflat.probes`.
With 200 rows either is overkill; I picked HNSW to practise the usual default.

**Cosine vs L2 vs inner product** ([api/reconlens/matching.py](api/reconlens/matching.py))
Both embedders return L2-normalized vectors, and for unit vectors cosine, L2 and inner product give the
same ranking (`|a-b|^2 = 2 - 2a.b`). The index uses `vector_cosine_ops` and the query orders by `<=>`
(cosine distance), score = `1 - distance`. The operator in `ORDER BY` must match the index's opclass or
Postgres will not use the index. Inner product (`<#>`) is the cheapest if you know vectors are normalized.

**Changing the embedding model** ([api/reconlens/seed.py](api/reconlens/seed.py), `catalog.embedding_model`)
Vectors from different models live in different spaces and cannot be compared, so every row stores its
model and the query filters `embedding_model = :current`. The seed re-embeds rows whose model differs.
For a live system: backfill the new model next to the old, dual-read or flip behind a flag, then drop the old
rows or column. Score scales change too, so re-run the eval and re-tune the threshold. Dimensions fixed
at `vector(1536)` is a related constraint: a different size means a new column/index.

**Deterministic vs AI** ([worker/.../ReconciliationCalculator.cs](worker/src/ReconLens.Worker/ReconciliationCalculator.cs))
Money is computed only in the worker, in C# `decimal`, from `catalog.unit_price` and the reported `amount`.
The embedder and any LLM only propose which catalog row a line is. The API response carries no prices, and the
agent has a single read-only tool (`search_catalog`) and instructions not to compute money. A wrong match
is then a visible, bounded error, not a silent number from a model.

**Idempotency** ([worker/.../Sales.cs](worker/src/ReconLens.Worker/Sales.cs), [api/reconlens/main.py](api/reconlens/main.py))
Batch key = sha256(`batch_id|content hash`) of the sorted lines: same data, same key; any changed field,
new key. `reconciliation_runs` lets the worker skip completed batches; line inserts are `ON CONFLICT DO NOTHING`;
the report is an upsert. The API stores responses in `api_idempotency` and replays them for a repeated
`Idempotency-Key`. So retrying `POST /reconcile` after a timeout cannot double-process, which is what makes
the retry policy safe. Caveat: the check-then-insert in the API is not atomic, two concurrent first calls with
one key could both do the work (results are upserts, so the outcome is still correct).

**Retries with Polly v8** ([worker/.../ReconcileApiClient.cs](worker/src/ReconLens.Worker/ReconcileApiClient.cs))
Standard resilience handler: 5 retries, exponential backoff with jitter (jitter avoids synchronized retry
storms), a 60 s timeout per attempt inside the retry so a hung call is retried. Retries 5xx, 408, 429 and
network errors. It must not retry other 4xx (a 404 for a missing batch will never succeed) and must not retry
non-idempotent POSTs; this one is retried only because of the Idempotency-Key. A circuit breaker
would be the next layer if the API is down for long.

**Delta MERGE** ([databricks/sales_raw.sql](databricks/sales_raw.sql))
`MERGE INTO sales_raw ... ON batch_id AND source_line_id` upserts: matched rows are updated, new ones inserted,
so reloading the same file never duplicates lines. Delta makes that atomic (ACID transaction log). The key
is the source system's stable line id, not a row number. The worker reads it through the SQL Statement
Execution API (`DatabricksSalesSource.cs`).

**Choosing the threshold from evals** ([api/evals/run_eval.py](api/evals/run_eval.py), [api/reconlens/config.py](api/reconlens/config.py))
Precision and recall trade off through one number. A false match silently puts a wrong catalog price into
`expected_total`; an unmatched line is only flagged for review. So false matches cost more and I favour
precision: 0.80 gives 0 false matches on the golden set and 0.976 recall, while 0.75 matches too many true
negatives on the full sales file. The sweep makes the trade-off visible instead of guessing.

**Hybrid search** ([api/reconlens/matching.py](api/reconlens/matching.py))
Exact identifiers should not go through fuzzy search: if the text holds a 13-digit EAN that exists in the
catalog it returns score 1.0, method `ean_exact`. Otherwise vector search runs with exact SQL filters
(`active`, `embedding_model`, optional `brand`) applied in the same query. Caveat: with an HNSW index,
filters are applied after the approximate scan, so a very selective filter can return fewer than `top_k` rows
(raise `ef_search`, or pgvector 0.8 iterative scans).

**Local hash embedder vs a real model** ([api/reconlens/embeddings.py](api/reconlens/embeddings.py))
`local-hash-v1` exists so the project runs offline, in CI and in tests with no key or cost: lowercase,
strip accents, expand abbreviations (`cpr` to `comprimido`), tokens plus character 3-grams, signed feature
hashing into 1536 dims, normalized. It is lexical, not semantic: "DIPIR 500 CPR" scores about 0.24 against its
true product (below the threshold), because "dipir" is not "dipirona" after hashing and no abbreviation
rule covers it. A real model would likely recover it; I have not measured that.

## Known limits / what I would do next

- The golden set and the sales lines come from the same noise generator (`datagen.py`), so the metrics are
  optimistic. Real data would need hand-labelled samples.
- Only 8 negatives in the golden set: too few to pick a threshold with confidence.
- The Databricks source is unit-tested only; I never ran it against a real workspace.
- The Azure OpenAI path (embeddings and agent chat) was not run; only the offline path is verified.
- No Kubernetes manifests yet (next: Deployment for the API, CronJob for the worker, Secret for keys, probes
  on `/health`). No Azure deployment either.
- Idempotency check in the API is not race-free (see above); the worker is a single instance.
- Matching runs line by line per batch; no batching of vector queries.
