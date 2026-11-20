namespace ReconLens.Worker;

/// <summary>One sales line joined to its catalog price. UnitPrice is null when unmatched.</summary>
public sealed record CalcLine(string StoreCnpj, int Quantity, decimal Amount, decimal? UnitPrice);

/// <summary>One row of reconciliation_report (minus batch_id / computed_at).</summary>
public sealed record StoreReport(
    string StoreCnpj, int LineCount, int UnmatchedCount, decimal ReportedTotal, decimal ExpectedTotal,
    decimal MatchedReported, decimal UnmatchedAmount, decimal Difference, int MismatchedLines);

/// <summary>Pure money math, no I/O. This is the only place money is computed.</summary>
public static class ReconciliationCalculator
{
    public const decimal Tolerance = 0.01m;

    public static IReadOnlyList<StoreReport> Compute(IEnumerable<CalcLine> lines) =>
        lines.GroupBy(l => l.StoreCnpj).OrderBy(g => g.Key, StringComparer.Ordinal).Select(g =>
        {
            var matched = g.Where(l => l.UnitPrice is not null).ToList();
            var unmatched = g.Where(l => l.UnitPrice is null).ToList();
            // Rounding happens only here, per line: qty * price -> 2 places, away from zero.
            var expected = matched.Sum(l => Expected(l));
            var matchedReported = matched.Sum(l => l.Amount);
            return new StoreReport(
                g.Key, g.Count(), unmatched.Count, g.Sum(l => l.Amount), expected,
                matchedReported, unmatched.Sum(l => l.Amount), matchedReported - expected,
                matched.Count(l => Math.Abs(l.Amount - Expected(l)) > Tolerance));
        }).ToList();

    private static decimal Expected(CalcLine l) =>
        Math.Round(l.Quantity * l.UnitPrice!.Value, 2, MidpointRounding.AwayFromZero);
}
