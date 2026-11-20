"""Needs a seeded Postgres: DATABASE_URL=... python -m reconlens.seed first. Skipped when unset."""

import csv
import os
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not set")

with open(Path(__file__).resolve().parents[2] / "data" / "catalog.csv", encoding="utf-8") as f:
    CATALOG = list(csv.DictReader(f))


@pytest.fixture(scope="module")
def client():
    from reconlens.main import app

    return TestClient(app)


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["db"] == "ok"


def test_match_clean_names_return_own_sku(client):
    for row in CATALOG[:3]:
        body = client.post("/match", json={"text": row["name"] + " " + row["brand"]}).json()
        assert body["best"]["sku"] == row["sku"]
        assert "unit_price" not in body["best"]


def test_match_ean_exact(client):
    row = CATALOG[10]
    body = client.post("/match", json={"text": f"qualquer coisa {row['ean']}"}).json()
    assert body["best"]["sku"] == row["sku"]
    assert body["best"]["method"] == "ean_exact" and body["best"]["score"] == 1.0


def test_match_unknown_product_is_below_threshold(client):
    body = client.post("/match", json={"text": "RIVAROXABANA 20MG 28 COMPRIMIDOS"}).json()
    assert body["best"] is None and body["candidates"]


def test_reconcile_idempotency_replay(client):
    import psycopg

    batch = f"pytest-{uuid.uuid4().hex[:8]}"
    row = CATALOG[0]
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        conn.execute("INSERT INTO sales_lines (batch_id, source_line_id, store_cnpj, sale_date, raw_product, "
                     "quantity, amount) VALUES (%s, 'L1', '12345678000190', '2026-11-10', %s, 1, 10.00)",
                     (batch, row["name"]))
    assert client.post(f"/reconcile/{batch}").status_code == 200
    key = f"key-{batch}"
    first = client.post(f"/reconcile/{batch}", headers={"Idempotency-Key": key}).json()
    assert first["lines"] == 1 and first["matched"] == 1
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        conn.execute("DELETE FROM match_results WHERE batch_id = %s", (batch,))
    replay = client.post(f"/reconcile/{batch}", headers={"Idempotency-Key": key}).json()
    assert replay == first
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        # replay did no work: match_results stays empty
        assert conn.execute("SELECT count(*) FROM match_results WHERE batch_id = %s", (batch,)).fetchone()[0] == 0


def test_reconcile_unknown_batch_404(client):
    assert client.post("/reconcile/no-such-batch").status_code == 404


def test_catalog_search_and_limit(client):
    row = CATALOG[0]
    body = client.get("/catalog", params={"q": row["sku"].lower(), "limit": 5}).json()
    assert [r["sku"] for r in body] == [row["sku"]]
    assert "embedding" not in body[0]
    assert len(client.get("/catalog", params={"limit": 3}).json()) == 3


def test_batches_lines_and_reports(client):
    import psycopg

    batch = f"pytest-{uuid.uuid4().hex[:8]}"
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        for i, raw in enumerate([CATALOG[0]["name"], "ZZZ NOT A PRODUCT QQQ"]):
            conn.execute("INSERT INTO sales_lines (batch_id, source_line_id, store_cnpj, sale_date, raw_product, "
                         "quantity, amount) VALUES (%s, %s, '12345678000190', '2026-11-10', %s, 2, 10.00)",
                         (batch, f"L{i}", raw))
    assert client.post(f"/reconcile/{batch}").json()["lines"] == 2

    listed = {b["batch_id"]: b for b in client.get("/batches").json()}
    assert listed[batch]["line_count"] == 2
    assert listed[batch]["matched"] + listed[batch]["unmatched"] == 2
    assert listed[batch]["run_status"] is None  # only the worker writes reconciliation_runs

    everything = client.get(f"/lines/{batch}").json()
    assert everything["total"] == 2 and everything["threshold"] > 0
    matched = client.get(f"/lines/{batch}", params={"status": "matched"}).json()["items"]
    assert [m["sku"] for m in matched] == [CATALOG[0]["sku"]]
    assert float(matched[0]["expected_amount"]) == float(matched[0]["unit_price"]) * 2
    unmatched = client.get(f"/lines/{batch}", params={"status": "unmatched"}).json()["items"]
    assert len(unmatched) == 1 and unmatched[0]["sku"] is None
    assert client.get(f"/lines/{batch}", params={"store_cnpj": "000"}).json()["total"] == 0
    page = client.get(f"/lines/{batch}", params={"limit": 1, "offset": 1}).json()
    assert page["total"] == 2 and len(page["items"]) == 1
    assert client.get(f"/lines/{batch}", params={"status": "bogus"}).status_code == 422

    assert client.get(f"/reports/{batch}").json() == []
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        conn.execute("INSERT INTO reconciliation_report VALUES (%s, '12345678000190', 2, 1, 20, 10, 10, 10, 0, 0)",
                     (batch,))
    rep = client.get(f"/reports/{batch}").json()
    assert len(rep) == 1 and rep[0]["store_cnpj"] == "12345678000190" and float(rep[0]["reported_total"]) == 20
