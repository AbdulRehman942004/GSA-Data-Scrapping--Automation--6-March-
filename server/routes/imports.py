import logging
from io import BytesIO

import pandas as pd
from fastapi import APIRouter, File, HTTPException, UploadFile
from sqlmodel import SQLModel

from database.db import get_engine
from database.repository import (
    bulk_insert_imported_parts,
    clear_gsa_links,
    clear_gsa_scraped_data,
    clear_imported_parts,
    get_imported_parts_count,
)

router = APIRouter(prefix="/api", tags=["Import"])
logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = (".xlsx", ".xls")


@router.post("/import")
async def import_excel(file: UploadFile = File(...)):
    """Upload an Excel file to replace the current imported_parts data."""
    if not file.filename or not file.filename.lower().endswith(ALLOWED_EXTENSIONS):
        raise HTTPException(400, "File must be an Excel file (.xlsx or .xls)")

    contents = await file.read()
    try:
        df = pd.read_excel(BytesIO(contents))
    except Exception as e:
        raise HTTPException(422, f"Could not read Excel file: {e}")

    # Map columns (case-insensitive)
    col_map: dict[str, str] = {}
    for col in df.columns:
        lower = col.strip().lower()
        if lower == "part_number":
            col_map["part_number"] = col
        elif lower == "manufacturer":
            col_map["manufacturer"] = col

    if "part_number" not in col_map:
        raise HTTPException(
            422,
            f"Excel must have a 'part_number' column. Found: {list(df.columns)}",
        )

    # Build records
    records: list[dict] = []
    for _, row in df.iterrows():
        pn = str(row[col_map["part_number"]]).strip()
        if not pn or pn.lower() == "nan":
            continue
        mfr = ""
        if "manufacturer" in col_map:
            mfr = str(row[col_map["manufacturer"]]).strip()
            if mfr.lower() == "nan":
                mfr = ""
        records.append({"part_number": pn, "manufacturer": mfr})

    if not records:
        raise HTTPException(422, "No valid rows found in the Excel file.")

    # Store in DB (replace previous import + clear stale link/scrape data)
    engine = get_engine()
    SQLModel.metadata.create_all(engine)  # ensure table exists
    clear_imported_parts(engine)
    clear_gsa_links(engine)
    clear_gsa_scraped_data(engine)
    count = bulk_insert_imported_parts(engine, records)
    logger.info(f"Imported {count} parts from {file.filename} (old links/scraped data cleared)")

    return {
        "status": "success",
        "filename": file.filename,
        "rows_imported": count,
    }


@router.get("/import/status")
async def import_status():
    """Return how many parts are currently imported."""
    engine = get_engine()
    count = get_imported_parts_count(engine)
    return {"imported_parts_count": count}
