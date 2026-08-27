"""
Custom Rule Approval Events - based on "ApprovalEventsForRulename.sql".

Files approved via a custom rule (not global/publisher/reputation trust).
The key risk this surfaces: custom rules approving files from unknown or
unapproved publishers, which is a common App Control policy weak spot.
"""
import pandas as pd

from . import AnalysisResult, Finding
from ..report import pptx_helpers as ph

TOP_N = 15
UNTRUSTED_PUBLISHER_STATES = {"", "unapproved", "nan", "none"}
MISSING_RULE_NAME = "(no rule name)*"
MISSING_RULE_FOOTNOTE = "* Blank/NULL rule names usually indicate a rule name that contains a UI special character that did not export cleanly."
MISSING_RULE_DETAIL_ROWS = 20


def _display_rule_name(value) -> str:
    text = "" if pd.isna(value) else str(value).strip()
    if text == "" or text.casefold() in ("null", "nan", "(no rule name)"):
        return MISSING_RULE_NAME
    return text


def analyze(df: pd.DataFrame) -> AnalysisResult:
    result = AnalysisResult(title="Custom Rule Approvals")
    if df is None or df.empty:
        result.error = "No Approval Events (rule name) data provided."
        return result

    df = df.copy()
    total = len(df)
    if "RuleName" in df.columns:
        df["RuleName"] = df["RuleName"].apply(_display_rule_name)

    by_rule = df["RuleName"].value_counts() if "RuleName" in df.columns else pd.Series(dtype=int)

    untrusted = pd.Series(dtype=int)
    if "PublisherState" in df.columns:
        state = df["PublisherState"].fillna("").astype(str).str.strip().str.lower()
        untrusted_mask = state.isin(UNTRUSTED_PUBLISHER_STATES)
        untrusted = df[untrusted_mask]

    result.findings.append(Finding("info", f"{total:,} file(s) approved via custom rule."))

    if len(untrusted) and total:
        pct = len(untrusted) / total
        sev = "warning" if pct > 0.25 else "caution"
        result.findings.append(Finding(sev, f"{len(untrusted):,} ({pct:.0%}) rule-approved files have no trusted/approved publisher - verify these rules are scoped as tightly as possible.", "Tighten custom rule scope (path/hash/publisher) so approvals aren't granted to files without a trusted publisher."))

    if len(by_rule):
        top_rule, top_count = by_rule.index[0], by_rule.iloc[0]
        result.findings.append(Finding("info", f"Most active rule: '{top_rule}' ({top_count:,} approvals)."))

    result.tables["top_rules"] = [["Rule", "Approvals"]] + [[r, int(c)] for r, c in by_rule.head(TOP_N).items()]

    if len(untrusted):
        cols = [c for c in ["RuleName", "ComputerName", "Publisher", "PublisherState", "FilePath", "FileHash"] if c in untrusted.columns]
        if "RuleName" in untrusted.columns:
            missing_rule_rows = untrusted[untrusted["RuleName"].eq(MISSING_RULE_NAME)]
            other_rows = untrusted[~untrusted.index.isin(missing_rule_rows.index)]
            top_untrusted = pd.concat([
                missing_rule_rows.head(MISSING_RULE_DETAIL_ROWS),
                other_rows.head(75 - min(len(missing_rule_rows), MISSING_RULE_DETAIL_ROWS)),
            ])[cols]
        else:
            top_untrusted = untrusted[cols].head(75)
        result.tables["untrusted_approvals"] = [cols] + top_untrusted.astype(object).where(pd.notna(top_untrusted), "").values.tolist()

    return result


def build_slides(prs, result: AnalysisResult) -> None:
    ph.add_section_slide(prs, result.title)

    slide = ph.add_content_slide(prs, "Custom Rule Approvals - Findings")
    findings = [(f.severity, f.message, f.recommendation) for f in result.findings]
    has_missing_rule_name = any(MISSING_RULE_NAME in f.message for f in result.findings)
    ph.add_findings_dashboard(
        slide,
        findings,
        height=ph.CONTENT_H - 0.35 if has_missing_rule_name else ph.CONTENT_H,
    )
    if has_missing_rule_name:
        ph.add_footnote(slide, MISSING_RULE_FOOTNOTE)

    if "top_rules" in result.tables:
        slide = ph.add_content_slide(prs, f"Top {TOP_N} Rules Approving Files")
        ph.add_table(slide, result.tables["top_rules"], font_size=10, center=True)
        if any(str(row[0]).endswith("*") for row in result.tables["top_rules"][1:]):
            ph.add_footnote(slide, MISSING_RULE_FOOTNOTE)

    if "untrusted_approvals" in result.tables:
        slides = ph.add_table_slides(prs, "Rule-Approved Files Without Trusted Publisher", result.tables["untrusted_approvals"], font_size=9)
        if any(str(row[0]).endswith("*") for row in result.tables["untrusted_approvals"][1:]):
            for slide in slides:
                ph.add_footnote(slide, MISSING_RULE_FOOTNOTE)
