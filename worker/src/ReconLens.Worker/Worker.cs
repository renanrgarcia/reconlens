using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;

namespace ReconLens.Worker;

public sealed class Worker(ReconciliationPipeline pipeline, WorkerOptions options, ILogger<Worker> log) : BackgroundService
{
    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        await TickAsync(stoppingToken); // one pass immediately
        using var timer = new PeriodicTimer(TimeSpan.FromSeconds(options.ScheduleSeconds));
        while (await timer.WaitForNextTickAsync(stoppingToken))
            await TickAsync(stoppingToken);
    }

    private async Task TickAsync(CancellationToken ct)
    {
        try { await pipeline.RunOnceAsync(ct); }
        catch (Exception ex) when (ex is not OperationCanceledException)
        {
            log.LogError(ex, "Reconciliation pass failed"); // e.g. source unreadable; try again next tick
        }
    }
}
