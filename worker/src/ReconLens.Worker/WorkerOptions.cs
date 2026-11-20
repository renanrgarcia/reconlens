using Npgsql;

namespace ReconLens.Worker;

/// <summary>Env-driven configuration (names fixed by docs/CONTRACT.md).</summary>
public sealed record WorkerOptions(
    string ConnectionString,
    string ApiBaseUrl,
    string SalesSource,
    string SalesCsvPath,
    int ScheduleSeconds,
    string DatabricksHost,
    string DatabricksToken,
    string DatabricksWarehouseId)
{
    public static WorkerOptions FromEnvironment(Func<string, string?> get)
    {
        string Get(string name, string fallback = "") =>
            string.IsNullOrWhiteSpace(get(name)) ? fallback : get(name)!;

        return new WorkerOptions(
            ConnectionString: ToConnectionString(Get("DATABASE_URL", "Host=localhost;Username=reconlens;Password=reconlens;Database=reconlens")),
            ApiBaseUrl: Get("API_BASE_URL", "http://localhost:8000"),
            SalesSource: Get("SALES_SOURCE", "csv").ToLowerInvariant(),
            SalesCsvPath: Get("SALES_CSV_PATH", "/data/sales.csv"),
            ScheduleSeconds: int.Parse(Get("SCHEDULE_SECONDS", "300")),
            DatabricksHost: Get("DATABRICKS_HOST"),
            DatabricksToken: Get("DATABRICKS_TOKEN"),
            DatabricksWarehouseId: Get("DATABRICKS_WAREHOUSE_ID"));
    }

    /// <summary>Accepts an Npgsql connection string or a postgresql:// URI.</summary>
    public static string ToConnectionString(string value)
    {
        if (!value.StartsWith("postgres://", StringComparison.OrdinalIgnoreCase) &&
            !value.StartsWith("postgresql://", StringComparison.OrdinalIgnoreCase))
            return value;

        var uri = new Uri(value);
        var user = uri.UserInfo.Split(':', 2);
        return new NpgsqlConnectionStringBuilder
        {
            Host = uri.Host,
            Port = uri.IsDefaultPort || uri.Port < 0 ? 5432 : uri.Port,
            Username = Uri.UnescapeDataString(user[0]),
            Password = user.Length > 1 ? Uri.UnescapeDataString(user[1]) : null,
            Database = uri.AbsolutePath.TrimStart('/'),
        }.ConnectionString;
    }
}
