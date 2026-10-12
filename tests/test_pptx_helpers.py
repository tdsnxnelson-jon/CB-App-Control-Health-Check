import os

import pandas as pd
import pytest

from healthcheck.analysis import AnalysisResult, Finding, block_analysis, custom_rules
from healthcheck.ingest import IngestResult
from healthcheck.report import builder
from healthcheck.report import pptx_helpers as ph
import main


def test_sanitize_chart_values_replaces_non_finite():
    values = [1.0, float("nan"), float("inf"), None, 3.0]

    assert ph._sanitize_chart_values(values) == [1.0, 0.0, 0.0, 0.0, 3.0]


def test_sanitize_chart_categories_replaces_non_finite():
    categories = ["2024-01-01", float("nan"), None, "2024-01-03"]

    assert ph._sanitize_chart_categories(categories) == ["2024-01-01", "", "", "2024-01-03"]


def test_wrap_to_width_preserves_full_operational_value():
    path = r"c:\program files\vendor\product\version\bin\important.exe"

    wrapped = ph._wrap_to_width(path, size_pt=10, width_in=1.5)

    assert wrapped.replace("\n", "") == path
    assert "..." not in wrapped


def test_categorize_keeps_logon_script_variants():
    assert block_analysis._categorize("Logon Script") == "Logon Script"
    assert block_analysis._categorize(" logon script ") == "Logon Script"
    assert block_analysis._categorize("Logon Script Data") == "Logon Script"


def test_custom_rule_chart_matches_blocking_execution_ratio():
    rows = (
        [{"Rule Type": "File Creation Control", "Action": "Approve"}] * 293
        + [{"Rule Type": "Execution Control", "Action": "Allow"}] * 413
        + [{"Rule Type": "Execution Control", "Action": "Block"}] * 2
    )
    frame = pd.DataFrame(rows).assign(Status="Enabled")
    frame = pd.concat([frame, pd.DataFrame([
        {"Rule Type": "Execution Control", "Action": "Block", "Status": "Disabled"},
        {"Rule Type": "Other", "Action": "Block", "Status": "Enabled"},
    ])], ignore_index=True)

    result = custom_rules.analyze(frame)
    metrics = dict(result.tables["metrics"][1:])

    assert metrics["Enabled Execution Control"] == 415
    assert metrics["Enabled blocking Execution Control"] == 2
    assert metrics["File Creation : blocking Execution"] == "146.5:1"
    assert any("ratio is 146.5:1" in finding.message for finding in result.findings)
    assert result.charts["rule_types"] == (
        "bar",
        ["File Creation Control", "Execution Control (blocking)"],
        {"Enabled rules": [293, 2]},
    )


def test_custom_rule_chart_keeps_zero_blocking_execution_count():
    frame = pd.DataFrame([
        {"Rule Type": "File Creation Control", "Action": "Approve", "Status": "Enabled"},
        {"Rule Type": "Execution Control", "Action": "Allow", "Status": "Enabled"},
    ])

    result = custom_rules.analyze(frame)

    assert dict(result.tables["metrics"][1:])["File Creation : blocking Execution"] == "n/a"
    assert result.charts["rule_types"][2] == {"Enabled rules": [1, 0]}


