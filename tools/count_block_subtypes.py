r"""Count BlockSubtype values in a large Block Analysis CSV export.

Usage:
    python tools/count_block_subtypes.py "C:\path\to\BlockAnalysis.csv"
    python tools/count_block_subtypes.py "C:\path\to\BlockAnalysis.csv" --output counts.csv
"""
import argparse
import csv
from collections import Counter
from pathlib import Path


def _encoding_for(path: Path) -> str:
    with path.open("rb") as source:
        prefix = source.read(3)
    if prefix.startswith((b"\xff\xfe", b"\xfe\xff")):
        return "utf-16"
    if prefix.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    return "utf-8-sig"


def _normalized(value: str) -> str:
    return value.strip().replace(" ", "").replace("_", "").casefold()


def count_subtypes(path: Path, encoding: str | None = None) -> tuple[Counter, int]:
    counts = Counter()
    row_count = 0
    selected_encoding = encoding or _encoding_for(path)

    try:
        source = path.open("r", encoding=selected_encoding, newline="")
        source.read(4096)
        source.seek(0)
    except UnicodeDecodeError:
        if encoding:
            raise
        source.close()
        selected_encoding = "latin-1"
        source = path.open("r", encoding=selected_encoding, newline="")

    with source:
        reader = csv.DictReader(source)
        if not reader.fieldnames:
            raise ValueError("The input file has no CSV header.")

        matching_columns = [
            name for name in reader.fieldnames
            if name and _normalized(name) == "blocksubtype"
        ]
        if not matching_columns:
            raise ValueError(
                "BlockSubtype column not found. Columns present: "
                + ", ".join(reader.fieldnames)
            )
        subtype_column = matching_columns[0]

        for row in reader:
            row_count += 1
            subtype = (row.get(subtype_column) or "").strip().strip('"')
            counts[subtype or "(blank)"] += 1

    return counts, row_count


def _write_counts(path: Path, counts: Counter) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as output:
        writer = csv.writer(output)
        writer.writerow(["BlockSubtype", "Count"])
        writer.writerows(counts.most_common())


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Count BlockSubtype values without loading the full CSV into memory."
    )
    parser.add_argument("input", type=Path, help="Block Analysis CSV file")
    parser.add_argument("--output", type=Path, help="Optional CSV file for the counts")
    parser.add_argument("--encoding", help="Override input encoding, for example utf-8 or utf-16")
    args = parser.parse_args()

    if not args.input.is_file():
        parser.error(f"Input file not found: {args.input}")

    try:
        counts, row_count = count_subtypes(args.input, args.encoding)
    except (OSError, UnicodeError, csv.Error, ValueError) as error:
        parser.error(str(error))

    print(f"Rows read: {row_count:,}")
    print(f"Unique BlockSubtype values: {len(counts):,}\n")
    print(f"{'Count':>12}  BlockSubtype")
    print(f"{'-' * 12}  {'-' * 60}")
    for subtype, count in counts.most_common():
        print(f"{count:>12,}  {subtype}")

    if args.output:
        _write_counts(args.output, counts)
        print(f"\nCounts written to: {args.output}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())