# app/ui/Home.py
# app/ui/Home.py
import streamlit as st
from datetime import datetime, timedelta
from app.services.db import run_query
from app.services.mbridge import ask_qwen, health_check
from app.services.queries import load_queries

# Load predefined queries
queries = load_queries()

st.title("FXLens")

# Sidebar
st.sidebar.header("Options")
mode = st.sidebar.radio("Choose query type", ["Predefined query", "Ask Atlas"])

# Qwen health check
with st.sidebar:
    st.write("### Atlas Status")
    st.write(health_check())

# --- Date range filters ---
st.sidebar.subheader("Date Range Filter")
default_end = datetime.utcnow().date()
default_start = default_end - timedelta(days=7)
start_date = st.sidebar.date_input("Start Date", default_start)
end_date = st.sidebar.date_input("End Date", default_end)

params = {"start_date": str(start_date), "end_date": str(end_date)}

# --- Query modes ---
if mode == "Predefined query":
    st.subheader("Choose a predefined question")
    qlist = [q["natural_language_question"] for q in queries]
    choice = st.selectbox("Select a question", qlist)

    if st.button("Run Predefined Query"):
        selected = next(q for q in queries if q["natural_language_question"] == choice)
        sql = selected["sql"]

        st.write("📊 Results:")
        try:
            df = run_query(sql, params=params)
            st.dataframe(df)
        except Exception as e:
            st.error(f"Error running query: {e}")

elif mode == "Ask Atlas":
    st.subheader("Ask your own question in natural language")
    user_question = st.text_area("Enter your question:")

    if st.button("Ask Atlas"):
        with st.spinner("Atlas is thinking..."):
            sql = ask_qwen(user_question)

        if sql.lower().startswith("error"):
            st.error(sql)
        else:
            st.write("📊 Results:")
            try:
                df = run_query(sql, params=params)
                st.dataframe(df)
            except Exception as e:
                st.error(f"Error running query: {e}")
