"""
Loads exported health-check data (CSV or multi-sheet Excel) from an input
folder into pandas DataFrames, keyed by the script identifiers in config.py.
"""
import os
import logging
import time
from typing import Dict, Optional, Union

import pandas as pd

from . import config, rpt_parser

log = logging.getLogger(__name__)

CSV_EXTS = (".csv", ".txt")
EXCEL_EXTS = (".xlsx", ".xls")
RPT_EXTS = (".rpt",)


class MissingInputError(Exception):
    """Raised when a required script's export file cannot be found."""


class IngestResult:
    """Container for one script's loaded data plus any load warnings."""

    def __init__(self, key: str, data: Union[pd.DataFrame, Dict[str, pd.DataFrame], None], warnings: list):
        self.key = key
        self.data = data
        self.warnings = warnings

    @property
    def ok(self) -> bool:
        return self.data is not None


def _find_file(input_dir: str, patterns: list, exts=CSV_EXTS + EXCEL_EXTS + RPT_EXTS) -> Optional[str]:
    candidates = []
    for fname in os.listdir(input_dir):
        lower = fname.lower()
        if not lower.endswith(exts):
            continue
        if any(p.lower() in lower for p in patterns):
            candidates.append(fname)
    if not candidates:
        return None
    # prefer the most recently modified match if there are several
    candidates.sort(key=lambda f: os.path.getmtime(os.path.join(input_dir, f)), reverse=True)
    return os.path.join(input_dir, candidates[0])


def _read_table(path: str) -> pd.DataFrame:
    if path.lower().endswith(EXCEL_EXTS):
        return pd.read_excel(path, sheet_name=0)
    # these exports are always comma-delimited - try the fast C engine with a
    # known separator first; only fall back to the slow sep=None sniffing
    # engine (10-20x slower on large files) if that actually fails to parse
    for enc in ("utf-8-sig", "utf-16", "latin-1"):
        try:
            return _strip_literal_quotes(pd.read_csv(path, encoding=enc, low_memory=False))
        except UnicodeDecodeError:
            continue
        except pd.errors.ParserError:
            break
    for enc in ("utf-8-sig", "utf-16", "latin-1"):
        try:
            return _strip_literal_quotes(pd.read_csv(path, encoding=enc, sep=None, engine="python"))
        except (UnicodeDecodeError, UnicodeError):
            continue
    return _strip_literal_quotes(pd.read_csv(path))


def _strip_literal_quotes(df: pd.DataFrame) -> pd.DataFrame:
    """Several of the source SQL scripts wrap text columns in literal
    double quotes (e.g. `'"'+pb.name+'"' AS 'Publisher'`), independent of
    the CSV file's own quoting. Strip one matching leading/trailing quote
    so values like Publisher/FilePath/Company don't show up as '""'."""
    for col in df.select_dtypes(include="object").columns:
        df[col] = df[col].astype(str).str.replace(r'^"(.*)"$', r"\1", regex=True)
        df.loc[df[col].isin(["nan", "NULL"]), col] = ""
    return df


def _validate_columns(df: pd.DataFrame, required: list, warnings: list, label: str):
    missing = [c for c in required if c not in df.columns]
    if missing:
        warnings.append(f"{label}: missing expected column(s): {', '.join(missing)}")


def load_csv_script(key: str, spec: dict, input_dir: str) -> IngestResult:
    warnings = []
    path = _find_file(input_dir, spec["filename_match"], exts=tuple(spec.get("extensions", CSV_EXTS + EXCEL_EXTS + RPT_EXTS)))
    if not path:
        return IngestResult(key, None, [f"No file found matching {spec['filename_match']} in {input_dir}"])
    try:
        df = _read_table(path)
    except Exception as e:  # noqa: BLE001 - surface any parse failure to the caller
        return IngestResult(key, None, [f"Failed to read {path}: {e}"])
    _validate_columns(df, spec.get("required_columns", []), warnings, os.path.basename(path))
    return IngestResult(key, df, warnings)


def load_rpt_multi_script(key: str, spec: dict, input_dir: str) -> IngestResult:
    """Loads a script that returns many result sets in one execution from a
    raw SSMS 'Results to File' (.rpt) export. No manual splitting required:
    every table-shaped block in the file is auto-detected and matched to a
    configured section by column-name signature."""
    warnings = []
    path = _find_file(input_dir, spec["filename_match"], exts=RPT_EXTS + CSV_EXTS + EXCEL_EXTS)
    if not path:
        return IngestResult(key, None, [f"No .rpt export found matching {spec['filename_match']} in {input_dir}"])

    if not path.lower().endswith(RPT_EXTS):
        return IngestResult(key, None, [f"{key} requires the raw .rpt export (SSMS Results to File), got {path}"])

    try:
        blocks = rpt_parser.parse(path)
    except Exception as e:  # noqa: BLE001
        return IngestResult(key, None, [f"Failed to parse {path}: {e}"])

    result = {}
    for section_key, required_cols in spec["sections"].items():
        match = rpt_parser.match_block(blocks, required_cols)
        if match is None:
            warning = f"{os.path.basename(path)}: no result set found for section '{section_key}' (looked for columns: {', '.join(required_cols)})"
            if section_key == "performance_history":
                warning += "; verify the Bit9 service account has VIEW SERVER STATE and that the Reporter/ProcessFileInstances scheduled task is running"
            warnings.append(warning)
            continue
        result[section_key] = match

    if key in ("db_maintenance", "purge_antibodies_scope"):
        metadata = rpt_parser.extract_daily_prune_metadata(path)
        if metadata:
            result["_metadata"] = pd.DataFrame([metadata])

    if not result:
        return IngestResult(key, None, warnings)
    # unwrap single-section scripts back to a plain DataFrame so analysis
    # modules that expect one table (e.g. orphaned_data, purge_antibodies_scope)
    # don't need to know about the multi-section container.
    if len(result) == 1 and len(spec["sections"]) == 1:
        only_key = next(iter(spec["sections"]))
        return IngestResult(key, result.get(only_key), warnings)
    return IngestResult(key, result, warnings)


def load_all(input_dir: str) -> Dict[str, IngestResult]:
    """Load every configured script's data from input_dir. Missing/broken
    inputs are recorded as warnings rather than raising, so a partial deck
    can still be built."""
    if not os.path.isdir(input_dir):
        raise MissingInputError(f"Input folder not found: {input_dir}")

    results = {}
    for key, spec in config.SCRIPTS.items():
        # .rpt parsing of the large multi-section scripts can take a while -
        # log before starting each one so the tool doesn't look hung.
        log.info(f"Loading {key} ({spec['sql_file']})...")
        start = time.monotonic()
        if spec["kind"] == config.CSV:
            results[key] = load_csv_script(key, spec, input_dir)
        else:
            results[key] = load_rpt_multi_script(key, spec, input_dir)
        elapsed = time.monotonic() - start
        status = "ok" if results[key].ok else "skipped"
        log.info(f"  -> {status} ({elapsed:.1f}s)")
        for w in results[key].warnings:
            log.warning(w)
    return results
