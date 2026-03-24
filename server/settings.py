"""
Central configuration for the GSA Scraping Automation server.

All tuneable constants, file paths, and environment-driven settings live here.
Import from this module instead of scattering os.getenv / hardcoded values
across the codebase.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ── Database ──────────────────────────────────────────────────────────────────
DB_HOST = os.getenv("POSTGRESQL_HOST", "localhost")
DB_PORT = os.getenv("POSTGRESQL_PORT", "5432")
DB_NAME = os.getenv("POSTGRESQL_DATABASE", "gsa_data")
DB_USER = os.getenv("POSTGRESQL_USERNAME", "postgres")
DB_PASSWORD = os.getenv("POSTGRESQL_PASSWORD")   # No fallback – must be set in .env

# ── API / CORS ─────────────────────────────────────────────────────────────────
# Comma-separated list of allowed origins, e.g. "http://localhost:3000,https://myapp.com"
ALLOWED_ORIGINS = [
    o.strip()
    for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:3001").split(",")
    if o.strip()
]

# ── File paths ────────────────────────────────────────────────────────────────
SERVER_DIR = os.path.dirname(os.path.abspath(__file__))

EXCEL_FILE_PATH = os.path.join(SERVER_DIR, "data", "GSA Advantage Low price.xlsx")

# ── Scraping timing ───────────────────────────────────────────────────────────
SCRAPE_DELAY_SECONDS: int = int(os.getenv("SCRAPE_DELAY_SECONDS", "6"))
PAGE_LOAD_TIMEOUT: int = int(os.getenv("PAGE_LOAD_TIMEOUT", "15"))

# ── Parallel scraping ────────────────────────────────────────────────────────
# 0 = auto-detect: min(3, cpu_count // 2), each Chrome instance ~300-500 MB RAM
SCRAPE_NUM_WORKERS: int = int(os.getenv("SCRAPE_NUM_WORKERS", "0"))
SCRAPE_MAX_WORKERS: int = int(os.getenv("SCRAPE_MAX_WORKERS", "5"))
SCRAPE_MAX_REQUESTS_PER_MINUTE: int = int(os.getenv("SCRAPE_MAX_REQUESTS_PER_MINUTE", "30"))
SCRAPE_WORKER_MAX_RETRIES: int = int(os.getenv("SCRAPE_WORKER_MAX_RETRIES", "3"))
