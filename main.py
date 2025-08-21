import os
import re
import psycopg2
import yaml
import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Any
from dotenv import load_dotenv

# -------------------- ENV --------------------
load_dotenv()  # loads .env in the project root if present

# -------------------- CONFIG --------------------
DB_CONFIG = {
    "dbname": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "host": os.getenv("DB_HOST"),
    "port": os.getenv("DB_PORT"),
    "sslmode": "require",   # Neon needs SSL
}

LMSTUDIO_API_URL = os.getenv(
    "LMSTUDIO_API_URL", "http://localhost:1234/v1/chat/completions"
)
LMSTUDIO_MODEL = os.getenv(
    "LMSTUDIO_MODEL", "qwen/qwen2.5-vl-7b"
)

QUERIES_REGISTRY_FILE = os.path.join(os.path.dirname(__file__), "queries_registry.yml")

# -------------------- APP --------------------
app = FastAPI(title="Forex Query API", version="1.0")

# -------------------- LOAD REGISTRY --------------------
if not os.path.exists(QUERIES_REGISTRY_FILE):
    raise FileNotFoundError(f"{QUERIES_REGISTRY_FILE} not found in {os.path.dirname(__file__)}")

with open(QUERIES_REGISTRY_FILE, "r", encoding="utf-8") as f:
    queries_registry = yaml.safe_load(f)

if not isinstance(queries_registry, list):
    raise RuntimeError("queries_registry.yml must be a YAML list of entries.")

# -------------------- MODELS --------------------
class QuestionRequest(BaseModel):
    question: str
    limit: Optional[int] = None
    params: Optional[dict] = None  # reserved for future {{param}} templating

# -------------------- HELPERS --------------------
def _json_friendly_rows(rows: List[tuple]) -> List[List[Any]]:
    out = []
    for r in rows:
        out.append([v if isinstance(v, (int, float)) or v is None else str(v) for v in r])
    return out

