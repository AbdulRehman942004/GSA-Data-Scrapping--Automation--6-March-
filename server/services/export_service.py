import pandas as pd
import os
import sys
import io
import logging
from datetime import datetime
from sqlmodel import Session, select

# Ensure the root project dir is in sys.path so we can import modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from database.db import get_engine
from database.models import GSAScrapedData, ImportedLink, ImportedPart, LinkScrapedData

logger = logging.getLogger(__name__)


def get_export_info() -> dict:
    """
    Return a lightweight summary of what data is available to export.
    Used by the frontend to show the user what will be in their download
    before actually streaming the file.

    Returns:
        {
          "has_parts_data":  bool,  # gsa_scraped_data has records
          "has_links_data":  bool,  # links_scraped_data has records
          "parts_records":   int,
          "links_records":   int,
          "active_engine":   "parts" | "links" | "both" | "none"
        }
    """
    try:
        engine = get_engine()
        with Session(engine) as session:
            parts_records = session.query(GSAScrapedData).count()
            links_records = session.query(LinkScrapedData).count()
    except Exception as e:
        logger.error(f"get_export_info DB error: {e}")
        return {"has_parts_data": False, "has_links_data": False,
                "parts_records": 0, "links_records": 0, "active_engine": "none"}

    has_parts = parts_records > 0
    has_links = links_records > 0

    if has_parts and has_links:
        engine_label = "both"
    elif has_parts:
        engine_label = "parts"
    elif has_links:
        engine_label = "links"
    else:
        engine_label = "none"

    return {
        "has_parts_data": has_parts,
        "has_links_data": has_links,
        "parts_records": parts_records,
        "links_records": links_records,
        "active_engine": engine_label,
    }


