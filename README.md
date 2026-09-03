# CB App Control Health Check

Automates the manual Carbon Black App Control (Cb Protection) health check:
takes the exported results of the existing SQL scripts and produces an
analyzed PPTX report instead of manual review + slide building.

## How it works

1. The customer's DBA/admin runs the SQL scripts (unchanged) against the
   App Control SQL Server database using SSMS.
2. Each script's result grid(s) are exported and dropped into one input
   folder (see **Export instructions** below).
3. `main.py` scans that folder, loads whatever it finds, runs the analysis,
   and writes a single PPTX report. Missing/unreadable inputs are skipped
   with a warning rather than failing the whole run.

## Install

```powershell
pip install -r requirements.txt
```

## Run

```powershell
python main.py --input "C:\path\to\export_folder" --customer "Acme Corp" --appcserver "appc01.acme.local"
```

Output defaults to `<customer>_<appcserver>_AppControl_HealthCheck.pptx`
when `--appcserver` is provided, otherwise
`<customer>_AppControl_HealthCheck.pptx`, in the current directory;
override with `--output`. If you get a "Permission denied" error, the
output file is likely still open in PowerPoint from a previous run - close
it (or pass a different `--output` path) and re-run.

## Export instructions per script

Most scripts return one result grid - export as **CSV** (SSMS: right-click
grid > Save Results As, or Results To > Results to File). The file name
just needs to contain a recognizable keyword (matching is fuzzy, see
`healthcheck/config.py`):

| Script | Export as | Filename must contain |
|---|---|---|
| `Approval Metrics+ v4.2.sql` | CSV | "approval metric" |
| `RuleAnalysis.sql` | CSV | "rule analysis" |
| Console export: Custom rules | CSV | "custom" |
| Console export: Computers | CSV | "computers" |
| `ApprovalEventsForRulename.sql` | CSV | "approval events" |
| `BlockAnalysis v6.2.sql` | CSV | "block analysis" |
| `UnapprovedFileAnalysis+ v6.1.sql` | CSV | "unapproved file" |
| `DatabaseErrorAnalysis.sql` | CSV | "database error" |

`BlockAnalysis v6.2 fast.sql` is an alternative for servers where v6.2 runs
too long. Same columns and same block counts, but it drops the discovery-event
lookup, so `Subtype`, `DiscoveryTimeStamp`, `DiscoveredBy`, `ProcessShort` and
`ProcessFull` come back empty and `RuleName` never reports
"Remote Writing Local".

Four scripts return **many** result grids in one execution
(`CbP_Analysis_Script.sql`, `DailyPrune_Debug_Scope.sql`,
`FilePath_Pruning_Scope_AllVersion.sql`, `PurgeAntibodiesPeriodDays scope.sql`).
For these, no manual splitting is needed - just export the **raw SSMS
text output** for the whole script run and drop that one file in:

- SSMS: **Query > Results To > Results to File** (or `Ctrl+Shift+F`),
  then run the script and save as `.rpt`.
- `healthcheck/rpt_parser.py` automatically finds every result-set table
  in that file (it strips STATISTICS IO/TIME noise, DBCC messages, etc.)
  and matches each one to the right section by its column names - no
  Excel, no manual copy/paste, no fixed section order required.

| Script | Filename must contain |
|---|---|
| `CbP_Analysis_Script.sql` | "cbp_analysis" |
| `DailyPrune_Debug_Scope.sql` | "dailyprune" |
| `FilePath_Pruning_Scope_AllVersion.sql` | "filepath_pruning" |
| `PurgeAntibodiesPeriodDays scope.sql` | "purgeantibodiesperioddays" |

These scripts also print a lot of diagnostic-only output (schema
validation, upgrade history, live SQL Server internals) that isn't
included in the automated report - that's meant for manual review during
the health check, not slide content. If a section can't be found in the
`.rpt` (e.g. missing `VIEW SERVER STATE` permission on the SQL login), the
tool logs a warning and skips just that section rather than failing.

## What each section of the report covers

- **Fleet Health** - per-computer sync %, approval-source breakdown,
  whitelist coverage, stale/low-sync computer callouts.
- **Approval Rule Activity** - which rules are approving the most files,
  daily trend/spikes.
- **Custom Rule Health** - custom rules with invalid trailing-slash paths,
  blocking Execution Control rule counts, File Creation Control ratio, and
  wildcard Process + Any User scope callouts.
