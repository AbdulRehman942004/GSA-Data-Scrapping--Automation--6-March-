import pandas as pd
import time
import os
from dotenv import load_dotenv
import shutil
from datetime import datetime
import logging
from sqlmodel import Field, Session, SQLModel, create_engine, select

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

class GSALink(SQLModel, table=True):
    __tablename__ = 'gsa_links'
    part_number: str = Field(primary_key=True)
    gsa_link: str = Field()
    created_at: datetime = Field(default_factory=datetime.utcnow)

class GSALinkAutomationFast:
    def __init__(self, excel_file_path):
        self.excel_file_path = excel_file_path
        self.base_url = "https://www.gsaadvantage.gov/advantage/ws/search/advantage_search"
        self.url_template = "?searchType=1&q=7:1{part_number}&s=6&c=25"
        self._setup_db()
        
    def _setup_db(self):
        """Initialize database connection"""
        try:
            host = os.getenv("POSTGRESQL_HOST", "localhost")
            port = os.getenv("POSTGRESQL_PORT", "5432")
            database = os.getenv("POSTGRESQL_DATABASE", "gsa_data")
            username = os.getenv("POSTGRESQL_USERNAME", "postgres")
            password = os.getenv("POSTGRESQL_PASSWORD", "12345")
            
            db_url = f"postgresql://{username}:{password}@{host}:{port}/{database}"
            self.engine = create_engine(db_url)
            
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
        """Save a single link to the database using an upsert or skip if None"""
        if not self.engine or not gsa_link:
            return False
            
        try:
            with Session(self.engine) as session:
                # Basic upsert (merge)
                statement = select(GSALink).where(GSALink.part_number == part_number)
                link_record = session.exec(statement).first()
                if link_record:
                    link_record.gsa_link = gsa_link
                    link_record.created_at = datetime.utcnow()
                else:
                    link_record = GSALink(part_number=part_number, gsa_link=gsa_link)
                    session.add(link_record)
                
                session.commit()
            return True
        except Exception as e:
            logger.error(f"Error saving {part_number} to DB: {str(e)}")
            return False
    
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
        """Main method to run the super-fast automation"""
        try:
            # Read Excel data
            df, stock_column_name = self.read_excel_data()
            if df is None:
                logger.error("No data found in Excel file")
                return False
            
            part_numbers = df[stock_column_name].dropna().astype(str).tolist()
            logger.info(f"Starting super-fast processing of {len(part_numbers)} part numbers")

            # Process all part numbers
            successful_links = 0
            start_time = time.time()

            for i, part_number in enumerate(part_numbers, 1):
                # Construct the URL directly
                gsa_url = self.construct_gsa_url(part_number)

                if gsa_url:
                    # Update the dataframe with the link
                    df.at[i-1, 'Links'] = gsa_url
                    
                    # Save directly to Postgres
                    self.save_results_to_db(part_number, gsa_url)
                    
                    successful_links += 1

                    # Show progress every 1000 items or for first 10 items
                    if i <= 10 or i % 1000 == 0 or i == len(part_numbers):
                        elapsed_time = time.time() - start_time
                        rate = i / elapsed_time if elapsed_time > 0 else 0
                        eta_seconds = (len(part_numbers) - i) / rate if rate > 0 else 0
                        eta_minutes = eta_seconds / 60

                        print(f"Progress: {i}/{len(part_numbers)} ({i/len(part_numbers)*100:.1f}%) - "
                              f"Rate: {rate:.1f} items/sec - ETA: {eta_minutes:.1f} min - "
                              f"Processing: {part_number}")
                        logger.info(f"Processed {i}/{len(part_numbers)}: {part_number}")

                # Save every 1000 items for safety
                # if i % 1000 == 0:
                #     save_success = self.save_results_to_excel(df)
                #     if not save_success:
                #         logger.error(f"Failed to save results at item {i}")
                #         print(f"ERROR: Failed to save Excel file at item {i}")

            # Final save (Excel fallback)
            # save_success = self.save_results_to_excel(df)
            # if not save_success:
            #     logger.error("Failed to save final results to Excel")
            #     return False

            # Calculate final statistics
            total_time = time.time() - start_time
            rate = len(part_numbers) / total_time if total_time > 0 else 0

            logger.info(f"Super-fast automation completed!")
            logger.info(f"Processed: {len(part_numbers)} part numbers")
            logger.info(f"Successful links: {successful_links}")
            logger.info(f"Total time: {total_time:.1f} seconds ({total_time/60:.1f} minutes)")
            logger.info(f"Processing rate: {rate:.1f} items/second")
            
            # Clean up old backup files
            # self.cleanup_old_backups()
            
            return True
            
        except Exception as e:
            logger.error(f"Error in super-fast automation: {str(e)}")
            return False
    
    def run_automation_fast_test_mode(self, test_count=5):
        """Test method to run super-fast automation with limited items"""
        try:
            # Read Excel data
            df, stock_column_name = self.read_excel_data()
            if df is None:
                logger.error("No data found in Excel file")
                return False
            
            stock_numbers = df[stock_column_name].dropna().astype(str).tolist()
            test_stock_numbers = stock_numbers[:test_count]
            
            logger.info(f"Test mode: Processing {len(test_stock_numbers)} stock numbers")
            
            # Process test stock numbers
            successful_links = 0
            start_time = time.time()
            
            for i, stock_number in enumerate(test_stock_numbers, 1):
                # Construct the URL directly
                gsa_url = self.construct_gsa_url(stock_number)
                
                if gsa_url:
                    # Update the dataframe with the link
                    df.at[i-1, 'Links'] = gsa_url
                    
                    # Save directly to Postgres
                    self.save_results_to_db(stock_number, gsa_url)
                    
                    successful_links += 1
                    print(f"[SUCCESS] {i}/{len(test_stock_numbers)} - {stock_number} -> {gsa_url}")
                    logger.info(f"Processed {i}/{len(test_stock_numbers)}: {stock_number}")
                else:
                    print(f"[FAILED] {i}/{len(test_stock_numbers)} - {stock_number} -> Failed to construct URL")
                    logger.error(f"Failed to construct URL for {stock_number}")
            
            # Calculate final statistics
            total_time = time.time() - start_time
            rate = len(test_stock_numbers) / total_time if total_time > 0 else 0
            
            print(f"\n[DONE] Test completed!")
            print(f"Processed: {len(test_stock_numbers)} stock numbers")
            print(f"Successful links: {successful_links}")
            print(f"Total time: {total_time:.2f} seconds")
            print(f"Processing rate: {rate:.1f} items/second")
            
            logger.info(f"Test automation completed successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error in test automation: {str(e)}")
            return False
    
    def run_automation_fast_custom_range(self, start_row, end_row):
        """Run super-fast automation for a specific range of rows"""
        try:
            # Read Excel data
            df, stock_column_name = self.read_excel_data()
            if df is None:
                logger.error("No data found in Excel file")
                return False
            
            stock_numbers = df[stock_column_name].dropna().astype(str).tolist()
            
            # Take only the specified range of stock numbers (convert to 0-based index)
            start_idx = start_row - 1  # Convert to 0-based index
            end_idx = end_row  # end_row is already 1-based, so we use it as-is
            custom_stock_numbers = stock_numbers[start_idx:end_idx]
            
            if len(custom_stock_numbers) == 0:
                logger.error(f"No stock numbers found in range {start_row}-{end_row}")
                return False
            
            logger.info(f"Custom range mode: Processing rows {start_row}-{end_row} ({len(custom_stock_numbers)} stock numbers)")
            
            # Process custom range stock numbers
            successful_links = 0
            start_time = time.time()
            
            for i, stock_number in enumerate(custom_stock_numbers, 1):
                actual_row = start_row + i - 1  # Calculate actual row number
                
                # Construct the URL directly
                gsa_url = self.construct_gsa_url(stock_number)
                
                if gsa_url:
                    # Update the dataframe with the link
                    df.at[actual_row-1, 'Links'] = gsa_url
                    
                    # Save directly to Postgres
                    self.save_results_to_db(stock_number, gsa_url)
                    
                    successful_links += 1
                    
                    # Show progress every 100 items or for first 10 items
                    if i <= 10 or i % 100 == 0 or i == len(custom_stock_numbers):
                        elapsed_time = time.time() - start_time
                        rate = i / elapsed_time if elapsed_time > 0 else 0
                        eta_seconds = (len(custom_stock_numbers) - i) / rate if rate > 0 else 0
                        eta_minutes = eta_seconds / 60
                        
                        print(f"Progress: {i}/{len(custom_stock_numbers)} (Row {actual_row}) - "
                              f"Rate: {rate:.1f} items/sec - ETA: {eta_minutes:.1f} min - "
                              f"Processing: {stock_number}")
                        logger.info(f"Processing {i}/{len(custom_stock_numbers)} (Row {actual_row}): {stock_number}")
                else:
                    print(f"[FAILED] Row {actual_row} - {stock_number} -> Failed to construct URL")
                    logger.error(f"Failed to construct URL for {stock_number} (Row {actual_row})")
            
            # Calculate final statistics
            total_time = time.time() - start_time
            rate = len(custom_stock_numbers) / total_time if total_time > 0 else 0
            
            logger.info(f"Custom range automation completed!")
            logger.info(f"Processed: {len(custom_stock_numbers)} stock numbers")
            logger.info(f"Successful links: {successful_links}")
            logger.info(f"Total time: {total_time:.1f} seconds ({total_time/60:.1f} minutes)")
            logger.info(f"Processing rate: {rate:.1f} items/second")
            
            return True
            
        except Exception as e:
            logger.error(f"Error in custom range automation: {str(e)}")
            return False

def main():
    """Main function to run the super-fast automation"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    excel_file = os.path.join(script_dir, "..", "new_requirements", "GSA Advantage Low price.xlsx")

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