def test_combined_database_findings_are_counted_once(tmp_path, monkeypatch):
    shared_message = "[antibodies] 15,851,821 file catalog rows have 0 prevalence."
    daily = AnalysisResult(title="Daily", findings=[Finding("critical", shared_message)])
    purge = AnalysisResult(title="Purge", findings=[
        Finding("critical", shared_message), Finding("caution", "Purge-specific finding"),
    ])
    captured = {}
    monkeypatch.setattr(builder.db_maintenance, "analyze_daily_prune", lambda data: daily)
    monkeypatch.setattr(builder.db_maintenance, "analyze_purge_antibodies", lambda data: purge)
    monkeypatch.setattr(builder.db_maintenance, "build_slides", lambda prs, results: captured.update(results=results))
    monkeypatch.setattr(builder, "_add_executive_summary", lambda prs, findings: captured.update(findings=findings))
    inputs = {key: IngestResult(key, {}, []) for key in ("db_maintenance", "purge_antibodies_scope")}

    builder.build_report(inputs, "Test", str(tmp_path / "report.pptx"))

    findings = [finding for _, items in captured["findings"] for finding in items]
    assert sum(finding.message == shared_message for finding in findings) == 1
    assert len(findings) == 2
    assert sum(len(result.findings) for result in captured["results"]) == 2
    expected = builder._score_section([Finding("critical", shared_message), Finding("caution", "Purge-specific finding")])
    assert builder._overall_health_score(captured["findings"]) == expected


def test_pie_chart_uses_bar_when_tiny_slice_would_render_invisibly():
    assert ph._should_use_pie_chart(["A", "B", "C"], [90, 9, 0.1]) is False
    assert ph._should_use_pie_chart(["A", "B", "C"], [50, 30, 20]) is True
    assert ph._should_use_pie_chart(["A", "B", "C"], [49, 49, 2]) is True


@pytest.mark.parametrize("daily_zero,purge_zero", [(700, 700), (300, 700), (700, 300)])
def test_database_catalog_identity_ignores_snapshot_and_metadata_differences(tmp_path, monkeypatch, daily_zero, purge_zero):
    def summary(zero):
        return pd.DataFrame({
            "Table: [antibodies]": ["Total row count", "0 prev count", "0 prev count that meet the criterion"],
            "Count": [1000, zero, 1],
        })

    captured = {}
    monkeypatch.setattr(builder.db_maintenance, "build_slides", lambda prs, results: captured.update(results=results))
    monkeypatch.setattr(builder, "_add_executive_summary", lambda prs, findings: captured.update(findings=findings))
    inputs = {
        "db_maintenance": IngestResult("db_maintenance", {
            "antibodies_prune_summary": summary(daily_zero),
            "_metadata": pd.DataFrame({"maxAgeDays": [30]}),
            "events_by_age": pd.DataFrame({"Action": ["DELETE"], "Count": [2000000]}),
            "deleted_instances_by_age": pd.DataFrame({"Action": ["DELETE"], "Count": [2000000]}),
        }, []),
        "purge_antibodies_scope": IngestResult("purge_antibodies_scope", {"purge_scope": summary(purge_zero)}, []),
    }

    builder.build_report(inputs, "Test", str(tmp_path / "report.pptx"))

    findings = [finding for _, items in captured["findings"] for finding in items]
    catalog = [finding for finding in findings if "file catalog rows have 0 prevalence" in finding.message]
    assert len(catalog) == 1
    assert catalog[0].severity == "critical"
    assert any("[events]" in finding.message for finding in findings)
    assert any("[antibody_instances_deleted]" in finding.message for finding in findings)
    assert any("currently meet the purge criterion" in finding.message for finding in findings)
    assert sum(len(result.findings) for result in captured["results"]) == 4
    assert builder._overall_health_score(captured["findings"]) == 20


def test_resolve_output_path_for_directory_target():
    directory = os.path.join("C:\\", "tmp", "reports") + os.sep
    path = main._resolve_output_path(directory, "Epic Hosting", "carbonblack11.ss.us.epichosted.com")

    expected = os.path.join(os.path.normpath(directory), "Epic Hosting_carbonblack11.ss.us.epichosted.com_AppControl_HealthCheck.pptx")
    assert path == expected


def test_format_elapsed():
    assert main._format_elapsed(12.34) == "12.3 seconds"
    assert main._format_elapsed(59.9) == "59.9 seconds"
    assert main._format_elapsed(60.0) == "01:00"
    assert main._format_elapsed(203.0) == "03:23"
    assert main._format_elapsed(3665.0) == "61:05"
