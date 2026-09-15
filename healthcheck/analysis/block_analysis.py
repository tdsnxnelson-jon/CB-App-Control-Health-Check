"""
Block Analysis - based on "BlockAnalysis v6.2.sql".

Enforcement events (execution/write blocks, prompts, terminations) classified
by likely cause (logon script, remote execution, approved-publisher gap,
truly unapproved, etc). Useful for spotting noisy hosts/paths and whether
blocks are mostly expected (unapproved software) vs. process issues
(remote/logon-script patterns that may need policy tuning).

v6.2 widens the subtype set (v6.1 only returned two "Execution prompt"
subtypes, so High-enforcement silent blocks were missing entirely) and adds
BlockOutcome / BlockCategory columns. Rows whose outcome is "Allowed" are
prompts the user let through - they are reported separately, not counted as
blocks.
"""
import re

import pandas as pd

from . import AnalysisResult, Finding
from ..report import pptx_helpers as ph

TOP_N = 15
REMOTE_CATEGORIES = ("Remote Application", "Remote Execution", "Remote Writing Local")

# Remediation modelling
REMEDIATION_TOP_N = 10
MIN_CANDIDATE_BLOCKS = 3
# Interpreters/host processes that must never be recommended as updaters - approving
# these would trust anything they write.
GENERIC_PROCESSES = {
    "powershell.exe", "powershell_ise.exe", "pwsh.exe", "cmd.exe", "explorer.exe", "svchost.exe",
    "services.exe", "rundll32.exe", "regsvr32.exe", "wscript.exe", "cscript.exe", "mshta.exe",
    "winlogon.exe", "dllhost.exe", "taskeng.exe", "taskhostw.exe", "python.exe", "pythonw.exe",
    "java.exe", "javaw.exe", "node.exe", "wmiprvse.exe", "msbuild.exe", "msiexec.exe",
    "winrshost.exe", "wsmprovhost.exe", "kernel:write",
}
RISKY_PATH_HINTS = (
    "<userprofiles>", "\\temp", "\\tmp", "\\downloads", "\\recycle", "\\appdata\\",
    "\\programdata\\", "\\public\\",
)
TRUSTED_PUBLISHER_TRUST = {"high", "medium"}
_VERSION_SEGMENT = re.compile(
    r"^(v?\d+(\.\d+)+.*|\{?[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\}?|[0-9a-f]{32,})$",
    re.IGNORECASE,
)
_USER_DIR = re.compile(r"^[a-z]:\\users\\[^\\]+", re.IGNORECASE)


def _categorize(rule_name: str) -> str:
    if not isinstance(rule_name, str):
        return "Unknown"

    normalized = rule_name.strip()
    lowered = normalized.casefold()

    for category in REMOTE_CATEGORIES:
        if category.casefold() == lowered:
            return category

    if lowered == "logon script" or lowered.startswith("logon script"):
        return "Logon Script"

    if normalized.startswith("Approved"):
        return "Approved (publisher/state) - policy gap"
    if normalized == "Unapproved":
        return "Unapproved (expected)"
    return "Other"


def _outcomes(df: pd.DataFrame) -> pd.Series:
    """BlockOutcome from v6.2, or derived from BlockSubtype for older exports."""
    if "BlockOutcome" in df.columns:
        return df["BlockOutcome"].fillna("Blocked").astype(str)
    subtype = df.get("BlockSubtype", pd.Series(index=df.index, dtype=object)).fillna("").astype(str)
    lowered = subtype.str.lower()
    return pd.Series(
        [
            "Allowed" if "allow" in s else ("Blocked (prompt)" if "prompt" in s else "Blocked")
            for s in lowered
        ],
        index=df.index,
    )


def _col(df: pd.DataFrame, name: str) -> pd.Series:
    """Column as clean strings; missing column -> all-empty series."""
    if name not in df.columns:
        return pd.Series("", index=df.index, dtype=object)
    return df[name].fillna("").astype(str).str.strip().str.strip('"')


def _normalize_dir(path: str) -> str:
    """Collapse a directory to the shape a path-based approval rule would use."""
    p = path.strip().strip('"').lower().rstrip("\\/")
    if not p:
        return ""
    p = _USER_DIR.sub("<userprofiles>", p)
    segments = ["*" if _VERSION_SEGMENT.match(seg) else seg for seg in p.split("\\")]
    if "*" in segments:  # everything under the first variable segment is the same rule
        segments = segments[: segments.index("*") + 1]
    return "\\".join(segments)


