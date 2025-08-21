import os
import requests
import re
from app.services.qlog import append_unanswered


QWEN_API_URL = os.getenv("QWEN_API_URL", "http://localhost:1234/v1/chat/completions")
QWEN_MODEL   = os.getenv("QWEN_MODEL",   "qwen/qwen2.5-vl-7b")

# System prompt ONLY for SQL generation
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

# helpers 

def _strip_fences(sql_text: str) -> str:
    sql_text = sql_text.strip()
    m = re.match(r"^```(?:sql)?\s*([\s\S]*?)\s*```$", sql_text, flags=re.IGNORECASE)
    return (m.group(1) if m else sql_text).strip()

def _clean(sql_text: str) -> str:
    sql = _strip_fences(sql_text)
    sql = sql.strip().rstrip(";") + ";"  # ensure trailing ;
    return sql

def _post(messages, temperature=0.3, max_tokens=512):
    payload = {
        "model": QWEN_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    r = requests.post(QWEN_API_URL, json=payload, timeout=60)
    r.raise_for_status()
    data = r.json()
    return data["choices"][0]["message"]["content"]

# public API 
def ask_qwen(user_question: str) -> str:
    """
    Ask Qwen to generate SQL. 
    If nothing useful is returned (empty, junk, or invalid),
    log it as unanswered so we can later add it to Predefined Queries.
    """
    try:
        content = _post(
            [
                {"role": "system", "content": SCHEMA_DESCRIPTION},
                {"role": "user",   "content": user_question},
            ],
            temperature=0.2,
            max_tokens=500,
        )
        sql = _clean(content)

        # --- sanity checks on the returned SQL ---
        bad_sql = (
            not sql
            or sql.strip().lower() in {"", "none;", "null;"}
            or "select" not in sql.lower()  # must be an SQL SELECT
            or "forex_bars" not in sql.lower()  # must use our table
        )

        if bad_sql:
            append_unanswered(user_question, failed_sql=sql or "")
            return ""   # signals UI to show "Atlas shrugged"

        return sql

    except Exception as e:
        # If the call itself fails (timeout, network, etc.), log it too
        append_unanswered(user_question, failed_sql=f"ERROR: {e}")
        return ""


def interpret_business(question: str) -> str:
    """
    Business-level interpretation (for Atlas mode only).
    Keep it concise and non-technical.
    """
    prompt = (
        "Explain in 3–6 sentences what the following FX analytics request means in business terms. "
        "Avoid SQL language. Be specific, action-oriented, and useful for a trader or pricing analyst.\n\n"
        f"Request:\n{question}"
    )
    content = _post([{"role": "user", "content": prompt}], temperature=0.4, max_tokens=300)
    return content.strip()

def _extract_urls(text: str):
    # Accept plain and markdown formats
    url_re = re.compile(r"(https?://[^\s\)\]]+)", flags=re.IGNORECASE)
    return [m.group(1).rstrip(".,);]") for m in url_re.finditer(text)]

def _http_ok(url: str) -> bool:
    try:
        headers = {"User-Agent": "FXLens/1.0 (+https://local)"}
        # Try HEAD first; some sites block HEAD -> fallback to GET
        resp = requests.head(url, allow_redirects=True, timeout=6, headers=headers)
        if resp.status_code < 400 and "text/html" in resp.headers.get("Content-Type", "").lower():
            return True
        resp = requests.get(url, allow_redirects=True, timeout=8, headers=headers, stream=True)
        ct = resp.headers.get("Content-Type", "").lower()
        return (resp.status_code < 400) and ("text/html" in ct or "application/xhtml+xml" in ct)
    except Exception:
        return False

def suggest_learn_more_links(topic: str, max_links: int = 3) -> list[str]:
    """
    Use LM Studio (Qwen) to suggest 1–3 authoritative URLs for learning more.
    We then validate the URLs actually resolve (HTTP < 400) before returning.
    """
    prompt = (
        "Give 2–3 credible, directly relevant webpages (full URLs) where someone can learn more about "
        f"this topic:\n\n{topic}\n\n"
        "Rules:\n"
        "- ONLY output raw URLs, one per line (no text, no markdown).\n"
        "- Prefer authoritative sources (captrader,fxstreet,babypips,/trendspider).\n"
        "- Links must be directly about the topic, not generic homepages."
    )
    raw = _post([{"role": "user", "content": prompt}], temperature=0.2, max_tokens=220)
    candidates = _extract_urls(raw)
    # Deduplicate and validate
    seen = set()
    valid = []
    for url in candidates:
        if url in seen:
            continue
        seen.add(url)
        if _http_ok(url):
            valid.append(url)
        if len(valid) >= max_links:
            break
    return valid

def health_check() -> bool:
    try:
        r = requests.get(QWEN_API_URL.replace("/chat/completions", "/models"), timeout=5)
        r.raise_for_status()
        return True
    except Exception:
        return False
