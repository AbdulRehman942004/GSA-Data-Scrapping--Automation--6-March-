# GSA Data Scraping Automation

## Overview
This project provides an automated pipeline for generating search links, normalizing manufacturer data, and scraping product information (price, unit of measure, and contractor) from the GSA Advantage platform.

## Project Structure
The automation process is divided into four main stages:

1. **link_generation**
   Constructs direct GSA Advantage search URLs for each product in the input Excel file using a deterministic pattern, bypassing the need for browser interaction.

2. **manufacturer_normalization**
   Extracts unique manufacturer names from the dataset and normalizes them into a simplified root format for accurate matching during the scraping phase.

3. **scraping**
   Uses Selenium to navigate the generated GSA Advantage links, extract product details (price, unit, contractor), and match them against the normalized manufacturer roots using fuzzy logic.

4. **update_missing_links**
   Identifies products that failed during the initial scraping phase and updates their search links to use an alternative identifier (Item Number instead of Item Stock Number-Butted) for a secondary scraping pass.

## Setup Instructions

### Prerequisites
- Python 3.9+ 
- Google Chrome (for the Selenium scraper)

### Installation
1. Clone or download the repository to your local machine:
   ```bash
   git clone https://github.com/AbdulRehman942004/GSA-Data-Scrapping--Automation--6-March-.git
   cd GSA-Data-Scrapping--Automation--6-March-
   ```

2. Create a virtual environment:
   
   **On Windows:**
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\activate
   ```
   *(Note: If you encounter an execution policy error on Windows, run `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser` first).*

   **On macOS/Linux:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## License
Proprietary - internal use only.