def run_sql(sql: str) -> dict:
    try:
        with psycopg2.connect(**DB_CONFIG) as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
                cols = [d[0] for d in cur.description]
                rows = cur.fetchall()
        return {"columns": cols, "rows": _json_friendly_rows(rows)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

def validate_read_only_sql(sql: str):
    s = sql.strip().lower()
    if not s.startswith("select"):
        raise HTTPException(status_code=400, detail="Only SELECT queries are allowed.")
    banned = [" insert ", " update ", " delete ", " drop ", " alter ", " create ",
              " truncate ", " grant ", " revoke ", " copy ", " do ", " call "]
    s_spaced = f" {s} "
    if any(kw in s_spaced for kw in banned):
        raise HTTPException(status_code=400, detail="Write/DDL statements are not allowed.")
    return True

def add_optional_limit(sql: str, limit: Optional[int]) -> str:
    if not limit:
        return sql
    stripped = sql.rstrip().rstrip(";")
    return f"{stripped} LIMIT {limit};"

# -------------------- LM STUDIO (QWEN) --------------------
PROMPT_SQL_ONLY = (
    "You are an expert PostgreSQL SQL generator. Return output in the EXACT format below:\n\n"
    "```sql\n"
    "SELECT ... -- A single valid PostgreSQL SELECT for table forex_bars ONLY\n"
    "```\n"
    "Interpretation: <1-3 concise business sentences about the result>\n"
    "Source: <one authoritative URL for context>\n\n"
    "Constraints:\n"
    "- Query ONLY the table forex_bars.\n"
    "- The table columns are:\n"
    "  symbol TEXT,\n"
    '  \"datetime\" TIMESTAMPTZ,\n'
    "  open DOUBLE PRECISION,\n"
    "  high DOUBLE PRECISION,\n"
    "  low DOUBLE PRECISION,\n"
    "  close DOUBLE PRECISION,\n"
    "  pip_hl DOUBLE PRECISION,\n"
    "  pip_oc DOUBLE PRECISION,\n"
    "  confidence_score DOUBLE PRECISION,\n"
    "  confidence_tag TEXT.\n"
    "- Use double quotes when referencing the \"datetime\" column.\n"
    "- Do NOT include any text before or after the three required parts.\n"
)

def ask_lmstudio_generate(question: str) -> tuple[str, str, Optional[str]]:
    """
    Ask LM Studio (Qwen) to produce:
      1) SQL in a fenced ```sql block
      2) Interpretation: ...
      3) Source: https://...
    Returns (sql, interpretation, source_url)
    """
    payload = {
        "model": LMSTUDIO_MODEL,
        "messages": [
            {"role": "system", "content": PROMPT_SQL_ONLY},
            {"role": "user",   "content": question.strip()}
        ],
        "temperature": 0,
        "max_tokens": 500,
    }
    try:
        resp = requests.post(LMSTUDIO_API_URL, json=payload, timeout=90)
        if resp.status_code != 200:
            raise HTTPException(status_code=500, detail=f"LM Studio API error: {resp.text}")
        content = resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LM Studio request failed: {e}")

    # Parse ```sql ... ```
    sql_block = re.search(r"```sql\s*(.*?)```", content, flags=re.IGNORECASE | re.DOTALL)
    if not sql_block:
        # fallback: any fenced block
        sql_block = re.search(r"```(?:\w+)?\s*(.*?)```", content, flags=re.DOTALL)
    if not sql_block:
        raise HTTPException(status_code=500, detail="Could not parse SQL code block from LM Studio response.")
    sql_code = sql_block.group(1).strip()
    sql_code = sql_code.split(";")[0].strip()  # first statement only

    # Interpretation
    i_match = re.search(r"^\s*Interpretation:\s*(.+)$", content, flags=re.IGNORECASE | re.MULTILINE)
    interpretation = i_match.group(1).strip() if i_match else "No interpretation provided."

    # Source URL
    s_match = re.search(r"^\s*Source:\s*(\S+)\s*$", content, flags=re.IGNORECASE | re.MULTILINE)
    source_url = s_match.group(1).strip() if s_match else None

    return sql_code, interpretation, source_url

# -------------------- ROUTES --------------------
@app.get("/")
def home():
    return {"status": "ok", "registry_entries": len(queries_registry)}

@app.post("/ask")
def ask_query(req: QuestionRequest):
    """
    Exact-match from YAML first.
    - If SQL present → run it.
    - If SQL missing/blank → LM Studio fallback but retain registry interpretation/source if present.
    No registry match → full LM Studio fallback.
    """
    q_in = req.question.strip()

    # 1) Exact match in YAML registry
    for entry in queries_registry:
        nlq = entry.get("natural_language_question", "").strip()
        if q_in.lower() == nlq.lower():
            sql = (entry.get("sql_query") or "").strip()

            # 1a) Registry SQL present → run it
            if sql:
                sql = add_optional_limit(sql, req.limit)
                validate_read_only_sql(sql)
                result = run_sql(sql)
                return {
                    "source": "registry",
                    "question": nlq,
                    "columns": result["columns"],
                    "rows": result["rows"],
                    "interpretation": entry.get("business_interpretation", "No interpretation available."),
                    "source_url": entry.get("source_url")
                }

            # 1b) Registry SQL missing → LM Studio fallback (keep registry interp/source if available)
            sql_gen, interp, src_url = ask_lmstudio_generate(q_in)
            sql_gen = add_optional_limit(sql_gen, req.limit)
            validate_read_only_sql(sql_gen)
            result = run_sql(sql_gen)
            interpretation = entry.get("business_interpretation") or interp or "No interpretation available."
            source_url = entry.get("source_url") or src_url
            return {
                "source": "registry_match_missing_sql_lmstudio_fallback",
                "question": nlq,
                "sql_generated": sql_gen,
                "columns": result["columns"],
                "rows": result["rows"],
                "interpretation": interpretation,
                "source_url": source_url
            }

    # 2) No registry match → full LM Studio fallback
    sql_gen, interp, src_url = ask_lmstudio_generate(q_in)
    sql_gen = add_optional_limit(sql_gen, req.limit)
    validate_read_only_sql(sql_gen)
    result = run_sql(sql_gen)
    return {
        "source": "lmstudio_fallback",
        "question": q_in,
        "sql_generated": sql_gen,
        "columns": result["columns"],
        "rows": result["rows"],
        "interpretation": interp or "No interpretation available.",
        "source_url": src_url
    }
