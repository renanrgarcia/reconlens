"""Deterministic data generator: catalog.csv, sales.csv, golden.csv.

Run: python -m reconlens.datagen   (writes ../data/*.csv, overwriting)
"""

import csv
import random
from datetime import date, timedelta
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
CATALOG_SEED, SALES_SEED, GOLDEN_SEED = 1, 42, 7  # golden deliberately differs from sales

BRANDS = ["EMS", "MEDLEY", "EUROFARMA", "GERMED", "NEO QUIMICA", "ACHE", "BIOLAB", "SANDOZ",
          "PRATI DONADUZZI", "CIMED", "HYPERA", "LEGRAND", "TEUTO", "BRAINFARMA", "SANOFI"]

# kind: cpr | cap | efv (solid, packs of N) ; gts | susp | xpe (liquid, volume in ml)
DRUGS = [
    ("DIPIRONA SODICA", "cpr", ["500MG", "1G"], [10, 20, 30]),
    ("PARACETAMOL", "cpr", ["500MG", "750MG"], [10, 20, 30]),
    ("IBUPROFENO", "cpr", ["200MG", "400MG", "600MG"], [10, 20, 30]),
    ("LOSARTANA POTASSICA", "cpr", ["25MG", "50MG", "100MG"], [30, 60]),
    ("METFORMINA CLORIDRATO", "cpr", ["500MG", "850MG", "1000MG"], [30, 60]),
    ("ATENOLOL", "cpr", ["25MG", "50MG", "100MG"], [30, 60]),
    ("SINVASTATINA", "cpr", ["10MG", "20MG", "40MG"], [10, 30]),
    ("LORATADINA", "cpr", ["10MG"], [12, 30]),
    ("CETIRIZINA", "cpr", ["10MG"], [10, 12]),
    ("DICLOFENACO SODICO", "cpr", ["50MG", "100MG"], [10, 20]),
    ("DICLOFENACO POTASSICO", "cpr", ["50MG"], [10, 20]),
    ("AZITROMICINA", "cpr", ["500MG"], [3, 5]),
    ("CIPROFLOXACINO", "cpr", ["250MG", "500MG"], [7, 14]),
    ("PREDNISONA", "cpr", ["5MG", "20MG"], [10, 20]),
    ("CAPTOPRIL", "cpr", ["25MG", "50MG"], [30, 60]),
    ("ENALAPRIL MALEATO", "cpr", ["5MG", "10MG", "20MG"], [30, 60]),
    ("HIDROCLOROTIAZIDA", "cpr", ["25MG", "50MG"], [30]),
    ("ANLODIPINO BESILATO", "cpr", ["5MG", "10MG"], [30, 60]),
    ("ATORVASTATINA CALCICA", "cpr", ["10MG", "20MG", "40MG", "80MG"], [30]),
    ("LEVOTIROXINA SODICA", "cpr", ["25MCG", "50MCG", "75MCG", "100MCG"], [30, 50]),
    ("NIMESULIDA", "cpr", ["100MG"], [12, 24]),
    ("VITAMINA C", "efv", ["500MG", "1G"], [10, 16]),
    ("AMOXICILINA", "cap", ["500MG"], [15, 21]),
    ("OMEPRAZOL", "cap", ["10MG", "20MG", "40MG"], [14, 28]),
    ("FLUCONAZOL", "cap", ["150MG"], [1, 2]),
    ("CEFALEXINA", "cap", ["500MG"], [8, 16]),
    ("ESOMEPRAZOL MAGNESICO", "cap", ["20MG", "40MG"], [14, 28]),
    ("DIPIRONA SODICA", "gts", ["500MG/ML"], [10, 20]),
    ("PARACETAMOL", "gts", ["200MG/ML"], [15, 20]),
    ("IBUPROFENO", "gts", ["50MG/ML", "100MG/ML"], [20, 30]),
    ("AMOXICILINA", "susp", ["250MG/5ML", "500MG/5ML"], [60, 150]),
    ("AMBROXOL", "xpe", ["15MG/5ML", "30MG/5ML"], [100, 120]),
    ("LORATADINA", "xpe", ["1MG/ML"], [60, 100]),
]
# add two bigger packs to every solid so the catalog has many near-identical neighbours
DRUGS = [(d, k, ds, ps + [ps[-1] * 2, ps[-1] * 3] if k in ("cpr", "cap", "efv") else ps) for d, k, ds, ps in DRUGS]
# Products that are never in the catalog (used for the ~8% unmatched lines and golden negatives)
OFF_CATALOG = [
    ("RIVAROXABANA", "cpr", ["15MG", "20MG"], [14, 28]),
    ("VARFARINA SODICA", "cpr", ["2,5MG", "5MG"], [30]),
    ("DOMPERIDONA", "cpr", ["10MG"], [20, 30]),
    ("BROMOPRIDA", "cpr", ["10MG"], [20]),
    ("DEXAMETASONA", "cpr", ["4MG"], [10, 20]),
    ("FUROSEMIDA", "cpr", ["40MG"], [20, 30]),
    ("ESPIRONOLACTONA", "cpr", ["25MG", "100MG"], [30]),
    ("GLIBENCLAMIDA", "cpr", ["5MG"], [30]),
    ("CARVEDILOL", "cpr", ["6,25MG", "12,5MG"], [30]),
    ("PROPRANOLOL", "cpr", ["40MG"], [30]),
    ("ALENDRONATO SODICO", "cpr", ["70MG"], [4]),
    ("SERTRALINA", "cpr", ["50MG"], [30]),
    ("ACIDO FOLICO", "cpr", ["5MG"], [30]),
    ("DOXICICLINA", "cap", ["100MG"], [10, 15]),
    ("PANTOPRAZOL", "cpr", ["20MG", "40MG"], [14, 28]),
    ("SECNIDAZOL", "cpr", ["1G"], [4]),
    ("METOCLOPRAMIDA", "gts", ["4MG/ML"], [10]),
    ("SALBUTAMOL", "xpe", ["2MG/5ML"], [100]),
    ("NISTATINA", "susp", ["100000UI/ML"], [50]),
    ("PREDNISOLONA", "gts", ["11MG/ML"], [20]),
]
FORM = {"cpr": "COMPRIMIDOS", "cap": "CAPSULAS", "efv": "COMPRIMIDOS EFERVESCENTES",
        "gts": "SOLUCAO ORAL GOTAS", "susp": "SUSPENSAO ORAL", "xpe": "XAROPE"}
