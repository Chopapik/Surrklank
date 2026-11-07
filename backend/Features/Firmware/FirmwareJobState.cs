using System.Text.Json;
using System.Text.RegularExpressions;
using Surrklank.Features.Application;
using Surrklank.Features.Firmware.DTOs;

namespace Surrklank.Features.Firmware;

public sealed class FirmwareJobState(StateService updates, ILogger<FirmwareJobState> logger)
{
    private readonly object _sync = new();
    private readonly string _logRoot = Path.Combine(Path.GetTempPath(), "surrklank-idf");
    private readonly List<Dictionary<string, object?>> _events = [];
    private string _stage = "idle";
    private double? _progress;
    private string? _error;
    private IReadOnlyDictionary<string, object?>? _result;
    private string? _job;
    private bool _busy;

    public FirmwareDto Snapshot()
    {
        lock (_sync)
            return new FirmwareDto(_stage, _progress, _error, _result, _busy, _events.ToArray());
    }

    public void Begin()
    {
        lock (_sync)
        {
            _job = DateTime.UtcNow.ToString("yyyyMMdd'T'HHmmssfffffff");
            _stage = "starting";
            _progress = null;
            _error = null;
            _result = null;
            _busy = true;
        }
        updates.Publish();
    }

    public void Finish()
    {
        lock (_sync)
            _busy = false;
        updates.Publish();
    }

    public string GetLogPath()
    {
        lock (_sync)
            return Path.Combine(_logRoot, $"{_job}-{_stage}.log");
    }

    public void ReportOutput(string line)
    {
        if (!line.Contains("Writing at") && !line.Contains("Wrote "))
            return;
        var match = Regex.Match(line, @"(\d+)\s*%");
        string stage;
        lock (_sync)
            stage = _stage;
        Record(stage, match.Success ? int.Parse(match.Groups[1].Value) : null,
            details: new()
            {
                ["message"] = line.Length > 200 ? line[^200..] : line
            });
    }

    public void Record(string stage, double? progress = null, string? error = null,
        IReadOnlyDictionary<string, object?>? result = null, Dictionary<string, object?>? details = null)
    {
        Dictionary<string, object?> entry;
        lock (_sync)
        {
            _stage = stage;
            if (progress.HasValue)
                _progress = progress;
            if (error != null)
                _error = error;
            if (result != null)
                _result = result;
            entry = new()
            {
                ["at"] = DateTimeOffset.UtcNow,
                ["job"] = _job,
                ["stage"] = stage
            };
            if (progress.HasValue)
                entry["progress"] = progress;
            if (error != null)
                entry["error"] = error;
            if (result != null)
                entry["result"] = result;
            if (details != null)
                foreach (var item in details)
                    entry[item.Key] = item.Value;
            _events.Add(entry);
            if (_events.Count > 30)
                _events.RemoveAt(0);
        }
        try
        {
            Directory.CreateDirectory(_logRoot);
            File.AppendAllText(Path.Combine(_logRoot, "validation.jsonl"),
                JsonSerializer.Serialize(entry, StateService.JsonOptions) + "\n");
        }
        catch (Exception ex) { logger.LogWarning(ex, "Could not write maintenance event"); }
        updates.Publish();
    }
}
