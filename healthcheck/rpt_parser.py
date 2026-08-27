"""
Parses SSMS "Results to File" (.rpt) output into a list of table blocks.

.rpt text mixes real result-set tables with a lot of SQL Server noise
(STATISTICS IO/TIME output, DBCC messages, "Warning: Null value..." etc.)
and PRINT statement banners. Rather than requiring the customer to hand-
split each grid into an Excel sheet, this parses the raw text directly:

  1. Strip known SQL Server noise lines.
  2. Scan for "header line" + "dash separator line" pairs (the standard
     SSMS fixed-width table format) and slice subsequent data lines using
     the column ranges implied by the separator line's dash runs.
  3. Discard any block with zero data rows - this naturally filters out
     the PRINT-statement "dash / banner text / dash" boxes used for
     section headers, since those never have data rows under them.

Blocks are matched to expected sections purely by column-name signature
(see ingest.py), so no section markers/ordering are relied upon.
"""
import re
from typing import List, NamedTuple

import pandas as pd

_NOISE_PATTERNS = [
    re.compile(r"^\s*Warning:"),
    re.compile(r"^\s*DBCC execution completed"),
    re.compile(r"^\s*SQL Server Execution Times:"),
    re.compile(r"^\s*CPU time\s*="),
    re.compile(r"^\s*SQL Server parse and compile time:"),
    re.compile(r"^Table '.*'\.\s*Scan count"),
    re.compile(r"^\s*Completion time:"),
    re.compile(r"^\(\d+ rows? affected\)\s*$"),
]

_DASH_LINE = re.compile(r"^-+( -+)*$")
_NUMERIC_WITH_COMMAS = re.compile(r"^-?[\d,]+(\.\d+)?$")
_MAX_AGE_DAYS = re.compile(r"maxAgeDays.*?:\s*\[(\d+)\]", re.IGNORECASE)


class RptBlock(NamedTuple):
    columns: List[str]
    rows: List[List[str]]

    def to_dataframe(self) -> pd.DataFrame:
        df = pd.DataFrame(self.rows, columns=self.columns)
        for col in df.columns:
            values = df[col].astype(str).str.strip()
            non_empty = values[values != ""]
            if len(non_empty) and non_empty.map(lambda v: bool(_NUMERIC_WITH_COMMAS.match(v))).all():
                df[col] = values.str.replace(",", "", regex=False)
        return df


def _is_noise(line: str) -> bool:
    return any(p.search(line) for p in _NOISE_PATTERNS)


def _column_ranges(dash_line: str):
    ranges = [m.span() for m in re.finditer(r"-+", dash_line)]
    if ranges:
        last_start, _ = ranges[-1]
        ranges[-1] = (last_start, None)  # last column: open-ended to avoid truncating long text
    return ranges


def _slice_row(line: str, ranges) -> List[str]:
    width = max((r[1] or len(line)) for r in ranges if r[1] is not None) if any(r[1] for r in ranges) else len(line)
    padded = line.ljust(max(width, len(line)))
    return [padded[start:end].strip() if end is not None else padded[start:].strip() for start, end in ranges]


def parse(path: str) -> List[RptBlock]:
    with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
        raw_lines = f.read().splitlines()

    lines = ["" if _is_noise(ln) else ln for ln in raw_lines]

    blocks: List[RptBlock] = []
    i = 1
    n = len(lines)
    while i < n:
        line = lines[i]
        header_candidate = lines[i - 1]
        if _DASH_LINE.match(line.strip()) and header_candidate.strip() and not _DASH_LINE.match(header_candidate.strip()):
            ranges = _column_ranges(line)
            columns = _slice_row(header_candidate, ranges)
            columns = [c if c else f"col_{idx}" for idx, c in enumerate(columns)]

            rows = []
            j = i + 1
            while j < n and lines[j].strip() != "" and not _DASH_LINE.match(lines[j].strip()):
                rows.append(_slice_row(lines[j], ranges))
                j += 1

            if rows:
                blocks.append(RptBlock(columns=columns, rows=rows))
            i = j
        else:
            i += 1

    return blocks


def extract_daily_prune_metadata(path: str) -> dict:
    with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
        text = f.read()
    match = _MAX_AGE_DAYS.search(text)
    return {"maxAgeDays": int(match.group(1))} if match else {}


def match_block(blocks: List[RptBlock], required_columns: List[str], min_ratio: float = 0.6):
    """Returns the DataFrame of the block whose columns best cover
    required_columns, or None if no block clears min_ratio coverage."""
    best = None
    best_score = 0
    for block in blocks:
        present = sum(1 for c in required_columns if c in block.columns)
        ratio = present / len(required_columns) if required_columns else 0
        if ratio < min_ratio:
            continue
        score = (present, len(block.rows))
        if best is None or score > best_score:
            best, best_score = block, score
    return best.to_dataframe() if best else None
