import pandas as pd
import time
import re
import os
import shutil
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from difflib import SequenceMatcher
from dotenv import load_dotenv
import sys
import logging
import yaml
from sqlmodel import Field, Session, SQLModel, create_engine, select

# Ensure the root project dir is in sys.path so we can import models.py
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from database.models import GSALink, GSAScrapedData
from database.db import get_engine

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Resolve paths relative to this script's location
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)

EXCEL_FILE = os.path.join(PROJECT_DIR, "new_requirements", "GSA Advantage Low price.xlsx")
MFR_MAPPING_FILE = os.path.join(PROJECT_DIR, "manufacturer_normalization", "convert_to_root", "original_to_root.csv")


class GSAScrapingAutomation:
    def __init__(self, excel_file_path, manufacturer_mapping_file):
        self.excel_file_path = excel_file_path
        self.manufacturer_mapping_file = manufacturer_mapping_file
        self.driver = None
        self.wait = None
        self.manufacturer_mapping = {}
        # Add caching for performance
        self._manufacturer_normalization_cache = {}

        # Pre-compile regex patterns for better performance
        self._compile_regex_patterns()
        
        self.engine = None
        self._setup_db()

    def _setup_db(self):
        """Initialize database connection"""
        try:
            self.engine = get_engine()
            SQLModel.metadata.create_all(self.engine)
            logger.info("Database connection setup successfully.")
        except Exception as e:
            logger.error(f"Failed to setup database: {str(e)}")
            self.engine = None

    def _compile_regex_patterns(self):
        """Pre-compile regex patterns for better performance"""
        # Price patterns
        self._price_patterns = [
            re.compile(r'\$\s*([\d,]+\.?\d*)', re.IGNORECASE),
            re.compile(r'([\d,]+\.\d{2})\s*EA', re.IGNORECASE),
            re.compile(r'([\d,]+\.\d{2})\s*USD', re.IGNORECASE),
            re.compile(r'price[:\s]*\$?\s*([\d,]+\.?\d*)', re.IGNORECASE),
            re.compile(r'unit[:\s]*\$?\s*([\d,]+\.?\d*)', re.IGNORECASE),
            re.compile(r'each[:\s]*\$?\s*([\d,]+\.?\d*)', re.IGNORECASE),
        ]

        # Contractor patterns
        self._contractor_patterns = [
            re.compile(r'contractor[:\s]*\n([^\n]+?)(?:\n|contract#|Contract#|includes)', re.IGNORECASE | re.MULTILINE),
            re.compile(r'contractor[:\s]*([^\n]+?)(?:\n|contract#|Contract#|includes)', re.IGNORECASE | re.MULTILINE),
            re.compile(r'vendor[:\s]*\n([^\n]+?)(?:\n|contract#|Contract#|includes)', re.IGNORECASE | re.MULTILINE),
            re.compile(r'supplier[:\s]*\n([^\n]+?)(?:\n|contract#|Contract#|includes)', re.IGNORECASE | re.MULTILINE),
            re.compile(r'company[:\s]*\n([^\n]+?)(?:\n|contract#|Contract#|includes)', re.IGNORECASE | re.MULTILINE),
            re.compile(r'distributor[:\s]*\n([^\n]+?)(?:\n|contract#|Contract#|includes)', re.IGNORECASE | re.MULTILINE),
        ]

        # Manufacturer patterns
        self._manufacturer_patterns = [
            re.compile(r'\bmfr[:\s]*([a-z0-9\s&.,®\-]+)', re.IGNORECASE),
            re.compile(r'\bmanufacturer[:\s]*([a-z0-9\s&.,®\-]+)', re.IGNORECASE),
            re.compile(r'\bmfg[:\s]*([a-z0-9\s&.,®\-]+)', re.IGNORECASE),
            re.compile(r'\bbrand[:\s]*([a-z0-9\s&.,®\-]+)', re.IGNORECASE)
        ]

        # Unit patterns - used as fallback only; primary extraction is line-based
        # Pattern: price/unit with slash e.g. "$80.00/EA"
        self._unit_slash_pattern = re.compile(
            r'\$\s*[\d,]+\.?\d*\s*/\s*([A-Za-z]{1,4})\b', re.IGNORECASE
        )
        # Pattern: strict labeled UOM field e.g. "uom: EA"
        self._unit_uom_pattern = re.compile(
            r'\buom\b\s*:\s*([A-Za-z]{1,4})\b', re.IGNORECASE
        )
        # Pattern: strict labeled unit field with colon e.g. "unit: EA"
        # Requires colon to avoid matching "united", "unit size", "unit price"
        self._unit_label_pattern = re.compile(
            r'\bunit\s*:\s*([A-Za-z]{1,4})\b', re.IGNORECASE
        )
        # Pattern: price followed immediately by a short abbreviation on the same line
        # e.g. "$ 80.00 EA" — the primary GSA Advantage display format
        self._unit_price_inline_pattern = re.compile(
            r'\$\s*[\d,]+\.?\d*\s+([A-Za-z]{2,4})\b'
        )

    def setup_driver(self):
        """Initialize Chrome driver with optimized options for speed"""
        chrome_options = Options()
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-plugins")
        chrome_options.add_argument("--disable-images")
        chrome_options.add_argument("--disable-web-security")
        chrome_options.add_argument("--disable-features=VizDisplayCompositor")
        chrome_options.add_argument("--disable-background-timer-throttling")
        chrome_options.add_argument("--disable-backgrounding-occluded-windows")
        chrome_options.add_argument("--disable-renderer-backgrounding")
        chrome_options.add_argument("--disable-background-networking")
        chrome_options.add_argument("--disable-sync")
        chrome_options.add_argument("--disable-translate")
        chrome_options.add_argument("--disable-ipc-flooding-protection")
        chrome_options.add_argument("--memory-pressure-off")
        chrome_options.add_argument("--max_old_space_size=4096")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        chrome_options.add_experimental_option("prefs", {
            "profile.default_content_setting_values": {
                "images": 2,
                "plugins": 2,
                "popups": 2,
                "geolocation": 2,
                "notifications": 2,
                "media_stream": 2,
            }
        })

        self.driver = webdriver.Chrome(options=chrome_options)
        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        self.wait = WebDriverWait(self.driver, 15)

    def load_manufacturer_mapping(self):
        """Load manufacturer root form mapping from CSV"""
        try:
            df_mapping = pd.read_csv(self.manufacturer_mapping_file)
            self.manufacturer_mapping = dict(zip(df_mapping['original'], df_mapping['root']))

            # Build a normalized-key mapping to handle punctuation/symbol variants
            self._normalized_manufacturer_lookup = {}
            for original, root in zip(df_mapping['original'], df_mapping['root']):
                norm_key = self.normalize_manufacturer(str(original))
                if norm_key:
                    self._normalized_manufacturer_lookup[norm_key] = root

            logger.info(f"Loaded {len(self.manufacturer_mapping)} manufacturer mappings")
            return True
        except Exception as e:
            logger.error(f"Error loading manufacturer mapping: {str(e)}")
            return False

    def normalize_manufacturer(self, manufacturer_name):
        """Normalize manufacturer name using root form logic with caching"""
        if not manufacturer_name:
            return ""

        if manufacturer_name in self._manufacturer_normalization_cache:
            return self._manufacturer_normalization_cache[manufacturer_name]

        result = self._normalize_to_root_like(manufacturer_name)
        self._manufacturer_normalization_cache[manufacturer_name] = result
        return result

    def _normalize_to_root_like(self, name):
        """Convert manufacturer name to root-like form (same logic as Step 2)"""
        if not name:
            return ""

        REMOVABLE_TERMS = {
            "inc", "incorporated", "corp", "corporation", "co", "company", "llc", "l.l.c",
            "ltd", "limited", "gmbh", "s.a.", "s.a", "s.p.a.", "spa", "ag", "kg", "nv",
            "plc", "pty", "pte", "sro", "s.r.o", "srl", "lp", "llp", "pc",
            "products", "product", "brands", "brand", "group", "international", "industries",
            "industry", "mfg", "manufacturing", "manufacturers", "division", "div",
            "usa", "u.s.a", "u.s.", "us", "america", "american", "north", "south",
            "europe", "european", "asia", "pacific",
        }

        lower = name.lower()
        tokens = re.sub(r"[^0-9a-z]+", " ", lower).split()

        filtered = [t for t in tokens if t not in REMOVABLE_TERMS]

        if filtered:
            chosen = filtered[0]
        else:
            alnum_runs = re.findall(r"[0-9a-z]+", lower)
            chosen = alnum_runs[0] if alnum_runs else ""

        return re.sub(r"[^0-9a-z]", "", chosen)

    def fuzzy_match_manufacturer(self, original_manufacturer, website_manufacturer, threshold=0.85):
        """Match manufacturer name using CSV mapping + normalization + fuzzy logic"""
        if not original_manufacturer or not website_manufacturer:
            return False

        # Strategy 1: CSV mapping - most reliable
        root_form = self.manufacturer_mapping.get(original_manufacturer)
        if root_form:
            website_alnum = re.sub(r"[^a-z0-9]", "", str(website_manufacturer).lower())
            if website_alnum and root_form in website_alnum:
                return True

            norm_website = self.normalize_manufacturer(website_manufacturer)
            if norm_website:
                if root_form in norm_website:
                    return True
                sim_root = SequenceMatcher(None, root_form, norm_website).ratio()
                if sim_root >= threshold:
                    return True

            # Containment check after stripping common suffixes
            original_clean = re.sub(
                r'\s+(inc|incorporated|corp|corporation|co|company|llc|ltd|limited|products|product|brands|brand)$',
                '', original_manufacturer.lower()
            )
            original_normalized = re.sub(r'[-\s]+', ' ', original_clean)
            website_normalized = re.sub(r'[-\s]+', ' ', website_manufacturer.lower())
            if original_normalized in website_normalized:
                return True

        # Strategy 2: Normalized-key mapping
        if not root_form:
            norm_key = self.normalize_manufacturer(original_manufacturer)
            if hasattr(self, '_normalized_manufacturer_lookup'):
                root_form = self._normalized_manufacturer_lookup.get(norm_key)
                if root_form:
                    website_alnum = re.sub(r"[^a-z0-9]", "", str(website_manufacturer).lower())
                    if website_alnum and root_form in website_alnum:
                        return True
                    norm_website = self.normalize_manufacturer(website_manufacturer)
                    if norm_website and root_form in norm_website:
                        return True

        # Strategy 3: Direct normalization comparison (fallback)
        norm_original = self.normalize_manufacturer(original_manufacturer)
        norm_website = self.normalize_manufacturer(website_manufacturer)

        if norm_original and norm_website:
            if len(norm_original) >= 3 and len(norm_website) >= 3:
                if norm_original in norm_website or norm_website in norm_original:
                    return True

            sim_direct = SequenceMatcher(None, norm_original, norm_website).ratio()
            required_threshold = threshold if len(norm_original) >= 4 and len(norm_website) >= 4 else 0.95
            if not (norm_original == norm_website and len(norm_original) <= 2):
                if sim_direct >= required_threshold:
                    return True

        return False

    def read_excel_data(self):
        """Read Excel file with GSA links"""
        try:
            df = pd.read_excel(self.excel_file_path)
            logger.info(f"Excel file loaded. Columns: {list(df.columns)}")

            # Find required columns
            column_mapping = {'manufacturer': None, 'part_number': None}

            for col in df.columns:
                col_lower = col.strip().lower()
                if col_lower == 'manufacturer':
                    column_mapping['manufacturer'] = col
                elif col_lower == 'part_number':
                    column_mapping['part_number'] = col

            missing = [k for k, v in column_mapping.items() if v is None]
            if missing:
                logger.error(f"Missing required columns: {missing}")
                return None, None

            # Ensure output columns exist and are string-compatible
            output_cols = [
                '1 GSA Low Price', 'Unit', 'Contractor:Name',
                '2 GSA Low Price', 'Unit.1', 'Contractor:Name.1'
            ]
            for col in output_cols:
                if col not in df.columns:
                    df[col] = ''
                else:
                    df[col] = df[col].astype(object)

            logger.info(f"Found {len(df)} rows to process")
            return df, column_mapping

        except Exception as e:
            logger.error(f"Error reading Excel file: {str(e)}")
            return None, None

    def scrape_gsa_page(self, gsa_url, target_manufacturer):
        """Scrape GSA page and return top 2 products matching the manufacturer"""
        try:
            if not self.driver:
                logger.error("Driver is not initialized!")
                return []

            logger.info(f"Scraping: {gsa_url}")
            self.driver.get(gsa_url)

            # Wait for page load
            try:
                WebDriverWait(self.driver, 8).until(
                    lambda d: d.execute_script("return document.readyState") == "complete"
                )
            except TimeoutException:
                logger.warning("Page readyState timeout, continuing anyway")

            time.sleep(2)

            # Wait for product elements
            def any_product_present(driver):
                for sel_type, sel_val in [
                    (By.CSS_SELECTOR, ".productViewControl"),
                    (By.CSS_SELECTOR, "app-ux-product-display-inline"),
                    (By.CSS_SELECTOR, ".product-item"),
                    (By.CSS_SELECTOR, ".result-item"),
                ]:
                    try:
                        if driver.find_elements(sel_type, sel_val):
                            return True
                    except:
                        continue
                return False

            try:
                WebDriverWait(self.driver, 5).until(any_product_present)
            except TimeoutException:
                logger.warning("No product elements found within 10 seconds")

            # First pass without scrolling
            products = self._find_product_elements()
            if not products:
                logger.warning(f"No products found: {gsa_url}")
                return []

            initial_matches = self._extract_and_filter_products(products, target_manufacturer)

            if len(initial_matches) >= 2:
                return initial_matches[:2]

            # Smart scroll if not enough matches
            if len(initial_matches) > 0:
                self._smart_scroll_to_load_more_products()
                products = self._find_product_elements()
                final_matches = self._extract_and_filter_products(products, target_manufacturer)
                return final_matches[:2]
            else:
                self._scroll_to_load_all_products()
                products = self._find_product_elements()
                final_matches = self._extract_and_filter_products(products, target_manufacturer)
                return final_matches[:2]

        except Exception as e:
            logger.error(f"Error scraping {gsa_url}: {str(e)}")
            return []

    def _smart_scroll_to_load_more_products(self):
        """Smart scroll - load more products"""
        try:
            last_height = self.driver.execute_script("return document.body.scrollHeight")
            for _ in range(5):
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
                new_height = self.driver.execute_script("return document.body.scrollHeight")
                if new_height == last_height:
                    break
                last_height = new_height
            self.driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(1)
        except Exception as e:
            logger.warning(f"Error during smart scrolling: {str(e)}")

    def _scroll_to_load_all_products(self):
        """Full scroll to load all products"""
        try:
            last_height = self.driver.execute_script("return document.body.scrollHeight")
            for _ in range(8):
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
                new_height = self.driver.execute_script("return document.body.scrollHeight")
                if new_height == last_height:
                    break
                last_height = new_height
            self.driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(1)
        except Exception as e:
            logger.warning(f"Error during full scrolling: {str(e)}")

    def _extract_and_filter_products(self, products, target_manufacturer):
        """Extract product info and filter by manufacturer match only"""
        # Skip header row if present
        start_index = 0
        if products:
            first_text = products[0].text.lower()
            if any(h in first_text for h in ['name contract number price', 'price low to high', 'view as grid', 'sort by']):
                start_index = 1

        all_products_info = []
        for i in range(start_index, len(products)):
            try:
                product_info = self._extract_product_info(products[i], i + 1, target_manufacturer)
                if product_info and (product_info.get('price') is not None or product_info.get('contractor') is not None):
                    # Skip header-like entries
                    contractor = product_info.get('contractor', '') or ''
                    if any(h in contractor.lower() for h in ['name contract', 'price low', 'view as', 'sort by']):
                        continue
                    all_products_info.append(product_info)
            except Exception as e:
                logger.warning(f"Error extracting product {i + 1}: {str(e)}")

        # Filter by manufacturer match only
        matching = []
        for product in all_products_info:
            if product.get('manufacturer_match', False):
                matching.append(product)
                logger.info(f"MATCHED Product {product['product_num']}: Price={product['price']}, "
                            f"Unit={product.get('unit')}, Contractor={product['contractor']}, "
                            f"Mfr={product.get('website_manufacturer')}")
            else:
                logger.debug(f"REJECTED Product {product['product_num']}: "
                             f"Mfr mismatch (target='{target_manufacturer}', "
                             f"found='{product.get('website_manufacturer')}')")

        return matching

    def _find_product_elements(self):
        """Find product elements on the GSA page"""
        product_selectors = [
            (By.CSS_SELECTOR, ".productViewControl"),
            (By.CSS_SELECTOR, "app-ux-product-display-inline"),
            (By.CSS_SELECTOR, ".product-item"),
            (By.CSS_SELECTOR, ".result-item"),
            (By.CSS_SELECTOR, ".product"),
            (By.CSS_SELECTOR, "[class*='product']"),
            (By.CSS_SELECTOR, "[class*='result']"),
            (By.XPATH, "//div[contains(@class, 'product')]"),
            (By.XPATH, "//div[contains(@class, 'result')]"),
            (By.XPATH, "//div[contains(@class, 'item')]"),
            (By.XPATH, "//tr[contains(@class, 'product')]"),
        ]
        for sel_type, sel_val in product_selectors:
            try:
                elements = self.driver.find_elements(sel_type, sel_val)
                if elements:
                    logger.info(f"Found {len(elements)} products with: {sel_type}={sel_val}")
                    return elements
            except:
                continue
        logger.warning("No product elements found with any selector")
        return []

    def _extract_product_info(self, product_element, product_num, target_manufacturer):
        """Extract price, unit, contractor and manufacturer from a product element"""
        try:
            product_text = product_element.text.lower()

            price = self._extract_price(product_text)
            unit = self._extract_unit(product_text)
            contractor = self._extract_contractor(product_text)
            website_manufacturer = self._extract_manufacturer(product_text)

            manufacturer_match = self.fuzzy_match_manufacturer(target_manufacturer, website_manufacturer)

            return {
                'product_num': product_num,
                'price': price,
                'unit': unit,
                'contractor': contractor,
                'manufacturer_match': manufacturer_match,
                'website_manufacturer': website_manufacturer,
                'raw_text': product_element.text[:200]
            }

        except Exception as e:
            logger.error(f"Error extracting product info: {str(e)}")
            return None

    def _extract_price(self, text):
        """Extract price from product text"""
        for pattern in self._price_patterns:
            matches = pattern.findall(text)
            if matches:
                try:
                    return float(matches[0].replace(',', '').strip())
                except:
                    continue
        return None

    def _extract_unit(self, text):
        """Extract unit of measure from product text.

        Strategy: find the line that contains the price, then extract the
        abbreviation that immediately follows the price on that same line.
        GSA Advantage consistently shows prices as "$ 80.00 EA" where the
        unit is the only token after the price on that line.  Fall back to
        labeled UOM/unit fields if no price line is found.
        """
        price_present = re.compile(r'\$\s*[\d,]+\.?\d*')

        # --- Step 1: scan line-by-line for the price line ---
        for line in text.splitlines():
            line = line.strip()
            if not line or not price_present.search(line):
                continue

            # Try "$ 80.00 EA" — unit directly after the price
            m = self._unit_price_inline_pattern.search(line)
            if m:
                unit = m.group(1).upper()
                # Accept 2-4 char abbreviations; reject if the whole line after
                # the price is just a continuation of a longer word (word
                # boundary already guaranteed by the pattern)
                if 2 <= len(unit) <= 4:
                    return unit

            # Try "$80.00/EA" — slash-separated unit
            m = self._unit_slash_pattern.search(line)
            if m:
                unit = m.group(1).upper()
                if 1 <= len(unit) <= 4:
                    return unit

        # --- Step 2: labeled UOM/unit fields anywhere in the text ---
        m = self._unit_uom_pattern.search(text)
        if m:
            unit = m.group(1).upper()
            if 1 <= len(unit) <= 4:
                return unit

        m = self._unit_label_pattern.search(text)
        if m:
            unit = m.group(1).upper()
            if 1 <= len(unit) <= 4:
                return unit

        return None

    def _extract_contractor(self, text):
        """Extract contractor name from product text"""
        for pattern in self._contractor_patterns:
            matches = pattern.findall(text)
            if matches:
                contractor = matches[0].strip()
                contractor = re.sub(r'\s+', ' ', contractor)
                contractor = re.sub(r'\s+contract\s*$', '', contractor, flags=re.IGNORECASE)
                contractor = re.sub(r'\s+includes\s*$', '', contractor, flags=re.IGNORECASE)
                contractor = re.sub(r'\s+inc\.?\s*$', ' Inc.', contractor, flags=re.IGNORECASE)
                contractor = re.sub(r'\s+llc\s*$', ' LLC', contractor, flags=re.IGNORECASE)
                contractor = re.sub(r'\s+corp\.?\s*$', ' Corp.', contractor, flags=re.IGNORECASE)
                return contractor.title()
        return None

    def _extract_manufacturer(self, text):
        """Extract manufacturer name from product text"""
        for pattern in self._manufacturer_patterns:
            m = pattern.search(text)
            if m:
                value = m.group(1).strip()
                return re.sub(r'\s+', ' ', value)
        return None

    def save_results_to_db(self, part_number, products_data):
        """Save scraped results to PostgreSQL DB via SQLModel"""
        try:
            val_1 = products_data[0] if len(products_data) > 0 else {}
            val_2 = products_data[1] if len(products_data) > 1 else {}
            
            with Session(self.engine) as session:
                # Check if it already exists to upsert
                statement = select(GSAScrapedData).where(GSAScrapedData.part_number == str(part_number))
                rec = session.exec(statement).first()
                
                if rec:
                    rec.gsa_low_price_1 = val_1.get('price')
                    rec.unit_1 = val_1.get('unit')
                    rec.contractor_1 = val_1.get('contractor')
                    rec.gsa_low_price_2 = val_2.get('price')
                    rec.unit_2 = val_2.get('unit')
                    rec.contractor_2 = val_2.get('contractor')
                    rec.created_at = datetime.utcnow()
                else:
                    rec = GSAScrapedData(
                        part_number=str(part_number),
                        gsa_low_price_1=val_1.get('price'),
                        unit_1=val_1.get('unit'),
                        contractor_1=val_1.get('contractor'),
                        gsa_low_price_2=val_2.get('price'),
                        unit_2=val_2.get('unit'),
                        contractor_2=val_2.get('contractor')
                    )
                    session.add(rec)
                    
                session.commit()
            
            logger.info(f"Saved {len(products_data)} products to DB for {part_number}")
            return True
        except Exception as e:
            logger.error(f"Error saving to DB for {part_number}: {str(e)}")
            return False

    def identify_missing_rows(self, df):
        """Identify rows where GSA scraped data is missing"""
        missing_rows = []
        for i, row in df.iterrows():
            part_number = row.get('Part Number') or row.get('part_number', '')
            if not part_number:
                continue
                
            with Session(self.engine) as session:
                statement = select(GSAScrapedData).where(GSAScrapedData.part_number == str(part_number))
                rec = session.exec(statement).first()
                if not rec:
                    missing_rows.append(i)
                    
        return missing_rows

    # ─────────────────────────────────────────────────────────────────
    # Run modes
    # ─────────────────────────────────────────────────────────────────

    def run_scraping_test_mode(self, item_limit=3):
        """Test with the first N rows"""
        try:
            if not self.load_manufacturer_mapping():
                return False

            df, column_mapping = self.read_excel_data()
            if df is None:
                return False

            self.setup_driver()
            successful = 0
            start_time = time.time()

            for i, row in df.head(item_limit).iterrows():
                try:
                    manufacturer = row[column_mapping['manufacturer']]
                    part_number = row[column_mapping['part_number']]

                    # Fetch link and flag from DB
                    with Session(self.engine) as session:
                        statement = select(GSALink).where(GSALink.part_number == str(part_number))
                        link_record = session.exec(statement).first()

                    if not link_record or not link_record.gsa_link:
                        logger.warning(f"Row {i + 1}: No DB URL for {part_number}")
                        continue
                        
                    if link_record.is_scraped:
                        logger.info(f"Row {i + 1}: Skipping {part_number} (already scraped)")
                        continue

                    gsa_url = link_record.gsa_link
                    print(f"\nTest {i + 1}/{item_limit} - {part_number} | Mfr: {manufacturer}")
                    t0 = time.time()

                    products_data = self.scrape_gsa_page(gsa_url, manufacturer)

                    if products_data:
                        successful += 1
                        self.save_results_to_db(part_number, products_data)
                        print(f"  SUCCESS: {len(products_data)} products ({time.time()-t0:.1f}s)")
                    else:
                        print(f"  WARNING: No matches found ({time.time()-t0:.1f}s)")

                    # Mark as scraped in DB
                    with Session(self.engine) as session:
                        statement = select(GSALink).where(GSALink.part_number == str(part_number))
                        rec = session.exec(statement).first()
                        if rec:
                            rec.is_scraped = True
                            session.add(rec)
                            session.commit()

                    time.sleep(1)

                except Exception as e:
                    logger.error(f"Error on row {i + 1}: {str(e)}")

            print(f"\nTest complete. {successful}/{item_limit} successful in {time.time()-start_time:.1f}s")
            return True

        except Exception as e:
            logger.error(f"Test mode error: {str(e)}")
            return False
        finally:
            if self.driver:
                self.driver.quit()

    def run_scraping_full(self):
        """Full automation - process all rows"""
        try:
            if not self.load_manufacturer_mapping():
                return False

            df, column_mapping = self.read_excel_data()
            if df is None:
                return False

            self.setup_driver()
            successful = 0
            start_time = time.time()

            for i, row in df.iterrows():
                try:
                    manufacturer = row[column_mapping['manufacturer']]
                    part_number = row[column_mapping['part_number']]

                    # Fetch link from DB
                    with Session(self.engine) as session:
                        statement = select(GSALink).where(GSALink.part_number == str(part_number))
                        link_record = session.exec(statement).first()

                    if not link_record or not link_record.gsa_link:
                        logger.warning(f"Row {i + 1}: No URL in DB for {part_number}")
                        continue
                        
                    if link_record.is_scraped:
                        logger.info(f"Row {i + 1}: Skipping {part_number} (already scraped)")
                        continue
                        
                    gsa_url = link_record.gsa_link

                    print(f"\nProgress: {i + 1}/{len(df)} ({(i+1)/len(df)*100:.1f}%) - {part_number}")
                    t0 = time.time()

                    products_data = self.scrape_gsa_page(gsa_url, manufacturer)
                    elapsed = time.time() - t0

                    if products_data:
                        successful += 1
                        self.save_results_to_db(part_number, products_data)
                        print(f"  SUCCESS: {len(products_data)} products ({elapsed:.1f}s)")
                    else:
                        print(f"  WARNING: No matches ({elapsed:.1f}s)")
                        
                    # Mark as scraped in DB
                    with Session(self.engine) as session:
                        statement = select(GSALink).where(GSALink.part_number == str(part_number))
                        rec = session.exec(statement).first()
                        if rec:
                            rec.is_scraped = True
                            session.add(rec)
                            session.commit()

                    total_elapsed = time.time() - start_time
                    avg = total_elapsed / (i + 1)
                    eta_h = (len(df) - i - 1) * avg / 3600
                    print(f"  Avg: {avg:.1f}s/row | ETA: {eta_h:.1f}h")

                except Exception as e:
                    logger.error(f"Error on row {i + 1}: {str(e)}")

            total_time = time.time() - start_time
            print(f"\nDone! {successful}/{len(df)} successful in {total_time/60:.1f} min")
            return True

        except Exception as e:
            logger.error(f"Full run error: {str(e)}")
            return False
        finally:
            if self.driver:
                self.driver.quit()

    def run_scraping_custom_range(self, start_row: int, end_row: int):
        """Process a specific row range (1-based, inclusive)"""
        try:
            if not self.load_manufacturer_mapping():
                return False

            df, column_mapping = self.read_excel_data()
            if df is None:
                return False

            # Convert to 0-based index and clamp
            start_idx = max(0, start_row - 1)
            end_idx = min(len(df) - 1, end_row - 1)
            if start_idx > end_idx:
                logger.error(f"Invalid range: {start_row}-{end_row}")
                return False

            self.setup_driver()
            successful = 0
            start_time = time.time()
            total = end_idx - start_idx + 1

            for offset, i in enumerate(range(start_idx, end_idx + 1), 1):
                try:
                    row = df.iloc[i]
                    manufacturer = df.at[i, column_mapping['manufacturer']]
                    part_number = df.at[i, column_mapping['part_number']]

                    with Session(self.engine) as session:
                        statement = select(GSALink).where(GSALink.part_number == str(part_number))
                        link_record = session.exec(statement).first()

                    if not link_record or not link_record.gsa_link:
                        logger.warning(f"Row {i + 1}: No URL in DB for {part_number}")
                        continue
                        
                    if link_record.is_scraped:
                        logger.info(f"Row {i + 1}: Skipping {part_number} (already scraped)")
                        continue

                    gsa_url = link_record.gsa_link

                    print(f"\nProgress: {offset}/{total} (Row {i + 1}) - {part_number}")
                    t0 = time.time()

                    products_data = self.scrape_gsa_page(gsa_url, manufacturer)
                    elapsed = time.time() - t0

                    if products_data:
                        successful += 1
                        self.save_results_to_db(part_number, products_data)
                        print(f"  SUCCESS: {len(products_data)} products ({elapsed:.1f}s)")
                    else:
                        print(f"  WARNING: No matches ({elapsed:.1f}s)")
                        
                    with Session(self.engine) as session:
                        statement = select(GSALink).where(GSALink.part_number == str(part_number))
                        rec = session.exec(statement).first()
                        if rec:
                            rec.is_scraped = True
                            session.add(rec)
                            session.commit()

                    total_elapsed = time.time() - start_time
                    avg = total_elapsed / offset
                    eta_h = (total - offset) * avg / 3600
                    print(f"  Avg: {avg:.1f}s/row | ETA: {eta_h:.1f}h")

                except Exception as e:
                    logger.error(f"Error on row {i + 1}: {str(e)}")

            total_time = time.time() - start_time
            print(f"\nDone! Rows {start_row}-{end_row}: {successful}/{total} successful in {total_time/60:.1f} min")
            return True

        except Exception as e:
            logger.error(f"Custom range error: {str(e)}")
            return False
        finally:
            if self.driver:
                self.driver.quit()

    def run_scraping_missing_only(self):
        """Scrape only rows where all output columns are empty"""
        try:
            if not self.load_manufacturer_mapping():
                return False

            df, column_mapping = self.read_excel_data()
            if df is None:
                return False

            missing_rows = self.identify_missing_rows(df)
            print(f"Found {len(missing_rows)} rows with missing data")

            if not missing_rows:
                print("All rows already have data!")
                return True

            start_from = input("Start from which row index? (0 for all, or enter row number): ").strip()
            if start_from.isdigit():
                start_from = int(start_from)
                missing_rows = [r for r in missing_rows if r >= start_from]
                print(f"Filtered to {len(missing_rows)} missing rows from row {start_from + 1}")

            self.setup_driver()
            successful = 0
            start_time = time.time()
            total = len(missing_rows)

            for offset, i in enumerate(missing_rows, 1):
                try:
                    manufacturer = df.at[i, column_mapping['manufacturer']]
                    part_number = df.at[i, column_mapping['part_number']]

                    # Fetch link from DB
                    with Session(self.engine) as session:
                        statement = select(GSALink).where(GSALink.part_number == str(part_number))
                        link_record = session.exec(statement).first()

                    if not link_record or not link_record.gsa_link:
                        logger.warning(f"Row {i + 1}: No DB URL for {part_number}")
                        continue
                        
                    if link_record.is_scraped:
                        logger.info(f"Row {i + 1}: Skipping {part_number} (already scraped)")
                        continue

                    gsa_url = link_record.gsa_link
                    
                    print(f"\nMissing {offset}/{total} (Row {i + 1}) - {part_number}")
                    t0 = time.time()

                    products_data = self.scrape_gsa_page(gsa_url, manufacturer)
                    elapsed = time.time() - t0

                    if products_data:
                        successful += 1
                        self.save_results_to_db(part_number, products_data)
                        print(f"  SUCCESS: {len(products_data)} products ({elapsed:.1f}s)")
                    else:
                        print(f"  WARNING: No matches ({elapsed:.1f}s)")

                    with Session(self.engine) as session:
                        statement = select(GSALink).where(GSALink.part_number == str(part_number))
                        rec = session.exec(statement).first()
                        if rec:
                            rec.is_scraped = True
                            session.add(rec)
                            session.commit()

                    total_elapsed = time.time() - start_time
                    avg = total_elapsed / offset
                    eta_h = (total - offset) * avg / 3600
                    print(f"  Avg: {avg:.1f}s/row | ETA: {eta_h:.1f}h")

                except Exception as e:
                    logger.error(f"Error on row {i + 1}: {str(e)}")

            total_time = time.time() - start_time
            print(f"\nDone! {successful}/{total} missing rows filled in {total_time/60:.1f} min")
            return True

        except Exception as e:
            logger.error(f"Missing-only error: {str(e)}")
            return False
        finally:
            if self.driver:
                self.driver.quit()


