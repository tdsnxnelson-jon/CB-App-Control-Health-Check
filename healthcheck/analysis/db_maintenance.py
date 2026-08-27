"""
DB Maintenance / Retention analysis - based on "DailyPrune_Debug_Scope.sql"
and "PurgeAntibodiesPeriodDays scope.sql".

These scripts don't delete anything themselves - they show what SHOULD be
eligible for deletion under the server's configured retention settings.
A large "eligible for delete but still present" count is the signal that
the DailyPruneTask / retention job is stuck or not keeping up, which is a
common cause of runaway DB growth on older App Control servers.
"""
import pandas as pd

from . import AnalysisResult, Finding
from ..report import pptx_helpers as ph

BACKLOG_WARN_ROWS = 100_000
BACKLOG_CRITICAL_ROWS = 1_000_000
ZERO_PREVALENCE_WARN_PCT = 0.26
ZERO_PREVALENCE_CRITICAL_PCT = 0.50
LOW_PURGEABLE_ZERO_PREV_PCT = 0.01


def _delete_keep_counts(df: pd.DataFrame):
    """df has one column of DELETE/KEEP-style labels and a count column."""
    if df is None or df.empty:
        return None, None
    label_col = df.columns[0]
    count_col = next((c for c in df.columns if c.lower() == "count"), df.columns[-1])
    counts = pd.to_numeric(df[count_col], errors="coerce")
    labels = df[label_col].astype(str).str.upper()
    delete_ct = counts[labels.str.contains("DELETE")].sum()
    keep_ct = counts[labels.str.contains("KEEP")].sum()
    return delete_ct, keep_ct


def _summary_value(df: pd.DataFrame, label: str):
    if df is None or df.empty:
        return None
    label_col = df.columns[0]
    count_col = "Count" if "Count" in df.columns else df.columns[-1]
    matches = df[df[label_col].astype(str).str.strip().str.casefold() == label.casefold()]
    if matches.empty:
        return None
    return pd.to_numeric(matches[count_col], errors="coerce").iloc[0]


def _metadata_value(sheets: dict, key: str):
    metadata = sheets.get("_metadata")
    if metadata is None or metadata.empty or key not in metadata.columns:
        return ""
    value = metadata[key].iloc[0]
    return "" if pd.isna(value) else value


def _format_antibodies_summary(summary_df: pd.DataFrame, max_age_days) -> list:
    total = _summary_value(summary_df, "Total row count")
    zero_prev = _summary_value(summary_df, "0 prev count")
    max_age_days_text = "" if max_age_days == "" or pd.isna(max_age_days) else f"{max_age_days:.0f}" if isinstance(max_age_days, (int, float)) else str(max_age_days)
    display_rows = [["Metric", "Count", "Percent of total", "Percent of 0 prevalence", "maxAgeDays"]]
    for label in ["Total row count", "0 prev count", "0 prev count that meet the criterion"]:
        count = _summary_value(summary_df, label)
        pct = count / total if total and pd.notna(total) and count is not None and pd.notna(count) else None
        zero_prev_pct = count / zero_prev if label != "Total row count" and zero_prev and pd.notna(zero_prev) and count is not None and pd.notna(count) else None
        display_rows.append([
            label,
            f"{count:,.0f}" if count is not None and pd.notna(count) else "",
            f"{pct:.1%}" if pct is not None and pd.notna(pct) else "",
            f"{zero_prev_pct:.1%}" if zero_prev_pct is not None and pd.notna(zero_prev_pct) else "",
            max_age_days_text,
        ])
    return display_rows


