"""
Executive Job Screener + CV Manager + Application Centre
Streamlit MVP.

Notes:
- Stores data in SQLite at ./data/job_screener.db by default.
- Local SQLite/filesystem storage may be ephemeral on Streamlit Cloud. For persistent
  multi-device use, configure a persistent database/object store (e.g. Supabase/S3).
- Does not scrape sites or bypass login, CAPTCHA, or platform controls.
- Supports application preparation, downloads, application tracking, and email drafts.
"""

from __future__ import annotations

import io
import os
import re
import sqlite3
import hashlib
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd
import streamlit as st

try:
    import pdfplumber
except Exception:
    pdfplumber = None

try:
    from docx import Document
except Exception:
    Document = None

APP_TITLE = "Executive Job Screener"
DATA_DIR = Path(os.getenv("APP_DATA_DIR", "data"))
CV_DIR = DATA_DIR / "cv_versions"
DB_PATH = Path(os.getenv("APP_DB_PATH", str(DATA_DIR / "job_screener.db")))
DATA_DIR.mkdir(parents=True, exist_ok=True)
CV_DIR.mkdir(parents=True, exist_ok=True)

st.set_page_config(page_title=APP_TITLE, page_icon="🎯", layout="wide")


# --------------------------- Database ---------------------------------------
def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS cv_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            stored_path TEXT NOT NULL,
            version_label TEXT NOT NULL,
            uploaded_at TEXT NOT NULL,
            text_content TEXT,
            sha256 TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company TEXT NOT NULL,
            role TEXT NOT NULL,
            location TEXT DEFAULT '',
            region TEXT DEFAULT '',
            industry TEXT DEFAULT '',
            description TEXT DEFAULT '',
            job_url TEXT DEFAULT '',
            source TEXT DEFAULT 'Manual',
            salary TEXT DEFAULT '',
            posted_date TEXT DEFAULT '',
            status TEXT DEFAULT 'Saved',
            score INTEGER DEFAULT 0,
            score_reason TEXT DEFAULT '',
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL,
            cv_version_id INTEGER,
            applied_at TEXT,
            status TEXT DEFAULT 'Prepared',
            cover_letter TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            follow_up_date TEXT DEFAULT '',
            application_url TEXT DEFAULT '',
            FOREIGN KEY(job_id) REFERENCES jobs(id),
            FOREIGN KEY(cv_version_id) REFERENCES cv_versions(id)
        );
        """)
        conn.commit()


init_db()


def query_df(sql: str, params=()) -> pd.DataFrame:
    with db() as conn:
        return pd.read_sql_query(sql, conn, params=params)


def execute(sql: str, params=()):
    with db() as conn:
        conn.execute(sql, params)
        conn.commit()


# --------------------------- CV helpers --------------------------------------
def extract_text(filename: str, raw: bytes) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf" and pdfplumber:
        try:
            with pdfplumber.open(io.BytesIO(raw)) as pdf:
                return "\n".join((p.extract_text() or "") for p in pdf.pages)
        except Exception:
            return ""
    if suffix == ".docx" and Document:
        try:
            doc = Document(io.BytesIO(raw))
            return "\n".join(p.text for p in doc.paragraphs)
        except Exception:
            return ""
    if suffix in (".txt", ".md"):
        return raw.decode("utf-8", errors="ignore")
    return ""


def save_cv(uploaded_file, version_label: str):
    raw = uploaded_file.getvalue()
    digest = hashlib.sha256(raw).hexdigest()
    # Avoid duplicate versions for identical files.
    existing = query_df("SELECT id FROM cv_versions WHERE sha256=?", (digest,))
    if not existing.empty:
        return int(existing.iloc[0]["id"]), "This exact file is already stored."
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", uploaded_file.name)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = CV_DIR / f"{stamp}_{safe_name}"
    path.write_bytes(raw)
    text = extract_text(uploaded_file.name, raw)
    execute(
        """INSERT INTO cv_versions(filename, stored_path, version_label, uploaded_at,
           text_content, sha256) VALUES(?,?,?,?,?,?)""",
        (uploaded_file.name, str(path), version_label, datetime.now().isoformat(timespec="seconds"),
         text, digest),
    )
    row = query_df("SELECT id FROM cv_versions WHERE sha256=?", (digest,))
    return int(row.iloc[0]["id"]), "CV version stored."


def get_cv_bytes(cv_id: int) -> Optional[bytes]:
    row = query_df("SELECT stored_path FROM cv_versions WHERE id=?", (cv_id,))
    if row.empty:
        return None
    path = Path(row.iloc[0]["stored_path"])
    return path.read_bytes() if path.exists() else None


# --------------------------- Job scoring -------------------------------------
ROLE_TERMS = {
    "COO": ["coo", "chief operating officer", "operations head", "operations director"],
    "Business Head": ["business head", "business unit head", "business director", "p&l head", "profit centre"],
    "VP": ["vice president", "vp ", "vp,", "vp-"],
    "CEO": ["ceo", "chief executive officer", "managing director", "md "],
}
INDUSTRY_TERMS = {
    "Education / EdTech": ["education", "edtech", "school", "k-12", "publishing", "learning"],
    "Enterprise Training / Skilling": ["training", "skilling", "certification", "workforce learning"],
    "IT / SaaS / Technology Services": ["saas", "software", "technology services", "it services", "digital"],
    "B2B Services": ["b2b", "services", "outsourcing", "consulting"],
}
GEO_TERMS = ["india", "middle east", "uae", "saudi", "qatar", "oman", "bahrain",
             "kuwait", "africa", "kenya", "nigeria", "south africa", "remote"]


def score_job(role: str, description: str, industry: str, region: str) -> tuple[int, str]:
    text = f"{role} {description}".lower()
    score = 0
    reasons = []
    for group, terms in ROLE_TERMS.items():
        if any(t in text for t in terms):
            score += 25
            reasons.append(f"Leadership match: {group}")
            break
    for group, terms in INDUSTRY_TERMS.items():
        if industry and industry.lower() == group.lower():
            score += 25
            reasons.append(f"Industry match: {group}")
            break
        if any(t in text for t in terms):
            score += 18
            reasons.append(f"Relevant sector: {group}")
            break
    if any(t in (region + " " + text).lower() for t in GEO_TERMS):
        score += 15
        reasons.append("Target geography")
    if any(t in text for t in ["p&l", "profit and loss", "revenue responsibility", "business ownership"]):
        score += 15
        reasons.append("P&L / business ownership")
    if any(t in text for t in ["transformation", "scale", "growth", "turnaround", "build"]):
        score += 10
        reasons.append("Growth / transformation mandate")
    if any(t in text for t in ["team of", "leadership team", "multiple functions", "cross-functional"]):
        score += 10
        reasons.append("Leadership scope")
    return min(score, 100), "; ".join(reasons) or "Limited keyword evidence; review manually."


def make_cover_letter(company: str, role: str, description: str = "") -> str:
    return f"""Dear Hiring Team,

