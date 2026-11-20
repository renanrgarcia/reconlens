using System.Globalization;
using System.Security.Cryptography;
using System.Text;

namespace ReconLens.Worker;

public sealed record SalesLine(
    string BatchId, string SourceLineId, string StoreCnpj, DateOnly SaleDate,
    string RawProduct, int Quantity, decimal Amount);

public interface ISalesSource
{
    Task<IReadOnlyList<SalesLine>> ReadAsync(CancellationToken ct);
}

public static class IdempotencyKey
{
    /// <summary>
    /// hex sha256(batch_id + "|" + contentHash). contentHash = sha256 of the lines sorted by
    /// source_line_id (ordinal), one canonical text row each, so input order does not matter
    /// but any changed field does.
    /// </summary>
    public static string For(string batchId, IEnumerable<SalesLine> lines)
    {
        var rows = lines.OrderBy(l => l.SourceLineId, StringComparer.Ordinal).Select(l => string.Join('|',
            l.SourceLineId, l.StoreCnpj, l.SaleDate.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture),
            l.RawProduct, l.Quantity.ToString(CultureInfo.InvariantCulture),
            l.Amount.ToString("0.00", CultureInfo.InvariantCulture)));
        var content = Sha256Hex(string.Join('\n', rows));
        return Sha256Hex(batchId + "|" + content);
    }

    private static string Sha256Hex(string s) =>
        Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(s))).ToLowerInvariant();
}
