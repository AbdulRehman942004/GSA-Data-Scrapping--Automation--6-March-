# GSA Data Scraping Automation

## Overview
This project provides an automated pipeline for generating search links, normalizing manufacturer data, and scraping product information (price, unit of measure, and contractor) from the GSA Advantage platform.

## Setup Instructions

### Prerequisites
- Python 3.11+ 
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
   
   # Optional: Proxy list (comma-separated ip:port:user:pass)
   SCRAPE_PROXIES=ip1:port1:user1:pass1,ip2:port2:user2:pass2
   ```

## License
Proprietary - internal use only.
