using System.Globalization;
using System.Text;

namespace ReconLens.Worker;

/// <summary>Reads data/sales.csv. The true_sku column (study ground truth) is ignored.</summary>
public sealed class CsvSalesSource(string path) : ISalesSource
{
    public async Task<IReadOnlyList<SalesLine>> ReadAsync(CancellationToken ct)
    {
        var text = await File.ReadAllTextAsync(path, Encoding.UTF8, ct);
        var rows = ParseCsv(text);
        var header = rows[0].Select(h => h.Trim().TrimStart('﻿')).ToList();
        int Col(string name) => header.IndexOf(name) is var i and >= 0 ? i : throw new InvalidDataException($"Missing column {name}");
        int batch = Col("batch_id"), id = Col("source_line_id"), cnpj = Col("store_cnpj"), date = Col("sale_date"),
            prod = Col("raw_product"), qty = Col("quantity"), amt = Col("amount");

        return rows.Skip(1).Select(r => new SalesLine(
            r[batch], r[id], r[cnpj],
            DateOnly.ParseExact(r[date], "yyyy-MM-dd", CultureInfo.InvariantCulture),
            r[prod], int.Parse(r[qty], CultureInfo.InvariantCulture),
            decimal.Parse(r[amt], NumberStyles.Number, CultureInfo.InvariantCulture))).ToList();
    }

    /// <summary>Minimal RFC 4180 parser (quoted fields, "" escapes, embedded commas/newlines). Skips blank lines.</summary>
    internal static List<List<string>> ParseCsv(string text)
    {
        var rows = new List<List<string>>();
        var row = new List<string>();
        var field = new StringBuilder();
        var quoted = false;
        for (var i = 0; i < text.Length; i++)
        {
            var c = text[i];
            if (quoted)
            {
                if (c == '"' && i + 1 < text.Length && text[i + 1] == '"') { field.Append('"'); i++; }
                else if (c == '"') quoted = false;
                else field.Append(c);
            }
            else if (c == '"') quoted = true;
            else if (c == ',') { row.Add(field.ToString()); field.Clear(); }
            else if (c is '\n' or '\r')
            {
                if (c == '\r' && i + 1 < text.Length && text[i + 1] == '\n') i++;
                row.Add(field.ToString()); field.Clear();
                if (row.Count > 1 || row[0].Length > 0) rows.Add(row);
                row = [];
            }
            else field.Append(c);
        }
        if (field.Length > 0 || row.Count > 0) { row.Add(field.ToString()); rows.Add(row); }
        return rows;
    }
}
