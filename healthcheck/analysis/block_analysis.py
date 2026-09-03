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
import pandas as pd

from . import AnalysisResult, Finding
from ..report import pptx_helpers as ph

TOP_N = 15
REMOTE_CATEGORIES = ("Remote Application", "Remote Execution", "Remote Writing Local")


def _categorize(rule_name: str) -> str:
    if not isinstance(rule_name, str):
        return "Unknown"
    if rule_name in REMOTE_CATEGORIES or rule_name == "Logon Script":
        return rule_name
    if rule_name.startswith("Approved"):
        return "Approved (publisher/state) - policy gap"
    if rule_name == "Unapproved":
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

    if len(by_category):
        result.charts["category_pie"] = ("pie", list(by_category.index), list(by_category.values))
    if len(by_day):
        result.charts["daily_blocks"] = ("line", [str(day) for day in by_day.index], {"Blocks/day": by_day.tolist()})

    return result


def build_slides(prs, result: AnalysisResult) -> None:
    ph.add_section_slide(prs, result.title)

    slide = ph.add_content_slide(prs, "Block Analysis - Findings")
    ph.add_findings_dashboard(slide, [(f.severity, f.message, f.recommendation) for f in result.findings])

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
