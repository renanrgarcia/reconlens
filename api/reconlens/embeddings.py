"""Embedders: Azure OpenAI text-embedding-3-small when configured, else offline local-hash-v1."""

import hashlib
import math
import os
import re
import unicodedata

from reconlens import config

LOCAL_MODEL = "local-hash-v1"
AZURE_MODEL = "text-embedding-3-small"

EAN_RE = re.compile(r"(?<!\d)\d{13}(?!\d)")
# number + unit glued into one token ("500 mg" -> "500mg", "250mg / 5 ml" -> "250mg/5ml")
DOSE_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(mg|mcg|g|ml|ui)(?![a-z])(?:\s*/\s*(\d*)\s*(ml))?")
ABBR = {
    "cpr": "comprimido", "cprs": "comprimido", "comp": "comprimido", "compr": "comprimido", "cp": "comprimido",
    "comprimidos": "comprimido", "caps": "capsula", "cap": "capsula", "cps": "capsula", "capsulas": "capsula",
    "sol": "solucao", "gts": "gotas", "gt": "gotas", "susp": "suspensao", "xpe": "xarope", "xar": "xarope",
    "sod": "sodica", "pot": "potassica", "clor": "cloridrato", "mag": "magnesico", "calc": "calcica",
    "mal": "maleato", "besil": "besilato", "eferv": "efervescente", "ef": "efervescente",
    "efervescentes": "efervescente",
}
STOP = {"c", "cx", "de", "com", "da", "do", "e"}
# feature weights: doses and pack counts decide between near-identical catalog rows
W_WORD, W_TRIGRAM, W_DOSE, W_NUMBER = 1.0, 0.4, 3.0, 2.0


def extract_ean(text: str) -> str | None:
    m = EAN_RE.search(text)
    return m.group(0) if m else None


def normalize(text: str) -> str:
    text = EAN_RE.sub(" ", text)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", text).strip()


def features(text: str) -> dict[str, float]:
    text = normalize(text)
    feats: dict[str, float] = {}

    def add(key: str, w: float) -> None:
        feats[key] = feats.get(key, 0.0) + w

    for m in DOSE_RE.finditer(text):
        num, unit, den, den_unit = m.groups()
        tok = num.replace(",", ".") + unit + (f"/{den}{den_unit}" if den_unit else "")
        add("d:" + tok, W_DOSE)
    rest = DOSE_RE.sub(" ", text)
    for tok in re.findall(r"[a-z]+|\d+", rest):
        if tok in STOP:
            continue
        if tok.isdigit():
            add("n:" + tok, W_NUMBER)
            continue
        tok = ABBR.get(tok, tok)
        add("w:" + tok, W_WORD)
        padded = f"^{tok}$"
        for i in range(len(padded) - 2):
            add("t:" + padded[i:i + 3], W_TRIGRAM)
    return feats


def hash_embed(text: str, dims: int = config.EMBEDDING_DIMS) -> list[float]:
    vec = [0.0] * dims
    for key, w in features(text).items():
        h = int.from_bytes(hashlib.blake2b(key.encode(), digest_size=8).digest(), "big")
        vec[h % dims] += w if (h >> 63) & 1 else -w
    norm = math.sqrt(sum(v * v for v in vec))
    return [v / norm for v in vec] if norm else vec


class LocalEmbedder:
    model = LOCAL_MODEL

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [hash_embed(t) for t in texts]


class AzureEmbedder:
    model = AZURE_MODEL

    def __init__(self) -> None:
        from openai import AzureOpenAI

        self._client = AzureOpenAI(
            azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
            api_key=os.environ["AZURE_OPENAI_API_KEY"],
            api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2024-10-21"),
        )
        self._deployment = os.environ["AZURE_OPENAI_EMBEDDING_DEPLOYMENT"]

    def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), 64):
            batch = [normalize(t) or " " for t in texts[i : i + 64]]
            resp = self._client.embeddings.create(model=self._deployment, input=batch)
            out += [d.embedding for d in resp.data]
        return out


def get_embedder() -> LocalEmbedder | AzureEmbedder:
    return AzureEmbedder() if config.azure_embeddings_configured() else LocalEmbedder()
