"""
Step 1 of the manufacturer normalization pipeline.

Reads an Essendant product Excel file, extracts unique manufacturer names
from a specified column, and writes them to a .txt file (one name per line).

The output feeds directly into normalize_mfr_names.py (Step 2).

Usage:
    python utils/extract_unique_manufacturers.py
    python utils/extract_unique_manufacturers.py --excel path/to/file.xlsx --output path/to/out.txt
"""
import argparse
from pathlib import Path
from typing import List

import pandas as pd

# Resolve paths relative to the server root (one level up from this file)
_SERVER_DIR = Path(__file__).resolve().parent.parent
_MFR_DATA_DIR = _SERVER_DIR / "manufacturer_normalization" / "identify_unique_mfr"

DEFAULT_COLUMN_NAME: str = "Manufacturer Long Name"


def load_unique_manufacturers(
    excel_path: Path, column_name: str = DEFAULT_COLUMN_NAME
) -> List[str]:
    """
    Load the specified Excel file, extract the manufacturer column, and return a
    sorted list of unique manufacturer names.

    The function trims surrounding whitespace and removes empty/null entries.
    """
    if not excel_path.exists():
        raise FileNotFoundError(f"Excel file not found: {excel_path}")

    dataframe = pd.read_excel(excel_path, engine="openpyxl")

    if column_name not in dataframe.columns:
        available = ", ".join([str(c) for c in dataframe.columns])
        raise KeyError(
            f"Column '{column_name}' not found. Available columns: {available}"
        )

    column_series = dataframe[column_name].astype("string").str.strip()
    column_series = column_series[column_series.notna() & (column_series != "")]
    unique_names = sorted(column_series.drop_duplicates().tolist())

    return unique_names


def write_list_to_file(values: List[str], output_path: Path) -> None:
    """Write each value on its own line to the output file."""
    output_path.write_text("\n".join(values), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Extract unique manufacturer names from an Excel file column and "
            "save the list to a .txt file."
        )
    )
    parser.add_argument(
        "--excel",
        type=Path,
        default=_MFR_DATA_DIR / "essendant-product-list (1).xlsx",
        help="Path to the Essendant product Excel file.",
    )
    parser.add_argument(
        "--column",
        type=str,
        default=DEFAULT_COLUMN_NAME,
        help=f"Column name to extract (default: '{DEFAULT_COLUMN_NAME}').",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=_MFR_DATA_DIR / "unique_manufacturers.txt",
        help="Output .txt file for unique manufacturer names.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    try:
        unique_manufacturers = load_unique_manufacturers(args.excel, args.column)
    except Exception as exc:
        print(f"Error: {exc}")
        return

    write_list_to_file(unique_manufacturers, args.output)

    print(f"Found {len(unique_manufacturers)} unique manufacturers in '{args.column}'.")
    print(f"Saved list to: {args.output}")


if __name__ == "__main__":
    main()
