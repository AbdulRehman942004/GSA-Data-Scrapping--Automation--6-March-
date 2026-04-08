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
    Smart export: only include a sheet when that engine's scraped data exists.

    Decision table
    ──────────────────────────────────────────────────────────────
    gsa_scraped_data   links_scraped_data   Sheets included
    ─────────────────  ──────────────────── ─────────────────────
    has records        empty                "GSA Parts Data" only
    empty              has records          "Links Scraped Data" only
    has records        has records          both sheets
    empty              empty                → error (None returned)
    ──────────────────────────────────────────────────────────────

    Returns (BytesIO buffer, filename) on success, or None on failure.
    """
    try:
        engine = get_engine()
    except Exception as e:
        logger.error(f"Failed to connect to the database: {e}")
        return None

    try:
        with Session(engine) as session:
            imported = session.exec(select(ImportedPart).order_by(ImportedPart.id)).all()
            scraped = session.exec(select(GSAScrapedData)).all()

            # Only export scraped rows whose link_id exists in the CURRENT imported_links
            # table. This is the hard session boundary: orphaned rows from past sessions
            # (link_id no longer in imported_links) are silently excluded.
            current_link_ids: set[int] = {
                il.id for il in session.exec(select(ImportedLink)).all()
            }
            links_scraped = session.exec(
                select(LinkScrapedData).order_by(
                    LinkScrapedData.link_id, LinkScrapedData.row_order
                )
            ).all()
            # Apply session filter in Python (works for any DB backend)
            links_scraped = [r for r in links_scraped if r.link_id in current_link_ids]

        has_parts_data = len(scraped) > 0
        has_links_data = len(links_scraped) > 0

        logger.info(
            f"Export info: has_parts_data={has_parts_data} ({len(scraped)} records), "
            f"has_links_data={has_links_data} ({len(links_scraped)} records)"
        )

        # Nothing to export at all
        if not has_parts_data and not has_links_data:
            logger.error(
                "No scraped data found in either pipeline (gsa_scraped_data and "
                "links_scraped_data are both empty). Run an extraction first."
            )
            return None

        timestamp = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
        output_buffer = io.BytesIO()

        def _val(d, key):
            v = d.get(key)
            return v if v is not None and not (isinstance(v, float) and pd.isna(v)) else ''

        with pd.ExcelWriter(output_buffer, engine='openpyxl') as writer:

            # ── Sheet 1: GSA Parts Data (price extraction engine) ─────────────
            if has_parts_data:
                rows = [
                    {"part_number": r.part_number, "manufacturer": r.manufacturer or ""}
                    for r in imported
                ]
                df = pd.DataFrame(rows) if rows else pd.DataFrame(
                    columns=["part_number", "manufacturer"]
                )

                for col in ['1 GSA Low Price', 'Unit', 'Contractor:Name',
                            '2 GSA Low Price', 'Unit.1', 'Contractor:Name.1']:
                    df[col] = pd.Series([None] * len(df), dtype='object')

                scraped_dict = {str(s.part_number).strip(): s for s in scraped}
                matched = 0
                for idx, row in df.iterrows():
                    pn = str(row['part_number']).strip()
                    if pn in scraped_dict:
                        s = scraped_dict[pn]
                        d = {
                            'gsa_low_price_1': s.gsa_low_price_1, 'unit_1': s.unit_1,
                            'contractor_1': s.contractor_1,
                            'gsa_low_price_2': s.gsa_low_price_2, 'unit_2': s.unit_2,
                            'contractor_2': s.contractor_2,
                        }
                        df.at[idx, '1 GSA Low Price']   = _val(d, 'gsa_low_price_1')
                        df.at[idx, 'Unit']               = _val(d, 'unit_1')
                        df.at[idx, 'Contractor:Name']    = _val(d, 'contractor_1')
                        df.at[idx, '2 GSA Low Price']    = _val(d, 'gsa_low_price_2')
                        df.at[idx, 'Unit.1']             = _val(d, 'unit_2')
                        df.at[idx, 'Contractor:Name.1']  = _val(d, 'contractor_2')
                        matched += 1

                df.to_excel(writer, sheet_name="GSA Parts Data", index=False)
                logger.info(f"Export Sheet 'GSA Parts Data': {matched} matched rows written")

            # ── Sheet 2: Links Scraped Data (link extraction engine) ──────────
            # One Excel row per product link.  Up to 6 comparison slots placed
            # side-by-side using the column pattern (no suffix = slot 1):
            #
            #   Link URL | Mfr Part Name | Mfr Part Number |
            #   GSA PRICE | Unit | Contractor | contract#: |      ← slot 1
            #   GSA PRICE.1 | Unit.1 | Contractor.1 | contract#:.1 | … ← slot 2
            #   … up to slot 6 (suffix .5)
            if has_links_data:
                from collections import defaultdict

                # Group scraped rows by link_id, preserving row_order sort
                link_groups: dict = defaultdict(list)
                for r in links_scraped:
                    link_groups[r.link_id].append(r)

                # Suffixes: "", ".1", ".2", ".3", ".4", ".5"
                _max_slots = 6
                _suffixes = [""] + [f".{i}" for i in range(1, _max_slots)]

                pivoted_rows = []
                for link_id in sorted(link_groups.keys()):
                    rows = sorted(link_groups[link_id], key=lambda r: r.row_order)
                    base = rows[0]

                    record: dict = {
                        "Link URL":                 base.link,
                        "Manufacturer Part Name":   base.manufacturer_part_name or "",
                        "Manufacturer Part Number": base.manufacturer_part_number or "",
                    }

                    for i, sfx in enumerate(_suffixes):
                        if i < len(rows):
                            r = rows[i]
                            record[f"GSA PRICE{sfx}"]  = r.price if r.price is not None else ""
                            record[f"Unit{sfx}"]        = r.unit or ""
                            record[f"Contractor{sfx}"]  = r.contractor_name or ""
                            record[f"contract#:{sfx}"]  = r.contract_number or ""
                        else:
                            record[f"GSA PRICE{sfx}"]  = ""
                            record[f"Unit{sfx}"]        = ""
                            record[f"Contractor{sfx}"]  = ""
                            record[f"contract#:{sfx}"]  = ""

                    pivoted_rows.append(record)

                df_links = pd.DataFrame(pivoted_rows)
                df_links.to_excel(writer, sheet_name="Links Scraped Data", index=False)
                logger.info(
                    f"Export Sheet 'Links Scraped Data': {len(df_links)} product row(s) "
                    f"(session-filtered from {len(links_scraped)} scraped records, "
                    f"{len(current_link_ids)} active links)"
                )

        # ── Choose a descriptive filename based on what was exported ──────────
        if has_parts_data and has_links_data:
            filename = f"gsa_full_export_{timestamp}.xlsx"
        elif has_parts_data:
            filename = f"gsa_parts_data_{timestamp}.xlsx"
        else:
            filename = f"gsa_links_data_{timestamp}.xlsx"

        output_buffer.seek(0)
        logger.info(f"Export ready: {filename}")
        return output_buffer, filename

    except Exception as e:
        logger.error(f"Export failed: {e}", exc_info=True)
        return None