def analyze_daily_prune(sheets: dict) -> AnalysisResult:
    result = AnalysisResult(title="DB Maintenance - Daily Prune Task")
    if not sheets:
        result.error = "No Daily Prune Debug data provided."
        return result

    labels = {
        "deleted_instances_by_age": "antibody_instances_deleted",
        "instance_groups_by_age": "antibody_instance_groups",
        "events_by_age": "events",
    }
    for sheet_key, table_name in labels.items():
        df = sheets.get(sheet_key)
        if df is None:
            continue
        delete_ct, keep_ct = _delete_keep_counts(df)
        if delete_ct is None or pd.isna(delete_ct):
            continue
        if delete_ct >= BACKLOG_CRITICAL_ROWS:
            result.findings.append(Finding("critical", f"[{table_name}] {delete_ct:,.0f} row(s) are past retention and not yet purged - DailyPruneTask likely stuck.", "Verify the DailyPruneTask scheduled task is running and completing successfully; a stuck task causes runaway DB growth."))
        elif delete_ct >= BACKLOG_WARN_ROWS:
            result.findings.append(Finding("warning", f"[{table_name}] {delete_ct:,.0f} row(s) are past retention and not yet purged.", "Monitor the DailyPruneTask; confirm it's completing within its scheduled window."))
        else:
            result.findings.append(Finding("ok", f"[{table_name}] retention backlog is small ({delete_ct:,.0f} row(s))."))
        result.tables[sheet_key] = [list(df.columns)] + df.astype(object).where(pd.notna(df), "").values.tolist()

    summary_df = sheets.get("antibodies_prune_summary")
    if summary_df is not None:
        max_age_days = _metadata_value(sheets, "maxAgeDays")
        total = _summary_value(summary_df, "Total row count")
        zero_prev = _summary_value(summary_df, "0 prev count")
        purgeable_zero_prev = _summary_value(summary_df, "0 prev count that meet the criterion")
        zero_prev_pct = zero_prev / total if total and pd.notna(total) and zero_prev is not None and pd.notna(zero_prev) else None
        if zero_prev_pct is not None and pd.notna(zero_prev_pct):
            max_age_days_text = "" if max_age_days == "" or pd.isna(max_age_days) else f"{max_age_days:.0f}" if isinstance(max_age_days, (int, float)) else str(max_age_days)
            max_age_text = f"; {purgeable_zero_prev:,.0f} meet maxAgeDays [{max_age_days_text}]" if purgeable_zero_prev is not None and pd.notna(purgeable_zero_prev) and max_age_days_text else ""
            message = f"[antibodies] {zero_prev:,.0f} of {total:,.0f} file catalog rows have 0 prevalence ({zero_prev_pct:.1%}){max_age_text}."
            if zero_prev_pct > ZERO_PREVALENCE_CRITICAL_PCT:
                result.findings.append(Finding("critical", message, "Prioritize reducing zero-prevalence file catalog rows; excessive catalog bloat can materially affect database performance."))
            elif zero_prev_pct >= ZERO_PREVALENCE_WARN_PCT:
                result.findings.append(Finding("warning", message, "Plan cleanup of zero-prevalence file catalog rows before catalog bloat becomes a larger database performance issue."))
            else:
                result.findings.append(Finding("ok", message))
        # table intentionally omitted here - duplicates the "Purge Scope" table
        # from analyze_purge_antibodies() (same maxAgeDays scope).

    if not result.findings:
        result.findings.append(Finding("info", "Daily prune sections loaded; no thresholds triggered."))

    return result


