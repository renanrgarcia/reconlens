using System.Net;
using Dapper;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging.Abstractions;
using Npgsql;
using ReconLens.Worker;
using Testcontainers.PostgreSql;

namespace ReconLens.Worker.Tests;

public sealed class PgFixture : IAsyncLifetime
{
    private readonly PostgreSqlContainer _pg = new PostgreSqlBuilder("pgvector/pgvector:pg16").Build();
    public NpgsqlDataSource Ds { get; private set; } = null!;

    public async Task InitializeAsync()
    {
        await _pg.StartAsync();
        Ds = NpgsqlDataSource.Create(_pg.GetConnectionString());
        // Prefer the real schema if the Python side has already written it; fall back to the contract copy.
        var real = Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "../../../../../../db/init/001_schema.sql"));
        var schema = await File.ReadAllTextAsync(File.Exists(real) ? real : Path.Combine(AppContext.BaseDirectory, "Resources", "schema.sql"));
        await using var c = await Ds.OpenConnectionAsync();
        await c.ExecuteAsync(schema);
        await c.ExecuteAsync("""
            INSERT INTO catalog (sku, name, brand, ean, unit_price) VALUES
              ('SKU1', 'DIPIRONA 500MG', 'LAB A', '7890000000011', 5.00),
              ('SKU2', 'AMOXICILINA 500MG', 'LAB B', '7890000000028', 6.50)
            """);
    }

    public async Task DisposeAsync() { await Ds.DisposeAsync(); await _pg.DisposeAsync(); }
}

public class PipelineIntegrationTests(PgFixture fx) : IClassFixture<PgFixture>
{
    private sealed class ListSource(List<SalesLine> lines) : ISalesSource
    {
        public Task<IReadOnlyList<SalesLine>> ReadAsync(CancellationToken ct) => Task.FromResult<IReadOnlyList<SalesLine>>(lines);
    }

    /// <summary>Fake matcher API: writes match_results straight to the DB like the real /reconcile would.</summary>
    private sealed class FakeApi(NpgsqlDataSource ds, bool fail = false) : HttpMessageHandler
    {
        public int Calls;
        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
        {
            Calls++;
            if (fail) return new HttpResponseMessage(HttpStatusCode.BadRequest);
            var batch = Uri.UnescapeDataString(request.RequestUri!.Segments.Last());
            await using var c = await ds.OpenConnectionAsync(ct);
            await c.ExecuteAsync("""
                INSERT INTO match_results (sales_line_id, batch_id, catalog_id, score, method, embedding_model)
                SELECT s.id, s.batch_id,
                       CASE WHEN s.raw_product LIKE '%DIPI%' THEN (SELECT id FROM catalog WHERE sku='SKU1')
                            WHEN s.raw_product LIKE '%AMOX%' THEN (SELECT id FROM catalog WHERE sku='SKU2') END,
                       0.9, 'vector', 'test'
                FROM sales_lines s WHERE s.batch_id = @batch
                ON CONFLICT (sales_line_id) DO NOTHING
                """, new { batch });
            return new HttpResponseMessage(HttpStatusCode.OK);
        }
    }

    private ReconciliationPipeline Pipeline(List<SalesLine> lines, FakeApi api)
    {
        var s = new ServiceCollection();
        s.AddReconcileApiClient("http://api", TimeSpan.FromMilliseconds(1)).ConfigurePrimaryHttpMessageHandler(() => api);
        var client = s.BuildServiceProvider().GetRequiredService<ReconcileApiClient>();
        return new ReconciliationPipeline(new ListSource(lines), new Database(fx.Ds), client, NullLogger<ReconciliationPipeline>.Instance);
    }

    private static SalesLine L(string batch, string id, string store, string product, int qty, decimal amount) =>
        new(batch, id, store, new DateOnly(2026, 1, 2), product, qty, amount);

    [Fact]
    public async Task Reconciles_batch_writes_report_and_second_run_is_skipped()
    {
        const string batch = "2026-01-02";
        const string A = "11111111000111", B = "22222222000122";
        var lines = new List<SalesLine>
        {
            L(batch, "1", A, "DIPIRONA 500", 2, 10.00m),   // 2*5.00=10.00 ok
            L(batch, "2", A, "AMOXICILINA", 3, 20.00m),    // 3*6.50=19.50, reported 20.00 -> +0.50 mismatch
            L(batch, "3", B, "COISA ESTRANHA", 1, 7.00m),  // unmatched
        };
        var api = new FakeApi(fx.Ds);
        var pipeline = Pipeline(lines, api);

        await pipeline.RunOnceAsync(CancellationToken.None);

        await using var c = await fx.Ds.OpenConnectionAsync();
        var rows = (await c.QueryAsync("SELECT * FROM reconciliation_report WHERE batch_id=@batch ORDER BY store_cnpj", new { batch })).ToList();
        Assert.Equal(2, rows.Count);
        // A: lines 2, unmatched 0, reported 30.00, expected 10.00+19.50=29.50, matched_reported 30.00, diff 0.50, mismatched 1
        Assert.Equal((2, 0, 30.00m, 29.50m, 30.00m, 0m, 0.50m, 1),
            ((int)rows[0].line_count, (int)rows[0].unmatched_count, (decimal)rows[0].reported_total, (decimal)rows[0].expected_total,
             (decimal)rows[0].matched_reported, (decimal)rows[0].unmatched_amount, (decimal)rows[0].difference, (int)rows[0].mismatched_lines));
        // B: lines 1, unmatched 1, reported 7.00, expected 0, matched_reported 0, unmatched 7.00, diff 0, mismatched 0
        Assert.Equal((1, 1, 7.00m, 0m, 0m, 7.00m, 0m, 0),
            ((int)rows[1].line_count, (int)rows[1].unmatched_count, (decimal)rows[1].reported_total, (decimal)rows[1].expected_total,
             (decimal)rows[1].matched_reported, (decimal)rows[1].unmatched_amount, (decimal)rows[1].difference, (int)rows[1].mismatched_lines));
        Assert.Equal(1, api.Calls);

        // Second pass with identical data: skipped, no API call, still exactly one completed run.
        await pipeline.RunOnceAsync(CancellationToken.None);
        Assert.Equal(1, api.Calls);
        var runs = (await c.QueryAsync<string>("SELECT status FROM reconciliation_runs WHERE batch_id=@batch", new { batch })).ToList();
        Assert.Equal(["completed"], runs);
        Assert.Equal(3, await c.ExecuteScalarAsync<int>("SELECT count(*) FROM sales_lines WHERE batch_id=@batch", new { batch }));
    }

    [Fact]
    public async Task Failed_batch_is_marked_failed_and_retried_next_pass()
    {
        const string batch = "2026-01-04";
        var lines = new List<SalesLine> { L(batch, "1", "11111111000111", "DIPIRONA", 1, 5.00m) };

        await Pipeline(lines, new FakeApi(fx.Ds, fail: true)).RunOnceAsync(CancellationToken.None); // does not throw
        await using var c = await fx.Ds.OpenConnectionAsync();
        Assert.Equal("failed", await c.ExecuteScalarAsync<string>("SELECT status FROM reconciliation_runs WHERE batch_id=@batch", new { batch }));

        var ok = new FakeApi(fx.Ds);
        await Pipeline(lines, ok).RunOnceAsync(CancellationToken.None);
        Assert.Equal(1, ok.Calls);
        Assert.Equal("completed", await c.ExecuteScalarAsync<string>("SELECT status FROM reconciliation_runs WHERE batch_id=@batch", new { batch }));
    }
}