def export_to_excel():
    """
    Smart export.

    Sheet decision table
    ─────────────────────────────────────────────────────────────────────────────
    GSA parts data     Internal scraped   External scraped   Sheets written
    ─────────────────  ─────────────────  ─────────────────  ────────────────────
    has records        –                  –                  "GSA Parts Data"
    –                  has records        –                  "Internal Links"
    –                  –                  has records        "External Links"
    –                  has records        has records        both link sheets
    has records        has records        has records        all three sheets
    none               none               none               → None (error)
    ─────────────────────────────────────────────────────────────────────────────

    Internal Links sheet columns (one row per product-detail link):
        Internal Link URL | Manufacturer Part Name |
        GSA PRICE | Unit | Contractor | contract#: |          ← slot 1
        GSA PRICE.1 | Unit.1 | Contractor.1 | contract#:.1 | ← slot 2  … up to slot 6

    External Links sheet columns (one row per search/external link):
        Manufacturer Part Number | External Link URL |
        GSA PRICE | Unit | Manufacturer Part Name | Contractor | contract#: |   ← slot 1
        GSA PRICE.1 | … up to slot 6

    Returns (BytesIO buffer, filename) on success, or None on failure.
    """
    from collections import defaultdict

    try:
        engine = get_engine()
    except Exception as e:
        logger.error(f"Failed to connect to the database: {e}")
        return None

    try:
        with Session(engine) as session:
            imported_parts = session.exec(select(ImportedPart).order_by(ImportedPart.id)).all()
            scraped_parts  = session.exec(select(GSAScrapedData)).all()

            # Build link-type lookup: link_id → link_type ("internal" | "external")
            # This is also the session boundary — only current-session link IDs allowed.
            imported_links_all = session.exec(select(ImportedLink)).all()
            link_type_map: dict[int, str] = {
                il.id: il.link_type for il in imported_links_all
            }
            current_link_ids: set[int] = set(link_type_map.keys())

            links_scraped_raw = session.exec(
                select(LinkScrapedData).order_by(
                    LinkScrapedData.link_id, LinkScrapedData.row_order
                )
            ).all()

        # Session filter: drop rows whose link_id is no longer in imported_links
        links_scraped = [r for r in links_scraped_raw if r.link_id in current_link_ids]

        # Split by link type
        internal_scraped = [r for r in links_scraped if link_type_map.get(r.link_id) == "internal"]
        external_scraped = [r for r in links_scraped if link_type_map.get(r.link_id) == "external"]

        has_parts_data    = len(scraped_parts) > 0
        has_internal_data = len(internal_scraped) > 0
        has_external_data = len(external_scraped) > 0

        logger.info(
            f"Export info: parts={len(scraped_parts)}, "
            f"internal_links={len(internal_scraped)}, "
            f"external_links={len(external_scraped)}"
        )

        if not has_parts_data and not has_internal_data and not has_external_data:
            logger.error("No scraped data found. Run an extraction first.")
            return None

        timestamp = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
        output_buffer = io.BytesIO()

        # Slot suffixes: "" for slot 1, ".1" … ".5" for slots 2–6
        _MAX_SLOTS = 6
        _SUFFIXES  = [""] + [f".{i}" for i in range(1, _MAX_SLOTS)]

        def _v(val):
            """Return empty string for None / NaN values."""
            if val is None:
                return ""
            if isinstance(val, float) and pd.isna(val):
                return ""
            return val

        def _pivot_internal(scraped_rows: list) -> pd.DataFrame:
            """
            Build the Internal Links sheet.

            Columns: Internal Link URL | Manufacturer Part Name |
                     GSA PRICE | Unit | Contractor | contract#:  (×6 slots)
            """
            groups: dict = defaultdict(list)
            for r in scraped_rows:
                groups[r.link_id].append(r)

            pivoted = []
            for link_id in sorted(groups.keys()):
                rows = sorted(groups[link_id], key=lambda r: r.row_order)
                base = rows[0]

                record: dict = {
                    "Internal Link URL":      _v(base.link),
                    "Manufacturer Part Name": _v(base.manufacturer_part_name),
                }
                for i, sfx in enumerate(_SUFFIXES):
                    if i < len(rows):
                        r = rows[i]
                        record[f"GSA PRICE{sfx}"]  = _v(r.price)
                        record[f"Unit{sfx}"]        = _v(r.unit)
                        record[f"Contractor{sfx}"]  = _v(r.contractor_name)
                        record[f"contract#:{sfx}"]  = _v(r.contract_number)
                    else:
                        record[f"GSA PRICE{sfx}"]  = ""
                        record[f"Unit{sfx}"]        = ""
                        record[f"Contractor{sfx}"]  = ""
                        record[f"contract#:{sfx}"]  = ""
                pivoted.append(record)

            return pd.DataFrame(pivoted)

        def _pivot_external(scraped_rows: list) -> pd.DataFrame:
            """
            Build the External Links sheet.

            Columns: Manufacturer Part Number | External Link URL |
                     GSA PRICE | Unit | Manufacturer Part Name | Contractor | contract#:  (×6 slots)
            """
            groups: dict = defaultdict(list)
            for r in scraped_rows:
                groups[r.link_id].append(r)

            pivoted = []
            for link_id in sorted(groups.keys()):
                rows = sorted(groups[link_id], key=lambda r: r.row_order)
                base = rows[0]

                record: dict = {
                    "Manufacturer Part Number": _v(base.manufacturer_part_number),
                    "External Link URL":        _v(base.link),
                }
                for i, sfx in enumerate(_SUFFIXES):
                    if i < len(rows):
                        r = rows[i]
                        record[f"GSA PRICE{sfx}"]            = _v(r.price)
                        record[f"Unit{sfx}"]                  = _v(r.unit)
                        record[f"Manufacturer Part Name{sfx}"] = _v(r.manufacturer_part_name)
                        record[f"Contractor{sfx}"]            = _v(r.contractor_name)
                        record[f"contract#:{sfx}"]            = _v(r.contract_number)
                    else:
                        record[f"GSA PRICE{sfx}"]            = ""
                        record[f"Unit{sfx}"]                  = ""
                        record[f"Manufacturer Part Name{sfx}"] = ""
                        record[f"Contractor{sfx}"]            = ""
                        record[f"contract#:{sfx}"]            = ""
                pivoted.append(record)

            return pd.DataFrame(pivoted)

        with pd.ExcelWriter(output_buffer, engine='openpyxl') as writer:

            # ── GSA Parts Data (price extraction pipeline) ────────────────────
            if has_parts_data:
                rows = [
                    {"part_number": r.part_number, "manufacturer": r.manufacturer or ""}
                    for r in imported_parts
                ]
                df = pd.DataFrame(rows) if rows else pd.DataFrame(
                    columns=["part_number", "manufacturer"]
                )
                for col in ['1 GSA Low Price', 'Unit', 'Contractor:Name',
                            '2 GSA Low Price', 'Unit.1', 'Contractor:Name.1']:
                    df[col] = pd.Series([None] * len(df), dtype='object')

                scraped_dict = {str(s.part_number).strip(): s for s in scraped_parts}
                matched = 0
                for idx, row in df.iterrows():
                    pn = str(row['part_number']).strip()
                    if pn in scraped_dict:
                        s = scraped_dict[pn]
                        df.at[idx, '1 GSA Low Price']   = _v(s.gsa_low_price_1)
                        df.at[idx, 'Unit']               = _v(s.unit_1)
                        df.at[idx, 'Contractor:Name']    = _v(s.contractor_1)
                        df.at[idx, '2 GSA Low Price']    = _v(s.gsa_low_price_2)
                        df.at[idx, 'Unit.1']             = _v(s.unit_2)
                        df.at[idx, 'Contractor:Name.1']  = _v(s.contractor_2)
                        matched += 1

                df.to_excel(writer, sheet_name="GSA Parts Data", index=False)
                logger.info(f"Export 'GSA Parts Data': {matched} row(s) matched")

            # ── Internal Links (product-detail link extraction) ───────────────
            if has_internal_data:
                df_int = _pivot_internal(internal_scraped)
                df_int.to_excel(writer, sheet_name="Internal Links", index=False)
                logger.info(f"Export 'Internal Links': {len(df_int)} product row(s)")

            # ── External Links (search/external link extraction) ──────────────
            if has_external_data:
                df_ext = _pivot_external(external_scraped)
                df_ext.to_excel(writer, sheet_name="External Links", index=False)
                logger.info(f"Export 'External Links': {len(df_ext)} product row(s)")

        # ── Filename ──────────────────────────────────────────────────────────
        parts_tag    = "parts_"    if has_parts_data    else ""
        internal_tag = "internal_" if has_internal_data else ""
        external_tag = "external_" if has_external_data else ""
        filename = f"gsa_{parts_tag}{internal_tag}{external_tag}export_{timestamp}.xlsx"

        output_buffer.seek(0)
        logger.info(f"Export ready: {filename}")
        return output_buffer, filename

    except Exception as e:
        logger.error(f"Export failed: {e}", exc_info=True)
        return None
