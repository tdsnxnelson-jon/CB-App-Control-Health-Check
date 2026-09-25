import pandas as pd

from healthcheck.analysis import block_analysis


def _event(**overrides):
    event = {
        "TimeStamp": "2026-09-24",
        "ComputerName": "host-01",
        "UserName": "user-01",
        "BlockSubtype": "Execution block (unapproved file)",
        "BlockOutcome": "Blocked",
        "BlockCategory": "Execution",
        "RuleName": "Unapproved",
        "BlockProcessFull": r"c:\vendor\updater.exe",
        "FilePath": r"c:\vendor\cache",
        "FileNameShort": "payload.exe",
        "FileHash": "abc123",
        "FileState": "Unapproved",
        "FileTrust": 5,
        "FileFlags": "",
        "Publisher": "Vendor Inc.",
        "PublisherState": "Unapproved",
        "PublisherTrust": "High",
    }
    event.update(overrides)
    return event


def test_aggregated_event_counts_match_expanded_rows():
    grouped_events = [
        _event(EventCount=5),
        _event(
            EventCount=3,
            ComputerName="host-02",
            TimeStamp="2026-09-25",
            FilePath=r"c:\vendor\other",
        ),
        _event(
            EventCount=2,
            BlockSubtype="Execution prompt allowed (unapproved file)",
            BlockOutcome="Allowed",
        ),
    ]
    aggregated = pd.DataFrame(grouped_events)
    expanded = pd.DataFrame([
        {key: value for key, value in event.items() if key != "EventCount"}
        for event in grouped_events
        for _ in range(event["EventCount"])
    ])

    aggregated_result = block_analysis.analyze(aggregated)
    expanded_result = block_analysis.analyze(expanded)

    assert aggregated_result.tables == expanded_result.tables
    assert aggregated_result.charts == expanded_result.charts
    assert aggregated_result.findings[0].message == "8 block event(s) analyzed."


def test_normalize_dir_collapses_generated_numeric_segments():
    path = (
        r"c:\program files\microsoft monitoring agent\agent\health service state"
        r"\monitoring host temporary files 41576\1493"
    )

    assert block_analysis._normalize_dir(path) == (
        r"c:\program files\microsoft monitoring agent\agent\health service state"
        r"\monitoring host temporary files *\*"
    )