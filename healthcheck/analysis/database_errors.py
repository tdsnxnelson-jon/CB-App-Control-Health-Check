"""
Database/Agent Error Analysis - based on "DatabaseErrorAnalysis.sql".

Correlates "Agent Database Error" events with surrounding agent activity
(restarts, cache checks, execution blocks) to help spot agents in a bad
state (cache corruption, repeated restarts).
"""
import pandas as pd

from . import AnalysisResult, Finding
from ..report import pptx_helpers as ph

TOP_N = 15


def analyze(df: pd.DataFrame) -> AnalysisResult:
    result = AnalysisResult(title="Agent Database Errors")
    if df is None or df.empty:
        result.error = "No Database Error Analysis data provided."
        return result

    df = df.copy()
    total = len(df)
    by_host = df["ComputerName"].value_counts() if "ComputerName" in df.columns else pd.Series(dtype=int)
    by_subtype = df["Subtype"].value_counts() if "Subtype" in df.columns else pd.Series(dtype=int)

    result.findings.append(Finding("info", f"{total:,} event(s) correlated around agent database errors, across {by_host.size} host(s)." if len(by_host) else f"{total:,} event(s) analyzed."))

    repeat_hosts = by_host[by_host > 1]
    if len(repeat_hosts):
        result.findings.append(Finding("warning", f"{len(repeat_hosts)} host(s) show repeated database-error activity - check agent cache health / consider re-cache or reinstall.", "Check agent cache health on these hosts; consider forcing a cache rebuild or reinstalling the agent if errors persist."))

    result.tables["top_hosts"] = [["Computer", "Related Events"]] + [[h, int(c)] for h, c in by_host.head(TOP_N).items()]
    result.tables["by_subtype"] = [["Event Subtype", "Count"]] + [[s, int(c)] for s, c in by_subtype.items()]

    return result


def build_slides(prs, result: AnalysisResult) -> None:
    ph.add_section_slide(prs, result.title)

    slide = ph.add_content_slide(prs, "Agent Database Errors - Findings")
    ph.add_findings_dashboard(slide, [(f.severity, f.message, f.recommendation) for f in result.findings])

    if "top_hosts" in result.tables:
        slide = ph.add_content_slide(prs, f"Top {TOP_N} Affected Hosts")
        ph.add_table(slide, result.tables["top_hosts"], font_size=10, center=True)

    if "by_subtype" in result.tables:
        slide = ph.add_content_slide(prs, "Related Event Types")
        ph.add_table(slide, result.tables["by_subtype"], font_size=10, center=True)
