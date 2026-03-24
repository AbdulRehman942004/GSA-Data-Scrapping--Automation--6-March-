import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlmodel import create_engine
from settings import DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD, SCRAPE_MAX_WORKERS

_engine = None


def get_engine():
    global _engine
    if _engine is not None:
        return _engine

    if not DB_PASSWORD:
        raise ValueError("POSTGRESQL_PASSWORD environment variable is not set.")

    db_url = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    _engine = create_engine(
        db_url,
        pool_size=max(10, SCRAPE_MAX_WORKERS * 2 + 5),
        max_overflow=10,
        pool_pre_ping=True,
    )
    return _engine
