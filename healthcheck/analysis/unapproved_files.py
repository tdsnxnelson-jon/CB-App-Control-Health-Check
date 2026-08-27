"""
Unapproved File Analysis - based on "UnapprovedFileAnalysis+ v6.1.sql".

New unapproved files seen on endpoints, matched in T-SQL against the
customer's active custom rules to explain why each one wasn't already
covered. Surfaces candidate publishers/paths for new approval rules.
"""
import pandas as pd

from . import AnalysisResult, Finding
from ..report import pptx_helpers as ph

TOP_N = 15


def analyze(df: pd.DataFrame) -> AnalysisResult:
    result = AnalysisResult(title="Unapproved File Analysis")
    if df is None or df.empty:
        result.error = "No Unapproved File Analysis data provided."
        return result

    df = df.copy()
    total = len(df)

    has_custom_rule = df["CustomRuleName"].astype(str).str.strip().ne("") if "CustomRuleName" in df.columns else pd.Series([False] * total)
    truly_unapproved = df[~has_custom_rule] if "RuleName" not in df.columns else df[df["RuleName"] == "Unapproved"]

    by_publisher = pd.Series(dtype=int)
    if "Publisher" in df.columns:
        publisher = df["Publisher"].fillna("").astype(str).str.strip()
        publisher = publisher.where(publisher.ne(""), "(No Publisher / Unsigned)")
        by_publisher = publisher.value_counts()
    by_path_dir = pd.Series(dtype=int)
    if "FilePath" in df.columns:
        by_path_dir = df["FilePath"].value_counts()

    result.findings.append(Finding("info", f"{total:,} new unapproved file event(s) analyzed."))

    if total:
        pct_unapproved = len(truly_unapproved) / total
        result.findings.append(Finding("warning" if pct_unapproved > 0.5 else "caution", f"{len(truly_unapproved):,} ({pct_unapproved:.0%}) have no matching custom rule or approval path - candidates for new rule creation or publisher approval.", "Review the top unapproved publishers/paths below and add targeted approval rules to reduce noise."))

    if len(by_publisher):
        top_pub, top_pub_count = by_publisher.index[0], by_publisher.iloc[0]
        if top_pub and str(top_pub).strip() and total:
            pct = top_pub_count / total
            if pct > 0.1:
                result.findings.append(Finding("caution", f"Publisher '{top_pub}' accounts for {pct:.0%} of unapproved files - consider a publisher-level approval rule.", "If this vendor's software is expected/trusted, add a publisher-level approval rule instead of approving files one at a time."))

    result.tables["top_publishers"] = [["Publisher", "Unapproved Files"]] + [[p, int(v)] for p, v in by_publisher.head(TOP_N).items()]
    result.tables["top_paths"] = [["File Path", "Occurrences"]] + [[p, int(v)] for p, v in by_path_dir.head(TOP_N).items()]

    return result


def build_slides(prs, result: AnalysisResult) -> None:
    ph.add_section_slide(prs, result.title)

    slide = ph.add_content_slide(prs, "Unapproved Files - Findings")
    ph.add_findings_dashboard(slide, [(f.severity, f.message, f.recommendation) for f in result.findings])

    if "top_publishers" in result.tables:
        slide = ph.add_content_slide(prs, f"Top {TOP_N} Publishers of Unapproved Files")
        ph.add_table(slide, result.tables["top_publishers"], font_size=10, center=True)

    if "top_paths" in result.tables:
        slide = ph.add_content_slide(prs, f"Top {TOP_N} Unapproved File Paths")
        ph.add_table(slide, result.tables["top_paths"], font_size=9, center=True)
