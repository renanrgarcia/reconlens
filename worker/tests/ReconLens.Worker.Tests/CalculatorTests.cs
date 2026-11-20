using ReconLens.Worker;

namespace ReconLens.Worker.Tests;

public class CalculatorTests
{
    private const string A = "11111111000111", B = "22222222000122";

    [Fact]
    public void Matched_exact()
    {
        // qty 3 * 4.50 = 13.50 == amount 13.50 -> expected 13.50, diff 0, mismatched 0
        var r = Assert.Single(ReconciliationCalculator.Compute([new CalcLine(A, 3, 13.50m, 4.50m)]));
        Assert.Equal(new StoreReport(A, 1, 0, 13.50m, 13.50m, 13.50m, 0m, 0m, 0), r);
    }

    [Fact]
    public void Matched_with_wrong_amount()
    {
        // qty 2 * 5.00 = 10.00; reported 12.00 -> diff +2.00, mismatched 1
        var r = Assert.Single(ReconciliationCalculator.Compute([new CalcLine(A, 2, 12.00m, 5.00m)]));
        Assert.Equal(new StoreReport(A, 1, 0, 12.00m, 10.00m, 12.00m, 0m, 2.00m, 1), r);
    }

    [Fact]
    public void Unmatched_line_only_counts_in_totals_and_unmatched()
    {
        // unmatched amount 7.50: reported 7.50, expected 0, matched_reported 0, diff 0
        var r = Assert.Single(ReconciliationCalculator.Compute([new CalcLine(A, 1, 7.50m, null)]));
        Assert.Equal(new StoreReport(A, 1, 1, 7.50m, 0m, 0m, 7.50m, 0m, 0), r);
    }

    [Fact]
    public void Groups_by_store()
    {
        // A: (2*5.00=10.00 vs 10.00 ok) + (1*3.00=3.00 vs 2.00 bad) + unmatched 4.00
        //    lines 3, unmatched 1, reported 16.00, expected 13.00, matched_reported 12.00, unmatched 4.00, diff -1.00, mismatched 1
        // B: (4*1.25=5.00 vs 5.00 ok) -> 1,0,5.00,5.00,5.00,0,0,0
        var rows = ReconciliationCalculator.Compute([
            new CalcLine(B, 4, 5.00m, 1.25m),
            new CalcLine(A, 2, 10.00m, 5.00m),
            new CalcLine(A, 1, 2.00m, 3.00m),
            new CalcLine(A, 1, 4.00m, null)]);
        Assert.Equal(2, rows.Count);
        Assert.Equal(new StoreReport(A, 3, 1, 16.00m, 13.00m, 12.00m, 4.00m, -1.00m, 1), rows[0]);
        Assert.Equal(new StoreReport(B, 1, 0, 5.00m, 5.00m, 5.00m, 0m, 0m, 0), rows[1]);
    }

    [Fact]
    public void Rounds_each_line_away_from_zero()
    {
        // 3 * 0.335 = 1.005 -> 1.01 (AwayFromZero; banker's would give 1.00). Two such lines: expected 2.02, not 2.01.
        // reported 1.01 each -> |1.01 - 1.01| = 0 -> not mismatched; diff 0.
        var r = Assert.Single(ReconciliationCalculator.Compute([
            new CalcLine(A, 3, 1.01m, 0.335m), new CalcLine(A, 3, 1.01m, 0.335m)]));
        Assert.Equal(2.02m, r.ExpectedTotal);
        Assert.Equal(0m, r.Difference);
        Assert.Equal(0, r.MismatchedLines);
    }

    [Fact]
    public void Tolerance_is_inclusive_of_one_cent()
    {
        // 1*10.00 = 10.00; reported 10.01 -> |diff| = 0.01, not > 0.01 -> ok. 10.02 -> mismatched.
        Assert.Equal(0, ReconciliationCalculator.Compute([new CalcLine(A, 1, 10.01m, 10.00m)])[0].MismatchedLines);
        Assert.Equal(1, ReconciliationCalculator.Compute([new CalcLine(A, 1, 10.02m, 10.00m)])[0].MismatchedLines);
    }
}
