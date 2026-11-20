# Databricks (optional)

Alternative sales source for the worker (`SALES_SOURCE=databricks`). It reads `sales_raw` through the
SQL Statement Execution API, so you only need a table and a SQL warehouse.

## Load `data/sales.csv` into Databricks Free Edition

1. Create the table: run `sales_raw.sql` (the `CREATE TABLE` part) in the SQL editor.
2. Upload the CSV: **Catalog > Create > Table > Upload file**, pick `data/sales.csv`, and create it as
   `sales_staging` (set `quantity` to INT, `amount` to DECIMAL(12,2), `sale_date` to DATE).
3. Run the `MERGE INTO` from `sales_raw.sql` to move staging into `sales_raw`. Re-running is safe.
4. Check: `SELECT batch_id, count(*) FROM sales_raw GROUP BY batch_id;` should show 5 batches, ~1000 lines.

## Worker settings

```
SALES_SOURCE=databricks
DATABRICKS_HOST=<workspace host, no https://>
DATABRICKS_TOKEN=<personal access token>
DATABRICKS_WAREHOUSE_ID=<SQL warehouse id>
```

Free Edition has no classic compute, so use the serverless SQL warehouse it provides. Never commit the token.
