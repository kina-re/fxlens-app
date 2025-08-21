# app/ui/Admin.py
import os
import streamlit as st
import pandas as pd
from app.services.qlog import read_unanswered, log_path, _ensure_log_exists

st.set_page_config(page_title="Admin • Unanswered Questions", layout="wide")
st.title("🛠️ Admin • Unanswered Qwen Questions")

rows = read_unanswered()
if not rows:
    st.info("No unanswered questions logged yet.")
else:
    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True)

    st.download_button(
        "📥 Download log as CSV",
        data=df.to_csv(index=False).encode("utf-8"),
        file_name="unanswered_questions.csv",
        mime="text/csv",
        use_container_width=True
    )
    st.caption(f"Log file: `{log_path()}`")

    # Clear log option
    st.subheader("Maintenance")
    confirm = st.checkbox("✅ I confirm I want to clear the unanswered questions log")
    if st.button("🗑️ Clear Log", use_container_width=True, disabled=not confirm):
        open(log_path(), "w").write("")  # truncate
        _ensure_log_exists()  # re-add headers
        st.success("Log cleared!")
        st.experimental_rerun()
