using Dapper;
using Npgsql;

namespace ReconLens.Worker;

/// <summary>Plain-SQL data access (Dapper).</summary>
public sealed class Database(NpgsqlDataSource ds)
{
    public async Task<bool> IsCompletedAsync(string key, CancellationToken ct)
    {
        await using var c = await ds.OpenConnectionAsync(ct);
        return await c.ExecuteScalarAsync<bool>(new CommandDefinition(
            "SELECT EXISTS (SELECT 1 FROM reconciliation_runs WHERE idempotency_key = @key AND status = 'completed')",
            new { key }, cancellationToken: ct));
    }

    public async Task StartRunAsync(string key, string batchId, CancellationToken ct)
    {
        await using var c = await ds.OpenConnectionAsync(ct);
        await c.ExecuteAsync(new CommandDefinition("""
            INSERT INTO reconciliation_runs (idempotency_key, batch_id, status) VALUES (@key, @batchId, 'running')
            ON CONFLICT (idempotency_key) DO UPDATE SET status = 'running', started_at = now(), completed_at = NULL
            """, new { key, batchId }, cancellationToken: ct));
    }

    public async Task FinishRunAsync(string key, string status, CancellationToken ct)
    {
        await using var c = await ds.OpenConnectionAsync(ct);
        await c.ExecuteAsync(new CommandDefinition(
            "UPDATE reconciliation_runs SET status = @status, completed_at = now() WHERE idempotency_key = @key",
            new { key, status }, cancellationToken: ct));
    }

    public async Task InsertLinesAsync(IEnumerable<SalesLine> lines, CancellationToken ct)
    {
        await using var c = await ds.OpenConnectionAsync(ct);
        await using var tx = await c.BeginTransactionAsync(ct);
        await c.ExecuteAsync(new CommandDefinition("""
            INSERT INTO sales_lines (batch_id, source_line_id, store_cnpj, sale_date, raw_product, quantity, amount)
            VALUES (@BatchId, @SourceLineId, @StoreCnpj, @SaleDate, @RawProduct, @Quantity, @Amount)
            ON CONFLICT (batch_id, source_line_id) DO NOTHING
            """, lines, tx, cancellationToken: ct));
        await tx.CommitAsync(ct);
    }

    /// <summary>Lines of the batch with the matched catalog price (null when unmatched).</summary>
    public async Task<List<CalcLine>> ReadMatchedLinesAsync(string batchId, CancellationToken ct)
    {
        await using var c = await ds.OpenConnectionAsync(ct);
        var rows = await c.QueryAsync<(string StoreCnpj, int Quantity, decimal Amount, decimal? UnitPrice)>(
            new CommandDefinition("""
            SELECT s.store_cnpj AS StoreCnpj, s.quantity AS Quantity, s.amount AS Amount, c.unit_price AS UnitPrice
            FROM sales_lines s
            LEFT JOIN match_results m ON m.sales_line_id = s.id
            LEFT JOIN catalog c ON c.id = m.catalog_id
            WHERE s.batch_id = @batchId
            """, new { batchId }, cancellationToken: ct));
        return rows.Select(r => new CalcLine(r.StoreCnpj, r.Quantity, r.Amount, r.UnitPrice)).ToList();
    }

    public async Task UpsertReportAsync(string batchId, IEnumerable<StoreReport> rows, CancellationToken ct)
    {
        await using var c = await ds.OpenConnectionAsync(ct);
        await using var tx = await c.BeginTransactionAsync(ct);
        await c.ExecuteAsync(new CommandDefinition("""
            INSERT INTO reconciliation_report (batch_id, store_cnpj, line_count, unmatched_count, reported_total,
                expected_total, matched_reported, unmatched_amount, difference, mismatched_lines)
            VALUES (@batchId, @StoreCnpj, @LineCount, @UnmatchedCount, @ReportedTotal,
                @ExpectedTotal, @MatchedReported, @UnmatchedAmount, @Difference, @MismatchedLines)
            ON CONFLICT (batch_id, store_cnpj) DO UPDATE SET
                line_count = EXCLUDED.line_count, unmatched_count = EXCLUDED.unmatched_count,
                reported_total = EXCLUDED.reported_total, expected_total = EXCLUDED.expected_total,
                matched_reported = EXCLUDED.matched_reported, unmatched_amount = EXCLUDED.unmatched_amount,
                difference = EXCLUDED.difference, mismatched_lines = EXCLUDED.mismatched_lines, computed_at = now()
            """, rows.Select(r => new
        {
            batchId,
            r.StoreCnpj,
            r.LineCount,
            r.UnmatchedCount,
            r.ReportedTotal,
            r.ExpectedTotal,
            r.MatchedReported,
            r.UnmatchedAmount,
            r.Difference,
            r.MismatchedLines,
        }), tx, cancellationToken: ct));
        await tx.CommitAsync(ct);
    }
}
