import os
from sqlmodel import create_engine
from dotenv import load_dotenv

def get_engine():
    load_dotenv()
    host = os.getenv("POSTGRESQL_HOST", "localhost")
    port = os.getenv("POSTGRESQL_PORT", "5432")
    database = os.getenv("POSTGRESQL_DATABASE", "gsa_data")
    username = os.getenv("POSTGRESQL_USERNAME", "postgres")
    password = os.getenv("POSTGRESQL_PASSWORD", "12345")
    db_url = f"postgresql://{username}:{password}@{host}:{port}/{database}"
    return create_engine(db_url)
