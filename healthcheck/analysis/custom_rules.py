"""
Custom rule inventory analysis from the App Control console Custom export.
"""
import pandas as pd

from . import AnalysisResult, Finding
from ..report import pptx_helpers as ph

EXEC_BLOCK_WARN_THRESHOLD = 10
MIN_FILE_CREATE_TO_EXEC_BLOCK_RATIO = 10.0
MAX_LIST_ROWS = 150


def _series(df: pd.DataFrame, column: str, default: str = "") -> pd.Series:
    if column in df.columns:
        return df[column].fillna(default).astype(str).str.strip()
    return pd.Series([default] * len(df), index=df.index, dtype="object")


def _enabled_mask(df: pd.DataFrame) -> pd.Series:
    return _series(df, "Status").str.casefold().eq("enabled")


def _table_from_df(df: pd.DataFrame, columns: list[str]) -> list[list]:
    present = [col for col in columns if col in df.columns]
    if not present:
        return []
    values = df[present].fillna("").astype(str).values.tolist()
    return [present] + values[:MAX_LIST_ROWS]


def analyze(df: pd.DataFrame) -> AnalysisResult:
    result = AnalysisResult(title="Custom Rule Health")
    if df is None or df.empty:
        result.error = "No Custom rule inventory data provided."
        return result

    df = df.copy()
    total = len(df)
    enabled = _enabled_mask(df)
    rule_type = _series(df, "Rule Type")
    action = _series(df, "Action")
    path = _series(df, "Path")
    process = _series(df, "Process")
    user_group = _series(df, "User or Group")

    invalid_path = df[enabled & path.ne("") & path.str.endswith(("\\", "/"), na=False)]
    exec_blocking = df[
        enabled
        & rule_type.str.casefold().eq("execution control")
        & action.str.contains("block", case=False, na=False)
    ]
    file_creation = df[enabled & rule_type.str.casefold().eq("file creation control")]
    broad_scope = df[
        enabled
        & process.eq("*")
        & user_group.str.casefold().eq("any user")
    ]

    exec_block_count = len(exec_blocking)
    file_creation_count = len(file_creation)
    ratio = file_creation_count / exec_block_count if exec_block_count else None

    result.findings.append(Finding("info", f"{total:,} custom rule(s) analyzed; {int(enabled.sum()):,} are enabled."))

    if len(invalid_path):
        result.findings.append(Finding(
            "warning",
            f"{len(invalid_path):,} enabled rule(s) have a Path ending in '\\' or '/'.",
            "Add a wildcard or process/file name at the end of each path so the rule evaluates as intended.",
        ))
    else:
        result.findings.append(Finding("ok", "No enabled rules have a Path ending in '\\' or '/'."))

    if exec_block_count > EXEC_BLOCK_WARN_THRESHOLD:
        result.findings.append(Finding(
            "warning",
            f"{exec_block_count:,} enabled Execution Control rule(s) are configured to block.",
            "Consider moving high-volume blocking patterns to File Creation Control rules where possible; they are more performant for this use case.",
        ))
    else:
        result.findings.append(Finding("ok", f"{exec_block_count:,} enabled blocking Execution Control rule(s) found."))

    ratio_text = "n/a" if ratio is None else f"{ratio:.1f}:1"
    if ratio is not None and ratio < MIN_FILE_CREATE_TO_EXEC_BLOCK_RATIO:
        result.findings.append(Finding(
            "warning",
            f"File Creation Control to blocking Execution Control ratio is {ratio_text}; target is at least 10:1.",
            "Prefer File Creation Control for blocking file-write patterns and reserve Execution Control blocks for true execute-time decisions.",
        ))
    else:
        result.findings.append(Finding("ok", f"File Creation Control to blocking Execution Control ratio is {ratio_text}."))

    if len(broad_scope):
        result.findings.append(Finding(
            "caution",
            f"{len(broad_scope):,} enabled rule(s) are Any Process, Any User.",
            "Narrow Process and User or Group scope to reduce unintended approval or block impact.",
        ))
    else:
        result.findings.append(Finding("ok", "No enabled rules are Any Process, Any User."))

    result.tables["metrics"] = [
        ["Metric", "Value"],
        ["Enabled custom rules", int(enabled.sum())],
        ["Enabled blocking Execution Control", exec_block_count],
        ["Enabled File Creation Control", file_creation_count],
        ["File Creation : blocking Execution", ratio_text],
        ["Path ends with slash", len(invalid_path)],
        ["Any Process, Any User", len(broad_scope)],
    ]
    result.tables["invalid_paths"] = _table_from_df(invalid_path, ["Rule Type", "Name", "Action", "Path", "Process", "User or Group", "Policy"])
    result.tables["exec_blocking"] = _table_from_df(exec_blocking, ["Name", "Operation", "Path", "Process", "User or Group", "Policy"])
    result.tables["broad_scope"] = _table_from_df(broad_scope, ["Rule Type", "Name", "Action", "Path", "Process", "User or Group", "Policy"])

    counts = rule_type[enabled].replace("", "(blank)").value_counts().head(12)
    if len(counts):
        result.charts["rule_types"] = ("bar", counts.index.tolist(), {"Enabled rules": counts.values.tolist()})

    return result


