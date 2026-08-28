"""
Fleet Health analysis - based on "Approval Metrics+ v4.2.sql".

Per-computer approval breakdown (global/local/policy/rule/unapproved),
agent sync percentage, and whitelist coverage. This is the core
"how healthy is this App Control fleet" view.
"""
import pandas as pd

from . import AnalysisResult, Finding
from ..report import pptx_helpers as ph

SYNC_WARN_THRESHOLD = 98.0
SYNC_CRITICAL_THRESHOLD = 90.0
WHITELIST_WARN_THRESHOLD = 0.90  # fraction
STALE_DAYS = 7


def analyze(df: pd.DataFrame) -> AnalysisResult:
    result = AnalysisResult(title="Fleet Health (Approval Metrics)")
    if df is None or df.empty:
        result.error = "No Approval Metrics data provided."
        return result

    df = df.copy()
    total = len(df)

    sync = pd.to_numeric(df.get("%Sync"), errors="coerce")
    whitelist = pd.to_numeric(df.get("%Whitelist"), errors="coerce")
    global_pct = pd.to_numeric(df.get("%Global"), errors="coerce")

    avg_sync = sync.mean()
    avg_whitelist = whitelist.mean()
    avg_global = global_pct.mean()

    low_sync = df[sync < SYNC_WARN_THRESHOLD]
    critical_sync = df[sync < SYNC_CRITICAL_THRESHOLD]

    if "Last Polled" in df.columns:
        last_polled = pd.to_datetime(df["Last Polled"], errors="coerce")
        # Use the most recent poll timestamp in the data as "now" - the report
        # may be reviewed long after it was collected, so wall-clock time is wrong.
        as_of = last_polled.max()
        if pd.isna(as_of):
            stale = df.iloc[0:0]
        else:
            stale_cutoff = as_of - pd.Timedelta(days=STALE_DAYS)
            stale = df[last_polled < stale_cutoff]
    else:
        stale = df.iloc[0:0]

    config_status_counts = df["ConfigStatus"].value_counts() if "ConfigStatus" in df.columns else pd.Series(dtype=int)
    non_ok_status = config_status_counts.drop(labels=[s for s in config_status_counts.index if str(s).strip().lower() in ("ok", "up to date", "current")], errors="ignore")

    # findings
    if avg_sync is not None and not pd.isna(avg_sync):
        if avg_sync < SYNC_CRITICAL_THRESHOLD:
            result.findings.append(Finding("critical", f"Fleet average agent sync is {avg_sync:.1f}% (critical, target >= {SYNC_WARN_THRESHOLD:.0f}%).", "Investigate fleet-wide agent connectivity/network issues and check for a stuck DailyPruneTask or SQL performance bottleneck causing the sync backlog."))
        elif avg_sync < SYNC_WARN_THRESHOLD:
            result.findings.append(Finding("warning", f"Fleet average agent sync is {avg_sync:.1f}% (below target {SYNC_WARN_THRESHOLD:.0f}%).", "Review the lowest-sync hosts below individually; check network connectivity and agent cache health."))
        else:
            result.findings.append(Finding("ok", f"Fleet average agent sync is {avg_sync:.1f}%."))

    if len(critical_sync) > 0:
        result.findings.append(Finding("critical", f"{len(critical_sync)} computer(s) below {SYNC_CRITICAL_THRESHOLD:.0f}% sync.", "Prioritize remediation of these hosts - verify connectivity, restart the agent service, or force a re-sync."))
    elif len(low_sync) > 0:
        result.findings.append(Finding("warning", f"{len(low_sync)} computer(s) below {SYNC_WARN_THRESHOLD:.0f}% sync.", "Monitor these hosts and force a cache re-sync if the condition persists."))

    if len(stale) > 0:
        result.findings.append(Finding("warning", f"{len(stale)} computer(s) have not polled in over {STALE_DAYS} days.", "Confirm these hosts are still active; decommissioned systems should be removed from App Control to keep reporting accurate."))

    if avg_whitelist is not None and not pd.isna(avg_whitelist) and avg_whitelist < WHITELIST_WARN_THRESHOLD:
        result.findings.append(Finding("caution", f"Average whitelist coverage is {avg_whitelist:.1%}, below the {WHITELIST_WARN_THRESHOLD:.0%} guideline.", "Review policy approval rules and expand publisher/path-based approvals to raise whitelist coverage."))

    if len(non_ok_status) > 0:
        result.findings.append(Finding("warning", f"{int(non_ok_status.sum()):,} computers are not reporting a fully current policy configuration.", "Review affected hosts for outdated approvals, outdated Yara rules, or unprotected status; verify policy assignment and synchronization in the console."))

    result.findings.append(Finding("info", f"{total} computer(s) analyzed."))

    # tables
    header = ["Metric", "Value"]
    summary_rows = [header,
        ["Computers analyzed", total],
        ["Average sync %", f"{avg_sync:.1f}%" if pd.notna(avg_sync) else "n/a"],
        ["Average whitelist %", f"{avg_whitelist:.1%}" if pd.notna(avg_whitelist) else "n/a"],
        ["Average global-approval %", f"{avg_global:.1%}" if pd.notna(avg_global) else "n/a"],
        ["Computers < 98% sync", len(low_sync)],
        ["Computers < 90% sync", len(critical_sync)],
        [f"Stale (> {STALE_DAYS}d no poll)", len(stale)],
    ]
    result.tables["summary"] = summary_rows

    worst_cols = [c for c in ["Computer Name", "%Sync", "ConfigStatus", "#Unapproved", "Last Polled"] if c in df.columns]
    if worst_cols and sync.notna().any():
        worst = df.assign(_sync=sync).sort_values("_sync").head(15)[worst_cols]
        result.tables["worst_sync"] = [worst_cols] + worst.astype(object).where(pd.notna(worst), "").values.tolist()

    approval_source_labels = [
        ("#Global TD", "Global: Trusted directory"),
        ("#Global Rep", "Global: Reputation"),
        ("#Global Oth", "Global: Other"),
        ("#Local Approval: UnValidated", "Local: Initialization (unvalidated)"),
        ("#Local Approval: Policy", "Local: Policy"),
        ("#Local Approval: Rule", "Local: Rule"),
    ]
    present = [(column, label) for column, label in approval_source_labels if column in df.columns]
    if present:
        categories = [label for _, label in present]
        values = [pd.to_numeric(df[column], errors="coerce").sum() for column, _ in present]
        result.charts["approval_sources"] = ("bar", categories, values, total)

    return result


