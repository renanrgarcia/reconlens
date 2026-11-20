"""Hybrid matching: exact EAN short-circuit, then cosine search over pgvector with exact filters."""

from pgvector import Vector

from reconlens import config
from reconlens.embeddings import extract_ean


def pick_best(candidates: list[dict], threshold: float) -> dict | None:
    """First candidate (list is score-ordered) at or above the threshold."""
    return next((c for c in candidates if c["score"] >= threshold), None)


def find_candidates(conn, embedder, text: str, top_k: int = 5, brand: str | None = None,
                    vec: list[float] | None = None) -> list[dict]:
    ean = extract_ean(text)
    if ean:
        row = conn.execute("SELECT id, sku, name, brand FROM catalog WHERE ean = %s AND active", (ean,)).fetchone()
        if row:
            return [{"catalog_id": row[0], "sku": row[1], "name": row[2], "brand": row[3],
                     "score": 1.0, "method": "ean_exact"}]
    q = Vector(vec if vec is not None else embedder.embed([text])[0])
    sql = ("SELECT id, sku, name, brand, 1 - (embedding <=> %s) AS score FROM catalog "
           "WHERE active = true AND embedding_model = %s")
    params: list = [q, embedder.model]
    if brand:
        sql += " AND brand = %s"
        params.append(brand)
    sql += " ORDER BY embedding <=> %s LIMIT %s"
    params += [q, top_k]
    return [{"catalog_id": r[0], "sku": r[1], "name": r[2], "brand": r[3], "score": float(r[4]), "method": "vector"}
            for r in conn.execute(sql, params).fetchall()]


def match(conn, embedder, text: str, top_k: int = 5, brand: str | None = None,
          threshold: float | None = None, vec: list[float] | None = None) -> dict:
    threshold = config.match_threshold() if threshold is None else threshold
    candidates = find_candidates(conn, embedder, text, top_k, brand, vec)
    return {"query": text, "embedding_model": embedder.model, "threshold": threshold,
            "best": pick_best(candidates, threshold), "candidates": candidates}
