using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Http.Resilience;
using Polly;

namespace ReconLens.Worker;

public sealed class ReconcileApiClient(HttpClient http)
{
    public async Task ReconcileAsync(string batchId, string idempotencyKey, CancellationToken ct)
    {
        using var req = new HttpRequestMessage(HttpMethod.Post, $"reconcile/{Uri.EscapeDataString(batchId)}");
        req.Headers.Add("Idempotency-Key", idempotencyKey);
        using var resp = await http.SendAsync(req, ct);
        resp.EnsureSuccessStatusCode();
    }
}

public static class ReconcileApiClientRegistration
{
    public static IHttpClientBuilder AddReconcileApiClient(
        this IServiceCollection services, string baseUrl, TimeSpan? retryDelay = null)
    {
        var builder = services.AddHttpClient<ReconcileApiClient>(c => c.BaseAddress = new Uri(baseUrl.TrimEnd('/') + "/"));
        builder.AddResilienceHandler("reconcile", pipeline =>
        {
            // Retrying a POST is normally unsafe, but /reconcile/{batch} is idempotent: every attempt carries the
            // same Idempotency-Key, and the API replays the stored response for a key it already processed.
            pipeline.AddRetry(new HttpRetryStrategyOptions
            {
                MaxRetryAttempts = 5,
                BackoffType = DelayBackoffType.Exponential,
                UseJitter = true,
                Delay = retryDelay ?? TimeSpan.FromSeconds(1),
                // Default predicate: 5xx, 408, 429 and HttpRequestException.
            });
            // Per-attempt timeout (inside the retry), so a hung attempt is retried.
            pipeline.AddTimeout(TimeSpan.FromSeconds(60));
        });
        return builder;
    }
}