def _group_risk(group: pd.DataFrame) -> str:
    """Non-empty reason string when a group must not be blanket-approved."""
    flags = _col(group, "FileFlags").str.lower()
    if flags.str.contains("malicious").any():
        return "file flagged malicious"
    if _col(group, "FileState").str.lower().eq("banned").any():
        return "banned file present"
    if _col(group, "BlockSubtype").str.lower().str.contains("banned").any():
        return "banned-file block"
    trust = pd.to_numeric(_col(group, "FileTrust"), errors="coerce")
    if (trust == 0).any():
        return "file trust 0 (known-bad signal)"
    return ""


def _candidate_keys(blocks: pd.DataFrame) -> list:
    """(action label, key series, target formatter) in assignment priority order."""
    publisher = _col(blocks, "Publisher")
    pub_state = _col(blocks, "PublisherState").str.lower()
    publisher_key = publisher.where((publisher != "") & (pub_state != "approved"), "")

    # v6.2 BlockProcessFull is the process that attempted the action; in v6.1 it repeated
    # the blocked file, so fall back to the discovery event's writing process.
    process_col = "BlockProcessFull" if "BlockOutcome" in blocks.columns else "ProcessFull"
    process = _col(blocks, process_col).str.lower()
    process_name = process.str.rsplit("\\", n=1).str[-1]
    process_key = process.where(~process_name.isin(GENERIC_PROCESSES) & (process != ""), "")

    path_key = _col(blocks, "FilePath").map(_normalize_dir)
    hash_key = _col(blocks, "FileHash")

    return [
        ("Approve publisher", publisher_key),
        ("Approve process as updater", process_key),
        ("Add path approval rule", path_key),
        ("Approve file by hash", hash_key),
    ]


def _remediations(blocks: pd.DataFrame) -> tuple:
    """Assign each block to at most one candidate approval, highest-value first.

    Returns (safe_candidates, risky_candidates, unassigned_block_count). Assignment is
    non-overlapping so "top N actions cover X% of blocks" is not double counted.
    """
    unassigned = pd.Series(True, index=blocks.index)
    candidates = []

    for action, keys in _candidate_keys(blocks):
        eligible = unassigned & keys.ne("")
        if not eligible.any():
            continue
        counts = keys[eligible].value_counts()
        for key, count in counts.items():
            if count < MIN_CANDIDATE_BLOCKS:
                continue
            rows = blocks.loc[eligible & keys.eq(key)]
            risk = _group_risk(rows)
            if action == "Approve publisher" and not risk:
                trust = _col(rows, "PublisherTrust").str.lower()
                if not trust.isin(TRUSTED_PUBLISHER_TRUST).any():
                    risk = f"publisher trust '{trust.iloc[0] or 'unknown'}'"
            if action == "Add path approval rule" and not risk:
                if any(hint in key for hint in RISKY_PATH_HINTS):
                    risk = "user-writable / temp location"
            candidates.append({
                "action": action,
                "target": _display_target(action, key, rows),
                "blocks": int(len(rows)),
                "hosts": int(_col(rows, "ComputerName").nunique()),
                "users": int(_col(rows, "UserName").nunique()),
                "risk": risk,
            })
            unassigned &= ~blocks.index.isin(rows.index)

    candidates.sort(key=lambda c: c["blocks"], reverse=True)
    safe = [c for c in candidates if not c["risk"]]
    risky = [c for c in candidates if c["risk"]]
    return safe, risky, int(unassigned.sum())


def _display_target(action: str, key: str, rows: pd.DataFrame) -> str:
    if action == "Approve file by hash":
        name = _col(rows, "FileNameShort").iloc[0] or "(unnamed)"
        return f"{name} ({key[:12]}...)"
    return key