def build_slides(prs, result: AnalysisResult) -> None:
    ph.add_section_slide(prs, result.title)

    slide = ph.add_content_slide(prs, "Fleet Health - Summary")
    findings_sorted = sorted(result.findings, key=lambda f: {"critical": 0, "warning": 1, "caution": 2, "info": 3, "ok": 4}.get(f.severity, 5))
    ph.add_findings_dashboard(slide, [(f.severity, f.message, f.recommendation) for f in findings_sorted])

    if "summary" in result.tables:
        slide = ph.add_content_slide(prs, "Fleet Health - Key Metrics")
        ph.add_table(slide, result.tables["summary"], center=True)

    if "worst_sync" in result.tables:
        slide = ph.add_content_slide(prs, "Fleet Health - Lowest Sync Computers")
        ph.add_table(slide, result.tables["worst_sync"], font_size=10, center=True)

    if "approval_sources" in result.charts:
        kind, categories, values, endpoint_count = result.charts["approval_sources"]
        slide = ph.add_content_slide(prs, "Fleet Health - Approval Source Breakdown")
        ph.add_bar_chart(slide, "Approved File Instances by Source (Current Snapshot)", categories, {"File instances": values}, horizontal=True)
        ph.add_footnote(slide, f"These are not events over a period. They are file instances across {endpoint_count:,} endpoints at export time.")
