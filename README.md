# FXLens – Forex Analysis App  

FXLens is a lightweight Forex analytics dashboard built with [Streamlit](https://streamlit.io/).  
It allows users to explore EUR/USD price action, analyze pip movements, and view curated insights.  

---

## Features  
- Query historical EUR/USD data with natural-language questions  
- Pre-curated insights (FXLens Curated) for quick exploration  
- Error handling with “Atlas Shrugged” messages for unsupported queries  
- Logs unanswered queries for continuous improvement  

---

## Run Locally  

1. Clone the repo:  
   ```bash
   git clone https://github.com/kina-re/fxlens-app.git
   cd fxlens-app

2. Create and activate environment (Python 3.10.9):
    pip install -r requirements.txt

3. Start the app:
    streamlit run app.py
   
Project Structure
   fxlens-app/
│── app.py                  # Main Streamlit app
│── requirements.txt        # Dependencies
│── unanswered_queries.csv  # Logged unanswered queries
│── queries/                # Curated SQL queries
│── README.md
│── .gitignore

License

MIT License – feel free to use and adapt.

Demo video coming soon.
The app will also be available on Streamlit Cloud once deployed.






