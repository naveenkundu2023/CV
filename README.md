Executive Job Screener + CV Manager + Application Centre
A Streamlit MVP for managing senior leadership job opportunities, storing CV versions,
scoring role fit, preparing application materials, and tracking application progress.
Included
- app.py — Streamlit application
- requirements.txt — Python dependencies
- app.py.txt — copy-friendly version of the Python source
Important limitations
This MVP does not scrape LinkedIn, Indeed, or employer websites, and it does not
bypass login, CAPTCHA, or application-site controls. It can prepare an application,
download the selected CV and cover letter, open an employer's application page, and
track whether you have applied. Actual direct submission requires an authorized API or
supported application integration.

The default database and CV storage are local. On Streamlit Community Cloud, local
storage may be ephemeral. For durable private storage and multi-device use, connect a
managed database (for example, Supabase/PostgreSQL) and private object storage.
Run locally
1. Install Python 3.10 or newer.
2. Extract the project folder.
3. Open a terminal in that folder.
4. Create and activate a virtual environment (optional but recommended):
   python -m venv .venv
   # Windows:
   .venv\Scripts\activate
   # macOS/Linux:
   source .venv/bin/activate
5. Install dependencies:
   pip install -r requirements.txt
6. Start the app:
   streamlit run app.py
Deploy on Streamlit Community Cloud
1. Create a private GitHub repository for this project.
2. Add app.py, requirements.txt, and this README.
3. In Streamlit Community Cloud, create an app from the repository.
4. Set the main file path to app.py.
5. Deploy.
Do not commit your CV, database, secrets, or private application information to GitHub.
Add a .gitignore containing at least:
data/
.venv/
__pycache__/
.streamlit/secrets.toml
Workflow
1. Open CV Manager and upload your CV. Each upload is saved as a version.
2. Add jobs manually or import a CSV in Jobs.
3. Review the role-fit score and shortlist status.
4. In Application Centre, select a job and CV version.
5. Review the generated cover letter, download materials, and open the employer's
   application page where required.
6. Mark the application status and record follow-up dates.
7. Export the job and application trackers from Settings or Application Centre.
CSV import format
Required fields:
- company
- role
Optional fields:
- location
- region
- industry
- description
- job_url
- salary
- posted_date
Storage configuration
By default, files are stored under data/ and SQLite is used. You may configure local
paths with environment variables:
- APP_DATA_DIR
- APP_DB_PATH
For production, add authentication, access controls, managed persistence, encrypted
storage, backups, and retention controls before uploading sensitive CVs or application
records.
