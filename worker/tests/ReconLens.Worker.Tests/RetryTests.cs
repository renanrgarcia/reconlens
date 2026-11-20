using System.Net;
using Microsoft.Extensions.DependencyInjection;
using ReconLens.Worker;

namespace ReconLens.Worker.Tests;

public class RetryTests
{
    private sealed class Flaky(int failures) : HttpMessageHandler
    {
        public int Calls;
        public List<string?> Keys = [];
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
        {
            Calls++;
            Keys.Add(request.Headers.GetValues("Idempotency-Key").Single());
            return Task.FromResult(new HttpResponseMessage(Calls <= failures ? HttpStatusCode.ServiceUnavailable : HttpStatusCode.OK));
        }
    }

    private static ServiceProvider Build(Flaky stub)
    {
        var s = new ServiceCollection();
        s.AddReconcileApiClient("http://api", TimeSpan.FromMilliseconds(1)).ConfigurePrimaryHttpMessageHandler(() => stub);
        return s.BuildServiceProvider();
    }

    [Fact]
    public async Task Retries_503_then_succeeds_with_same_idempotency_key()
    {
        var stub = new Flaky(2);
        await Build(stub).GetRequiredService<ReconcileApiClient>().ReconcileAsync("2026-01-02", "key-1", CancellationToken.None);
        Assert.Equal(3, stub.Calls);
        Assert.All(stub.Keys, k => Assert.Equal("key-1", k));
    }

    [Fact]
    public async Task Gives_up_after_five_retries()
    {
        var stub = new Flaky(int.MaxValue);
        await Assert.ThrowsAsync<HttpRequestException>(() =>
            Build(stub).GetRequiredService<ReconcileApiClient>().ReconcileAsync("b", "k", CancellationToken.None));
        Assert.Equal(6, stub.Calls); // 1 attempt + 5 retries
    }
}
