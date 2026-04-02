"""
Internal Link Scraper
---------------------
Handles product_detail links from the imported_links table.

Flow for each link (is_product_detail=True):
  1. Open the product detail URL in Chrome.
  2. Click the "Compare Available Sources" button (right side of page).
  3. Inside the compare modal, read the "Currently Selected" section to get:
       - Manufacturer Part Name
       - Manufacturer Part Number
  4. Read all rows from the comparison table.
     - sort_order="low_to_high"  → rows already ascending by price, read top→bottom.
     - sort_order="high_to_low"  → click the Price/Unit header to sort descending,
                                   then read top→bottom.
  5. For each row, extract: price, unit, contractor name.
  6. Click the contractor name link → popup appears with Contract #.
     Scrape the contract number, then close the popup.
  7. Save all rows into links_scraped_data DB table.
  8. Mark the ImportedLink as is_scraped=True.
"""

import logging
import random
import re
import sys
import os
import time
from typing import Optional

from selenium import webdriver
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    NoSuchElementException,
    TimeoutException,
)
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from database.db import get_engine
from database.repository import (
    clear_links_scraped_data_for_link,
    get_all_product_detail_links,
    insert_link_scraped_rows,
    mark_imported_link_scraped,
)
from settings import PAGE_LOAD_TIMEOUT, SCRAPE_DELAY_SECONDS

logger = logging.getLogger(__name__)

# Maximum compare-table rows to scrape per product_detail link
MAX_ROWS_PER_LINK = 6

# ─────────────────────────────────────────────────────────────────────────────
# Selector constants  (multiple fallbacks; first match wins)
# ─────────────────────────────────────────────────────────────────────────────

_COMPARE_BTN_SELECTORS = [
    (By.XPATH, "//*[contains(text(), 'Compare Available Sources')]"),
    (By.XPATH, "//*[contains(text(), 'Compare Sources')]"),
    (By.XPATH, "//*[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'compare available')]"),
    (By.XPATH, "//*[contains(@class,'compare') and (self::button or self::a)]"),
    (By.CSS_SELECTOR, "button.compareBtn"),
    (By.CSS_SELECTOR, "a.compareBtn"),
    (By.CSS_SELECTOR, "[class*='compare-source']"),
    (By.CSS_SELECTOR, "[class*='compareSource']"),
    (By.CSS_SELECTOR, "[ng-click*='compare']"),
]

_COMPARE_TABLE_ROW_SELECTORS = [
    (By.CSS_SELECTOR, "app-ux-compare-sources table tbody tr"),
    (By.CSS_SELECTOR, ".compare-sources-modal table tbody tr"),
    (By.CSS_SELECTOR, "modal table tbody tr"),
    (By.CSS_SELECTOR, ".modal-body table tbody tr"),
    (By.CSS_SELECTOR, ".modal table tbody tr"),
    (By.XPATH, "//div[contains(@class,'modal')]//table//tbody//tr"),
    (By.CSS_SELECTOR, "table tbody tr"),
]

_MODAL_CLOSE_SELECTORS = [
    (By.CSS_SELECTOR, ".modal-header button.close"),
    (By.CSS_SELECTOR, ".modal .close"),
    (By.CSS_SELECTOR, "[aria-label='Close']"),
    (By.CSS_SELECTOR, "button.close"),
    (By.XPATH, "//button[contains(@class,'close')]"),
    (By.XPATH, "//button[text()='×']"),
]

_PRICE_SORT_HEADER_SELECTORS = [
    (By.XPATH, "//th[contains(., 'Price')]"),
    (By.XPATH, "//th[contains(., 'Price/Unit')]"),
    (By.CSS_SELECTOR, "th.price"),
    (By.XPATH, "//span[contains(@class,'sort') and contains(ancestor::th,'.')]"),
]

# ─────────────────────────────────────────────────────────────────────────────


