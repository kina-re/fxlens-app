# app/services/db.py
import os
import re
import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# Load env vars from .env
load_dotenv()

# Prefer a full DATABASE_URL if provided; otherwise build from parts
DATABASE_URL = os.getenv("POSTGRES_URL")
if not DATABASE_URL:
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = os.getenv("DB_PORT", "5432")
    DB_NAME = os.getenv("DB_NAME", "postgres")
    DB_USER = os.getenv("DB_USER", "postgres")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")
    # Use psycopg2 driver
    DATABASE_URL = f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# Create a single global SQLAlchemy engine
engine = create_engine(DATABASE_URL, future=True, pool_pre_ping=True)

# Regex to convert psycopg2-style %(name)s -> SQLAlchemy :name
_PSYCO_RE = re.compile(r"%\((\w+)\)s")

def _to_sa_binds(sql: str) -> str:
    """
    Convert %(name)s to :name for SQLAlchemy text() calls.
    If :name already present, leaves as-is.
    """
    # If it already contains any :name, assume it's fine
    if ":" in sql and not _PSYCO_RE.search(sql):
        return sql
    return _PSYCO_RE.sub(r":\1", sql)

def run_query(query: str, params: dict | None = None) -> pd.DataFrame:
    """
    Execute SQL and return a DataFrame.
    Accepts either %(name)s (psycopg2) or :name (SQLAlchemy) placeholders.
    """
    sql_clean = query.strip().rstrip(";")  # avoid trailing ; issues
    sql_clean = _to_sa_binds(sql_clean)
    with engine.connect() as conn:
        df = pd.read_sql(text(sql_clean), conn, params=params or {})
    return df

def get_min_datetime():
    with engine.connect() as conn:
        return conn.execute(text("SELECT MIN(datetime) FROM forex_bars")).scalar()

def get_max_datetime():
    with engine.connect() as conn:
        return conn.execute(text("SELECT MAX(datetime) FROM forex_bars")).scalar()

if __name__ == "__main__":
    print("Testing DB (SQLAlchemy) ...")
    print("Earliest:", get_min_datetime())
    print("Latest  :", get_max_datetime())
    print(run_query("SELECT * FROM forex_bars ORDER BY datetime DESC LIMIT 5"))
