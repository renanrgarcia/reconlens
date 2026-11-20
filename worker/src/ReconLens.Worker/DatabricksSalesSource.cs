using System.Globalization;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Text.Json;

namespace ReconLens.Worker;

/// <summary>
/// Reads sales_raw through the Databricks SQL Statement Execution API.
/// NOT tested against a real workspace (no Databricks available in this project's environment).
/// </summary>
public sealed class DatabricksSalesSource(HttpClient http, string host, string token, string warehouseId) : ISalesSource
{
    private const string Sql = "SELECT batch_id, source_line_id, store_cnpj, sale_date, raw_product, quantity, amount FROM sales_raw";

    public async Task<IReadOnlyList<SalesLine>> ReadAsync(CancellationToken ct)
    {
        var baseUrl = host.TrimEnd('/');
        if (!baseUrl.StartsWith("http", StringComparison.OrdinalIgnoreCase)) baseUrl = "https://" + baseUrl;
        http.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", token);

        var resp = await http.PostAsJsonAsync($"{baseUrl}/api/2.0/sql/statements",
            new { warehouse_id = warehouseId, statement = Sql, wait_timeout = "30s" }, ct);
        resp.EnsureSuccessStatusCode();
        var doc = await JsonDocument.ParseAsync(await resp.Content.ReadAsStreamAsync(ct), cancellationToken: ct);

        // wait_timeout elapsed while still queued/running: poll until terminal.
        while (State(doc) is "PENDING" or "RUNNING")
        {
            await Task.Delay(TimeSpan.FromSeconds(2), ct);
            var id = doc.RootElement.GetProperty("statement_id").GetString();
            var poll = await http.GetAsync($"{baseUrl}/api/2.0/sql/statements/{id}", ct);
            poll.EnsureSuccessStatusCode();
            doc = await JsonDocument.ParseAsync(await poll.Content.ReadAsStreamAsync(ct), cancellationToken: ct);
        }
        if (State(doc) != "SUCCEEDED")
            throw new InvalidOperationException($"Databricks statement ended as {State(doc)}: {doc.RootElement.GetProperty("status")}");

        return Parse(doc.RootElement);
    }

    private static string? State(JsonDocument d) => d.RootElement.GetProperty("status").GetProperty("state").GetString();

    internal static List<SalesLine> Parse(JsonElement root)
    {
        var cols = root.GetProperty("manifest").GetProperty("schema").GetProperty("columns")
            .EnumerateArray().Select((c, i) => (Name: c.GetProperty("name").GetString()!, Index: i))
            .ToDictionary(x => x.Name, x => x.Index);
        if (!root.TryGetProperty("result", out var result) || !result.TryGetProperty("data_array", out var data))
            return [];

        // data_array values are strings (or null) regardless of column type.
        return data.EnumerateArray().Select(row =>
        {
            string V(string n) => row[cols[n]].GetString() ?? throw new InvalidDataException($"null {n}");
            return new SalesLine(V("batch_id"), V("source_line_id"), V("store_cnpj"),
                DateOnly.Parse(V("sale_date"), CultureInfo.InvariantCulture), V("raw_product"),
                int.Parse(V("quantity"), CultureInfo.InvariantCulture),
                decimal.Parse(V("amount"), NumberStyles.Number, CultureInfo.InvariantCulture));
        }).ToList();
    }
}
