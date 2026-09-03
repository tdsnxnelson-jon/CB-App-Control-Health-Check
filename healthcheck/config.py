"""
Maps each source .sql script to the exported input file(s) the tool expects.

Two input "kinds":
  - "csv":       script returns a single result set -> customer exports one
                 CSV (SSMS: Results to Grid > right-click > Save Results As).
  - "rpt_multi": script returns many result sets in one execution -> customer
                 exports the *raw* SSMS "Results to File" (.rpt) output for
                 the whole run (SSMS: Query > Results To > Results to File,
                 or Ctrl+Shift+F, then run the script). No manual splitting
                 required - healthcheck/rpt_parser.py auto-detects each
                 result-set table inside the file and matches it to a
                 "section" below by column-name signature.

filename_match is a case-insensitive substring used to auto-detect the file
for a script when scanning an input folder (so exact file naming isn't
required, e.g. "Approval Metrics_2026-08-01.csv" still matches "approval").
"""

CSV = "csv"
RPT_MULTI = "rpt_multi"

SCRIPTS = {
    "fleet_health": {
        "sql_file": "Approval Metrics+ v4.2.sql",
        "kind": CSV,
        "filename_match": ["approval metric"],
        "required_columns": [
            "Computer ID", "Computer Name", "Connected", "Agemt Version",
            "Last Polled", "Initialized", "Platform", "Policy", "%Sync",
            "ConfigStatus", "#Global Approval", "#Global TD", "#Global Rep",
            "#Global Oth", "#Local Approval: Initialization",
            "#Local Approval: UnValidated", "#Local Approval: Policy",
            "#Local Approval: Rule", "#Unapproved", "#Files",
            "#Unapprove Events", "%Whitelist", "%Global",
        ],
    },
    "rule_analysis": {
        "sql_file": "RuleAnalysis.sql",
        "kind": CSV,
        "filename_match": ["ruleanalysis", "rule analysis"],
        "required_columns": ["Event", "Rule", "Count", "Day"],
    },
    "custom_rules": {
        "sql_file": "Console export: Custom rules",
        "kind": CSV,
        "filename_match": ["custom"],
        "extensions": [".csv", ".txt"],
        "required_columns": [
            "Status", "Rule Type", "Name", "Action", "Operation", "Path",
            "Process", "User or Group", "Policy",
        ],
    },
    "computer_inventory": {
        "sql_file": "Console export: Computers",
        "kind": CSV,
        "filename_match": ["computers"],
        "extensions": [".csv", ".txt"],
        "required_columns": [
            "Computer Name", "Connected", "Policy Status", "Upgrade Status",
            "Connected Enforcement", "Disconnected Enforcement", "Active",
            "Agent Version", "Days Offline",
        ],
    },
    "approval_events": {
        "sql_file": "ApprovalEventsForRulename.sql",
        "kind": CSV,
        "filename_match": ["approvalevents", "approval events"],
        "required_columns": [
            "TimeStamp", "TimeDate", "ComputerName", "Policy", "UserName",
            "Subtype", "RuleName", "Publisher", "PublisherState", "FileHash",
        ],
    },
    "block_analysis": {
        "sql_file": "BlockAnalysis v6.2.sql",
        "kind": CSV,
        "filename_match": ["blockanalysis", "block analysis"],
        "required_columns": [
            "TimeStamp", "ComputerName", "Policy", "Subtype", "BlockSubtype",
            "RuleName", "DiscoveredBy", "FilePath", "Publisher",
            "PublisherState",
        ],
    },
    "unapproved_files": {
        "sql_file": "UnapprovedFileAnalysis+ v6.1.sql",
        "kind": CSV,
        "filename_match": ["unapprovedfileanalysis", "unapproved file"],
        "required_columns": [
            "TimeStamp", "ComputerName", "Policy", "RuleName", "FilePath",
            "Publisher", "PublisherState", "FileHash", "CustomRuleName",
        ],
    },
    "database_errors": {
        "sql_file": "DatabaseErrorAnalysis.sql",
        "kind": CSV,
        "filename_match": ["databaseerroranalysis", "database error"],
        "required_columns": ["TimeStamp", "ComputerName", "Subtype", "Param1"],
    },
    "orphaned_data": {
        "sql_file": "FilePath_Pruning_Scope_AllVersion.sql",
        "kind": RPT_MULTI,
        "filename_match": ["filepath_pruning", "filepath pruning", "orphan"],
        "sections": {
            "table_bloat": [
                "TableName", "RowsCount", "TotalSpaceKB", "UsedSpaceKB",
                "UnusedSpaceKB", "OrphanedRowsCount", "OrphanedPercent",
                "OrphanedSpaceKB", "NonOrphanedSpaceKB",
            ],
        },
    },
    "server_health": {
        "sql_file": "CbP_Analysis_Script.sql",
        "kind": RPT_MULTI,
        "filename_match": ["cbp_analysis", "server health", "cbp analysis"],
        "sections": {
            "sync_percent": ["Type", "Agent Sync Percent"],
            "avg_load_per_agent": [
                "Total non-deleted host count", "Count of Hosts Included",
                "Average No. of File Operations (FO)/host",
                "Average No. of Events/host",
            ],
            "queue_backlog": [
                "FO Queue 1: Agent-Side backlog (overall - including disabled)",
                "EVENT (Queue) backlog (overall)",
                "FO Queue 2: Server side backlog (size of Temp AB Table) (overall - including disabled)",
            ],
            "daily_throughput": [
                "Date", "FO_Processed", "ABs_Created", "AbInst_Created",
                "FRs_Created", "FO_ProcessingTimeSpent(HR)", "FO_PerHost",
                "E_Total", "E_Hosts", "E_PerHost", "ScheduleTasks_Total(HR)",
            ],
            "performance_history": [
                "File_Rate_M", "Projected_File_Rate_M", "BackLog_Rate_M",
                "Projected_BackLog_Rate_M", "AB_BackLog_M", "AB_Rows_M",
                "date_created",
            ],
        },
    },
    "db_maintenance": {
        "sql_file": "DailyPrune_Debug_Scope.sql",
        "kind": RPT_MULTI,
        "filename_match": ["dailyprune", "daily prune"],
        "sections": {
            "deleted_instances_by_age": ["Table: [antibody_instances_deleted]", "count"],
            "instance_groups_by_age": ["Table: [antibody_instance_groups]", "Count"],
            "antibodies_prune_summary": ["Table: [antibodies]", "Count"],
            "antibodies_by_creation_date": [
                "Date", "Total_Count_of_ABs_By_Creation_Date",
                "0_prev_by_Zero_fill_Date", "0_prev_that_meet_criterion_by_Zero_fill_Date",
                "file_rules", "ab_groups", "ab_instance_groups",
                "ab_instances_snapshots", "totals",
            ],
            "events_by_age": ["Table: [events]", "count"],
        },
    },
    "purge_antibodies_scope": {
        "sql_file": "PurgeAntibodiesPeriodDays scope.sql",
        "kind": RPT_MULTI,
        "filename_match": ["purgeantibodiesperioddays", "purge antibodies"],
        "sections": {
            "purge_scope": ["Table: [antibodies]", "Count"],
        },
    },
}

# Overall health score configuration.
#
# Each analysis section starts at 100 points and loses points per finding
# based on severity (see "penalties"). The overall score is the weighted
# average of section scores, using only sections that produced findings for
# this customer (missing/skipped inputs don't drag the score down).
#
# "db_maintenance" and "purge_antibodies_scope" share one weight/label since
# they're presented as a single "Database maintenance" section in the report.
HEALTH_SCORE = {
    "weights": {
        "fleet_health": 3,
        "server_health": 3,
        "database_errors": 2,
        "db_maintenance": 2,
        "rule_analysis": 1,
        "custom_rules": 1,
        "computer_inventory": 1,
        "approval_events": 1,
        "block_analysis": 1,
        "unapproved_files": 1,
        "orphaned_data": 1,
    },
    "penalties": {
        "critical": 25,
        "warning": 10,
        "caution": 5,
        "info": 0,
    },
    # score thresholds for the letter grade shown next to the number
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
