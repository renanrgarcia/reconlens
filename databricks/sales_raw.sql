-- Delta table holding the raw sales lines the worker reads (SALES_SOURCE=databricks).
CREATE TABLE IF NOT EXISTS sales_raw (
  batch_id        STRING        NOT NULL,   -- YYYY-MM-DD
  source_line_id  STRING        NOT NULL,
  store_cnpj      STRING        NOT NULL,   -- 14 digits
  sale_date       DATE          NOT NULL,
  raw_product     STRING        NOT NULL,
  quantity        INT           NOT NULL,
  amount          DECIMAL(12,2) NOT NULL,
  true_sku        STRING                    -- ground truth for study only, the worker ignores it
) USING DELTA;

-- Upsert example keyed on (batch_id, source_line_id): re-running a load never duplicates lines.
-- `sales_staging` is any table/view with the same columns (e.g. a CSV loaded through the UI).
MERGE INTO sales_raw AS t
USING sales_staging AS s
  ON t.batch_id = s.batch_id AND t.source_line_id = s.source_line_id
WHEN MATCHED THEN UPDATE SET
  t.store_cnpj = s.store_cnpj, t.sale_date = s.sale_date, t.raw_product = s.raw_product,
  t.quantity = s.quantity, t.amount = s.amount, t.true_sku = s.true_sku
WHEN NOT MATCHED THEN INSERT *;