FORM_ABBR = {"COMPRIMIDOS": ["CPR", "COMP", "CPRS", "CP", "COMPR"], "CAPSULAS": ["CAPS", "CAP", "CPS"],
             "COMPRIMIDOS EFERVESCENTES": ["CPR EFERV", "COMP EF"],
             "SOLUCAO ORAL GOTAS": ["SOL ORAL GTS", "GTS", "SOL ORAL"],
             "SUSPENSAO ORAL": ["SUSP ORAL", "SUSP"], "XAROPE": ["XPE", "XAR"]}
WORD_ABBR = {"SODICA": "SOD", "POTASSICA": "POT", "CLORIDRATO": "CLOR", "POTASSICO": "POT",
             "SODICO": "SOD", "BESILATO": "BESIL", "MALEATO": "MAL", "CALCICA": "CALC", "MAGNESICO": "MAG"}


def combos(drugs):
    for drug, kind, doses, packs in drugs:
        for dose in doses:
            for pack in packs:
                yield drug, kind, dose, pack


def name_of(drug, kind, dose, pack):
    if kind in ("cpr", "cap", "efv"):
        return f"{drug} {dose} {pack} {FORM[kind]}"
    return f"{drug} {dose} {FORM[kind]} {pack}ML"


def make_catalog(rng, n=200):
    items = rng.sample(list(combos(DRUGS)), n)
    items.sort(key=lambda c: (c[0], c[1], c[2], c[3]))
    rows, used_ean = [], set()
    for i, (drug, kind, dose, pack) in enumerate(items, 1):
        while True:
            body = "789" + "".join(str(rng.randrange(10)) for _ in range(9))
            check = (10 - sum(int(d) * (3 if j % 2 else 1) for j, d in enumerate(body)) % 10) % 10
            ean = body + str(check)
            if ean not in used_ean:
                used_ean.add(ean)
                break
        price = round(rng.uniform(4, 95), 2)
        rows.append({"sku": f"SKU{i:04d}", "name": name_of(drug, kind, dose, pack), "brand": rng.choice(BRANDS),
                     "ean": ean, "unit_price": f"{price:.2f}", "_item": (drug, kind, dose, pack)})
    return rows


def typo(rng, word):
    if len(word) < 4 or not word.isalpha():
        return word
    i = rng.randrange(1, len(word) - 1)
    if rng.random() < 0.5:
        return word[:i] + word[i + 1:]  # drop a char
    return word[:i] + word[i + 1] + word[i] + word[i + 2:]  # swap neighbours


