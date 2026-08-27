"""
Orphaned Path/File Name Analysis - based on "FilePath_Pruning_Scope_AllVersion.sql".

Flags database bloat in the pathnames/filenames tables caused by rows no
longer referenced anywhere (a known DB growth/performance issue on
long-running App Control servers).
"""
import pandas as pd

from . import AnalysisResult, Finding
from ..report import pptx_helpers as ph

ORPHAN_PCT_WARNING = 0.20
ORPHAN_PCT_CRITICAL = 0.40


def analyze(df: pd.DataFrame) -> AnalysisResult:
    result = AnalysisResult(title="Database Bloat - Orphaned Rows")
    if df is None or df.empty:
        result.error = "No orphaned path/file name data provided."
        return result

    df = df.copy()
    for col in ["RowsCount", "UsedSpaceKB", "OrphanedRowsCount", "OrphanedPercent", "OrphanedSpaceKB"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    for _, row in df.iterrows():
        name = row.get("TableName", "table")
        pct = row.get("OrphanedPercent", 0) or 0
        space_kb = row.get("OrphanedSpaceKB", 0) or 0
        if pct >= ORPHAN_PCT_CRITICAL:
            result.findings.append(Finding("critical", f"[{name}] {pct:.1%} of rows are orphaned (~{space_kb / 1024:.0f} MB) - schedule a maintenance/prune pass.", "Schedule a maintenance window to run the pathname/filename cleanup procedure with TDSYNNEX/vendor support."))
        elif pct >= ORPHAN_PCT_WARNING:
            result.findings.append(Finding("warning", f"[{name}] {pct:.1%} of rows are orphaned (~{space_kb / 1024:.0f} MB).", "Plan a maintenance window for the pathname/filename cleanup procedure before this grows further."))
        else:
            result.findings.append(Finding("ok", f"[{name}] orphaned rows within normal range ({pct:.1%}).", f"Thresholds: warning at {ORPHAN_PCT_WARNING:.0%}, critical at {ORPHAN_PCT_CRITICAL:.0%}."))

    cols = [c for c in ["TableName", "RowsCount", "UsedSpaceKB", "OrphanedRowsCount", "OrphanedPercent", "OrphanedSpaceKB"] if c in df.columns]
    display = df[cols].copy()
    if "OrphanedPercent" in display.columns:
        display["OrphanedPercent"] = display["OrphanedPercent"].map(lambda v: f"{v:.1%}" if pd.notna(v) else "")
    result.tables["table_bloat"] = [cols] + display.astype(object).where(pd.notna(display), "").values.tolist()

    return result


def build_slides(prs, result: AnalysisResult) -> None:
    ph.add_section_slide(prs, result.title)

    slide = ph.add_content_slide(prs, "Database Bloat - Findings")
    ph.add_findings_dashboard(slide, [(f.severity, f.message, f.recommendation) for f in result.findings])

    if "table_bloat" in result.tables:
        slide = ph.add_content_slide(prs, "Orphaned Row / Space Detail")
        ph.add_table(slide, result.tables["table_bloat"], font_size=10, center=True)
