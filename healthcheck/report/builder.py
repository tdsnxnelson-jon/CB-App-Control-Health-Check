"""
Assembles the full PPTX deck from all loaded/analyzed inputs.
"""
import datetime
import logging
import re
from typing import Optional

from .. import config
from ..ingest import IngestResult
from ..report import pptx_helpers as ph
from ..analysis import fleet_health, rule_analysis, custom_rules, computer_inventory, approval_events, block_analysis, unapproved_files, database_errors, orphaned_data, server_health, db_maintenance

log = logging.getLogger(__name__)

# "purge_antibodies_scope" reports into the same weighted bucket as
# "db_maintenance" - they're shown as one "Database maintenance" section.
_SCORE_GROUP = {"purge_antibodies_scope": "db_maintenance"}


def build_report(results: dict, customer_name: str, output_path: str, appc_server: Optional[str] = None) -> str:
    prs = ph.create_deck()
    subtitle_lines = [customer_name]
    if appc_server:
        subtitle_lines.append(appc_server)
    subtitle_lines.append(datetime.date.today().isoformat())
    ph.add_title_slide(
        prs,
        "Carbon Black App Control - Health Check",
        "\n".join(subtitle_lines),
    )

    all_findings = []

    def _run(key, module, build_fn=None):
        ingest: IngestResult = results.get(key)
        if not ingest or not ingest.ok:
            reason = "; ".join(ingest.warnings) if ingest and ingest.warnings else "no input file found"
            log.warning(f"Skipping '{key}': {reason}")
            return
        analysis = module.analyze(ingest.data)
        if analysis.error:
            log.warning(f"'{key}': {analysis.error}")
            return
        (build_fn or module.build_slides)(prs, analysis)
        all_findings.append((key, analysis.findings))

    _run("fleet_health", fleet_health)
    _run("rule_analysis", rule_analysis)
    _run("custom_rules", custom_rules)
    _run("computer_inventory", computer_inventory)
    _run("approval_events", approval_events)
    _run("block_analysis", block_analysis)
    _run("unapproved_files", unapproved_files)
    _run("database_errors", database_errors)
    _run("orphaned_data", orphaned_data)
    _run("server_health", server_health)

    # DB maintenance combines two inputs into one section
    prune_ingest = results.get("db_maintenance")
    purge_ingest = results.get("purge_antibodies_scope")
    prune_results = []
    if prune_ingest and prune_ingest.ok:
        a = db_maintenance.analyze_daily_prune(prune_ingest.data)
        if not a.error:
            prune_results.append(a)
            all_findings.append(("db_maintenance", a.findings))
    if purge_ingest and purge_ingest.ok:
        a = db_maintenance.analyze_purge_antibodies(purge_ingest.data)
        if not a.error:
            prune_results.append(a)
            all_findings.append(("purge_antibodies_scope", a.findings))
    if prune_results:
        db_maintenance.build_slides(prs, prune_results)

    _add_executive_summary(prs, all_findings)

    prs.save(output_path)
    return output_path


def _score_section(findings) -> float:
    """100 minus per-finding severity penalties (config.HEALTH_SCORE), floored at 0."""
    penalties = config.HEALTH_SCORE["penalties"]
    score = 100 - sum(penalties.get(f.severity, 0) for f in findings)
    return max(0, score)


def _overall_health_score(all_findings) -> Optional[float]:
    """Weighted average of section scores, using only sections that ran."""
    weights = config.HEALTH_SCORE["weights"]
    grouped: dict = {}
    for key, findings in all_findings:
        group = _SCORE_GROUP.get(key, key)
        grouped.setdefault(group, []).extend(findings)

    total_weight = 0.0
    weighted_sum = 0.0
    for group, findings in grouped.items():
        weight = weights.get(group, 1)
        weighted_sum += weight * _score_section(findings)
        total_weight += weight

    if total_weight == 0:
        return None
    return weighted_sum / total_weight


def _grade_for_score(score: float) -> str:
    for threshold, grade in config.HEALTH_SCORE["grade_bands"]:
        if score >= threshold:
            return grade
    return "F"


