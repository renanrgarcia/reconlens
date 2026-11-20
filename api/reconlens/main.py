import json
from functools import lru_cache

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
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
