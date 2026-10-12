"""
Computer inventory analysis from the App Control console Computers export.
"""
import pandas as pd
from datetime import date

from . import AnalysisResult, Finding
from ..report import pptx_helpers as ph

MAX_LIST_ROWS = 150

_WINDOWS_LIFECYCLE_DATES = {
    (8, 12): ("2026-06-22", None, None),
    (8, 11): ("2026-03-05", "2027-09-01", None),
    (8, 10): ("2025-02-26", "2027-02-26", None),
    (8, 9): ("2023-04-24", "2024-10-24", "2026-10-24"),
    (8, 8): ("2022-10-20", "2024-04-20", "2026-04-20"),
    (8, 7): ("2021-11-25", "2023-05-25", "2025-05-25"),
    (8, 6): ("2021-04-01", "2022-10-01", "2024-10-01"),
    (8, 5): ("2020-11-03", "2022-05-03", "2024-05-03"),
    (8, 1): ("2019-06-03", "2021-06-03", "2022-12-03"),
}

_AGENT_LIFECYCLE_DATES = {
    "windows_desktop": _WINDOWS_LIFECYCLE_DATES,
    "windows_server": _WINDOWS_LIFECYCLE_DATES,
    "linux": {
        (8, 9): ("2026-05-11", None, None),
        (8, 8): ("2024-05-08", "2026-06-08", "2027-11-11"),
        (8, 7): ("2023-12-14", "2026-03-14", None),
        (8, 6): ("2021-02-04", "2024-08-04", None),
        (8, 5): ("2020-09-25", "2024-03-25", None),
        (7, 4): ("2019-05-31", "2022-11-30", None),
    },
    "macos": {
        (8, 11): ("2026-09-09", None, None),
        (8, 10): ("2025-09-08", None, None),
        (8, 9): ("2023-07-27", "2024-07-27", "2026-03-08"),
        (8, 8): ("2023-02-22", "2024-08-22", "2026-08-22"),
        (8, 7): ("2021-11-11", "2023-05-11", "2025-05-11"),
        (8, 6): ("2021-06-01", "2022-12-01", "2024-12-01"),
        (8, 5): ("2021-03-17", "2022-09-17", "2024-09-17"),
    },
}


def _series(df: pd.DataFrame, column: str, default: str = "") -> pd.Series:
    if column in df.columns:
        return df[column].fillna(default).astype(str).str.strip()
    return pd.Series([default] * len(df), index=df.index, dtype="object")


def _lifecycle_platform(os_name: str) -> str:
    value = os_name.casefold()
    if "windows" in value or value.startswith("win"):
        if "server" in value:
            return "windows_server"
        if any(marker in value for marker in ("desktop", "workstation", "windows 10", "windows 11", "windows 8", "windows 7", "win 10", "win 11")):
            return "windows_desktop"
        return ""
    if "linux" in value:
        return "linux"
    if "mac" in value or "darwin" in value:
        return "macos"
    return ""


def _agent_lifecycle_status(os_name: str, version: str, as_of: date | None = None) -> str:
    platform = _lifecycle_platform(os_name)
    parts = str(version).split(".")
    if not platform or len(parts) < 2 or not parts[0].isdigit() or not parts[1].isdigit():
        return "Unknown"
    lifecycle_dates = _AGENT_LIFECYCLE_DATES.get(platform, {}).get((int(parts[0]), int(parts[1])))
    if lifecycle_dates is None:
        return "Unknown"

    current_date = as_of or date.today()
    ga_date, eos_date, eol_date = (date.fromisoformat(value) if value else None for value in lifecycle_dates)
    if ga_date and current_date < ga_date:
        return "Not GA"
    if eol_date and current_date >= eol_date:
        return "EOL"
    if eos_date and current_date >= eos_date:
        return "EOS"
    return "GA"


def _agent_version_table(df: pd.DataFrame, as_of: date | None = None) -> list[list]:
    os_columns = {str(column).strip().casefold(): column for column in df.columns}
    os_column = next((os_columns[name] for name in ("operating system", "os name", "os", "platform") if name in os_columns), None)
    operating_system = _series(df, os_column, "Unknown") if os_column else pd.Series(["Unknown"] * len(df), index=df.index)
    operating_system = operating_system.replace("", "Unknown")
    versions = _series(df, "Agent Version").replace("", "(blank)")
    grouped = pd.DataFrame({"Operating System": operating_system, "Agent Version": versions}).groupby(
        ["Operating System", "Agent Version"], sort=False, dropna=False
    ).size()
    total = len(df)
    rows = [["Operating System", "Agent Version", "Lifecycle", "Count", "Percentage"]]
    version_sort_key = lambda version: (
        bool(str(version).split(".")) and all(part.isdigit() for part in str(version).split(".")),
        tuple(int(part) for part in str(version).split(".") if part.isdigit()),
    )
    sorted_rows = sorted(grouped.items(), key=lambda item: version_sort_key(item[0][1]), reverse=True)
    for (os_name, version), count in sorted_rows:
        rows.append([
            os_name,
            version,
            _agent_lifecycle_status(os_name, version, as_of),
            int(count),
            f"{(count / total):.1%}" if total else "0.0%",
        ])
    rows.append(["Grand Total", "", "", total, "100.0%" if total else "0.0%"])
    return rows


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
    ]:
        result.tables[key] = _count_table(df, column, f"Count of {column}")
    result.tables["agent_version"] = _agent_version_table(df)

    return result