def _add_executive_summary(prs, all_findings):
    """Inserts a top-level summary slide right after the title slide,
    listing only critical/warning findings across every section."""
    priority = {"critical": 0, "warning": 1}
    highlights = []
    for key, findings in all_findings:
        for f in findings:
            if f.severity in priority:
                highlights.append((priority[f.severity], f.severity, key, _executive_message(key, f.message)))
    highlights.sort(key=lambda x: x[0])

    slide = ph.add_content_slide(prs, "Executive Summary")
    critical_count = sum(1 for _, sev, _, _ in highlights if sev == "critical")
    warning_count = sum(1 for _, sev, _, _ in highlights if sev == "warning")
    sections_count = len({_section_label(key) for _, _, key, _ in highlights[:8]})

    metrics = [
        ("High-priority issues", critical_count, "critical" if critical_count else "ok"),
        ("Items to watch", warning_count, "warning" if warning_count else "ok"),
        ("Areas affected", sections_count, "info"),
    ]
    score = _overall_health_score(all_findings)
    if score is not None:
        grade = _grade_for_score(score)
        tone = "ok" if grade in ("A", "B") else "warning" if grade == "C" else "critical"
        metrics.insert(0, ("Overall health score", f"{score:.0f} ({grade})", tone))
    ph.add_metric_strip(slide, metrics)
    items = [(sev, f"{_section_label(key)}: {msg}") for _, sev, key, msg in highlights[:8]] or [("ok", "No high-priority concerns were found in the analyzed data.")]
    ph.add_finding_cards(slide, items, top=ph.CONTENT_TOP + 0.95, height=ph.CONTENT_H - 0.95, show_recommendations=False, max_items=8)

    # move this slide to position 1 (right after the title slide)
    xml_slides = prs.slides._sldIdLst
    slides = list(xml_slides)
    xml_slides.remove(slides[-1])
    xml_slides.insert(1, slides[-1])


def _section_label(key: str) -> str:
    return {
        "fleet_health": "Fleet health",
        "rule_analysis": "Rule activity",
        "custom_rules": "Custom rule health",
        "computer_inventory": "Computer inventory",
        "approval_events": "Custom approvals",
        "block_analysis": "Blocked activity",
        "unapproved_files": "Unapproved files",
        "database_errors": "Agent stability",
        "orphaned_data": "Database size",
        "server_health": "Server health",
        "db_maintenance": "Database maintenance",
        "purge_antibodies_scope": "Database maintenance",
    }.get(key, key.replace("_", " ").title())


def _executive_message(key: str, message: str) -> str:
    text = re.sub(r"\[[^\]]+\]\s*", "", str(message))
    if key == "fleet_health":
        if "below 90" in text:
            count = _first_match(r"([\d,]+)\s+computer", text)
            return f"{count} endpoints are well below the reporting target."
        if "not polled" in text:
            count = _first_match(r"([\d,]+)\s+computer", text)
            return f"{count} endpoints have not checked in for more than 7 days."
        if "non-OK policy config status" in text:
            count = _first_match(r"([\d,]+)\s+computer", text)
            return f"{count} endpoints have policy status issues."
    elif key == "rule_analysis":
        if "Approval volume spiked" in text:
            date = _first_match(r"on ([^(]+)\s*\(", text)
            recent = _first_match(r"\(([\d,]+) vs", text)
            usual = _first_match(r"~([\d,]+)/day", text)
            return f"Approval activity spiked on {date}: {recent} vs. usual {usual}/day."
    elif key == "block_analysis":
        if "already-approved publisher/state" in text:
            count = _first_match(r"([\d,]+\s+\([^)]*\))", text)
            return f"{count} blocks involved software with an existing approval signal."
    elif key == "unapproved_files":
        if "no matching custom rule or approval path" in text:
            count = _first_match(r"([\d,]+\s+\([^)]*\))", text)
            return f"{count} files are outside current approval coverage."
    elif key == "database_errors":
        if "database-error activity" in text:
            count = _first_match(r"([\d,]+)\s+host", text)
            return f"{count} hosts show repeated agent stability issues."
    elif key in ("db_maintenance", "purge_antibodies_scope"):
        if "past retention" in text:
            count = _first_match(r"([\d,]+)\s+row", text)
            return f"{count} records are past retention; database cleanup is behind schedule."
    replacements = [
        ("computer(s)", "computers"),
        ("row(s)", "records"),
        ("file-op", "file processing"),
        ("Agent-side", "Agent"),
        ("AB_BackLog_M", "file processing queue"),
        ("DailyPruneTask", "database cleanup"),
        ("sync", "check-in"),
        ("publisher/state", "publisher approval"),
        ("custom rule", "custom approval rule"),
    ]
    for old, new in replacements:
        text = text.replace(old, new)
    text = re.sub(r"\s*-\s*(investigate|review|verify|check|consider|schedule|monitor|plan).*$", ".", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*\((critical,\s*)?target[^)]*\)", "", text, flags=re.IGNORECASE)
    text = text.replace(" - ", ": ")
    text = text.replace("computer(s)", "computers").replace("host(s)", "hosts")
    return text.strip()


def _first_match(pattern: str, text: str, default: str = "Several") -> str:
    match = re.search(pattern, text)
    return match.group(1).strip() if match else default