def noisy_line(rng, drug, kind, dose, pack, brand, ean=None):
    """Turn a clean product into a messy sales-line text."""
    form = FORM[kind]
    drug_words = []
    for w in drug.split():
        if w in WORD_ABBR and rng.random() < 0.5:
            w = WORD_ABBR[w]
        drug_words.append(w)
    if rng.random() < 0.2:  # truncate the head word: "DIPIR"
        drug_words[0] = drug_words[0][: rng.randint(5, 7)]
    if len(drug_words) > 1 and rng.random() < 0.15:
        drug_words = drug_words[:1]  # drop qualifier
    dose_txt = rng.choice([dose, dose, dose.replace("MG", " MG").replace("MCG", " MCG"), dose.lower()])
    form_txt = rng.choice(FORM_ABBR[form]) if rng.random() < 0.7 else form
    if kind in ("cpr", "cap", "efv"):
        pack_txt = rng.choice([f"{pack} {form_txt}", f"{pack}{form_txt}", f"{form_txt} {pack}", f"C/{pack} {form_txt}",
                               f"CX {pack} {form_txt}"])
    else:
        pack_txt = rng.choice([f"{form_txt} {pack}ML", f"{form_txt} {pack} ML", f"{pack}ML {form_txt}"])
    chunks = [" ".join(drug_words), dose_txt, pack_txt]
    if rng.random() < 0.4:
        b = brand if rng.random() < 0.6 else brand.split()[0]
        chunks.append(b)
    if rng.random() < 0.2:
        rng.shuffle(chunks)
    words = " ".join(chunks).split()
    if rng.random() < 0.35:
        k = rng.randrange(len(words))
        words[k] = typo(rng, words[k])
    text = " ".join(words)
    text = rng.choice([text, text, text.lower(), text.title()])
    if ean:
        text = rng.choice([f"{ean} {text}", f"{text} {ean}", f"{ean} {drug_words[0]}"])
    return text


def make_lines(rng, n, catalog, miss_rate=0.08):
    """Yield (raw_product, true_sku, unit_price) with ~miss_rate off-catalog products."""
    out = []
    for _ in range(n):
        if rng.random() < miss_rate:
            drug, kind, dose, pack = rng.choice(list(combos(OFF_CATALOG)))
            raw = noisy_line(rng, drug, kind, dose, pack, rng.choice(BRANDS))
            out.append((raw, "", round(rng.uniform(5, 120), 2)))
        else:
            c = rng.choice(catalog)
            ean = c["ean"] if rng.random() < 0.10 else None
            raw = noisy_line(rng, *c["_item"], c["brand"], ean)
            out.append((raw, c["sku"], float(c["unit_price"])))
    return out


def write_csv(path, fields, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def main():
    DATA_DIR.mkdir(exist_ok=True)
    catalog = make_catalog(random.Random(CATALOG_SEED))
    write_csv(DATA_DIR / "catalog.csv", ["sku", "name", "brand", "ean", "unit_price"], catalog)

    rng = random.Random(SALES_SEED)
    cnpjs = [f"{rng.randrange(10**7, 10**8)}0001{rng.randrange(10, 100)}" for _ in range(8)]
    days = [date(2026, 11, 10) + timedelta(days=i) for i in range(5)]
    sales = []
    for i, (raw, sku, price) in enumerate(make_lines(rng, 1000, catalog), 1):
        qty = rng.choice([1, 1, 1, 2, 2, 3, 4, 5, 6])
        amount = round(qty * price, 2)
        if sku and rng.random() < 0.08:  # discount / pricing error
            amount = round(amount * rng.choice([0.85, 0.9, 0.95, 1.05, 1.1]), 2)
            if abs(amount - qty * price) <= 0.01:
                amount += 0.5
        d = rng.choice(days).isoformat()
        sales.append({"batch_id": d, "source_line_id": f"L{i:05d}", "store_cnpj": rng.choice(cnpjs),
                      "sale_date": d, "raw_product": raw, "quantity": qty, "amount": f"{amount:.2f}", "true_sku": sku})
    sales.sort(key=lambda r: (r["batch_id"], r["source_line_id"]))
    write_csv(DATA_DIR / "sales.csv", ["batch_id", "source_line_id", "store_cnpj", "sale_date", "raw_product",
                                       "quantity", "amount", "true_sku"], sales)

    grng = random.Random(GOLDEN_SEED)
    golden = [{"raw_product": r, "expected_sku": s} for r, s, _ in make_lines(grng, 42, catalog, miss_rate=0)]
    golden += [{"raw_product": r, "expected_sku": ""} for r, _, _ in make_lines(grng, 8, catalog, miss_rate=1)]
    grng.shuffle(golden)
    write_csv(DATA_DIR / "golden.csv", ["raw_product", "expected_sku"], golden)
    print(f"catalog={len(catalog)} sales={len(sales)} golden={len(golden)} -> {DATA_DIR}")


if __name__ == "__main__":
    main()
