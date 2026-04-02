import logging
from io import BytesIO

import pandas as pd
from fastapi import APIRouter, File, HTTPException, UploadFile
from sqlmodel import SQLModel

from database.db import get_engine
from database.repository import (
    bulk_insert_imported_links,
    bulk_insert_imported_parts,
    clear_gsa_links,
    clear_gsa_scraped_data,
    clear_imported_links,
    clear_imported_parts,
    get_imported_links_count,
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


@router.post("/import/links")
async def import_links(file: UploadFile = File(...)):
    """
    Upload an Excel file to import links. Accepts two formats:

    Format 1 (internal): Single column ``internal_links``
    Format 2 (external): Two columns ``part_number`` + ``external_links``
    """
    if not file.filename or not file.filename.lower().endswith(ALLOWED_EXTENSIONS):
        raise HTTPException(400, "File must be an Excel file (.xlsx or .xls)")

    contents = await file.read()
    try:
        df = pd.read_excel(BytesIO(contents))
    except Exception as e:
        raise HTTPException(422, f"Could not read Excel file: {e}")

    # Map columns (case-insensitive, trimmed)
    col_map: dict[str, str] = {}
    for col in df.columns:
        lower = col.strip().lower()
        if lower == "internal link url":
            col_map["internal_links"] = col
        elif lower == "external link url":
            col_map["external_links"] = col
        elif lower == "manufacturer part number":
            col_map["part_number"] = col

    # Detect format
    has_internal = "internal_links" in col_map
    has_external = "external_links" in col_map and "part_number" in col_map

    if not has_internal and not has_external:
        raise HTTPException(
            422,
            "Excel must have either an 'Internal Link URL' column, "
            "or both 'Manufacturer Part Number' and 'External Link URL' columns. "
            f"Found: {list(df.columns)}",
        )

    records: list[dict] = []

    if has_internal:
        for _, row in df.iterrows():
            link = str(row[col_map["internal_links"]]).strip()
            if not link or link.lower() == "nan":
                continue
            is_pd = "product_detail" in link.lower()
            records.append({
                "link": link,
                "part_number": None,
                "is_product_detail": is_pd,
                "link_type": "internal",
            })

    if has_external:
        for _, row in df.iterrows():
            link = str(row[col_map["external_links"]]).strip()
            pn = str(row[col_map["part_number"]]).strip()
            if not link or link.lower() == "nan":
                continue
            if not pn or pn.lower() == "nan":
                pn = None
            is_pd = "product_detail" in link.lower()
            records.append({
                "link": link,
                "part_number": pn,
                "is_product_detail": is_pd,
                "link_type": "external",
            })

    if not records:
        raise HTTPException(422, "No valid rows found in the Excel file.")

    engine = get_engine()
    SQLModel.metadata.create_all(engine)
    clear_imported_links(engine)
    count = bulk_insert_imported_links(engine, records)

    product_detail_count = sum(1 for r in records if r["is_product_detail"])
    search_count = count - product_detail_count
    internal_count = sum(1 for r in records if r["link_type"] == "internal")
    external_count = count - internal_count
    logger.info(
        f"Imported {count} links from {file.filename} "
        f"({internal_count} internal, {external_count} external, "
        f"{product_detail_count} product_detail, {search_count} advantage_search)"
    )

    return {
        "status": "success",
        "filename": file.filename,
        "rows_imported": count,
        "internal_links": internal_count,
        "external_links": external_count,
        "product_detail_links": product_detail_count,
        "search_links": search_count,
    }


@router.get("/import/status")
async def import_status():
    """Return counts for imported parts and imported links."""
    engine = get_engine()
    parts_count = get_imported_parts_count(engine)
    links_count = get_imported_links_count(engine)

    # Count product_detail vs search links
    from database.models import ImportedLink
    from sqlmodel import Session, select
    with Session(engine) as session:
        product_detail_count = len(
            session.exec(select(ImportedLink).where(ImportedLink.is_product_detail == True)).all()
        )
    search_count = links_count - product_detail_count

    return {
        "imported_parts_count": parts_count,
        "imported_links_count": links_count,
        "product_detail_count": product_detail_count,
        "search_count": search_count,
    }
