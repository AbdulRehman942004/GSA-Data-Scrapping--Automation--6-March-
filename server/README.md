# GSA Data Scraping Automation

## Overview
This project provides an automated pipeline for generating search links, normalizing manufacturer data, and scraping product information (price, unit of measure, and contractor) from the GSA Advantage platform.

## Project Structure
The automation process is divided into three main stages:

1. **link_generation**
   Constructs direct GSA Advantage search URLs for each product in the input Excel file using a deterministic pattern, bypassing the need for browser interaction. 
   It features a super-fast generation mode (`gsa_link_automation_fast.py`) that exports the results to an Excel fallback file as well as a PostgreSQL database using SQLModel for robust data management.

2. **manufacturer_normalization**
   Extracts unique manufacturer names from the dataset and normalizes them into a simplified root format for accurate matching during the scraping phase.

3. **scraping**
   Uses Selenium to navigate the generated GSA Advantage links, extract product details (price, unit, contractor), and match them against the normalized manufacturer roots using fuzzy logic. Also includes a utility to update search links for missing rows using alternative identifiers for a secondary scraping pass.

## Setup Instructions

### Prerequisites
- Python 3.9+ 
- Google Chrome (for the Selenium scraper)
- PostgreSQL Server (running locally or remotely)

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

### Configuration
1. Create a PostgreSQL database named `gsa_data` (default). You can do this using `psql`, pgAdmin, or your preferred SQL client:
   ```sql
   CREATE DATABASE gsa_data;
   ```

2. Copy the `.env.example` file to `.env` in the root directory:
   ```bash
   cp .env.example .env
   ```

3. Update the `.env` file with your PostgreSQL credentials:
   ```env
   POSTGRESQL_HOST=localhost
   POSTGRESQL_PORT=5432
   POSTGRESQL_DATABASE=gsa_data
   POSTGRESQL_USERNAME=postgres
   POSTGRESQL_PASSWORD=yourpassword
   ```

### Running Link Generation
To run the super fast link generator and store results in the database:
```bash
cd link_generation
python gsa_link_automation_fast.py
```
This script runs entirely automatically, validating and securely saving the links to both tracking `.xlsx` files and the PostgreSQL database using SQLModel.

## License
Proprietary - internal use only.
