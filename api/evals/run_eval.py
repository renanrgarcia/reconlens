"""Evaluate matching against data/golden.csv.

Usage: python evals/run_eval.py [--api-url http://localhost:8000] [--golden PATH]
Needs DATABASE_URL (direct mode) or a running API (--api-url).
"""

import argparse
import csv
import json
import urllib.request
from pathlib import Path

from reconlens import config, db, matching
from reconlens.embeddings import get_embedder

GOLDEN = Path(__file__).resolve().parents[2] / "data" / "golden.csv"
SWEEP = [0.3, 0.4, 0.5, 0.6, 0.7, 0.75, 0.8, 0.85, 0.9]


def top1_scores(rows, api_url):
    """Return [(expected_sku, top1_sku, top1_score)] using the top-1 candidate (threshold applied later)."""
    out = []
    if api_url:
        for r in rows:
            req = urllib.request.Request(api_url.rstrip("/") + "/match", method="POST",
                                         data=json.dumps({"text": r["raw_product"], "top_k": 1}).encode(),
                                         headers={"Content-Type": "application/json"})
            cands = json.load(urllib.request.urlopen(req))["candidates"]
            out.append((r["expected_sku"], cands[0]["sku"] if cands else "", cands[0]["score"] if cands else 0.0))
    else:
        emb = get_embedder()
        with db.connect() as conn:
            for r in rows:
                cands = matching.find_candidates(conn, emb, r["raw_product"], top_k=1)
                out.append((r["expected_sku"], cands[0]["sku"] if cands else "", cands[0]["score"] if cands else 0.0))
    return out


def metrics(results, threshold):
    pos = [r for r in results if r[0]]
    neg = [r for r in results if not r[0]]

    def best(r):
        return r[1] if r[2] >= threshold else None

    false = [r for r in results if best(r) and best(r) != r[0]]
    return {
        "recall": sum(best(r) == r[0] for r in pos) / len(pos),
        "false_match": len(false) / len(results),
        "false_match_neg": sum(best(r) is not None for r in neg) / len(neg) if neg else 0.0,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--api-url")
    ap.add_argument("--golden", default=str(GOLDEN))
    args = ap.parse_args()
    with open(args.golden, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    results = top1_scores(rows, args.api_url)
    pos = [r for r in results if r[0]]
    p1 = sum(r[1] == r[0] for r in pos) / len(pos)
    threshold = config.match_threshold()
    m = metrics(results, threshold)
    print(f"golden pairs: {len(results)} ({len(pos)} positive, {len(results) - len(pos)} negative)")
    print(f"precision@1 (positives):          {p1:.3f}")
    print(f"threshold:                        {threshold}")
    print(f"recall at threshold:              {m['recall']:.3f}")
    print(f"false-match rate (all rows):      {m['false_match']:.3f}")
    print(f"false-match rate (negatives only): {m['false_match_neg']:.3f}")
    print("\nthreshold sweep:")
    print("  thr    recall  false_all  false_neg")
    for t in SWEEP:
        s = metrics(results, t)
        print(f"  {t:.2f}   {s['recall']:.3f}   {s['false_match']:.3f}      {s['false_match_neg']:.3f}")


if __name__ == "__main__":
    main()
