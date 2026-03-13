import pandas as pd
from sqlalchemy import create_engine
import os
import sys
from datetime import datetime

# Ensure the root project dir is in sys.path so we can import modules
sys.path.append(os.path.abspath(os.path.dirname(__file__)))
from database.db import get_engine

def export_to_excel():
    
    try:
        engine = get_engine()
    except Exception as e:
        print(f"Failed to connect to the database: {e}")
        return None
    
    # File paths
    script_dir = os.path.dirname(os.path.abspath(__file__))
    input_excel = os.path.join(script_dir, "new_requirements", "GSA Advantage Low price.xlsx")
    
    output_dir = os.path.join(script_dir, "scrapped_data")
    os.makedirs(output_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
    filename = f"gsa_scrapped_products_{timestamp}.xlsx"
    output_excel = os.path.join(output_dir, filename)
    
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
    
    # Create an easy lookup dictionary from part_number to data row
    print("Merging scraped data into Excel structure...")
    scraped_dict = {}
    for _, row in scraped_df.iterrows():
        scraped_dict[str(row['part_number'])] = row
        
    # Update the final dataframe
    updated_count = 0
    for idx, row in df.iterrows():
        part_num = str(row[part_num_col])
        if part_num in scraped_dict:
            data = scraped_dict[part_num]
            df.at[idx, '1 GSA Low Price'] = data['gsa_low_price_1'] if pd.notna(data['gsa_low_price_1']) else ''
            df.at[idx, 'Unit'] = data['unit_1'] if pd.notna(data['unit_1']) else ''
            df.at[idx, 'Contractor:Name'] = data['contractor_1'] if pd.notna(data['contractor_1']) else ''
            df.at[idx, '2 GSA Low Price'] = data['gsa_low_price_2'] if pd.notna(data['gsa_low_price_2']) else ''
            df.at[idx, 'Unit.1'] = data['unit_2'] if pd.notna(data['unit_2']) else ''
            df.at[idx, 'Contractor:Name.1'] = data['contractor_2'] if pd.notna(data['contractor_2']) else ''
            updated_count += 1
            
    print(f"Successfully matched and injected {updated_count} rows with scraped data.")
    
    print(f"Saving final deliverable to: {output_excel}")
    try:
        df.to_excel(output_excel, index=False, engine='openpyxl')
    except Exception as e:
        print(f"Error saving to Excel file: {e}")
        return None
        
    print(f"Done! Export completed successfully. Saved to: {output_excel}")
    return output_excel

if __name__ == "__main__":
    export_to_excel()
