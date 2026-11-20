using Microsoft.Extensions.Logging;

namespace ReconLens.Worker;

public sealed class ReconciliationPipeline(
    ISalesSource source, Database db, ReconcileApiClient api, ILogger<ReconciliationPipeline> log)
{
    public async Task RunOnceAsync(CancellationToken ct)
    {
        var lines = await source.ReadAsync(ct);
        foreach (var batch in lines.GroupBy(l => l.BatchId).OrderBy(g => g.Key, StringComparer.Ordinal))
        {
            try { await RunBatchAsync(batch.Key, batch.ToList(), ct); }
            catch (Exception ex) when (ex is not OperationCanceledException)
            {
                log.LogError(ex, "Batch {Batch} failed", batch.Key);
            }
        }
    }

    private async Task RunBatchAsync(string batchId, List<SalesLine> lines, CancellationToken ct)
    {
        var key = IdempotencyKey.For(batchId, lines);
        if (await db.IsCompletedAsync(key, ct))
        {
            log.LogInformation("Batch {Batch}: skipped, already reconciled", batchId);
            return;
        }

        await db.StartRunAsync(key, batchId, ct);
        try
        {
            await db.InsertLinesAsync(lines, ct);
            await api.ReconcileAsync(batchId, key, ct);
            var report = ReconciliationCalculator.Compute(await db.ReadMatchedLinesAsync(batchId, ct));
            await db.UpsertReportAsync(batchId, report, ct);
            await db.FinishRunAsync(key, "completed", ct);
            foreach (var r in report)
                log.LogInformation(
                    "Batch {Batch} store {Store}: lines={Lines} unmatched={Unmatched} reported={Reported} expected={Expected} diff={Diff} mismatched={Mismatched}",
                    batchId, r.StoreCnpj, r.LineCount, r.UnmatchedCount, r.ReportedTotal, r.ExpectedTotal, r.Difference, r.MismatchedLines);
        }
        catch
        {
            await db.FinishRunAsync(key, "failed", CancellationToken.None);
            throw;
        }
    }
}
