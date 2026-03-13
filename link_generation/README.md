## GSA Link Automation (Super Fast)

This project automates generating GSA Advantage search links for Essendant items directly from an Excel file. It uses a deterministic URL pattern, so no browser automation is needed, enabling very high throughput.

### Features
- Direct URL construction: no Selenium/browser required
- Processes entire spreadsheets quickly (tens of thousands of rows)
- Automatic backups of output Excel file with timestamp suffix
- Safe save flow using temporary file and validation
- Multiple run modes: test, full, and custom row range

### Project Structure
- `gsa_link_automation_fast.py`: Main CLI to generate links quickly
- `analyze_pattern.py`: Helper/analysis script that derived and validates the URL pattern
- `essendant-product-list.xlsx`: Input Excel (source of stock numbers)
- `essendant-product-list_with_gsa_links.xlsx`: Output Excel (includes a `Links` column)
- `requirements.txt`: Python dependencies

### Requirements
- Python 3.9+ recommended
- See `requirements.txt` for packages:
  - pandas
  - openpyxl
  - (selenium and webdriver-manager are listed but not required for the fast mode)

Install dependencies:

```bash
pip install -r requirements.txt
```

### Input Excel Expectations
- File: `essendant-product-list.xlsx` in the project root
- Must contain a column named similar to `Item Stock Number-Butted` (case-insensitive match on both "item stock number" and "butted")
- A `Links` column is optional; it will be created if missing

### Output
- `essendant-product-list_with_gsa_links.xlsx` with a populated `Links` column
- Backups are created alongside the output, as `essendant-product-list_with_gsa_links.xlsx.backup_YYYYMMDD_HHMMSS`

### How It Works (URL Pattern)
The discovered pattern for GSA Advantage search is:

```
Base: https://www.gsaadvantage.gov/advantage/ws/search/advantage_search
Query: ?searchType=1&q=7:1{STOCK_NUMBER}&s=7&c=100
```

The script trims each stock number and inserts it into the query.

### Usage
Run the main program:

```bash
python gsa_link_automation_fast.py
```

Then choose a mode:
- 1: Test mode (first 5 rows) — prints constructed links and saves output
- 2: Full automation — processes all rows; asks for confirmation
- 3: Custom range — processes a user-specified 1-based row range
- 4: Exit

### Safety, Backups, and Validation
- Before overwriting the output file, a timestamped backup is created if a previous file exists
- Writes first to a temporary file, validates presence of required columns (`Item Stock Number-Butted`, `Links`), then moves into place
- After save, final validation runs; if it fails, the script attempts to restore from the most recent backup
- Old backups are cleaned up, keeping the most recent 5

### Troubleshooting
- "Could not find 'Item Stock Number-Butted' column":
  - Ensure your input file has a column name containing both "Item Stock Number" and "Butted"
  - Check for extra spaces or different punctuation
- "Excel file is empty" or validation failures:
  - Confirm the input file path and that it contains data rows
- Permission errors when saving:
  - Close the Excel file in other applications before running the script
  - Ensure you have write permissions to the directory
- Dependency issues:
  - Reinstall requirements: `pip install --upgrade -r requirements.txt`

### Notes
- The fast path does not require Selenium; the listed Selenium dependencies are safe to keep but not used by `gsa_link_automation_fast.py`
- For pattern analysis or verification, you can run `analyze_pattern.py` (expects `essendant-product-list_with_gsa_links.xlsx` to exist)

### License
Proprietary — internal use only unless otherwise specified by the owner.


