using System.Text.Json;
using ReconLens.Worker;

namespace ReconLens.Worker.Tests;

public class SourceAndKeyTests
{
    private static SalesLine L(string id, decimal amount = 10m) =>
        new("2026-01-02", id, "11111111000111", new DateOnly(2026, 1, 2), "X", 1, amount);

    [Fact]
    public void Key_ignores_line_order()
    {
        Assert.Equal(IdempotencyKey.For("b", [L("1"), L("2")]), IdempotencyKey.For("b", [L("2"), L("1")]));
    }

    [Fact]
    public void Key_changes_when_amount_or_batch_changes()
    {
        var k = IdempotencyKey.For("b", [L("1"), L("2")]);
        Assert.NotEqual(k, IdempotencyKey.For("b", [L("1"), L("2", 10.01m)]));
        Assert.NotEqual(k, IdempotencyKey.For("c", [L("1"), L("2")]));
        Assert.Equal(64, k.Length);
    }

    [Fact]
    public async Task Csv_source_reads_quoted_fields_and_ignores_true_sku()
    {
        var lines = await new CsvSalesSource(Path.Combine(AppContext.BaseDirectory, "fixtures", "sales.csv"))
            .ReadAsync(CancellationToken.None);
        Assert.Equal(3, lines.Count);
        Assert.Equal("DIPIRONA 500MG, 10 CP", lines[0].RawProduct);
        Assert.Equal("AMOXICILINA \"500\"", lines[2].RawProduct);
        Assert.Equal(7.50m, lines[1].Amount);
        Assert.Equal(new DateOnly(2026, 1, 3), lines[2].SaleDate);
    }

    [Fact]
    public void Database_url_uri_is_converted()
    {
        var cs = WorkerOptions.ToConnectionString("postgresql://u:p%40ss@db:5433/recon");
        Assert.Contains("Host=db", cs);
        Assert.Contains("Port=5433", cs);
        Assert.Contains("Username=u", cs);
        Assert.Contains("Password=p@ss", cs);
        Assert.Contains("Database=recon", cs);
        Assert.Equal("Host=x;Database=y", WorkerOptions.ToConnectionString("Host=x;Database=y"));
    }

    [Fact]
    public void Databricks_response_is_parsed_by_manifest_column_names()
    {
        // Columns deliberately out of order; values are strings in data_array.
        const string json = """
        {"status":{"state":"SUCCEEDED"},
         "manifest":{"schema":{"columns":[{"name":"amount"},{"name":"batch_id"},{"name":"source_line_id"},{"name":"store_cnpj"},
           {"name":"sale_date"},{"name":"raw_product"},{"name":"quantity"}]}},
         "result":{"data_array":[["12.30","2026-01-02","S1","11111111000111","2026-01-02","DIPIRONA","2"]]}}
        """;
        var line = Assert.Single(DatabricksSalesSource.Parse(JsonDocument.Parse(json).RootElement));
        Assert.Equal(new SalesLine("2026-01-02", "S1", "11111111000111", new DateOnly(2026, 1, 2), "DIPIRONA", 2, 12.30m), line);
    }
}
