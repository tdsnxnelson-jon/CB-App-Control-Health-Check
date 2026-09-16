# Repository Instructions

## Project scope

This repository is a standalone Python CLI that ingests Carbon Black App Control health-check exports and generates an analyzed PowerPoint report.

The main flow is:

```text
main.py -> healthcheck/ingest.py -> healthcheck/analysis/*.py -> healthcheck/report/builder.py
```

Use the existing architecture and helper APIs. Keep changes focused. Do not introduce a web server, live database connection, or unrelated refactor unless explicitly requested.

## Coding conventions

- Use Python and match the existing style.
- Prefer small, local changes over broad rewrites.
- Preserve public APIs and existing input formats unless the task requires a change.
- Use structured parsing for CSV, RPT, and PPTX data; do not parse structured data with fragile string hacks.
- Keep source files ASCII unless non-ASCII is already required by the feature.
- Do not add unnecessary comments, abstractions, dependencies, or metadata.
- Do not modify customer data folders or generated reports unless explicitly asked.
- Never discard user changes or use destructive Git commands such as `git reset --hard` or `git checkout --`.
- Before implementing anything, tell me if my approach is wrong. Specifically:
  - If I'm solving the wrong problem, say so first
  - If there's a significantly better alternative I haven't considered, name it and explain why it's better
  - If my idea will cause problems at scale or in edge cases, describe them concretely
  - Rank tradeoffs — don't just list pros and cons equally, tell me which matters more
  - If something I'm asking for is straightforward and fine, just do it — reserve pushback for when it genuinely matters
- Do not implement first and add caveats at the end. Push back before writing any code.
- If I ask you to implement something and you think the feature itself is unnecessary or there's a simpler approach that avoids the problem entirely, say that instead of building it.

## Input and export formats

The application scans one input folder and matches files by case-insensitive filename keywords defined in `healthcheck/config.py`.

- Single-result SQL scripts use CSV exports.
- Console Computers and Custom Rules exports use CSV or TXT.
- Multi-result SQL scripts require the complete raw SSMS Results to File output as one `.rpt` file. Do not manually split these result sets.
- The RPT scripts are `CbP_Analysis_Script SAFE v2.sql`, `DailyPrune_Debug_Scope.sql`, `FilePath_Pruning_Scope_AllVersion.sql`, and `PurgeAntibodiesPeriodDays scope.sql`.
- `UnapprovedFileAnalysis+ v6.1.sql` supports multiple non-overlapping CSV chunks. Preserve all intended chunks and remove stale or duplicate files.

Refer to `SQL Scripts/README.md` and `SQL Scripts/PRODUCTION RUN GUIDANCE.md` for the complete export workflow and production-safety guidance.

## Analysis and report rules

- Add new analysis behavior in the owning module under `healthcheck/analysis/`.
- Use `healthcheck/report/pptx_helpers.py` for shared PowerPoint layout and rendering.
- Preserve complete operational values such as file paths, rule names, targets, and recommendations. Wrap long table values rather than truncating them.
- When adding a warning, critical, or caution `Finding`, include a concrete recommendation when appropriate.
- Keep PPTX content inside the fixed 16:9 slide geometry and avoid title, table, chart, or footnote overlap.
- For remediation coverage, each block must remain attributed to one best-fit action so coverage is not double-counted.

## Validation

Run the focused tests for changes to the report or analysis:

```powershell
python -m pytest tests/test_pptx_helpers.py -q
python -m py_compile healthcheck/report/pptx_helpers.py healthcheck/analysis/block_analysis.py
```

For broader changes, run:

```powershell
python -m pytest -q
```

When changing PPTX layout, run an end-to-end report build when representative input data is available. Check for Python errors, missing inputs, slide-boundary overflow, and complete rendering of long values.

## SQL production safety

Do not recommend running the original `CbP_Analysis_Script.sql` on a busy production primary. Prefer the SAFE script and a readable Availability Group secondary. Treat SQL changes as production-sensitive and do not claim they are production-safe without execution-plan or representative-load validation.

## Git workflow

- Do not commit or push unless the user explicitly asks.
- Before committing, inspect `git status` and the complete diff.
- Run relevant tests before committing.
- Never overwrite remote history. If the remote has diverged, fetch and integrate it with a merge or rebase before pushing.

