import pandas as pd
import os
import sys
import io
from datetime import datetime

# Ensure the root project dir is in sys.path so we can import modules
sys.path.append(os.path.abspath(os.path.dirname(__file__)))
from database.db import get_engine
from settings import EXCEL_FILE_PATH

def export_to_excel():

    try:
        engine = get_engine()
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Failed to connect to the database: {e}")
        return None

    input_excel = EXCEL_FILE_PATH
    
    timestamp = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
    filename = f"gsa_scrapped_products_{timestamp}.xlsx"
    
    print(f"Reading base Excel file: {input_excel}")
    try:
        df = pd.read_excel(input_excel)
    except Exception as e:
        print(f"Error reading Excel file: {e}")
        return None
        
    print(f"Querying scraped data from PostgreSQL...")
    try:
        # Read the scraped data
        scraped_df = pd.read_sql("SELECT * FROM gsa_scraped_data", engine)
    except Exception as e:
        print(f"Error reading from database: {e}")
        return None
        
    print(f"Found {len(scraped_df)} scraped records in the database.")
    
    # Identify part number column in the original excel
    part_num_col = None
    for col in df.columns:
        if col.strip().lower() == 'part_number':
            part_num_col = col
            break
            
    if not part_num_col:
        print("Could not find 'part_number' column in the Excel file.")
        return None
        
    # Prepare the output columns in the dataframe if they don't exist
    output_cols = [
        '1 GSA Low Price', 'Unit', 'Contractor:Name',
        '2 GSA Low Price', 'Unit.1', 'Contractor:Name.1'
    ]
    for col in output_cols:
        if col not in df.columns:
            df[col] = ''
        else:
            df[col] = df[col].astype(object)
    
    # Build a direct lookup: part_number → row
    print("Merging scraped data into Excel structure...")
    scraped_df['part_number'] = scraped_df['part_number'].astype(str).str.strip()
    scraped_dict = scraped_df.set_index('part_number').to_dict('index')
        
    def _val(data, key):
        v = data.get(key)
        return v if v is not None and not (isinstance(v, float) and pd.isna(v)) else ''

    # Update the final dataframe
    updated_count = 0
    for idx, row in df.iterrows():
        part_num = str(row[part_num_col]).strip()
        if part_num in scraped_dict:
            data = scraped_dict[part_num]
            df.at[idx, '1 GSA Low Price'] = _val(data, 'gsa_low_price_1')
            df.at[idx, 'Unit'] = _val(data, 'unit_1')
            df.at[idx, 'Contractor:Name'] = _val(data, 'contractor_1')
            df.at[idx, '2 GSA Low Price'] = _val(data, 'gsa_low_price_2')
            df.at[idx, 'Unit.1'] = _val(data, 'unit_2')
            df.at[idx, 'Contractor:Name.1'] = _val(data, 'contractor_2')
            updated_count += 1
            
    print(f"Successfully matched and injected {updated_count} rows with scraped data.")
    
    print(f"Generating dynamic in-memory Excel deliverable: {filename}")
    try:
        output_buffer = io.BytesIO()
        df.to_excel(output_buffer, index=False, engine='openpyxl')
        output_buffer.seek(0)
    except Exception as e:
        print(f"Error compiling in-memory Excel data: {e}")
        return None
        
    print(f"Done! API Export memory buffer prepared successfully.")
    return output_buffer, filename

if __name__ == "__main__":
    export_to_excel()
