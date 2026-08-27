"""
Server Health analysis - based on "CbP_Analysis_Script.sql".

This source script runs many independent diagnostic queries in one
execution (schema/version checks, sync %, queue backlogs, daily
throughput, SQL Server performance history). Customers export it as one
workbook with a sheet per result set (see config.SCRIPTS["server_health"]).
This module covers the sections most predictive of day-to-day health;
the schema/upgrade-history/SQL-Server-internals sections in the original
script are diagnostic-only and are intentionally left for manual review.
"""
import pandas as pd

from . import AnalysisResult, Finding
from ..report import pptx_helpers as ph

SYNC_WARN_THRESHOLD = 98.0


def _first_numeric(df: pd.DataFrame, col: str):
    if df is None or col not in df.columns:
        return None
    val = pd.to_numeric(df[col], errors="coerce").dropna()
    return val.iloc[0] if len(val) else None


def analyze(sheets: dict) -> AnalysisResult:
    result = AnalysisResult(title="Server Health")
    if not sheets:
        result.error = "No Server Health (CbP_Analysis_Script) data provided."
        return result

    sync_df = sheets.get("sync_percent")
    load_df = sheets.get("avg_load_per_agent")
    queue_df = sheets.get("queue_backlog")
    daily_df = sheets.get("daily_throughput")
    perf_df = sheets.get("performance_history")

    if sync_df is not None and "Agent Sync Percent" in sync_df.columns:
        for _, row in sync_df.iterrows():
            pct = pd.to_numeric(row.get("Agent Sync Percent"), errors="coerce")
            label = row.get("Type", "sync")
            if pd.isna(pct):
                continue
            if pct < SYNC_WARN_THRESHOLD:
                result.findings.append(Finding("warning", f"Agent sync ({label}) is {pct:.0f}%, below the {SYNC_WARN_THRESHOLD:.0f}% target.", "See the Fleet Health section for host-level detail; investigate connectivity or backlog causes."))
            else:
                result.findings.append(Finding("ok", f"Agent sync ({label}) is {pct:.0f}%."))
        result.tables["sync_percent"] = [list(sync_df.columns)] + sync_df.astype(object).where(pd.notna(sync_df), "").values.tolist()

    if load_df is not None:
        avg_fo = _first_numeric(load_df, "Average No. of File Operations (FO)/host")
        avg_ev = _first_numeric(load_df, "Average No. of Events/host")
        if avg_fo is not None and not (500 <= avg_fo <= 1500):
            result.findings.append(Finding("caution", f"Average file operations/host is {avg_fo:.0f}/day, outside the typical 500-1500 range.", "Confirm this aligns with expected agent behavior for this environment; investigate recent software rollouts if unexpectedly high."))
        if avg_ev is not None and not (50 <= avg_ev <= 150):
            result.findings.append(Finding("caution", f"Average events/host is {avg_ev:.0f}/day, outside the typical 50-150 range.", "Review recent rule/policy changes if this is a new trend; a sustained high rate can indicate noisy rules."))
        result.tables["avg_load"] = [list(load_df.columns)] + load_df.astype(object).where(pd.notna(load_df), "").values.tolist()

    if queue_df is not None:
        result.tables["queue_backlog"] = [list(queue_df.columns)] + queue_df.astype(object).where(pd.notna(queue_df), "").values.tolist()
        fo_backlog = _first_numeric(queue_df, "FO Queue 1: Agent-Side backlog (overall - including disabled)")
        if fo_backlog is not None and fo_backlog > 1_000_000:
            result.findings.append(Finding("warning", f"Agent-side file-op backlog is {fo_backlog:,.0f} - investigate connectivity/agent cache health.", "Check agent-to-server and server-to-SQL connectivity; large backlogs typically indicate a processing bottleneck."))

    if daily_df is not None and "Date" in daily_df.columns:
        daily_df = daily_df.copy()
        daily_df["Date"] = pd.to_datetime(daily_df["Date"], errors="coerce")
        daily_df = daily_df.sort_values("Date")
        if "E_Total" in daily_df.columns:
            events = pd.to_numeric(daily_df["E_Total"].astype(str).str.replace(",", "", regex=False), errors="coerce")
            if len(events.dropna()) >= 2 and events.iloc[:-1].mean():
                if events.iloc[-1] > events.iloc[:-1].mean() * 1.5:
                    result.findings.append(Finding("warning", "Event volume spiked on the most recent day analyzed - check for recent policy/software changes.", "Correlate with recent policy or software changes across the fleet."))
            result.charts["daily_events"] = ("line", daily_df["Date"].dt.strftime("%Y-%m-%d").tolist(), {"Events": events.fillna(0).tolist()})
        result.tables["daily_throughput"] = [list(daily_df.columns)] + daily_df.astype(object).where(pd.notna(daily_df), "").values.tolist()

    if perf_df is not None and "AB_BackLog_M" in perf_df.columns:
        backlog = pd.to_numeric(perf_df["AB_BackLog_M"], errors="coerce").dropna()
        if len(backlog) and backlog.iloc[0] and backlog.iloc[0] > 1_000_000:
            result.findings.append(Finding("warning", f"File-op backlog (AB_BackLog_M) is {backlog.iloc[0]:,.0f} - server may be falling behind on processing.", "Check the ProcessFileInstances scheduled task health - a growing backlog usually means it isn't keeping up."))

    if not result.findings:
        result.findings.append(Finding("info", "Server health sections loaded; no thresholds triggered."))

    return result


def build_slides(prs, result: AnalysisResult) -> None:
    ph.add_section_slide(prs, result.title)

    slide = ph.add_content_slide(prs, "Server Health - Findings")
    ph.add_findings_dashboard(slide, [(f.severity, f.message, f.recommendation) for f in result.findings])

    for key, title in [
        ("sync_percent", "Agent Sync Percentage"),
        ("avg_load", "Average File Ops / Events per Host"),
        ("queue_backlog", "Queue Backlog"),
    ]:
        if key in result.tables:
            slide = ph.add_content_slide(prs, title)
            ph.add_table(slide, result.tables[key], font_size=10, center=True)

    if "daily_events" in result.charts:
        _, categories, series = result.charts["daily_events"]
        slide = ph.add_content_slide(prs, "Daily Event Volume")
        ph.add_line_chart(slide, "Events per Day", categories, series)

    if "daily_throughput" in result.tables:
        ph.add_table_slides(prs, "Daily Throughput Detail", result.tables["daily_throughput"], font_size=8)