def main():
    print("\n" + "=" * 60)
    print("GSA SCRAPING AUTOMATION")
    print("=" * 60)
    print(f"Input:        GSA Advantage Low price.xlsx")
    print(f"Match by:     Manufacturer Name")
    print(f"Output:       PostgreSQL DB (gsa_scraped_data table)")
    print("=" * 60)

    automation = GSAScrapingAutomation(EXCEL_FILE, MFR_MAPPING_FILE)

    while True:
        print("\nChoose automation mode:")
        print("1. Test mode (first 3 rows)")
        print("2. Full automation (all rows)")
        print("3. Custom range (specific rows)")
        print("4. Missing rows only")
        print("5. Exit")

        choice = input("\nEnter your choice (1-5): ").strip()

        if choice == '5':
            print("Goodbye!")
            break
        elif choice == '1':
            print("\nRunning test mode (first 3 rows)...")
            success = automation.run_scraping_test_mode(3)
        elif choice == '2':
            confirm = input("Process all rows? (y/n): ").strip().lower()
            if confirm in ('y', 'yes'):
                success = automation.run_scraping_full()
            else:
                print("Cancelled.")
                continue
        elif choice == '3':
            try:
                start_row = int(input("Start row (1-based): "))
                end_row = int(input("End row (1-based): "))
                if start_row < 1 or end_row < start_row:
                    print("Invalid range.")
                    continue
                success = automation.run_scraping_custom_range(start_row, end_row)
            except ValueError:
                print("Please enter valid numbers.")
                continue
        elif choice == '4':
            success = automation.run_scraping_missing_only()
        else:
            print("Invalid choice.")
            continue

        if success:
            print("\nAutomation completed successfully!")
        else:
            print("\nAutomation failed. Check logs for details.")

        again = input("\nRun another? (y/n): ").strip().lower()
        if again not in ('y', 'yes'):
            print("Goodbye!")
            break


if __name__ == "__main__":
    main()
