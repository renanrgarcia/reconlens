using Npgsql;
using ReconLens.Worker;

var options = WorkerOptions.FromEnvironment(Environment.GetEnvironmentVariable);
var builder = Host.CreateApplicationBuilder(args);

builder.Services.AddSingleton(options);
builder.Services.AddSingleton(NpgsqlDataSource.Create(options.ConnectionString));
builder.Services.AddSingleton<Database>();
builder.Services.AddReconcileApiClient(options.ApiBaseUrl);
builder.Services.AddHttpClient("databricks");
builder.Services.AddSingleton<ISalesSource>(sp => options.SalesSource == "databricks"
    ? new DatabricksSalesSource(sp.GetRequiredService<IHttpClientFactory>().CreateClient("databricks"),
        options.DatabricksHost, options.DatabricksToken, options.DatabricksWarehouseId)
    : new CsvSalesSource(options.SalesCsvPath));
builder.Services.AddTransient<ReconciliationPipeline>();
builder.Services.AddHostedService<Worker>();

builder.Build().Run();