def analyze(df: pd.DataFrame) -> AnalysisResult:
    result = AnalysisResult(title="Block Analysis")
    if df is None or df.empty:
        result.error = "No Block Analysis data provided."
        return result

    df = df.copy()
    outcome = _outcomes(df)
    allowed_count = int((outcome == "Allowed").sum())
    blocks = df.loc[outcome != "Allowed"]
    total = len(blocks)

    if not total:
        result.error = (
            f"No enforcement blocks in the export ({allowed_count:,} allowed prompt(s) only)."
        )
        return result

    category = blocks.get("RuleName", pd.Series(dtype=object)).map(_categorize)
    by_category = category.value_counts()
    by_subtype = (
        df["BlockSubtype"].fillna("(unknown)").value_counts()
        if "BlockSubtype" in df.columns
        else pd.Series(dtype=int)
    )

    by_computer = blocks["ComputerName"].value_counts() if "ComputerName" in blocks.columns else pd.Series(dtype=int)
    by_path = blocks["FilePath"].value_counts() if "FilePath" in blocks.columns else pd.Series(dtype=int)
    timestamps = pd.to_datetime(blocks.get("TimeStamp"), errors="coerce")
    by_day = blocks.loc[timestamps.notna()].groupby(timestamps.dt.date).size().sort_index()

    result.findings.append(Finding("info", f"{total:,} block event(s) analyzed."))

    if "BlockOutcome" not in df.columns:
        result.findings.append(Finding(
            "caution",
            "This export came from BlockAnalysis v6.1, which only returned execution-prompt events - "
            "silent High-enforcement blocks are missing, so block volume and remediation coverage are understated.",
            "Re-run the data collection with BlockAnalysis v6.2 to capture all enforcement events.",
        ))

    if allowed_count:
        result.findings.append(Finding(
            "caution",
            f"{allowed_count:,} additional execution prompt(s) were allowed by the end user - these are not counted as blocks.",
            "Users overriding prompts defeats enforcement; review whether these policies should move to High enforcement or the files should be approved by rule.",
        ))

    if "BlockCategory" in blocks.columns:
        write_blocks = int((blocks["BlockCategory"] == "Write").sum())
        if write_blocks:
            result.findings.append(Finding(
                "info",
                f"{write_blocks:,} of the blocks are write blocks (rest are execution/termination).",
            ))

    remote_count = sum(by_category.get(c, 0) for c in REMOTE_CATEGORIES)
    if remote_count:
        pct = remote_count / total
        result.findings.append(Finding("caution" if pct < 0.2 else "warning", f"{remote_count:,} ({pct:.0%}) blocks involve remote execution/write patterns - review network share and remote-admin policy scoping.", "Review network share and remote-admin policy scoping; consider tighter path-based rules for remote execution."))

    gap_count = by_category.get("Approved (publisher/state) - policy gap", 0)
    if gap_count:
        pct = gap_count / total
        result.findings.append(Finding("warning", f"{gap_count:,} ({pct:.0%}) blocked files came from an already-approved publisher/state - indicates a rule ordering or scoping gap worth investigating.", "Check rule evaluation order in the console - an approved-publisher/state file shouldn't reach a block unless a higher-priority deny/unapproved rule is misconfigured."))

    if len(by_computer):
        top_host, top_host_count = by_computer.index[0], by_computer.iloc[0]
        if total and top_host_count / total > 0.2:
            result.findings.append(Finding("warning", f"'{top_host}' accounts for {top_host_count / total:.0%} of all blocks - investigate this host individually.", "Investigate this host individually for misconfiguration, unusual software, or a misapplied policy."))

    result.tables["by_category"] = [["Category", "Count"]] + [[c, int(v)] for c, v in by_category.items()]
    if len(by_subtype):
        result.tables["by_subtype"] = [["Event Subtype", "Count"]] + [[s, int(v)] for s, v in by_subtype.items()]
    result.tables["top_computers"] = [["Computer", "Blocks"]] + [[c, int(v)] for c, v in by_computer.head(TOP_N).items()]
    result.tables["top_paths"] = [["File Path", "Blocks"]] + [[p, int(v)] for p, v in by_path.head(TOP_N).items()]

    _add_remediations(result, blocks, total)

    if len(by_category):
        result.charts["category_pie"] = ("pie", list(by_category.index), list(by_category.values))
    if len(by_day):
        result.charts["daily_blocks"] = ("line", [str(day) for day in by_day.index], {"Blocks/day": by_day.tolist()})

    return result


