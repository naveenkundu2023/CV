Executive Job Screener — Automatic CV-driven Job Discovery
This version extracts a draft profile from an uploaded CV, searches configured job sources, filters listings by age and explicit experience requirements, scores matches, and displays them on the dashboard.
Your configured search rules
- Markets: India, Middle East, Africa
- Posting age: up to 90 days
- Exclude vacancies that explicitly require fewer than 15 years of experience
- Position and industry terms are extracted from the CV and can be edited in CV & Profile
- Match by leadership role, industry, responsibilities, P&L, sales, operations, leadership, transformation and market
Files
- app.py: complete Streamlit app
- app.py.txt: same code in text format for copying
- requirements.txt: Python dependencies
Run locally
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
Deploy
Push app.py and requirements.txt to GitHub and set Streamlit's main file to app.py. Upload the CV in CV & Profile, review the extracted profile, then click Scan for new and refreshed jobs on the dashboard.
Job sources
- Arbeitnow: public API, no key required. Coverage in India, Middle East and Africa may be limited.
- Adzuna: API credentials required. Add to Streamlit Cloud → app Settings → Secrets:
ADZUNA_APP_ID = "your_app_id"
ADZUNA_APP_KEY = "your_app_key"
- Jooble: API key required:
JOOBLE_API_KEY = "your_jooble_key"
This code maps India to Adzuna's India market, Middle East to UAE, and Africa to South Africa as representative countries. Broader regional coverage requires country-by-country queries and supported API access. The app cannot guarantee all available vacancies because job-source coverage and API plans vary.
Filters and matching
- Listings older than 90 days are excluded; listings without a reliable date are excluded too.
- If a job explicitly requires fewer than 15 years of experience, it is excluded. If no years are stated, the app cannot know the employer's minimum and ranks the job by profile fit.
- Scores are heuristic and should be reviewed, not treated as guarantees.
- Click Scan to refresh. Continuous scanning requires a separate scheduler; Streamlit Community Cloud does not run a scan continuously while the app sleeps.
Privacy and persistence
Do not commit your CV, job database or API secrets to a public GitHub repository. Default local storage may be ephemeral on Streamlit Cloud. For reliable CV history, use a managed database and private object storage. Add to .gitignore:
data/
.venv/
__pycache__/
.streamlit/secrets.toml
This app prepares links and tracks jobs; it does not bypass third-party login/CAPTCHA or automatically submit job applications.
