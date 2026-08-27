"""
Computer inventory analysis from the App Control console Computers export.
"""
import pandas as pd

from . import AnalysisResult, Finding
from ..report import pptx_helpers as ph

MAX_LIST_ROWS = 150


def _series(df: pd.DataFrame, column: str, default: str = "") -> pd.Series:
    if column in df.columns:
        return df[column].fillna(default).astype(str).str.strip()
    return pd.Series([default] * len(df), index=df.index, dtype="object")


def _count_table(df: pd.DataFrame, column: str, count_label: str, include_percent: bool = True) -> list[list]:
    if column not in df.columns:
        return []
    values = _series(df, column).replace("", "(blank)")
    counts = values.value_counts(sort=False)
    total = int(counts.sum())
    header = ["Row Labels", count_label] + (["Percentage"] if include_percent else [])
    rows = [header]
    for label, count in counts.items():
        row = [label, int(count)]
        if include_percent:
            row.append(f"{(count / total):.1%}" if total else "0.0%")
        rows.append(row)
    total_row = ["Grand Total", total]
    if include_percent:
        total_row.append("100.0%" if total else "0.0%")
    rows.append(total_row)
    return rows


def _connectivity_table(df: pd.DataFrame, days_offline: pd.Series) -> list[list]:
    connected = _series(df, "Connected")
    total = len(df)
    disconnected_10 = connected.str.contains("Disconnected", case=False, na=False) & (days_offline > 10)
    selected = connected[connected.str.startswith("Connected", na=False) | disconnected_10].copy()
    selected.loc[disconnected_10] = "Disconnected for >10 days"
    counts = selected.value_counts(sort=False)
    preferred_order = [
        "Connected",
        "Connected, health check has failed",
        "Connected, Not requested",
        "Connected, Reboot required",
        "Connected, Upgrades disabled",
        "Disconnected for >10 days",
    ]
    rows = [["Row Labels", "Count of Connected", "Percentage"]]
    for label in preferred_order:
        if label in counts.index:
            count = int(counts[label])
            rows.append([label, count, f"{(count / total):.1%}" if total else "0.0%"])
    for label, count in counts.items():
        if label not in preferred_order:
            rows.append([label, int(count), f"{(count / total):.1%}" if total else "0.0%"])
    return rows


def _computer_table(df: pd.DataFrame, columns: list[str]) -> list[list]:
    present = [col for col in columns if col in df.columns]
    if not present:
        return []
    return [present] + df[present].fillna("").astype(str).values.tolist()[:MAX_LIST_ROWS]


def analyze(df: pd.DataFrame) -> AnalysisResult:
    result = AnalysisResult(title="Computer Inventory Health")
    if df is None or df.empty:
        result.error = "No Computers inventory data provided."
        return result

    df = df.copy()
    total = len(df)
    connected = _series(df, "Connected")
    active = _series(df, "Active")
    days_offline = pd.to_numeric(df.get("Days Offline"), errors="coerce") if "Days Offline" in df.columns else pd.Series([None] * len(df), index=df.index)

    connected_computers = df[connected.str.casefold().eq("connected")]
    disconnected_10 = df[connected.str.contains("disconnected", case=False, na=False) & (days_offline > 10)]
    inactive = df[active.str.casefold().eq("no")]

    result.findings.append(Finding("info", f"{total:,} computer(s) analyzed from the console inventory export."))
    result.findings.append(Finding("info", f"{len(connected_computers):,} computer(s) are currently connected."))
    if len(disconnected_10):
        result.findings.append(Finding(
            "warning",
            f"{len(disconnected_10):,} computer(s) have been disconnected for more than 10 days.",
            "Confirm whether these endpoints are retired, rebuilt, or blocked from communicating; remove stale records when appropriate.",
        ))
    if len(inactive):
        result.findings.append(Finding(
            "caution",
            f"{len(inactive):,} computer(s) are marked inactive.",
            "Review inactive systems before relying on fleet-wide policy and agent health percentages.",
        ))

    result.tables["connected_summary"] = _connectivity_table(df, days_offline)
    result.tables["active_summary"] = _count_table(df, "Active", "Count of Active")
    result.tables["connected_computers"] = _computer_table(connected_computers, ["Computer Name", "Connected", "Active", "Policy", "Agent Version", "Last Poll"])
    result.tables["disconnected_10"] = _computer_table(disconnected_10, ["Computer Name", "Connected", "Days Offline", "Active", "Policy", "Last Poll"])

    for key, column in [
        ("connected_enforcement", "Connected Enforcement"),
        ("disconnected_enforcement", "Disconnected Enforcement"),
        ("policy_status", "Policy Status"),
        ("upgrade_status", "Upgrade Status"),
        ("agent_version", "Agent Version"),
    ]:
        result.tables[key] = _count_table(df, column, f"Count of {column}")

    return result


def build_slides(prs, result: AnalysisResult) -> None:
    ph.add_section_slide(prs, result.title)

    slide = ph.add_content_slide(prs, "Computer Inventory - Findings")
    ph.add_findings_dashboard(slide, [(f.severity, f.message, f.recommendation) for f in result.findings])

    _add_connectivity_slide(prs, result)
    _add_policy_agent_slide(prs, result)

    if result.tables.get("disconnected_10", [])[1:]:
        ph.add_table_slides(prs, "Computers Disconnected for More Than 10 Days", result.tables["disconnected_10"], font_size=8, max_total_rows=MAX_LIST_ROWS)


def _add_connectivity_slide(prs, result: AnalysisResult) -> None:
    slide = ph.add_content_slide(prs, "Computer Connectivity Summary")
    if "connected_summary" in result.tables:
        ph.add_table(slide, result.tables["connected_summary"], left=0.45, top=1.35, width=6.2, height=2.0, font_size=10, max_rows=8)
    if "active_summary" in result.tables:
        ph.add_table(slide, result.tables["active_summary"], left=0.45, top=3.85, width=5.2, height=1.6, font_size=10, max_rows=8)
    if result.tables.get("disconnected_10", [])[1:]:
        rows = result.tables["disconnected_10"]
        names = [["Disconnected for >10 days"]] + [[row[0]] for row in rows[1:31]]
        ph.add_table(slide, names, left=7.0, top=1.35, width=5.7, height=5.4, font_size=9, max_rows=31)


def _add_policy_agent_slide(prs, result: AnalysisResult) -> None:
    slide = ph.add_content_slide(prs, "Policy and Agent Health")
    tables = [
        ("connected_enforcement", 0.45, 1.25, 5.95, 1.0),
        ("disconnected_enforcement", 0.45, 2.6, 5.95, 1.0),
        ("policy_status", 0.45, 3.95, 5.95, 1.35),
        ("upgrade_status", 7.0, 1.25, 5.85, 1.65),
        ("agent_version", 7.0, 3.3, 5.85, 1.35),
    ]
    for key, left, top, width, height in tables:
        rows = result.tables.get(key)
        if rows:
            ph.add_table(slide, rows, left=left, top=top, width=width, height=height, font_size=8, max_rows=8)