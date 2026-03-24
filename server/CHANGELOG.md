# Changelog

All notable changes to this project will be documented in this file.

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
