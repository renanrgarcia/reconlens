import math

from reconlens.embeddings import LOCAL_MODEL, LocalEmbedder, extract_ean, hash_embed, normalize
from reconlens.matching import pick_best


def cos(a, b):
    return sum(x * y for x, y in zip(a, b, strict=True))


def test_embedder_deterministic_and_normalized():
    a, b = hash_embed("DIPIRONA SODICA 500MG 10 COMPRIMIDOS"), hash_embed("DIPIRONA SODICA 500MG 10 COMPRIMIDOS")
    assert a == b
    assert len(a) == 1536
    assert math.isclose(math.sqrt(sum(x * x for x in a)), 1.0, rel_tol=1e-9)
    assert LocalEmbedder.model == LOCAL_MODEL


def test_normalization_handles_noise():
    assert normalize("  Dipirôna   SÓDICA ") == "dipirona sodica"
    clean = hash_embed("DIPIRONA SODICA 500MG 10 COMPRIMIDOS")
    assert cos(clean, hash_embed("dipirona sod 500 mg 10 cpr")) > 0.8
    other_dose = hash_embed("DIPIRONA SODICA 1G 10 COMPRIMIDOS")
    assert cos(clean, other_dose) < cos(clean, hash_embed("dipirona 500mg 10 comp"))


def test_extract_ean():
    assert extract_ean("7891234567895 DIPIRONA") == "7891234567895"
    assert extract_ean("DIPIRONA 7891234567895") == "7891234567895"
    assert extract_ean("DIPIRONA 500MG 10 CPR") is None
    assert extract_ean("123456789012345") is None  # 15 digits is not an EAN-13


def test_ean_is_ignored_by_embedding():
    assert hash_embed("7891234567895 DIPIRONA") == hash_embed("DIPIRONA")


def test_threshold_logic():
    cands = [{"sku": "A", "score": 0.9}, {"sku": "B", "score": 0.6}]
    assert pick_best(cands, 0.8)["sku"] == "A"
    assert pick_best(cands, 0.9)["sku"] == "A"  # inclusive
    assert pick_best(cands, 0.95) is None
    assert pick_best([], 0.5) is None
