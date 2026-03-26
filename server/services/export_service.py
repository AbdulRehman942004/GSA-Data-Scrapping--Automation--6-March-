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
from database.models import GSAScrapedData, ImportedPart

logger = logging.getLogger(__name__)


def export_to_excel():
    """Build an Excel export from imported_parts joined with gsa_scraped_data.

    Returns (BytesIO buffer, filename) on success, or None on failure.
    """
    try:
        engine = get_engine()
    except Exception as e:
        logger.error(f"Failed to connect to the database: {e}")
        return None

    try:
        with Session(engine) as session:
            # 1. Load imported parts as the base dataset
            imported = session.exec(select(ImportedPart).order_by(ImportedPart.id)).all()
            if not imported:
                logger.error("No imported parts found. Nothing to export.")
                return None

            rows = [
                {"part_number": r.part_number, "manufacturer": r.manufacturer or ""}
                for r in imported
            ]
            df = pd.DataFrame(rows)
            logger.info(f"Export: loaded {len(df)} imported parts")

            # 2. Load scraped data
            scraped = session.exec(select(GSAScrapedData)).all()
            logger.info(f"Export: found {len(scraped)} scraped records")

        # 3. Prepare output columns (use object dtype to allow mixed str/float)
        output_cols = [
            '1 GSA Low Price', 'Unit', 'Contractor:Name',
            '2 GSA Low Price', 'Unit.1', 'Contractor:Name.1'
        ]
        for col in output_cols:
            df[col] = pd.Series([None] * len(df), dtype='object')

        # 4. Merge scraped data into the export
        updated_count = 0
        if scraped:
            scraped_dict = {}
            for s in scraped:
                scraped_dict[str(s.part_number).strip()] = {
                    'gsa_low_price_1': s.gsa_low_price_1,
                    'unit_1': s.unit_1,
                    'contractor_1': s.contractor_1,
                    'gsa_low_price_2': s.gsa_low_price_2,
                    'unit_2': s.unit_2,
                    'contractor_2': s.contractor_2,
                }

            def _val(data, key):
                v = data.get(key)
                return v if v is not None and not (isinstance(v, float) and pd.isna(v)) else ''

            for idx, row in df.iterrows():
                part_num = str(row['part_number']).strip()
                if part_num in scraped_dict:
                    data = scraped_dict[part_num]
                    df.at[idx, '1 GSA Low Price'] = _val(data, 'gsa_low_price_1')
                    df.at[idx, 'Unit'] = _val(data, 'unit_1')
                    df.at[idx, 'Contractor:Name'] = _val(data, 'contractor_1')
                    df.at[idx, '2 GSA Low Price'] = _val(data, 'gsa_low_price_2')
                    df.at[idx, 'Unit.1'] = _val(data, 'unit_2')
                    df.at[idx, 'Contractor:Name.1'] = _val(data, 'contractor_2')
                    updated_count += 1

            logger.info(f"Export: matched {updated_count} rows with scraped data")

        # 5. Write to in-memory buffer
        timestamp = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
        filename = f"gsa_scrapped_products_{timestamp}.xlsx"

        output_buffer = io.BytesIO()
        df.to_excel(output_buffer, index=False, engine='openpyxl')
        output_buffer.seek(0)

        logger.info(f"Export: {filename} ready ({updated_count} rows with data)")
        return output_buffer, filename

    except Exception as e:
        logger.error(f"Export failed: {e}", exc_info=True)
        return None
