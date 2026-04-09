# Changelog

All notable changes to this project will be documented in this file.

## v4.1.2 - 2026-04-08
### Added
Hightlighted the headings of internal and external link columns for better understanding

## v4.1.1 - 2026-04-08
### Added
Added maunfactorer part number in internal and external link

## v4.1.0 - 2026-04-08
### Added
Complete the functionality of import external link from excel sheet

## v4.0.0 - 2026-04-08
### Added
Complete the functionality of import internal link from excel sheet

## v3.0.0 - 2026-03-27

### Added
- Dynamic Excel file upload functionality (.xlsx/.csv) for updating scraper targets.
- File parsing service to extract spreadsheet rows and dynamically map them to the database.
- Data validation logic to ensure uploaded files match the required column structure before database insertion.
- Database batch insertion logic to store the newly uploaded targets for the scraper to read.

## v2.0.0 - 2026-03-24

### Changed
- Refactored proxy allocation so workers pick dynamic proxies from the full available pool.
- Updated error handling to completely tear down and restart browsers upon unexpected GSA timeouts or "access denied" payloads.
- Modified request delays to include an additive random jitter (1.0x to 1.5x of baseline) ensuring delays never run faster than the configured minimum.

### Added
- User-Agent profile rotation (Chrome, Edge, Firefox) upon browser initialization.
- Random scrolling and pause injection to emulate genuine human interaction.
- `SCRAPE_PROXIES` array tracking capability to bypass static constraints.

## v1.0.0 - 2026-03-14

### Added
- Link generation scripts for constructing deterministic GSA Advantage search URLs.
- Manufacturer name normalization utilities to extract and map root forms.
- Selenium-based web scraper to extract product prices, units, and contractor information.
- Fuzzy matching algorithm for verifying manufacturer names during scraping.
- Link update tool for missing rows to facilitate secondary scraping attempts using alternative product identifiers.
- Basic project structure separated into sequential automation stages.
