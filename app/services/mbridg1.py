import os
import requests
import re

QWEN_API_URL = os.getenv("QWEN_API_URL", "http://localhost:1234/v1/chat/completions")
QWEN_MODEL   = os.getenv("QWEN_MODEL",   "qwen/qwen2.5-vl-7b")

# 👇 Schema description that will be injected into Qwen
SCHEMA_DESCRIPTION = """
You are a helpful assistant that generates ONLY SQL queries for PostgreSQL.

The database has one table called `forex_bars` with the following columns:
- datetime (timestamp): the time of the forex bar
- open (float): opening price
- high (float): highest price
- low (float): lowest price
- close (float): closing price
- volume (float): trading volume
- pip_hl (float): pip difference (high - low)
- pip_oc (float): pip difference (close - open)
- confidence_score (float): numeric confidence value
- confidence_tag (text): category label
- id (int)
- symbol (text)


Rules:
1. Use only these columns. Do not invent new ones.
2. Always include a filter:
   WHERE CAST(datetime AS date) BETWEEN :start_date AND :end_date
   (unless the user explicitly provides their own filter).
3. Return ONLY SQL in a ```sql ... ``` code block. No explanations.
4. Use ONLY this table (forex_bars).

5. Do NOT invent any new tables or columns.
6. Always return plain SQL, no explanations or comments.
7. Prefer aliases for clarity if needed.

"""

# --- helper to strip code fences and clean ---
def _strip_fences(sql_text: str) -> str:
    sql_text = sql_text.strip()
    m = re.match(r"^```(?:sql)?\s*([\s\S]*?)\s*```$", sql_text, flags=re.IGNORECASE)
    return (m.group(1) if m else sql_text).strip()

def _clean(sql_text: str) -> str:
    sql = _strip_fences(sql_text)
    sql = sql.strip().rstrip(";") + ";"  # ensure trailing ;
    return sql

# --- ask_qwen ---
def ask_qwen(user_question: str) -> str:
    payload = {
        "model": QWEN_MODEL,
        "messages": [
            {"role": "system", "content": SCHEMA_DESCRIPTION},
            {"role": "user",   "content": user_question},
        ],
        "temperature": 0.2,
        "max_tokens": 500,
    }
    r = requests.post(QWEN_API_URL, json=payload, timeout=60)
    r.raise_for_status()
    data = r.json()
    sql_raw = data["choices"][0]["message"]["content"]
    return _clean(sql_raw)

def health_check() -> bool:
    try:
        r = requests.get(QWEN_API_URL.replace("/chat/completions", "/models"), timeout=5)
        r.raise_for_status()
        return True
    except Exception:
        return False
