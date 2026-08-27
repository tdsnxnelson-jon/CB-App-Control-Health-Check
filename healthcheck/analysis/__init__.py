"""
Common types shared by every analysis module.

Each module exposes:
  analyze(data) -> AnalysisResult
  build_slides(prs, result) -> None   (adds its slides to the deck)
"""
from dataclasses import dataclass, field
from typing import Any, List


@dataclass
class Finding:
    severity: str  # "critical" | "warning" | "caution" | "ok" | "info"
    message: str
    recommendation: str = None  # actionable next step; expected for anything above "info"


@dataclass
class AnalysisResult:
    title: str
    findings: List[Finding] = field(default_factory=list)
    tables: dict = field(default_factory=dict)   # name -> list[list] (row 0 = header)
    charts: dict = field(default_factory=dict)    # name -> (kind, categories, series/values)
    error: str = None                             # set when input data was missing/invalid


def severity_rank(sev: str) -> int:
    return {"critical": 4, "warning": 3, "caution": 2, "info": 1, "ok": 0}.get(sev, 0)
