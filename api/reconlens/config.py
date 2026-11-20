"""Environment-driven settings, read at call time so tests can override them."""

import os

# Chosen from api/evals/run_eval.py with the local-hash-v1 embedder. Golden set (50 pairs, only 8
# negatives): 0.75 and 0.80 both give 0 false matches, recall 1.000 / 0.976. The golden negatives are
# too few to pick between them, so I cross-checked on the 1000 sales lines (77 true negatives): 0.75
# still matches 22% of the negatives, 0.80 matches 9% (recall 0.984), 0.85 matches none but recall
# falls to 0.949. A false match silently corrupts the reconciliation totals while an unmatched line
# is only flagged for review, so 0.80 is the compromise. Re-tune when switching to Azure embeddings
# (different score scale).
DEFAULT_MATCH_THRESHOLD = "0.80"
EMBEDDING_DIMS = 1536


def database_url() -> str:
    return os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/postgres")


def match_threshold() -> float:
    return float(os.environ.get("MATCH_THRESHOLD") or DEFAULT_MATCH_THRESHOLD)


def azure_embeddings_configured() -> bool:
    return all(os.environ.get(k) for k in (
        "AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_API_KEY", "AZURE_OPENAI_EMBEDDING_DEPLOYMENT"))


def azure_chat_configured() -> bool:
    return all(os.environ.get(k) for k in (
        "AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_API_KEY", "AZURE_OPENAI_CHAT_DEPLOYMENT"))