I am writing to express my interest in the {role} opportunity at {company}.

I bring extensive leadership experience across business growth, P&L ownership, sales and operations, service delivery, and team development in education, technology-enabled services, and B2B environments. My experience includes building and scaling businesses, strengthening customer and partner relationships, and aligning commercial priorities with operational execution.

The opportunity to contribute to {company}'s next stage of growth is of particular interest. I would welcome a discussion on how my background could support the organisation's objectives.

Regards,
Naveen Kundu
"""


# --------------------------- UI ----------------------------------------------
st.title("🎯 Executive Job Screener")
st.caption("Job discovery • CV versions • application preparation • application tracking")

with st.sidebar:
    st.header("Navigation")
    page = st.radio("Open", ["Dashboard", "CV Manager", "Jobs", "Application Centre", "Settings"])
    st.divider()
    st.caption("Private MVP: keep your CV and database in a secure, persistent storage environment.")

if page == "Dashboard":
    jobs = query_df("SELECT * FROM jobs ORDER BY score DESC, created_at DESC")
    apps = query_df("SELECT * FROM applications")
    cvs = query_df("SELECT * FROM cv_versions")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Saved jobs", len(jobs))
    c2.metric("Applications", len(apps))
    c3.metric("CV versions", len(cvs))
    c4.metric("High-fit roles", int((jobs["score"] >= 70).sum()) if not jobs.empty else 0)
    st.subheader("Highest-fit opportunities")
    if jobs.empty:
        st.info("Add jobs in the Jobs tab or import a CSV.")
    else:
        st.dataframe(jobs[["company", "role", "location", "score", "status"]].head(10),
                     use_container_width=True, hide_index=True)
    st.subheader("Recent applications")
    if apps.empty:
        st.info("Prepared or submitted applications will appear here.")
    else:
        st.dataframe(query_df("""
            SELECT a.id, j.company, j.role, a.status, a.applied_at, a.follow_up_date
            FROM applications a JOIN jobs j ON j.id=a.job_id
            ORDER BY a.id DESC LIMIT 10
        """), use_container_width=True, hide_index=True)

elif page == "CV Manager":
    st.subheader("CV versions")
    st.write("Upload your CV and keep dated versions. The app retains the original file and extracted text when available.")
    with st.form("cv_upload_form"):
        file = st.file_uploader("Upload CV (PDF, DOCX, or TXT)", type=["pdf", "docx", "txt"])
        label = st.text_input("Version label", value=f"Base CV - {date.today().isoformat()}")
        submitted = st.form_submit_button("Save CV version")
    if submitted:
        if not file:
            st.error("Please select a CV file.")
        else:
            cv_id, message = save_cv(file, label.strip() or "CV")
            st.success(f"{message} Version ID: {cv_id}")
    cv_df = query_df("SELECT id, filename, version_label, uploaded_at FROM cv_versions ORDER BY id DESC")
    if not cv_df.empty:
        st.dataframe(cv_df, use_container_width=True, hide_index=True)
        cv_id = st.selectbox("Download stored CV", cv_df["id"].tolist(), format_func=lambda x: f"Version {x}")
        data = get_cv_bytes(int(cv_id))
        if data:
            fname = cv_df.loc[cv_df["id"] == cv_id, "filename"].iloc[0]
            st.download_button("Download selected CV", data, file_name=fname)
    else:
        st.info("No CV uploaded yet.")

elif page == "Jobs":
    st.subheader("Add a job")
    with st.form("job_form"):
        col1, col2 = st.columns(2)
        company = col1.text_input("Company *")
        role = col2.text_input("Role *")
        location = col1.text_input("Location")
        region = col2.selectbox("Market", ["India", "Middle East", "Africa", "Global / Remote", "Other"])
        industry = st.selectbox("Industry", [
            "Education / EdTech", "Enterprise Training / Skilling",
            "IT / SaaS / Technology Services", "Publishing / K-12", "B2B Services", "Other"
        ])
        url = st.text_input("Job URL")
        salary = st.text_input("Compensation (optional)")
        desc = st.text_area("Job description", height=180)
        save_job = st.form_submit_button("Save and score job")
    if save_job:
        if not company.strip() or not role.strip():
            st.error("Company and role are required.")
        else:
            score, reason = score_job(role, desc, industry, region)
            execute("""INSERT INTO jobs(company, role, location, region, industry, description,
                      job_url, salary, score, score_reason, created_at)
                      VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                    (company.strip(), role.strip(), location, region, industry, desc, url, salary,
                     score, reason, datetime.now().isoformat(timespec="seconds")))
            st.success(f"Job saved. Fit score: {score}/100")
            st.caption(reason)

    st.divider()
    st.subheader("Import jobs from CSV")
    st.caption("Expected columns: company, role. Optional: location, region, industry, description, job_url, salary, posted_date.")
    csv_file = st.file_uploader("Choose job CSV", type=["csv"], key="jobs_csv")
    if csv_file:
        data = pd.read_csv(csv_file).fillna("")
        st.dataframe(data.head(), use_container_width=True)
        if st.button("Import CSV jobs"):
            count = 0
            for _, r in data.iterrows():
                comp, rol = str(r.get("company", "")).strip(), str(r.get("role", "")).strip()
                if not comp or not rol:
                    continue
                desc = str(r.get("description", ""))
                industry = str(r.get("industry", ""))
                region = str(r.get("region", ""))
                score, reason = score_job(rol, desc, industry, region)
                execute("""INSERT INTO jobs(company, role, location, region, industry, description,
                          job_url, salary, posted_date, score, score_reason, created_at)
                          VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (comp, rol, str(r.get("location", "")), region, industry, desc,
                         str(r.get("job_url", "")), str(r.get("salary", "")),
                         str(r.get("posted_date", "")), score, reason,
                         datetime.now().isoformat(timespec="seconds")))
                count += 1
            st.success(f"Imported {count} jobs.")

    jobs = query_df("SELECT * FROM jobs ORDER BY score DESC, id DESC")
    if not jobs.empty:
        st.subheader("Saved jobs")
        st.dataframe(jobs[["id", "company", "role", "location", "industry", "score", "status", "job_url"]],
                     use_container_width=True, hide_index=True)
        job_id = st.selectbox("Select job to update", jobs["id"].tolist())
        new_status = st.selectbox("Job status", ["Saved", "Shortlisted", "Preparing", "Applied", "Interview", "Offer", "Rejected", "Closed"])
        if st.button("Update job status"):
            execute("UPDATE jobs SET status=? WHERE id=?", (new_status, int(job_id)))
            st.success("Status updated.")

elif page == "Application Centre":
    st.subheader("Prepare and manage applications")
    jobs = query_df("SELECT id, company, role, job_url FROM jobs ORDER BY score DESC, id DESC")
    cvs = query_df("SELECT id, filename, version_label FROM cv_versions ORDER BY id DESC")
    if jobs.empty:
        st.info("Save a job first in the Jobs tab.")
    else:
        selected_job = st.selectbox("Choose job", jobs["id"].tolist(),
            format_func=lambda x: f"{jobs.loc[jobs.id == x, 'company'].iloc[0]} — {jobs.loc[jobs.id == x, 'role'].iloc[0]}")
        job_row = jobs[jobs.id == selected_job].iloc[0]
        cv_id = st.selectbox("CV version", cvs["id"].tolist() if not cvs.empty else [None],
            format_func=lambda x: (f"Version {x}: " + str(cvs.loc[cvs.id == x, "version_label"].iloc[0])) if x is not None and not cvs.empty else "No CV stored")
        cover = st.text_area("Cover letter / application message",
                             value=make_cover_letter(job_row["company"], job_row["role"]), height=260)
        app_url = st.text_input("Application URL", value=str(job_row["job_url"] or ""))
        st.caption("Review the CV and message before sending. This MVP prepares and tracks applications; it does not automate restricted third-party forms.")
        cv_bytes = get_cv_bytes(int(cv_id)) if cv_id is not None else None
        if cv_bytes:
            cv_filename = cvs.loc[cvs.id == cv_id, "filename"].iloc[0]
            st.download_button("Download CV for this application", cv_bytes, file_name=cv_filename)
        st.download_button("Download cover letter", cover, file_name="cover_letter.txt")
        col_a, col_b = st.columns(2)
        if app_url and col_a.button("Open application page"):
            st.link_button("Continue on employer site", app_url)
        if col_b.button("Save application as Prepared"):
            execute("""INSERT INTO applications(job_id, cv_version_id, status, cover_letter,
                      application_url, notes) VALUES(?,?,?,?,?,?)""",
                    (int(selected_job), int(cv_id) if cv_id is not None else None,
                     "Prepared", cover, app_url, "Prepared in Streamlit; final submission may be external."))
            st.success("Application saved as Prepared.")
        st.divider()
        st.subheader("Mark an application as submitted")
        app_records = query_df("""
            SELECT a.id, j.company, j.role, a.status
            FROM applications a JOIN jobs j ON j.id=a.job_id ORDER BY a.id DESC
        """)
        if not app_records.empty:
            app_id = st.selectbox("Application record", app_records["id"].tolist(),
                format_func=lambda x: f"#{x} — {app_records.loc[app_records.id == x, 'company'].iloc[0]} / {app_records.loc[app_records.id == x, 'role'].iloc[0]}")
            app_status = st.selectbox("Update application status", ["Prepared", "Applied", "Interview", "Offer", "Rejected", "Withdrawn"])
            followup = st.date_input("Follow-up date", value=date.today() + timedelta(days=7))
            notes = st.text_area("Application notes", placeholder="Confirmation number, recruiter, next steps...")
            if st.button("Save application update"):
                applied_at = datetime.now().isoformat(timespec="seconds") if app_status == "Applied" else None
                execute("UPDATE applications SET status=?, applied_at=COALESCE(?, applied_at), follow_up_date=?, notes=? WHERE id=?",
                        (app_status, applied_at, followup.isoformat(), notes, int(app_id)))
                st.success("Application record updated.")

    apps = query_df("""
        SELECT a.id, j.company, j.role, a.status, a.applied_at, a.follow_up_date, a.notes
        FROM applications a JOIN jobs j ON j.id=a.job_id ORDER BY a.id DESC
    """)
    if not apps.empty:
        st.subheader("Application tracker")
        st.dataframe(apps, use_container_width=True, hide_index=True)
        st.download_button("Export application tracker CSV", apps.to_csv(index=False).encode("utf-8"),
                           file_name="application_tracker.csv", mime="text/csv")

elif page == "Settings":
    st.subheader("Settings and data portability")
    st.write(f"Database path: `{DB_PATH}`")
    st.write(f"CV storage path: `{CV_DIR}`")
    st.warning("On Streamlit Community Cloud, local files may not be durable across app restarts or redeployments. For persistent private storage, use a managed database and private object storage.")
    all_jobs = query_df("SELECT * FROM jobs")
    all_apps = query_df("SELECT * FROM applications")
    all_cvs = query_df("SELECT id, filename, version_label, uploaded_at FROM cv_versions")
    st.download_button("Export jobs CSV", all_jobs.to_csv(index=False).encode("utf-8"),
                       file_name="jobs_export.csv", mime="text/csv")
    st.download_button("Export applications CSV", all_apps.to_csv(index=False).encode("utf-8"),
                       file_name="applications_export.csv", mime="text/csv")
    st.download_button("Export CV version index CSV", all_cvs.to_csv(index=False).encode("utf-8"),
                       file_name="cv_index.csv", mime="text/csv")

st.caption("Executive Job Screener MVP • Review every application before submission.")
