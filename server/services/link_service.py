import pandas as pd
import time
import os
from dotenv import load_dotenv
import shutil
from datetime import datetime
import logging
from sqlmodel import Field, Session, SQLModel, create_engine, select
import sys
import yaml

# Ensure the root project dir is in sys.path so we can import models.py
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from database.models import GSALink
from database.db import get_engine
from database.repository import upsert_link

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
class GSALinkAutomationFast:
    def __init__(self, excel_file_path):
        self.excel_file_path = excel_file_path
        
        # Load config
        config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config.yml')
        with open(config_path, 'r') as file:
            config = yaml.safe_load(file)
            
        self.base_url = config['gsa_urls']['base_url']
        self.url_template = config['gsa_urls']['url_template']
        self._setup_db()
        self.stop_requested = False

    def stop(self):
        """Signal the automation to stop as soon as possible"""
        self.stop_requested = True
        logger.info("Stop signal received. Finishing current task...")
        
    def _setup_db(self):
        """Initialize database connection"""
        try:
            self.engine = get_engine()
            
            # Create table if it doesn't exist
            SQLModel.metadata.create_all(self.engine)
            
            logger.info("Database connection setup successfully.")
        except Exception as e:
            logger.error(f"Failed to setup database: {str(e)}")
            self.engine = None

    def read_excel_data(self):
        """Read Excel file and extract part_number column"""
        try:
            df = pd.read_excel(self.excel_file_path)
            logger.info(f"Excel file loaded successfully. Columns: {list(df.columns)}")

            # Look for part_number column (case insensitive)
            part_number_column = None
            for col in df.columns:
                if col.strip().lower() == 'part_number':
                    part_number_column = col
                    break

            if part_number_column is None:
                logger.error("Could not find 'part_number' column in the Excel file")
                return None, None

            # Extract non-null values from the column
            part_numbers = df[part_number_column].dropna().astype(str).tolist()
            logger.info(f"Found {len(part_numbers)} part numbers to process")

            # Ensure Links column exists and is string-compatible
            if 'Links' not in df.columns:
                df['Links'] = ''
                logger.info("Added 'Links' column to Excel")
            else:
                df['Links'] = df['Links'].astype(object)

            return df, part_number_column

        except Exception as e:
            logger.error(f"Error reading Excel file: {str(e)}")
            return None, None

    def construct_gsa_url(self, part_number):
        """Construct GSA Advantage search URL directly"""
        try:
            # Clean the part number (remove any extra spaces or characters)
            clean_part_number = str(part_number).strip()

            # Construct the URL using the pattern
            query_part = self.url_template.format(part_number=clean_part_number)
            full_url = self.base_url + query_part

            return full_url

        except Exception as e:
            logger.error(f"Error constructing URL for {part_number}: {str(e)}")
            return None
    
    def create_backup(self, file_path):
        """Create a timestamped backup of the file"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = f"{file_path}.backup_{timestamp}"
            shutil.copy2(file_path, backup_path)
            logger.info(f"Backup created: {backup_path}")
            return backup_path
        except Exception as e:
            logger.error(f"Error creating backup: {str(e)}")
            return None
    
    def validate_excel_file(self, file_path):
        """Validate that the Excel file can be read and has expected structure"""
        try:
            # Try to read the file
            test_df = pd.read_excel(file_path)

            # Check if it has the expected columns
            required_columns = ['part_number', 'Links']
            missing_columns = [col for col in required_columns if col not in test_df.columns]
            
            if missing_columns:
                logger.error(f"Missing required columns: {missing_columns}")
                return False
            
            # Check if the file has data
            if len(test_df) == 0:
                logger.error("Excel file is empty")
                return False
            
            logger.info(f"Excel file validation successful: {len(test_df)} rows, {len(test_df.columns)} columns")
            return True
            
        except Exception as e:
            logger.error(f"Excel file validation failed: {str(e)}")
            return False
    
    def save_results_to_excel(self, df):
        """Save the updated dataframe to Excel file with backup and validation"""
        script_dir = os.path.dirname(os.path.abspath(__file__))
        output_file = os.path.join(script_dir, "GSA Advantage Low price_with_gsa_links.xlsx")
        temp_file = f"{output_file}.temp.xlsx"
        
        try:
            # Step 1: Create backup of existing file if it exists
            if os.path.exists(output_file):
                backup_path = self.create_backup(output_file)
                if not backup_path:
                    logger.warning("Could not create backup, proceeding anyway...")
            
            # Step 2: Save to temporary file first
            logger.info(f"Saving to temporary file: {temp_file}")
            df.to_excel(temp_file, index=False, engine='openpyxl')
            
            # Step 3: Validate the temporary file
            if not self.validate_excel_file(temp_file):
                logger.error("Temporary file validation failed, aborting save")
                if os.path.exists(temp_file):
                    os.remove(temp_file)
                return False
            
            # Step 4: Replace original file with validated temporary file
            if os.path.exists(output_file):
                os.remove(output_file)
            
            shutil.move(temp_file, output_file)
            
            # Step 5: Final validation of the saved file
            if not self.validate_excel_file(output_file):
                logger.error("Final file validation failed!")
                # Try to restore from backup
                backup_files = [f for f in os.listdir('.') if f.startswith(f"{output_file}.backup_")]
                if backup_files:
                    latest_backup = max(backup_files)
                    logger.info(f"Attempting to restore from backup: {latest_backup}")
                    shutil.copy2(latest_backup, output_file)
                    if self.validate_excel_file(output_file):
                        logger.info("Successfully restored from backup")
                        return True
                return False
            
            logger.info(f"Results successfully saved to Excel ({output_file})")
            return True
            
        except Exception as e:
            logger.error(f"Error saving results to Excel: {str(e)}")
            
            # Cleanup temporary file if it exists
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except:
                    pass
            
            # Try to restore from backup if save failed
            try:
                backup_files = [f for f in os.listdir('.') if f.startswith(f"{output_file}.backup_")]
                if backup_files and not os.path.exists(output_file):
                    latest_backup = max(backup_files)
                    logger.info(f"Attempting to restore from backup: {latest_backup}")
                    shutil.copy2(latest_backup, output_file)
                    if self.validate_excel_file(output_file):
                        logger.info("Successfully restored from backup after error")
                        return True
            except Exception as restore_error:
                logger.error(f"Failed to restore from backup: {str(restore_error)}")
            
            return False

    def save_results_to_db(self, part_number, gsa_link):
        """Save a single link to the database using an upsert or skip if None."""
        if not self.engine or not gsa_link:
            return False
        try:
            return upsert_link(self.engine, part_number, gsa_link)
        except Exception as e:
            logger.error(f"Error saving {part_number} to DB: {str(e)}")
            return False

    def _execute_link_loop(self, part_numbers):
        """Core loop: construct and persist GSA URLs for each part number."""
        total = len(part_numbers)
        successful_links = 0
        start_time = time.time()

        for i, part_number in enumerate(part_numbers, 1):
            if self.stop_requested:
                logger.warning("Stop requested. Exiting loop.")
                break

            gsa_url = self.construct_gsa_url(part_number)
            if gsa_url:
                self.save_results_to_db(part_number, gsa_url)
                successful_links += 1

                if i <= 10 or i % 1000 == 0 or i == total:
                    elapsed = time.time() - start_time
                    rate = i / elapsed if elapsed > 0 else 0
                    eta_min = ((total - i) / rate / 60) if rate > 0 else 0
                    logger.info(
                        f"Progress: {i}/{total} ({i/total*100:.1f}%) | "
                        f"Rate: {rate:.1f}/sec | ETA: {eta_min:.1f} min | "
                        f"Part: {part_number}"
                    )
            else:
                logger.error(f"Failed to construct URL for {part_number}")

        total_time = time.time() - start_time
        rate = total / total_time if total_time > 0 else 0
        logger.info(
            f"Link loop complete: {successful_links}/{total} successful | "
            f"{total_time:.1f}s | {rate:.1f} items/sec"
        )
        return successful_links
    
    def cleanup_old_backups(self, keep_last=5):
        """Clean up old backup files, keeping only the most recent ones"""
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            backup_files = [f for f in os.listdir(script_dir) if f.startswith("GSA Advantage Low price_with_gsa_links.xlsx.backup_")]
            backup_files.sort(reverse=True)

            files_to_delete = backup_files[keep_last:]
            for backup_file in files_to_delete:
                try:
                    os.remove(os.path.join(script_dir, backup_file))
                    logger.info(f"Cleaned up old backup: {backup_file}")
                except Exception as e:
                    logger.warning(f"Could not delete backup {backup_file}: {str(e)}")

        except Exception as e:
            logger.warning(f"Error during backup cleanup: {str(e)}")
    
    def run_automation_fast(self):
        """Run link generation for all part numbers."""
        try:
            df, col = self.read_excel_data()
            if df is None:
                logger.error("No data found in Excel file")
                return False
            part_numbers = df[col].dropna().astype(str).tolist()
            logger.info(f"Full mode: processing {len(part_numbers)} part numbers")
            self._execute_link_loop(part_numbers)
            return True
        except Exception as e:
            logger.error(f"Error in full automation: {str(e)}")
            return False

    def run_automation_fast_test_mode(self, item_limit=5):
        """Run link generation for the first item_limit part numbers."""
        try:
            df, col = self.read_excel_data()
            if df is None:
                logger.error("No data found in Excel file")
                return False
            part_numbers = df[col].dropna().astype(str).tolist()[:item_limit]
            logger.info(f"Test mode: processing {len(part_numbers)} part numbers")
            self._execute_link_loop(part_numbers)
            return True
        except Exception as e:
            logger.error(f"Error in test automation: {str(e)}")
            return False

    def run_automation_fast_custom_range(self, start_row, end_row):
        """Run link generation for a 1-based inclusive row range."""
        try:
            df, col = self.read_excel_data()
            if df is None:
                logger.error("No data found in Excel file")
                return False
            all_numbers = df[col].dropna().astype(str).tolist()
            part_numbers = all_numbers[start_row - 1:end_row]
            if not part_numbers:
                logger.error(f"No part numbers in range {start_row}-{end_row}")
                return False
            logger.info(f"Custom range mode: rows {start_row}-{end_row} ({len(part_numbers)} items)")
            self._execute_link_loop(part_numbers)
            return True
        except Exception as e:
            logger.error(f"Error in custom range automation: {str(e)}")
            return False

def main():
    """Main function to run the super-fast automation"""
    import sys
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    from settings import EXCEL_FILE_PATH
    excel_file = EXCEL_FILE_PATH

    while True:
        print("\n" + "="*60)
        print("GSA LINK AUTOMATION - SUPER FAST VERSION")
        print("="*60)
        print("Input:  GSA Advantage Low price.xlsx")
        print("Output: PostgreSQL DB (gsa_links table)")
        print("="*60)
        print("Choose automation mode:")
        print("1. Test mode (first 5 stock numbers)")
        print("2. Full automation (all stock numbers) - SUPER FAST!")
        print("3. Custom range (specific rows) - SUPER FAST!")
        print("4. Exit")
        
        choice = input("\nEnter your choice (1/2/3/4): ").strip()
        
        if choice == '4':
            print("Goodbye! Exiting the program...")
            break
        elif choice in ['1', '2', '3']:
            automation = GSALinkAutomationFast(excel_file)
            
            if choice == '1':
                print("\n[TEST] Running test mode with first 5 stock numbers...")
                success = automation.run_automation_fast_test_mode(5)
            elif choice == '2':
                print("\n[FULL] Running SUPER FAST full automation with all part numbers...")
                print("[INFO] This will process all 18,264 items in approximately 30 minutes!")
                confirm = input("Are you sure you want to proceed? (y/n): ").strip().lower()
                if confirm in ['y', 'yes']:
                    success = automation.run_automation_fast()
                else:
                    print("Operation cancelled.")
                    continue
            elif choice == '3':
                try:
                    start_row = int(input("Enter start row number (1-based): "))
                    end_row = int(input("Enter end row number (1-based): "))
                    
                    if start_row < 1 or end_row < start_row:
                        print("ERROR: Invalid range. Start row must be >= 1 and end row must be >= start row.")
                        continue
                    
                    print(f"\n[RANGE] Running SUPER FAST custom range automation for rows {start_row}-{end_row}...")
                    success = automation.run_automation_fast_custom_range(start_row, end_row)
                except ValueError:
                    print("ERROR: Please enter valid numbers for the range.")
                    continue
            
            if success:
                print("\n[SUCCESS] Super-fast automation completed successfully!")
                print("[SUCCESS] All links generated using direct URL construction!")
            else:
                print("\n[ERROR] Automation failed. Check the logs for details.")
            
            # Ask if user wants to run another automation
            continue_choice = input("\nDo you want to run another automation? (y/n): ").strip().lower()
            if continue_choice not in ['y', 'yes']:
                print("Goodbye! Exiting the program...")
                break
        else:
            print("[ERROR] Invalid choice. Please enter 1, 2, 3, or 4.")

if __name__ == "__main__":
    main()

