"""
Rule Analysis - based on "RuleAnalysis.sql".

Daily counts of file-approval events grouped by event type and rule name.
Surfaces which rules are doing the bulk of approvals and whether approval
volume is trending up/down.
"""
import pandas as pd

from . import AnalysisResult, Finding
from ..report import pptx_helpers as ph

TOP_N = 15
MISSING_RULE_NAME = "(no rule name)*"
MISSING_RULE_FOOTNOTE = "* Blank/NULL rule names usually indicate a rule name that contains a UI special character that did not export cleanly."


def _display_rule_name(value) -> str:
    text = "" if pd.isna(value) else str(value).strip()
    if text == "" or text.casefold() in ("null", "nan", "(no rule name)"):
        return MISSING_RULE_NAME
    return text


def analyze(df: pd.DataFrame) -> AnalysisResult:
    result = AnalysisResult(title="Approval Rule Activity")
    if df is None or df.empty:
        result.error = "No Rule Analysis data provided."
        return result

    df = df.copy()
    df["Count"] = pd.to_numeric(df.get("Count"), errors="coerce").fillna(0)
    df["Day"] = pd.to_datetime(df.get("Day"), errors="coerce")
    df["Rule"] = df["Rule"].apply(_display_rule_name)

    total_approvals = df["Count"].sum()
    by_rule = df.groupby("Rule", dropna=False)["Count"].sum().sort_values(ascending=False)
    by_day = df.groupby(df["Day"].dt.date)["Count"].sum().sort_index()
    by_event = df.groupby("Event", dropna=False)["Count"].sum().sort_values(ascending=False)

    result.findings.append(Finding("info", f"{int(total_approvals):,} approval events across {df['Rule'].nunique()} distinct rule(s)."))

    top_rule = by_rule.index[0] if len(by_rule) else None
    if top_rule is not None:
        top_share = by_rule.iloc[0] / total_approvals if total_approvals else 0
        if top_share > 0.5:
            result.findings.append(Finding("caution", f"Rule '{top_rule}' accounts for {top_share:.0%} of all approvals - consider reviewing for over-broad scope.", "Audit this rule's path/process/publisher scope - an overly broad rule can undermine least-privilege approval policy."))

    if len(by_day) >= 2:
        recent, prior = by_day.iloc[-1], by_day.iloc[:-1].mean()
        if prior and recent > prior * 1.5:
            result.findings.append(Finding("warning", f"Approval volume spiked on {by_day.index[-1]} ({int(recent):,} vs. ~{prior:.0f}/day average).", "Correlate with recent software deployments or policy changes to confirm the spike was expected."))

    result.tables["top_rules"] = [["Rule", "Approvals"]] + [[r, int(c)] for r, c in by_rule.head(TOP_N).items()]
    result.tables["by_event"] = [["Event Type", "Count"]] + [[e, int(c)] for e, c in by_event.items()]
    if len(by_day):
        result.charts["daily_trend"] = ("line", [str(d) for d in by_day.index], {"Approvals/day": by_day.values.tolist()})

    return result


def build_slides(prs, result: AnalysisResult) -> None:
    ph.add_section_slide(prs, result.title)

    slide = ph.add_content_slide(prs, "Rule Activity - Findings")
    ph.add_findings_dashboard(slide, [(f.severity, f.message, f.recommendation) for f in result.findings])

    if "top_rules" in result.tables:
        slide = ph.add_content_slide(prs, f"Top {TOP_N} Rules by Approval Volume")
        ph.add_table(slide, result.tables["top_rules"], font_size=10, center=True)
        if any(str(row[0]).endswith("*") for row in result.tables["top_rules"][1:]):
            ph.add_footnote(slide, MISSING_RULE_FOOTNOTE)

    if "daily_trend" in result.charts:
        _, categories, series = result.charts["daily_trend"]
        slide = ph.add_content_slide(prs, "Daily Approval Volume")
        ph.add_line_chart(slide, "Approvals per Day", categories, series)
