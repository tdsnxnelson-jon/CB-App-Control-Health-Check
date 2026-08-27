"""
CB App Control Health Check - CLI entry point.

Usage:
    python main.py --input "C:\\path\\to\\export_folder" --customer "Acme Corp" --output "Acme_HealthCheck.pptx"

Input folder must contain the exported results from the SQL scripts in
sql/ (see README.md for exact export instructions and naming).
"""
import argparse
import logging
import os
import sys

from colorama import Fore, Style, init as colorama_init

from healthcheck import ingest
from healthcheck.report import builder


class ColorFormatter(logging.Formatter):
    """Colorizes only the levelname prefix, not the rest of the message."""

    _COLORS = {
        logging.DEBUG: Fore.CYAN,
        logging.INFO: Fore.GREEN,
        logging.WARNING: Fore.YELLOW,
        logging.ERROR: Fore.RED,
        logging.CRITICAL: Fore.RED + Style.BRIGHT,
    }

    def format(self, record):
        color = self._COLORS.get(record.levelno, "")
        if color:
            record.levelname = f"{color}{record.levelname}{Style.RESET_ALL}"
        return super().format(record)


def _setup_logging(verbose: bool):
    colorama_init()
    handler = logging.StreamHandler()
    handler.setFormatter(ColorFormatter("%(levelname)s: %(message)s"))
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO, handlers=[handler])


def main():
    parser = argparse.ArgumentParser(description="Generate a Carbon Black App Control health check PPTX from exported SQL script results.")
    parser.add_argument("--input", required=True, help="Folder containing exported CSV/XLSX results.")
    parser.add_argument("--customer", required=True, help="Customer name, used on the title slide and output filename.")
    parser.add_argument("--appcserver", default=None, help="App Control server name, shown on the title slide and default output filename.")
    parser.add_argument("--output", default=None, help="Output .pptx path (default includes --customer and, when provided, --appcserver).")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging.")
    args = parser.parse_args()

    _setup_logging(args.verbose)

    output_name = f"{args.customer}_AppControl_HealthCheck.pptx"
    if args.appcserver:
        server_name = _safe_filename_part(args.appcserver)
        output_name = f"{args.customer}_{server_name}_AppControl_HealthCheck.pptx"
    output_path = args.output or os.path.join(os.getcwd(), output_name)

    try:
        results = ingest.load_all(args.input)
    except ingest.MissingInputError as e:
        logging.error(str(e))
        sys.exit(1)

    loaded = [k for k, r in results.items() if r.ok]
    skipped = [k for k, r in results.items() if not r.ok]
    logging.info(f"Loaded: {', '.join(loaded) if loaded else '(none)'}")
    if skipped:
        logging.warning(f"Skipped (missing/invalid input): {', '.join(skipped)}")

    if not loaded:
        logging.error("No valid input data found - nothing to report on.")
        sys.exit(1)

    while True:
        try:
            out = builder.build_report(results, args.customer, output_path, args.appcserver)
            break
        except PermissionError:
            logging.warning(f"Could not write to '{output_path}' - the file is likely open in PowerPoint, or the folder is read-only.")
            choice = input(f"{Fore.YELLOW}Press 1 after closing the file to retry, or 2 to exit: {Style.RESET_ALL}").strip()
            if choice == "1":
                continue
            logging.error("Exiting - report was not written.")
            sys.exit(1)
    logging.info(f"Report written to: {out}")


def _safe_filename_part(value: str) -> str:
    return "".join("_" if c in '<>:"/\\|?*' else c for c in value).strip().strip(".") or "AppControlServer"


if __name__ == "__main__":
    main()
