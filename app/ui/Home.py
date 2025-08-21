# app/ui/Home.py
import streamlit as st
from datetime import datetime, timedelta
from app.services.db import run_query
from app.services.mbridge import (
    ask_qwen,
    interpret_business,
    suggest_learn_more_links,
    health_check,
)
from app.services.queries import load_queries
from app.services.qlog import append_unanswered   # <-- added

# Load predefined queries (expects keys including interpretation, learn_more)
queries = load_queries()

st.title("FXLens")

# Sidebar
st.sidebar.header("Options")
mode = st.sidebar.radio("Choose query type", ["FXLens Insights", "Ask Atlas"])

with st.sidebar:
    st.write("### Atlas Status")
    st.write(health_check())

# Date range filters 
st.sidebar.subheader("Date Range Filter")
default_end = datetime.utcnow().date()
default_start = default_end - timedelta(days=7)
start_date = st.sidebar.date_input("Start Date", default_start)
end_date = st.sidebar.date_input("End Date", default_end)

# Threshold input
threshold_pips = st.sidebar.number_input(
    "Threshold (pips)", min_value=1, max_value=500, value=50, step=5
)

gap_threshold = st.sidebar.number_input(
    "Min Opening Gap (pips)", min_value=1, max_value=200, value=5, step=1
)

min_daily_pips = st.sidebar.number_input(
    "Min Daily Pip Range", min_value=1, max_value=2000, value=20, step=5
)


params = {"start_date": str(start_date), 
          "end_date": str(end_date),
          "threshold_pips": threshold_pips, 
          "min_gap_pips": gap_threshold,
          "min_daily_pips": min_daily_pips
          }

# Query modes 
if mode == "FXLens Insights":
    st.subheader("Choose a predefined question")
    qlist = [q["natural_language_question"] for q in queries]
    choice = st.selectbox("Select a question", qlist)

    if st.button("Ask FXLens"):
        selected = next(q for q in queries if q["natural_language_question"] == choice)
        sql = selected["sql"]
        interpretation = selected.get("interpretation") or selected.get("business_interpretation") or "—"
        learn_more = selected.get("learn_more")

        st.write("Results:")
        try:
            df = run_query(sql, params=params)
            st.dataframe(df)

            # YAML interpretation (business level)
            if interpretation and interpretation.strip() != "—":
                st.markdown(f"**Business interpretation:** {interpretation}")

            # Learn more (directly from YAML)
            if learn_more:
                st.markdown("**Learn more:**")
                if isinstance(learn_more, (list, tuple)):
                    for u in learn_more:
                        st.markdown(f"- [{u}]({u})")
                else:
                    st.markdown(f"- [{learn_more}]({learn_more})")

        except Exception as e:
            st.error(f"FXLens is foggy on this one. If it’s relevant, I’ll add it to Curated Queries")

elif mode == "Ask Atlas":
    st.subheader("Ask your own question in natural language")
    user_question = st.text_area("Enter your question:",
                                 value="What is the maximum closing price of EUR/USD in the last 30 days?",
                                 placeholder="Type your FX question here…")

    if st.button("Ask Atlas"):
        with st.spinner("Atlas is thinking..."):
            sql = ask_qwen(user_question)

        # Treat empty/invalid SQL as unanswered and log it
        if not sql or not str(sql).strip() or str(sql).strip().lower() in {"none;", "null;"}:
            append_unanswered(user_question, failed_sql=sql or "")
            st.warning("Sorry, I couldn't generate a valid SQL for that. I've logged your question so we can improve.")
        elif str(sql).lower().startswith("error"):
            # If your ask_qwen ever returns an "Error ..." string, log it too
            append_unanswered(user_question, failed_sql=sql)
            st.error(sql)
        else:
            st.write("Results:")
            try:
                df = run_query(sql, params=params)
                st.dataframe(df)

                # Business interpretation (Qwen, not SQL explanation)
                explanation = interpret_business(user_question)
                st.markdown(f"**Business interpretation:** {explanation}")

                # Learn more via LM Studio suggestions (validated)
                links = suggest_learn_more_links(explanation or user_question)
                if links:
                    st.markdown("**Learn more:**")
                    for u in links:
                        st.markdown(f"- [{u}]({u})")

            except Exception as e:
                # If the generated SQL fails at execution, also log as unanswered
                append_unanswered(user_question, failed_sql=sql)
                st.error(f"Atlas shrugged!!! — He can't answer that one right now.")
                st.info(
                        "I’ll run this query manually and, if the data supports it, "
                        "I'll add it to the FXLens Insights, so it’s available next time."
                 )
