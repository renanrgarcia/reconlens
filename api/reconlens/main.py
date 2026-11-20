import json
from functools import lru_cache
from typing import Literal

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.responses import JSONResponse
from psycopg.rows import dict_row
from pydantic import BaseModel

from reconlens import config, db, matching
from reconlens.embeddings import get_embedder

app = FastAPI(title="ReconLens")


@lru_cache
def embedder():
    return get_embedder()


class MatchRequest(BaseModel):
    text: str
    top_k: int = 5
    brand: str | None = None


@app.get("/health")
def health():
    try:
        with db.connect() as conn:
            conn.execute("SELECT 1")
        return {"status": "ok", "db": "ok", "embedding_model": embedder().model}
    except Exception:
        return JSONResponse({"status": "degraded", "db": "error", "embedding_model": embedder().model}, status_code=503)


@app.post("/match")
def match(req: MatchRequest):
    with db.connect() as conn:
        return matching.match(conn, embedder(), req.text, req.top_k, req.brand)


@app.post("/reconcile/{batch_id}")
def reconcile(batch_id: str, idempotency_key: str | None = Header(default=None)):
    emb, threshold = embedder(), config.match_threshold()
    with db.connect() as conn:
        if idempotency_key:
            row = conn.execute("SELECT response FROM api_idempotency WHERE idempotency_key = %s",
                               (idempotency_key,)).fetchone()
            if row:
                return row[0]
        lines = conn.execute("SELECT id, raw_product FROM sales_lines WHERE batch_id = %s ORDER BY id",
                             (batch_id,)).fetchall()
        if not lines:
            raise HTTPException(404, f"no sales_lines for batch {batch_id}")
        vectors = emb.embed([raw for _, raw in lines])
        matched = 0
        for (line_id, raw), vec in zip(lines, vectors, strict=True):
            cands = matching.find_candidates(conn, emb, raw, top_k=1, vec=vec)
            best = matching.pick_best(cands, threshold)
            top = cands[0] if cands else None
            matched += best is not None
            conn.execute(
                """INSERT INTO match_results (sales_line_id, batch_id, catalog_id, score, method, embedding_model)
                   VALUES (%s, %s, %s, %s, %s, %s)
                   ON CONFLICT (sales_line_id) DO UPDATE SET catalog_id = EXCLUDED.catalog_id, score = EXCLUDED.score,
                     method = EXCLUDED.method, embedding_model = EXCLUDED.embedding_model, matched_at = now()""",
                (line_id, batch_id, best["catalog_id"] if best else None, top["score"] if top else 0.0,
                 best["method"] if best else "none", emb.model))
        result = {"batch_id": batch_id, "lines": len(lines), "matched": matched,
                  "unmatched": len(lines) - matched, "embedding_model": emb.model, "threshold": threshold}
        if idempotency_key:
            conn.execute("INSERT INTO api_idempotency (idempotency_key, response) VALUES (%s, %s) "
                         "ON CONFLICT DO NOTHING", (idempotency_key, json.dumps(result)))
        conn.commit()
        return result


# ---- read-only endpoints for the UI. Money numbers come from reconciliation_report (written by the worker). ----

def _rows(sql: str, params: tuple | list = ()) -> list[dict]:
    with db.connect() as conn:
        return conn.cursor(row_factory=dict_row).execute(sql, params).fetchall()


@app.get("/batches")
def batches():
    return _rows(
        """SELECT s.batch_id, count(*) AS line_count,
                  count(m.catalog_id) AS matched, count(*) - count(m.catalog_id) AS unmatched,
                  (SELECT r.status FROM reconciliation_runs r WHERE r.batch_id = s.batch_id
                   ORDER BY r.started_at DESC LIMIT 1) AS run_status
           FROM sales_lines s LEFT JOIN match_results m ON m.sales_line_id = s.id
           GROUP BY s.batch_id ORDER BY s.batch_id""")


@app.get("/reports/{batch_id}")
def report(batch_id: str):
    return _rows("SELECT * FROM reconciliation_report WHERE batch_id = %s ORDER BY store_cnpj", (batch_id,))


@app.get("/lines/{batch_id}")
def lines(batch_id: str, status: Literal["all", "matched", "unmatched"] = "all", store_cnpj: str | None = None,
          limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0)):
    where, params = ["s.batch_id = %s"], [batch_id]
    if status != "all":
        where.append("m.catalog_id IS NOT NULL" if status == "matched" else "m.catalog_id IS NULL")
    if store_cnpj:
        where.append("s.store_cnpj = %s")
        params.append(store_cnpj)
    cond = " AND ".join(where)
    frm = ("FROM sales_lines s LEFT JOIN match_results m ON m.sales_line_id = s.id "
           "LEFT JOIN catalog c ON c.id = m.catalog_id WHERE " + cond)
    items = _rows(
        "SELECT s.id, s.source_line_id, s.store_cnpj, s.sale_date, s.raw_product, s.quantity, s.amount, "
        "c.sku, c.name, c.unit_price, c.unit_price * s.quantity AS expected_amount, m.score, m.method " + frm +
        " ORDER BY s.id LIMIT %s OFFSET %s", [*params, limit, offset])
    total = _rows("SELECT count(*) AS n " + frm, params)[0]["n"]
    return {"total": total, "limit": limit, "offset": offset, "threshold": config.match_threshold(), "items": items}


@app.get("/catalog")
def catalog(q: str = "", limit: int = Query(50, ge=1, le=500)):
    like = f"%{q}%"
    return _rows("SELECT id, sku, name, brand, ean, unit_price, active, embedding_model FROM catalog "
                 "WHERE name ILIKE %s OR sku ILIKE %s OR brand ILIKE %s ORDER BY sku LIMIT %s",
                 (like, like, like, limit))