class InternalLinkScraper:
    """Scrapes product_detail links via the Compare Available Sources modal."""

    def __init__(
        self,
        sort_order: str = "low_to_high",
        stop_event=None,
        on_row_complete=None,
        worker_id: Optional[int] = None,
    ):
        self.sort_order = sort_order
        self._stop_event = stop_event
        self._stop_flag = False
        self._on_row_complete = on_row_complete
        self._worker_id = worker_id
        self.driver = None
        self.wait = None
        self.engine = get_engine()
        self._wid = f"[ILS-W{worker_id}] " if worker_id is not None else "[ILS] "

    # ── stop handling ─────────────────────────────────────────────────────────

    @property
    def stop_requested(self) -> bool:
        if self._stop_event is not None:
            return self._stop_event.is_set()
        return self._stop_flag

    def stop(self):
        if self._stop_event is not None:
            self._stop_event.set()
        else:
            self._stop_flag = True

    # ── driver management ─────────────────────────────────────────────────────

    def setup_driver(self):
        """Initialize Chrome driver with the same stealth options as the main scraper."""
        opts = Options()
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Edge/122.0.0.0 Safari/537.36",
        ]
        opts.add_argument(f"user-agent={random.choice(user_agents)}")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--disable-blink-features=AutomationControlled")
        opts.add_argument("--disable-extensions")
        opts.add_argument("--disable-background-timer-throttling")
        opts.add_argument("--disable-backgrounding-occluded-windows")
        opts.add_argument("--disable-renderer-backgrounding")
        opts.add_argument("--memory-pressure-off")
        # Do NOT disable images — they aren't needed but GSA Angular needs the page to render
        opts.add_experimental_option("excludeSwitches", ["enable-automation"])
        opts.add_experimental_option("useAutomationExtension", False)

        self.driver = webdriver.Chrome(options=opts)
        self.driver.execute_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        self.wait = WebDriverWait(self.driver, PAGE_LOAD_TIMEOUT)
        logger.info(f"{self._wid}Chrome driver ready.")

    def _ensure_driver(self):
        """Reinitialize driver if it has crashed or been closed."""
        if self.driver is None:
            self.setup_driver()
            return
        try:
            _ = self.driver.title
        except Exception:
            logger.warning(f"{self._wid}Driver detached — reinitializing.")
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None
            self.setup_driver()

    def _quit_driver(self):
        try:
            if self.driver:
                self.driver.quit()
        except Exception:
            pass
        self.driver = None

    # ── public entry points ───────────────────────────────────────────────────

    def run_assigned_links(self, links: list) -> int:
        """
        Called by ParallelLinkExtractionOrchestrator to process a pre-assigned
        partition of links.  The driver must already be set up by the caller
        (or this method sets it up itself).
        """
        if not self.driver:
            self.setup_driver()
        return self._run_loop(links)

    def run_full(self):
        """Scrape all unscraped product_detail links."""
        links = get_all_product_detail_links(self.engine)
        if not links:
            logger.info(f"{self._wid}No product_detail links to scrape.")
            return True
        logger.info(f"{self._wid}Starting internal link scraping: {len(links)} links.")
        try:
            self.setup_driver()
            self._run_loop(links)
            return True
        except Exception as e:
            logger.error(f"{self._wid}run_full error: {e}")
            return False
        finally:
            self._quit_driver()

    def run_test(self, item_limit: int = 3):
        """Scrape the first N unscraped product_detail links."""
        links = get_all_product_detail_links(self.engine)[:item_limit]
        if not links:
            logger.info(f"{self._wid}No product_detail links to scrape.")
            return True
        try:
            self.setup_driver()
            self._run_loop(links)
            return True
        except Exception as e:
            logger.error(f"{self._wid}run_test error: {e}")
            return False
        finally:
            self._quit_driver()

    # ── core loop ─────────────────────────────────────────────────────────────

    def _run_loop(self, links: list) -> int:
        """Process a list of ImportedLink records. Returns count of successes."""
        total = len(links)
        successful = 0

        for offset, link_rec in enumerate(links, 1):
            if self.stop_requested:
                logger.warning(f"{self._wid}Stop requested — exiting loop.")
                break

            url = link_rec.link
            logger.info(f"{self._wid}[{offset}/{total}] Processing: {url}")

            try:
                self._ensure_driver()

                # Clear any previously stored data for this link
                clear_links_scraped_data_for_link(self.engine, link_rec.id)

                rows = self._scrape_product_detail_page(url)

                if rows:
                    insert_link_scraped_rows(self.engine, link_rec.id, url, rows)
                    successful += 1
                    logger.info(f"{self._wid}Saved {len(rows)} row(s) for link id={link_rec.id}")
                else:
                    logger.warning(f"{self._wid}No data scraped for link id={link_rec.id}")

                mark_imported_link_scraped(self.engine, link_rec.id)

                if self._on_row_complete:
                    self._on_row_complete(url, bool(rows))

            except Exception as e:
                logger.error(f"{self._wid}Error on link id={link_rec.id}: {e}")
                self._quit_driver()  # fresh driver on next iteration
                if self._on_row_complete:
                    self._on_row_complete(url, False)

            # Polite delay between pages
            delay = float(SCRAPE_DELAY_SECONDS) * random.uniform(1.0, 1.5)
            if self._stop_event is not None:
                self._stop_event.wait(timeout=delay)
            else:
                time.sleep(delay)

        logger.info(
            f"{self._wid}Loop done: {successful}/{total} successful."
        )
        return successful

    # ── per-page scraping ─────────────────────────────────────────────────────

    def _scrape_product_detail_page(self, url: str) -> list[dict]:
        """
        Open a product detail page, click Compare Available Sources, extract all rows.
        Returns a list of dicts ready for insert_link_scraped_rows().
        """
        try:
            logger.info(f"{self._wid}Loading: {url}")
            self.driver.get(url)
            self._wait_for_page_ready(timeout=12)
            time.sleep(2)

            # ── Step 1: click "Compare Available Sources" ─────────────────────
            if not self._click_compare_sources_button():
                logger.warning(f"{self._wid}Compare button not found on: {url}")
                return []

            # Wait for the compare modal / table to appear
            time.sleep(2)
            self._wait_for_compare_table(timeout=10)

            # ── Step 2: optionally sort descending ────────────────────────────
            if self.sort_order == "high_to_low":
                self._click_price_header_to_sort_descending()
                time.sleep(1.5)

            # ── Step 3: read manufacturer info from "Currently Selected" header
            mfr_name, mfr_part_num = self._read_currently_selected_info()

            # ── Step 4: extract all table rows ────────────────────────────────
            rows = self._extract_all_compare_rows(mfr_name, mfr_part_num)
            return rows

        except Exception as e:
            logger.error(f"{self._wid}_scrape_product_detail_page failed for {url}: {e}")
            self._quit_driver()
            return []

    # ── page helpers ──────────────────────────────────────────────────────────

    def _wait_for_page_ready(self, timeout: int = 10):
        try:
            WebDriverWait(self.driver, timeout).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
        except TimeoutException:
            logger.warning(f"{self._wid}Page readyState timeout — continuing anyway.")

    def _wait_for_compare_table(self, timeout: int = 10):
        try:
            WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "table"))
            )
        except TimeoutException:
            logger.warning(f"{self._wid}Compare table did not appear within {timeout}s.")

    def _click_compare_sources_button(self) -> bool:
        """Find and click the Compare Available Sources button."""
        for sel_type, sel_val in _COMPARE_BTN_SELECTORS:
            try:
                el = self.driver.find_element(sel_type, sel_val)
                if el and el.is_displayed():
                    self.driver.execute_script("arguments[0].scrollIntoView(true);", el)
                    time.sleep(0.4)
                    try:
                        el.click()
                    except ElementClickInterceptedException:
                        self.driver.execute_script("arguments[0].click();", el)
                    logger.info(f"{self._wid}Clicked Compare button via {sel_type}={sel_val!r}")
                    return True
            except (NoSuchElementException, Exception):
                continue
        return False

    def _click_price_header_to_sort_descending(self):
        """
        Click the Price/Unit column header in the compare table to switch to
        descending order (high → low). GSA Advantage toggles asc/desc on each click;
        one click is enough if the default is ascending.
        """
        for sel_type, sel_val in _PRICE_SORT_HEADER_SELECTORS:
            try:
                el = self.driver.find_element(sel_type, sel_val)
                if el and el.is_displayed():
                    el.click()
                    logger.info(f"{self._wid}Clicked Price sort header — now descending.")
                    return
            except (NoSuchElementException, Exception):
                continue
        logger.warning(f"{self._wid}Price sort header not found — reading rows top→bottom regardless.")

    # ── Currently Selected header ─────────────────────────────────────────────

    def _read_currently_selected_info(self) -> tuple[Optional[str], Optional[str]]:
        """
        Extract Manufacturer Name and Manufacturer Part Number from the
        'Currently Selected' section at the top of the compare sources modal.
        """
        mfr_name = None
        mfr_part_num = None

        try:
            # The "Currently Selected" block is usually a small table/div just
            # above the comparison rows, inside the modal.
            candidate_selectors = [
                ".currently-selected",
                "[class*='currently-selected']",
                "[class*='currentlySelected']",
                ".modal-body .selected-info",
                ".modal-body table:first-of-type",
            ]
            for sel in candidate_selectors:
                try:
                    block = self.driver.find_element(By.CSS_SELECTOR, sel)
                    text = block.text
                    mfr_name, mfr_part_num = self._parse_currently_selected_text(text)
                    if mfr_name or mfr_part_num:
                        logger.info(
                            f"{self._wid}Currently Selected → name={mfr_name!r}, "
                            f"part_num={mfr_part_num!r}"
                        )
                        return mfr_name, mfr_part_num
                except NoSuchElementException:
                    continue

            # Fallback: scan the entire modal text
            modal_text = ""
            for modal_sel in [".modal-body", ".modal", "[role='dialog']"]:
                try:
                    modal_text = self.driver.find_element(By.CSS_SELECTOR, modal_sel).text
                    break
                except NoSuchElementException:
                    continue

            if modal_text:
                mfr_name, mfr_part_num = self._parse_currently_selected_text(modal_text)

        except Exception as e:
            logger.warning(f"{self._wid}Could not read Currently Selected section: {e}")

        return mfr_name, mfr_part_num

    def _parse_currently_selected_text(self, text: str) -> tuple[Optional[str], Optional[str]]:
        """
        Parse free text from the Currently Selected header area.
        Looks for 'Manufacturer Name' and 'Manufacturer Part Number' labels.
        """
        mfr_name = None
        mfr_part_num = None

        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

        for i, line in enumerate(lines):
            low = line.lower()
            if "manufacturer name" in low and i + 1 < len(lines):
                mfr_name = lines[i + 1]
            elif "manufacturer part number" in low and i + 1 < len(lines):
                mfr_part_num = lines[i + 1]
            elif "manufacturer part" in low and i + 1 < len(lines) and not mfr_part_num:
                mfr_part_num = lines[i + 1]

        # Inline pattern: "Manufacturer Name: RACKMOUNT" on a single line
        if not mfr_name:
            m = re.search(r'manufacturer\s+name\s*[:\-]\s*(.+)', text, re.IGNORECASE)
            if m:
                mfr_name = m.group(1).split('\n')[0].strip()

        if not mfr_part_num:
            m = re.search(r'manufacturer\s+part\s+(?:number|#|no)\s*[:\-]\s*([^\s\n]+)',
                          text, re.IGNORECASE)
            if m:
                mfr_part_num = m.group(1).strip()

        return mfr_name or None, mfr_part_num or None

    # ── Table row extraction ──────────────────────────────────────────────────

    def _find_compare_table_rows(self) -> list:
        """Return all <tr> elements from the compare sources table."""
        for sel_type, sel_val in _COMPARE_TABLE_ROW_SELECTORS:
            try:
                rows = self.driver.find_elements(sel_type, sel_val)
                if rows:
                    logger.info(
                        f"{self._wid}Found {len(rows)} table rows "
                        f"via {sel_type}={sel_val!r}"
                    )
                    return rows
            except Exception:
                continue
        logger.warning(f"{self._wid}No compare table rows found with any selector.")
        return []

    def _extract_all_compare_rows(
        self,
        mfr_name: Optional[str],
        mfr_part_num: Optional[str],
    ) -> list[dict]:
        """Iterate every row in the compare table and build result dicts."""
        table_rows = self._find_compare_table_rows()
        if not table_rows:
            return []

        results = []
        _header_keywords = {
            "price/unit", "contractor", "features", "deliv days",
            "min order", "fob/shipping", "socio", "photo",
        }

        for idx, tr in enumerate(table_rows):
            # Stop once we have collected the required number of rows
            if len(results) >= MAX_ROWS_PER_LINK:
                logger.info(f"{self._wid}Reached {MAX_ROWS_PER_LINK}-row limit — stopping table scan.")
                break

            try:
                row_text = tr.text.strip()
                if not row_text:
                    continue

                # Skip pure header rows
                low_text = row_text.lower()
                if any(kw in low_text for kw in _header_keywords):
                    # Allow rows that ALSO contain a price (data rows can mention "ea")
                    if not re.search(r'\$\s*[\d,]+\.?\d*', low_text):
                        continue

                price = self._parse_price(row_text)
                unit = self._parse_unit(row_text)
                contractor_name = self._get_contractor_link_text(tr)

                if price is None and not contractor_name:
                    continue  # blank / separator row

                # Click contractor link to fetch the contract number
                contract_number = self._fetch_contract_number(tr, contractor_name)

                results.append({
                    "manufacturer_part_name": mfr_name,
                    "manufacturer_part_number": mfr_part_num,
                    "price": price,
                    "unit": unit,
                    "contractor_name": contractor_name,
                    "contract_number": contract_number,
                    "row_order": len(results),  # sequential within this link
                })

                logger.info(
                    f"{self._wid}Row {len(results)}/{MAX_ROWS_PER_LINK}: "
                    f"price={price}, unit={unit}, contractor={contractor_name!r}, "
                    f"contract#={contract_number!r}"
                )

            except Exception as e:
                logger.warning(f"{self._wid}Error parsing table row {idx}: {e}")
                continue

        return results

    # ── price / unit / contractor parsing ────────────────────────────────────

    def _parse_price(self, text: str) -> Optional[float]:
        for pat in [
            r'\$\s*([\d,]+\.?\d*)',
            r'([\d,]+\.\d{2})\s*(?:EA|BX|BT|PK|DZ|CS|PR|SE|LO|KT)',
        ]:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                try:
                    return float(m.group(1).replace(',', ''))
                except ValueError:
                    continue
        return None

    def _parse_unit(self, text: str) -> Optional[str]:
        # "$104.99 EA" — unit directly after price on the same line
        for line in text.splitlines():
            m = re.search(r'\$\s*[\d,]+\.?\d*\s+([A-Za-z]{2,4})\b', line)
            if m:
                return m.group(1).upper()
            # "$104.99/EA"
            m = re.search(r'\$\s*[\d,]+\.?\d*\s*/\s*([A-Za-z]{1,4})\b', line)
            if m:
                return m.group(1).upper()
        return None

    def _get_contractor_link_text(self, tr) -> Optional[str]:
        """Return the text of the contractor <a> link inside this <tr>."""
        _skip = {"select", "details", "more info", "info", "compare"}
        try:
            links = tr.find_elements(By.TAG_NAME, "a")
            for lnk in links:
                txt = lnk.text.strip()
                if txt and len(txt) > 2 and txt.lower() not in _skip:
                    # Reject price-like strings
                    if not re.match(r'^\$?[\d,]+\.?\d*$', txt):
                        return txt
        except Exception:
            pass
        return None

    # ── contract number (click contractor → popup) ────────────────────────────

    def _fetch_contract_number(
        self, tr, contractor_name: Optional[str]
    ) -> Optional[str]:
        """
        Click the contractor link in the given row, read the contract number
        from the resulting popup, then close it.
        Returns None on failure so the row is still saved.
        """
        if not contractor_name:
            return None

        original_handles = set(self.driver.window_handles)

        try:
            # Find the exact link element
            contractor_link = None
            for lnk in tr.find_elements(By.TAG_NAME, "a"):
                if lnk.text.strip() == contractor_name:
                    contractor_link = lnk
                    break

            if not contractor_link:
                return None

            self.driver.execute_script("arguments[0].scrollIntoView(true);", contractor_link)
            time.sleep(0.3)
            try:
                contractor_link.click()
            except ElementClickInterceptedException:
                self.driver.execute_script("arguments[0].click();", contractor_link)

            time.sleep(1.5)

            # ── Case A: new tab / window opened ──────────────────────────────
            new_handles = set(self.driver.window_handles) - original_handles
            if new_handles:
                new_handle = new_handles.pop()
                self.driver.switch_to.window(new_handle)
                time.sleep(1)
                contract_num = self._read_contract_number_from_current_view()
                self.driver.close()
                self.driver.switch_to.window(list(original_handles)[0])
                return contract_num

            # ── Case B: modal/popup on the same page ─────────────────────────
            contract_num = self._read_contract_number_from_current_view()
            self._close_modal()
            return contract_num

        except Exception as e:
            logger.warning(
                f"{self._wid}Could not get contract# for {contractor_name!r}: {e}"
            )
            # Best-effort modal close so next row can still be processed
            try:
                self._close_modal()
            except Exception:
                pass
            # If a new tab was opened and we crashed, switch back
            try:
                remaining_handles = set(self.driver.window_handles)
                extra = remaining_handles - original_handles
                for h in extra:
                    self.driver.switch_to.window(h)
                    self.driver.close()
                if original_handles:
                    self.driver.switch_to.window(list(original_handles)[0])
            except Exception:
                pass
            return None

    def _read_contract_number_from_current_view(self) -> Optional[str]:
        """
        Scrape the contract number from either:
          - The contractor info modal overlay, or
          - A new page that opened after clicking the contractor link.

        The contractor detail page / modal shows:
            Contract:  47QTCA23D00CC
        """
        time.sleep(0.8)

        # Try modal-scoped selectors first
        modal_selectors = [
            ".modal-body",
            ".modal",
            "[role='dialog']",
            ".contractor-info",
            "[class*='contractorInfo']",
            "[class*='contractor-info']",
        ]
        for sel in modal_selectors:
            try:
                el = self.driver.find_element(By.CSS_SELECTOR, sel)
                cn = self._parse_contract_number(el.text)
                if cn:
                    return cn
            except NoSuchElementException:
                continue

        # Fallback: full page body
        try:
            body_text = self.driver.find_element(By.TAG_NAME, "body").text
            return self._parse_contract_number(body_text)
        except Exception:
            return None

    def _parse_contract_number(self, text: str) -> Optional[str]:
        """
        Extract a GSA contract number from a block of text.
        GSA contract numbers look like: 47QTCA23D00CC  (10–20 uppercase alphanum chars).
        """
        patterns = [
            r'contract\s*[:#\-]?\s*([A-Z0-9]{6,20})',
            r'contract\s+number\s*[:#\-]?\s*([A-Z0-9]{6,20})',
            r'contract\s+#\s*([A-Z0-9]{6,20})',
        ]
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                candidate = m.group(1).strip()
                # Sanity-check: looks like a real contract number
                if re.match(r'^[A-Z0-9]{6,20}$', candidate):
                    return candidate
        return None

    def _close_modal(self):
        """Close a popup / modal on the current page."""
        for sel_type, sel_val in _MODAL_CLOSE_SELECTORS:
            try:
                el = self.driver.find_element(sel_type, sel_val)
                if el and el.is_displayed():
                    el.click()
                    time.sleep(0.5)
                    return
            except (NoSuchElementException, Exception):
                continue
        # Last resort: press Escape
        try:
            self.driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
            time.sleep(0.5)
        except Exception:
            pass
