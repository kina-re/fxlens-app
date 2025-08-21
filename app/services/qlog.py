import os
import csv
from datetime import datetime

LOG_FILE = "unanswered_queries.csv"

def append_unanswered(question: str, failed_sql: str = None):
    """
    Append an unanswered question (and optional failed SQL) to a CSV log.
    """
    file_exists = os.path.isfile(LOG_FILE)
    with open(LOG_FILE, mode="a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["timestamp", "question", "failed_sql"])
        writer.writerow([datetime.utcnow().isoformat(), question, failed_sql or ""])

# Alias for backward compatibility
log_failed_query = append_unanswered