- **Computer Inventory Health** - connected/active computer summaries,
  connected computer list, disconnected >10 day list, and policy/agent
  health pivots from the console Computers export.
- **Custom Rule Approvals** - rule-approved files with no trusted
  publisher (policy risk).
- **Block Analysis** - blocked-execution root cause breakdown (remote
  exec, logon script, publisher-approval gaps, genuinely unapproved).
- **Unapproved File Analysis** - top publishers/paths generating
  unapproved files with no matching custom rule (new-rule candidates).
- **Agent Database Errors** - hosts with repeated agent DB errors.
- **Database Bloat** - orphaned pathname/filename row %, table space.
- **Server Health** - agent sync %, average load/agent, queue backlogs,
  daily throughput trend.
- **DB Maintenance** - whether DailyPruneTask/antibody purge retention is
  keeping up or backlogged.
- **Executive Summary** - all critical/warning findings across every
  section, on one slide up front.

## Health score and weighting

The Executive Summary includes an overall health score and letter grade when
at least one analysis section runs. Each analyzed section starts at 100 and
loses points for its findings:

$$
\mathrm{section\ score} = \max(0, 100 - \sum \mathrm{severity\ penalties})
$$

The overall score is the weighted average of the available section scores:

$$
\mathrm{overall\ score} = \frac{\sum(\mathrm{section\ score} \times \mathrm{weight})}{\sum \mathrm{weight}}
$$

Only sections with usable input are included. Missing, unreadable, or skipped
exports do not reduce the score or contribute their weight. The DailyPrune and
purge-antibodies analyses share the single **Database maintenance** score and
weight because they are presented as one report section.

Configure scoring in `healthcheck/config.py`, in the `HEALTH_SCORE` mapping:

```python
HEALTH_SCORE = {
    "weights": {
        "fleet_health": 3,
        "server_health": 3,
        "database_errors": 2,
        # Other sections default to weight 1 when omitted.
    },
    "penalties": {
        "critical": 25,
        "warning": 10,
        "caution": 5,
        "info": 0,
    },
    "grade_bands": [
          (97, "A+"),
          (93, "A"),
          (90, "A-"),
          (87, "B+"),
          (83, "B"),
          (80, "B-"),
          (77, "C+"),
          (73, "C"),
          (70, "C-"),
          (67, "D+"),
          (63, "D"),
          (60, "D-"),
        (0, "F"),
    ],
}
```

- Increase a section's weight to make it contribute more to the overall score;
  use whole numbers for clear, predictable weighting. Sections omitted from
  `weights` use `1`.
- Increase a severity penalty to make each finding at that severity reduce its
  section score more sharply. Scores cannot fall below `0`.
- Keep `grade_bands` in descending score order. The first threshold met is the
  grade shown in the Executive Summary.
- Use the analysis keys shown in the `weights` mapping. In particular, use
  `db_maintenance`, not `purge_antibodies_scope`, for the shared maintenance
  weight.

## Project layout

```
main.py                     CLI entry point
healthcheck/
  config.py                 input file/section name -> expected columns
  ingest.py                 loads CSV/.rpt into DataFrames per script
  rpt_parser.py              parses raw SSMS "Results to File" (.rpt) output
  analysis/                 one module per script, each with analyze()/build_slides()
  report/
    pptx_helpers.py          generic slide/table/chart builders
    builder.py                assembles the full deck + executive summary
tools/
  render_preview.py           dev-only: renders slides to PNG via PowerPoint
                               COM automation, for visually checking layout
                               changes (requires local PowerPoint + pywin32)
```

## Known gaps / follow-ups

- No live SQL Server connection yet - all input is file-based. If direct
  DB access becomes viable, `ingest.py` can add a query-based loader
  alongside the file-based one without changing the analysis layer.
- `CbP_Analysis_Script.sql` and `DailyPrune_Debug_Scope.sql` cover more
  sections than are currently analyzed (SQL Server internals, schema
  validation, scheduled task execution history, file-op-by-host/extension
  breakdowns). Add more `sections` entries in `config.py` + extend
  `server_health.py` / `db_maintenance.py` as needed - `rpt_parser.py`
  already exposes every table it finds, no ingestion changes required.
- The console UI export inputs intentionally prefer `Computers*.csv` and
  `Custom*.csv`. The similarly named `.xlsx` files produced during manual
  review may contain pivot tables instead of raw inventory rows.
- Thresholds (sync %, backlog size, orphan %, etc.) are starting points
  based on the comments in the original SQL scripts - tune them against
  real customer data.
