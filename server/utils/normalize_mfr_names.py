"""
Step 2 of the manufacturer normalization pipeline.

Reads unique_manufacturers.txt (produced by extract_unique_manufacturers.py),
computes a root form for each name, and writes the original→root mapping to
original_to_root.csv. That CSV is the file used at runtime by ManufacturerNormalizer.

Usage:
    python utils/normalize_mfr_names.py
    python utils/normalize_mfr_names.py --input path/to/unique.txt --output path/to/mapping.csv
"""
import argparse
import csv
import re
from pathlib import Path
from typing import Iterable, List, Tuple

# Resolve paths relative to the server root (one level up from this file)
_SERVER_DIR = Path(__file__).resolve().parent.parent
_MFR_DIR = _SERVER_DIR / "manufacturer_normalization"

# Terms to strip when determining the root name.
REMOVABLE_TERMS = {
    # corporate forms
    "inc", "incorporated", "corp", "corporation", "co", "company", "llc", "l.l.c",
    "ltd", "limited", "gmbh", "s.a.", "s.a", "s.p.a.", "spa", "ag", "kg", "nv",
    "plc", "pty", "pte", "sro", "s.r.o", "srl", "lp", "llp", "pc",
    # common descriptors
    "products", "product", "brands", "brand", "group", "international", "industries",
    "industry", "mfg", "manufacturing", "manufacturers", "division", "div",
    # geography / noise
    "usa", "u.s.a", "u.s.", "us", "america", "american", "north", "south",
    "europe", "european", "asia", "pacific",
}

_NON_ALNUM_TO_SPACE = re.compile(r"[^0-9a-z]+")
_STRIP_NON_ALNUM = re.compile(r"[^0-9a-z]")


def normalize_to_root(name: str) -> str:
    """Convert a manufacturer display name to a simple root form."""
    if not name:
        return ""

    lower = name.lower()
    tokens = _NON_ALNUM_TO_SPACE.sub(" ", lower).split()
    filtered = [t for t in tokens if t not in REMOVABLE_TERMS]

    if filtered:
        chosen = filtered[0]
    else:
        alnum_runs = re.findall(r"[0-9a-z]+", lower)
        chosen = alnum_runs[0] if alnum_runs else ""

    return _STRIP_NON_ALNUM.sub("", chosen)


def read_unique_list(input_path: Path) -> List[str]:
    text = input_path.read_text(encoding="utf-8")
    lines = [line.strip() for line in text.splitlines()]
    return [line for line in lines if line]


def build_mapping(names: Iterable[str]) -> List[Tuple[str, str]]:
    return [(original, normalize_to_root(original)) for original in names]


def write_mapping_csv(rows: List[Tuple[str, str]], output_csv: Path) -> None:
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["original", "root"])
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Normalize manufacturer names to root form and write original→root CSV."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=_MFR_DIR / "identify_unique_mfr" / "unique_manufacturers.txt",
        help="Path to the unique manufacturers .txt file (Step 1 output).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=_MFR_DIR / "convert_to_root" / "original_to_root.csv",
        help="Path to write the original→root CSV mapping.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if not args.input.exists():
        print(f"Error: input file not found: {args.input}")
        return

    names = read_unique_list(args.input)
    mapping = build_mapping(names)
    write_mapping_csv(mapping, args.output)

    non_empty = sum(1 for _, r in mapping if r)
    print(f"Processed {len(mapping)} names; {non_empty} produced non-empty roots.")
    print(f"Wrote mapping to: {args.output}")


if __name__ == "__main__":
    main()
