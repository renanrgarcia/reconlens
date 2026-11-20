"""Load data/catalog.csv into the catalog table with embeddings.

Run: python -m reconlens.seed [--reembed]
Rows are only re-embedded when new, changed, or embedded with a different model (or with --reembed).
"""

import argparse
import csv
import os
import time
from pathlib import Path

import psycopg
from pgvector import Vector

from reconlens import db
from reconlens.embeddings import get_embedder

DEFAULT_CSV = Path(__file__).resolve().parents[2] / "data" / "catalog.csv"


def connect_with_retry(seconds: int = 60) -> psycopg.Connection:
    for attempt in range(seconds):
        try:
            return db.connect()
        except psycopg.OperationalError:
            if attempt == seconds - 1:
                raise
            time.sleep(1)
    raise RuntimeError("unreachable")


def seed(csv_path: Path, reembed: bool = False) -> tuple[int, int]:
    embedder = get_embedder()
    with open(csv_path, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    with connect_with_retry() as conn:
        existing = {r[0]: r[1:] for r in conn.execute("SELECT sku, name, brand, embedding_model FROM catalog")}
        todo = [r for r in rows if reembed or existing.get(r["sku"]) != (r["name"], r["brand"], embedder.model)]
        vectors = embedder.embed([f"{r['name']} {r['brand']}" for r in todo])
        for r, vec in zip(todo, vectors, strict=True):
            conn.execute(
                """INSERT INTO catalog (sku, name, brand, ean, unit_price, embedding, embedding_model)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (sku) DO UPDATE SET name = EXCLUDED.name, brand = EXCLUDED.brand, ean = EXCLUDED.ean,
                     unit_price = EXCLUDED.unit_price, embedding = EXCLUDED.embedding,
                     embedding_model = EXCLUDED.embedding_model""",
                (r["sku"], r["name"], r["brand"], r["ean"], r["unit_price"], Vector(vec), embedder.model))
        conn.commit()
    return len(todo), len(rows)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--reembed", action="store_true", help="re-embed every row")
    ap.add_argument("--csv", default=os.environ.get("CATALOG_CSV", str(DEFAULT_CSV)))
    args = ap.parse_args()
    n, total = seed(Path(args.csv), args.reembed)
    print(f"seeded {n}/{total} catalog rows (model={get_embedder().model})")