def build_slides(prs, result: AnalysisResult) -> None:
    ph.add_section_slide(prs, result.title)

    slide = ph.add_content_slide(prs, "Rule Types")
    ph.add_rich_bullets(slide, [
        (0, [("Execution Control (Allow)", True, False), (" - use this sparingly and only when necessary. For example:", False, False)]),
        (1, [("When a file is executed from a UNC path or a network share", False, False)]),
        (1, [("When you wish to enforce that a file runs only from a certain folder or by certain users or groups.", False, False)]),
        (1, [("When you must allow the file to run, but for reporting or security purposes, you wish to keep the file unapproved.", False, False)]),
        (1, [("Less performant", False, False)]),
        (2, [("Have to evaluate rules until hit or end of list", False, False)]),
        (2, [("Rule expansion - Process x Path x User", False, False)]),
        (0, [("DO NOT WRITE CUSTOM RULES FROM BLOCK EVENTS!!!", True, True)]),
        (1, [("You are only seeing the executed data, not how the data was discovered", False, False)]),
        (1, [("Using Events, use the filters to find the New Unapproved File to Computer subtype for a hash to successfully write the desired custom rule for approval.", False, False)]),
    ], font_size=14)

    slide = ph.add_content_slide(prs, "Rule Types - Security and Performance")
    ph.add_rich_bullets(slide, [
        (0, [("File Creation", True, False), (" rules are more secure.", False, False)]),
        (1, [("Files approved via pattern matching", False, False)]),
        (2, [("Can be spoofed", False, False)]),
        (2, [("BUT the hash of the file is used to permit execution and is therefore much harder to circumvent.", False, False)]),
        (1, [("Execution Control is merely a bypass to an unapproved file", False, False)]),
        (2, [("Considered the highest level of a rule", False, False)]),
        (2, [("Can allow previously banned malicious files to execute if not placed correctly in the rank of the Custom Rules.", False, False)]),
        (0, [("File Creation", True, False), (" rules are more performant", False, False)]),
        (1, [("Only have to worry about files on the local system", False, False)]),
    ], font_size=15)

    slide = ph.add_content_slide(prs, "Custom Rule Health - Findings")
    ph.add_findings_dashboard(slide, [(f.severity, f.message, f.recommendation) for f in result.findings])

    if "metrics" in result.tables:
        slide = ph.add_content_slide(prs, "Custom Rule Health - Key Metrics")
        ph.add_table(slide, result.tables["metrics"], font_size=12, center=True)

    if "rule_types" in result.charts:
        _, categories, series = result.charts["rule_types"]
        slide = ph.add_content_slide(prs, "Enabled Custom Rules by Type")
        ph.add_bar_chart(slide, "Enabled Rule Types", categories, series, horizontal=True)

    if result.tables.get("invalid_paths", [])[1:]:
        ph.add_table_slides(prs, "Rules With Path Ending in Slash", result.tables["invalid_paths"], font_size=8, col_widths=[1.0, 1.7, 0.95, 2.2, 2.1, 1.0, 3.48], max_total_rows=MAX_LIST_ROWS)

    if result.tables.get("exec_blocking", [])[1:]:
        ph.add_table_slides(prs, "Enabled Blocking Execution Control Rules", result.tables["exec_blocking"], font_size=8, col_widths=[1.5, 0.95, 2.35, 2.25, 1.0, 4.38], max_total_rows=MAX_LIST_ROWS)

    if result.tables.get("broad_scope", [])[1:]:
        ph.add_table_slides(prs, "Enabled Rules With Any Process and Any User", result.tables["broad_scope"], font_size=8, col_widths=[1.0, 1.7, 0.95, 2.2, 2.1, 1.0, 3.48], max_total_rows=MAX_LIST_ROWS)