def analyze_purge_antibodies(df: pd.DataFrame) -> AnalysisResult:
    result = AnalysisResult(title="DB Maintenance - Antibody Purge Scope")
    max_age_days = ""
    if isinstance(df, dict):
        max_age_days = _metadata_value(df, "maxAgeDays")
        df = df.get("purge_scope")
    if df is None or df.empty:
        result.error = "No Purge Antibodies scope data provided."
        return result

    df = df.copy()
    total = _summary_value(df, "Total row count")
    zero_prev = _summary_value(df, "0 prev count")
    purgeable_zero_prev = _summary_value(df, "0 prev count that meet the criterion")
    zero_prev_pct = zero_prev / total if total and pd.notna(total) and zero_prev is not None and pd.notna(zero_prev) else None
    if zero_prev_pct is not None and pd.notna(zero_prev_pct):
        max_age_days_text = "" if max_age_days == "" or pd.isna(max_age_days) else f"{max_age_days:.0f}" if isinstance(max_age_days, (int, float)) else str(max_age_days)
        max_age_text = f"; {purgeable_zero_prev:,.0f} meet maxAgeDays [{max_age_days_text}]" if purgeable_zero_prev is not None and pd.notna(purgeable_zero_prev) and max_age_days_text else ""
        message = f"[antibodies] {zero_prev:,.0f} of {total:,.0f} file catalog rows have 0 prevalence ({zero_prev_pct:.1%}){max_age_text}."
        if zero_prev_pct > ZERO_PREVALENCE_CRITICAL_PCT:
            result.findings.append(Finding("critical", message, "Prioritize reducing zero-prevalence file catalog rows; excessive catalog bloat can materially affect database performance."))
        elif zero_prev_pct >= ZERO_PREVALENCE_WARN_PCT:
            result.findings.append(Finding("warning", message, "Plan cleanup of zero-prevalence file catalog rows before catalog bloat becomes a larger database performance issue."))
        else:
            result.findings.append(Finding("ok", message))

        purgeable_zero_prev_pct = purgeable_zero_prev / zero_prev if zero_prev and pd.notna(zero_prev) and purgeable_zero_prev is not None and pd.notna(purgeable_zero_prev) else None
        if purgeable_zero_prev_pct is not None and pd.notna(purgeable_zero_prev_pct) and purgeable_zero_prev_pct < LOW_PURGEABLE_ZERO_PREV_PCT:
            result.findings.append(Finding("caution", f"Only {purgeable_zero_prev:,.0f} zero-prevalence file catalog row(s) currently meet the purge criterion ({purgeable_zero_prev_pct:.1%} of 0-prevalence rows). Daily pruning at this level will not materially reduce the existing {zero_prev:,.0f}-row 0-prevalence catalog volume by itself.", "Monitor this count over successive health checks; a one-day low value can be an anomaly, while a rising trend should be investigated before it becomes a database performance issue."))

    result.tables["purge_scope"] = _format_antibodies_summary(df, max_age_days)
    return result


def build_slides(prs, results) -> None:
    """results: list of AnalysisResult (daily prune + purge scope), rendered
    as a single combined section since both cover the same antibody/file
    catalog retention story."""
    daily_result = next((r for r in results if r.title == "DB Maintenance - Daily Prune Task"), None)
    purge_result = next((r for r in results if r.title == "DB Maintenance - Antibody Purge Scope"), None)

    ph.add_section_slide(prs, "DB Maintenance")

    if purge_result:
        slide = ph.add_content_slide(prs, "Pruning the File Catalog")
        ph.add_rich_bullets(slide, [
            (0, [("File catalog pruning is disabled by default.", False, False)]),
            (0, [("You can turn it on by changing the shepherd_config property PurgeAntibodiesPeriodDays.", False, False)]),
            (1, [("A value of 0 means that files will never be deleted from the catalog.", False, False)]),
            (1, [("https://<appc_server>/shepherd_config.php", False, False, "https://<appc_server>/shepherd_config.php")]),
            (0, [("When this pruning is enabled, App Control will automatically delete all files with a prevalence of 0 (i.e., not existing on any endpoint), after N days from reaching 0 prevalence.", False, False)]),
            (0, [("Note that if a 0-prevalence file reappears on any endpoint during these N days, its pruning will be canceled.", False, False)]),
            (0, [("Linux 8.8.4 Release Notes", False, False, "https://techdocs.broadcom.com/us/en/carbon-black/app-control/app-control-agents/index/appc-release-notes_tile_agents/carbon-black-app-control-linux-agent/carbon-black-app-control-linux-agent-8-8-4-release-notes.html")]),
        ], font_size=15)

    combined_findings = []
    for result in results:
        combined_findings.extend((f.severity, f.message, f.recommendation) for f in result.findings)
    slide = ph.add_content_slide(prs, "DB Maintenance - Findings")
    ph.add_findings_dashboard(slide, combined_findings)

    if purge_result and "purge_scope" in purge_result.tables:
        ph.add_table_slides(prs, "DB Maintenance - Antibody Purge Scope - Purge Scope", purge_result.tables["purge_scope"], font_size=9)

    if daily_result:
        for name, rows in daily_result.tables.items():
            ph.add_table_slides(prs, f"{daily_result.title} - {name.replace('_', ' ').title()}", rows, font_size=9)
    if purge_result:
        for name, rows in purge_result.tables.items():
            if name == "purge_scope":
                continue
            ph.add_table_slides(prs, f"{purge_result.title} - {name.replace('_', ' ').title()}", rows, font_size=9)