def _add_remediations(result: AnalysisResult, blocks: pd.DataFrame, total: int) -> None:
    """Top-N approval actions ranked by how many blocks each would remove."""
    safe, risky, one_offs = _remediations(blocks)
    top = safe[:REMEDIATION_TOP_N]

    if top:
        covered = sum(c["blocks"] for c in top)
        pct = covered / total
        lead = top[0]
        result.findings.append(Finding(
            "warning" if pct >= 0.2 else "info",
            f"{len(top)} recommended approval action(s) would address {covered:,} of {total:,} blocks "
            f"({pct:.0%}); the single largest is \"{lead['action']}: {lead['target']}\" "
            f"({lead['blocks']:,} blocks across {lead['hosts']:,} computer(s)).",
            "Create these approvals in the console highest-coverage first to cut recurring block volume and the support tickets it generates." if pct >= 0.2 else None,
        ))

        running = 0
        cumulative = []
        for c in top:
            running += c["blocks"]
            cumulative.append(round(running / total * 100, 1))
        result.charts["remediation_coverage"] = (
            "line",
            [
                f"{i}. {c['action']}: {c['target']}"
                for i, c in enumerate(top, start=1)
            ],
            {"% of blocks addressed": cumulative},
        )

    if top or risky:
        rows = [["Recommended Action", "Target", "Blocks", "Computers", "Users"]]
        rows += [[c["action"], c["target"], c["blocks"], c["hosts"], c["users"]] for c in top]
        rows += [
            ["Investigate (do not approve)", f"{c['target']} - {c['risk']}", c["blocks"], c["hosts"], c["users"]]
            for c in risky[:5]
        ]
        result.tables["remediations"] = rows

    if risky:
        risky_blocks = sum(c["blocks"] for c in risky)
        result.findings.append(Finding(
            "warning",
            f"{len(risky)} block cluster(s) ({risky_blocks:,} blocks) look actionable but must not be blanket-approved "
            f"(e.g. {risky[0]['target']}: {risky[0]['risk']}).",
            "Triage these individually - approving them would trust an untrusted publisher, a temp/user-writable location, or a file with a known-bad signal.",
        ))

    if one_offs:
        result.findings.append(Finding(
            "info",
            f"{one_offs:,} block(s) form no repeating pattern (fewer than {MIN_CANDIDATE_BLOCKS} per candidate rule) - these are one-off/expected enforcement.",
        ))


def build_slides(prs, result: AnalysisResult) -> None:
    ph.add_section_slide(prs, result.title)

    slide = ph.add_content_slide(prs, "Block Analysis - Findings")
    ph.add_findings_dashboard(slide, [(f.severity, f.message, f.recommendation) for f in result.findings])

    if "remediations" in result.tables:
        slide = ph.add_content_slide(prs, "Top Remediation Opportunities")
        ph.add_table(
            slide,
            result.tables["remediations"],
            font_size=10,
            center=True,
            col_widths=[2.6, 6.4, 1.1, 1.3, 1.0],
        )
        ph.add_footnote(slide, "Each block is attributed to a single best-fit action, so the counts do not overlap.")

    if "remediation_coverage" in result.charts:
        _, categories, series = result.charts["remediation_coverage"]
        slide = ph.add_content_slide(prs, "Cumulative Block Reduction")
        ph.add_line_chart(slide, "Cumulative % of blocks addressed", categories, series)
        ph.add_footnote(slide, "X axis: cumulative recommended approval actions applied; each label shows the action and target in coverage order.")

    if "daily_blocks" in result.charts:
        _, categories, series = result.charts["daily_blocks"]
        slide = ph.add_content_slide(prs, "Blocks Over Time")
        ph.add_line_chart(slide, "Blocks per Day", categories, series)

    if "category_pie" in result.charts:
        _, categories, values = result.charts["category_pie"]
        slide = ph.add_content_slide(prs, "Blocks by Root Cause")
        chart_colors = ph.PIE_COLORS[:len(categories)]
        ph.add_pie_chart(
            slide,
            "Block Root Cause",
            categories,
            values,
            left=ph.MARGIN,
            width=6.1,
            show_legend=False,
            colors=chart_colors,
        )
        root_cause_rows = [["", "Root Cause", "Blocks"], ["", "Total blocks", sum(values)]]
        root_cause_rows.extend(["", category, count] for category, count in zip(categories, values))
        table = ph.add_table(
            slide,
            root_cause_rows,
            left=6.8,
            top=1.8,
            width=5.85,
            height=4.6,
            font_size=10,
            col_widths=[0.35, 4.2, 1.3],
        )
        for row_index, color in enumerate(chart_colors, start=2):
            cell = table.cell(row_index, 0)
            cell.fill.solid()
            cell.fill.fore_color.rgb = color

    if "top_computers" in result.tables:
        slide = ph.add_content_slide(prs, f"Top {TOP_N} Computers by Block Count")
        ph.add_table(slide, result.tables["top_computers"], font_size=10, center=True)

    if "by_subtype" in result.tables:
        slide = ph.add_content_slide(prs, "Enforcement Events by Subtype")
        ph.add_table(slide, result.tables["by_subtype"], font_size=10, center=True)

    if "top_paths" in result.tables:
        slide = ph.add_content_slide(prs, f"Top {TOP_N} Blocked File Paths")
        ph.add_table(slide, result.tables["top_paths"], font_size=9, center=True)
