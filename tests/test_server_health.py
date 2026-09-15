import pandas as pd

from healthcheck.analysis import server_health


def test_event_storm_retention_truncation_finding():
    dates = pd.date_range("2026-09-01", periods=5, freq="D")
    # 4 prior days with 0/missing events, 5th day with 2.5M events
    daily_df = pd.DataFrame({
        "Date": dates,
        "E_Total": ["0", "0", "0", "0", "2,500,000"],
    })
    sheets = {"daily_throughput": daily_df}
    result = server_health.analyze(sheets)

    matching = [f for f in result.findings if "Event storm" in f.message or "retention truncation" in f.message]
    assert len(matching) == 1
    assert "2,500,000" in matching[0].message
    assert "Address the event storm" in matching[0].recommendation
    assert "PurgeEventThreshold" in matching[0].recommendation


def test_event_spike_with_prior_history():
    dates = pd.date_range("2026-09-01", periods=5, freq="D")
    daily_df = pd.DataFrame({
        "Date": dates,
        "E_Total": ["1000", "1200", "1100", "1050", "5000"],
    })
    sheets = {"daily_throughput": daily_df}
    result = server_health.analyze(sheets)

    matching = [f for f in result.findings if "spiked" in f.message]
    assert len(matching) == 1
    assert "5,000" in matching[0].message
    assert "Address the event surge" in matching[0].recommendation


def test_single_day_event_storm():
    daily_df = pd.DataFrame({
        "Date": ["2026-09-10"],
        "E_Total": ["2,512,543"],
    })
    sheets = {"daily_throughput": daily_df}
    result = server_health.analyze(sheets)

    matching = [f for f in result.findings if "Event storm" in f.message]
    assert len(matching) == 1
    assert "2,512,543" in matching[0].message
    assert "Address the event storm" in matching[0].recommendation


def test_elevated_average_events_per_host():
    load_df = pd.DataFrame({
        "Average No. of File Operations (FO)/host": ["1000"],
        "Average No. of Events/host": ["2176"],
    })
    sheets = {"avg_load_per_agent": load_df}
    result = server_health.analyze(sheets)

    matching = [f for f in result.findings if "2,176" in f.message and f.severity == "warning"]
    assert len(matching) == 1
    assert "Address the event storm" in matching[0].recommendation