def build_slides(prs, result: AnalysisResult) -> None:
    ph.add_section_slide(prs, result.title)
    _add_inactive_agents_slide(prs)

    slide = ph.add_content_slide(prs, "Computer Inventory - Findings")
    ph.add_findings_dashboard(slide, [(f.severity, f.message, f.recommendation) for f in result.findings])

    _add_connectivity_slide(prs, result)
    _add_policy_agent_slide(prs, result)

    agent_versions = result.tables.get("agent_version")
    if agent_versions and agent_versions[1:]:
        ph.add_table_slides(
            prs,
            "Agent Version Inventory",
            agent_versions,
            font_size=8,
            max_total_rows=len(agent_versions) - 1,
        )

    if result.tables.get("disconnected_10", [])[1:]:
        ph.add_table_slides(prs, "Computers Disconnected for More Than 10 Days", result.tables["disconnected_10"], font_size=8, max_total_rows=MAX_LIST_ROWS)


def _add_inactive_agents_slide(prs) -> None:
    slide = ph.add_content_slide(prs, "Key Characteristics of Inactive Agents")
    left = 0.55
    column_width = 5.85
    right = 6.9
    heading_size = 13
    body_size = 10

    characteristics = [
        (0, [("Heartbeat Timeout: ", True, False), ("The agent has not checked in within its configured timeframe. A common Smart Computer Group threshold is 30 days or more.", False, False)]),
        (0, [("Management vs. Enforcement: ", True, False), ("The agent continues enforcing its last known policy, but cannot receive new approvals, bans, or policy updates until it reconnects as Active or Connected.", False, False)]),
        (0, [("License Impact: ", True, False), ("Inactive agents continue to consume a license seat until the computer record is deleted or moved to an Unmanaged state.", False, False)]),
    ]
    reasons = [
        (0, [("1. Endpoint Offline: ", True, False), ("Powered off, in storage, or decommissioned without uninstalling the agent.", False, False)]),
        (0, [("2. Network Isolation: ", True, False), ("A firewall or network change blocks agent-to-server communication (often port 41002).", False, False)]),
        (0, [("3. Service Failure: ", True, False), ("The Carbon Black App Control agent service, such as Parity Agent, is stopped or crashed.", False, False)]),
        (0, [("4. Certificate Issues: ", True, False), ("A server SSL certificate update may prevent authentication if the agent did not receive the new trusted root.", False, False)]),
    ]
    actions = [
        (0, [("Verify Connectivity: ", True, False), ("Check whether the host is reachable and required endpoint-to-server ports are open.", False, False)]),
        (0, [("Check Local Service: ", True, False), ("Windows: services.msc > Carbon Black App Control Agent (or Parity Agent). Linux/macOS: run b9cli --status, if available.", False, False)]),
        (0, [("Administrative Cleanup: ", True, False), ("Delete the console computer record when the endpoint is no longer in use to reclaim its license seat and remove it from the active computers list.", False, False)]),
        (0, [("Warning: ", True, False), ("Disabled mode is not Inactive. A disabled agent is still communicating but has stopped enforcing security rules. Confirm the agent is healthy and active before upgrading.", False, False)]),
    ]

    ph._add_text(slide, left, 1.35, column_width, 0.28, "Key Characteristics", size=heading_size, bold=True, color=ph.NAVY)
    ph.add_rich_bullets(slide, characteristics, left=left, top=1.72, width=column_width, height=5.25, font_size=body_size)

    ph._add_text(slide, right, 1.35, column_width, 0.28, "Common Reasons for Inactive Status", size=heading_size, bold=True, color=ph.NAVY)
    ph.add_rich_bullets(slide, reasons, left=right, top=1.72, width=column_width, height=2.45, font_size=body_size)
    ph._add_text(slide, right, 4.25, column_width, 0.28, "How to Handle Inactive Agents", size=heading_size, bold=True, color=ph.NAVY)
    ph.add_rich_bullets(slide, actions, left=right, top=4.6, width=column_width, height=2.37, font_size=body_size)


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
    ]
    for key, left, top, width, height in tables:
        rows = result.tables.get(key)
        if rows:
            ph.add_table(slide, rows, left=left, top=top, width=width, height=height, font_size=8, max_rows=8)
    ph.add_footnote(slide, f"Agent lifecycle stage as of {date.today().isoformat()}; based on Broadcom platform-specific OER lifecycle dates.")