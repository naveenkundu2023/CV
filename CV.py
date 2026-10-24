import io, os, re, json, hashlib, sqlite3
from pathlib import Path
from datetime import datetime, timedelta, timezone, date
import pandas as pd
import requests
import streamlit as st
try:
    import pdfplumber
except Exception: pdfplumber=None
try:
    from docx import Document
except Exception: Document=None

st.set_page_config(page_title='Executive Job Screener', page_icon='🎯', layout='wide')
DATA=Path(os.getenv('APP_DATA_DIR','data')); DATA.mkdir(exist_ok=True); (DATA/'cv_versions').mkdir(exist_ok=True)
DB=Path(os.getenv('APP_DB_PATH',str(DATA/'jobs.db')))

def conn():
    c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c
def init():
    with conn() as c:
        c.executescript('''CREATE TABLE IF NOT EXISTS cvs(id INTEGER PRIMARY KEY,filename TEXT,path TEXT,label TEXT,uploaded TEXT,text TEXT,hash TEXT UNIQUE);
        CREATE TABLE IF NOT EXISTS profile(id INTEGER PRIMARY KEY CHECK(id=1),json TEXT,updated TEXT);
        CREATE TABLE IF NOT EXISTS jobs(id INTEGER PRIMARY KEY,job_key TEXT UNIQUE,company TEXT,role TEXT,location TEXT,market TEXT,description TEXT,url TEXT,source TEXT,posted TEXT,years INTEGER,score INTEGER,reasons TEXT,last_seen TEXT);
        CREATE TABLE IF NOT EXISTS scans(id INTEGER PRIMARY KEY,at TEXT,sources TEXT,queries TEXT,count INTEGER,notes TEXT);
        CREATE TABLE IF NOT EXISTS shortlist(id INTEGER PRIMARY KEY,job_key TEXT UNIQUE,status TEXT,notes TEXT,updated TEXT);''')
def df(sql,params=()):
    with conn() as c: return pd.read_sql_query(sql,c,params=params)
def run(sql,params=()):
    with conn() as c: c.execute(sql,params); c.commit()
def now(): return datetime.now().astimezone().isoformat(timespec='seconds')
def secret(k):
    try: return st.secrets.get(k,os.getenv(k,''))
    except Exception: return os.getenv(k,'')
def extract(name,raw):
    try:
        if name.lower().endswith('.pdf') and pdfplumber:
            with pdfplumber.open(io.BytesIO(raw)) as p: return '\n'.join(x.extract_text() or '' for x in p.pages)
        if name.lower().endswith('.docx') and Document: return '\n'.join(x.text for x in Document(io.BytesIO(raw)).paragraphs)
        if name.lower().endswith('.txt'): return raw.decode('utf-8',errors='ignore')
    except Exception: pass
    return ''
def profile_from(text):
    t=text.lower()
    roles=[]
    for label,terms in [('CEO / Managing Director',['ceo','chief executive','managing director']),('COO / Operations Head',['coo','chief operating','operations head','service delivery']),('Business Head / P&L Head',['business head','p&l','profit centre','profit center']),('VP / Vice President',['vice president','vp sales','vp operations']),('Sales / Commercial Leadership',['sales','business development','commercial']),('Country / Regional Head',['country head','regional head','international'])]:
        if any(x in t for x in terms): roles.append(label)
    industry_terms={'Education / EdTech / K-12':['education','edtech','k-12','school','preschool','learning'],'Enterprise Training / Skilling':['training','skilling','certification'],'IT / SaaS / Technology Services':['saas','software','technology','digital','ict','erp'],'Publishing':['publishing','publisher','books','content'],'B2B Services':['b2b','service delivery','consulting','operations']}
    industries=[k for k,v in industry_terms.items() if any(x in t for x in v)]
    skill_terms={'P&L / Business Ownership':['p&l','profit centre','profit center','business head','revenue'],'Sales & Business Development':['sales','business development','acquisition','channel'],'Operations & Service Delivery':['operations','service delivery'],'Team Leadership':['team','leadership','people'],'Partner / Franchise Management':['franchise','partner network','channel partner'],'International Business':['middle east','uae','international','overseas'],'Business Growth / Transformation':['growth','scaled','transformation','turnaround'],'Product / Content / Digital':['product','content','digital','saas','technology']}
    skills=[k for k,v in skill_terms.items() if any(x in t for x in v)]
    years=[int(x) for x in re.findall(r'\b(19[89]\d|20[012]\d)\b',text)]
    years=[x for x in years if 1980<=x<datetime.now().year]
    exp=max(15,datetime.now().year-min(years)) if years else 15
    return {'roles':roles or ['VP / Vice President','Business Head / P&L Head','COO / Operations Head'],'industries':industries or list(industry_terms),'skills':skills,'experience_years':min(exp,50),'markets':['India','Middle East','Africa'],'days':90,'min_required':15}
def get_profile():
    x=df('SELECT json FROM profile WHERE id=1')
    return json.loads(x.iloc[0,0]) if not x.empty else None
def save_profile(p): run('INSERT INTO profile(id,json,updated) VALUES(1,?,?) ON CONFLICT(id) DO UPDATE SET json=excluded.json,updated=excluded.updated',(json.dumps(p),now()))
ROLE_TERMS={'CEO / Managing Director':['ceo','chief executive','managing director','country manager','general manager'],'COO / Operations Head':['coo','chief operating','operations director','head of operations','service delivery'],'Business Head / P&L Head':['business head','business unit head','p&l','profit and loss','business director','general manager'],'VP / Vice President':['vice president','vp ','vp,','vp-'],'Sales / Commercial Leadership':['sales director','head of sales','commercial director','business development director'],'Country / Regional Head':['country head','country director','regional head','regional director']}
IND={'Education / EdTech / K-12':['education','edtech','k-12','school','preschool','learning'],'Enterprise Training / Skilling':['training','skilling','certification','corporate learning'],'IT / SaaS / Technology Services':['saas','software','technology services','it services','digital solutions','ict'],'Publishing':['publishing','publisher','books','digital content'],'B2B Services':['b2b','services','consulting','outsourcing','service delivery']}
MARKETS={'India':['india','mumbai','delhi','bengaluru','bangalore','hyderabad','chennai','pune','gurugram','gurgaon','noida','ahmedabad','kolkata'],'Middle East':['middle east','uae','united arab emirates','dubai','abu dhabi','saudi','riyadh','qatar','doha','oman','muscat','bahrain','kuwait','gcc','jeddah'],'Africa':['africa','kenya','nairobi','nigeria','lagos','south africa','johannesburg','cape town','ghana','egypt','morocco','rwanda','uganda','tanzania']}
def parse_date(x):
    try:
        d=pd.to_datetime(x,utc=True,errors='coerce'); return None if pd.isna(d) else d.to_pydatetime()
    except Exception:return None
def market_of(loc,desc=''):
    l=(loc or '').lower()
    for m,terms in MARKETS.items():
        if any(t in l for t in terms): return m
    return ''
def req_years(text):
    vals=[]
    for p in [r'(\d{1,2})\s*\+?\s*(?:years|yrs)\s+(?:of\s+)?(?:experience|exp)',r'(?:experience|exp)\s+(?:of\s+)?(\d{1,2})\s*\+?\s*(?:years|yrs)',r'minimum\s+of\s+(\d{1,2})\s+(?:years|yrs)']:
        vals += [int(x) for x in re.findall(p,(text or '').lower())]
    return max(vals) if vals else None
def score(title,desc,market,p):
    t=f'{title} {desc}'.lower(); s=0; reasons=[]
    if any(any(term in title.lower() for term in ROLE_TERMS.get(r,[r.lower()])) for r in p['roles']): s+=28; reasons.append('Leadership role match')
    elif any(x in t for x in ['p&l','profit and loss','business unit','revenue growth','operations leadership']): s+=14; reasons.append('Related leadership responsibilities')
    for i in p['industries']:
        if any(x in t for x in IND.get(i,[i.lower()])): s+=22; reasons.append('Industry: '+i); break
    skillterms={'P&L / Business Ownership':['p&l','profit and loss','business ownership','profitability'],'Sales & Business Development':['sales','business development','revenue','commercial'],'Operations & Service Delivery':['operations','service delivery'],'Team Leadership':['team','leadership','people management'],'Partner / Franchise Management':['partner','franchise','channel'],'International Business':['international','global','regional','gcc'],'Business Growth / Transformation':['growth','scale','transformation','turnaround','expansion'],'Product / Content / Digital':['product','content','digital','saas','technology']}
    hits=sum(1 for sk in p['skills'] if any(x in t for x in skillterms.get(sk,[sk.lower()])))
    s+=min(25,hits*5)
    if hits: reasons.append(f'{hits} functional matches')
    if market in p['markets']: s+=15; reasons.append('Target market: '+market)
    if any(x in t for x in ['15+ years','15 years','20 years','senior leadership','executive leadership']): s+=8; reasons.append('Senior experience level')
    return min(100,s),'; '.join(reasons) or 'Keyword overlap; review manually'
def key_for(j): return hashlib.sha256('|'.join(str(j.get(k,'' )).lower().strip() for k in ['company','title','location','url']).encode()).hexdigest()
def search_arbeitnow(query):
    out=[]
    for page in [1,2,3]:
        try:
            r=requests.get('https://www.arbeitnow.com/api/job-board-api',params={'page':page},timeout=15,headers={'User-Agent':'ExecutiveJobScreener/1.0'}); r.raise_for_status()
            items=r.json().get('data',[])
            if not items: break
            for x in items:
                searchable=f"{x.get('title','')} {x.get('description','')} {x.get('location','')}".lower()
                if any(z.lower() in searchable for z in query.split()): out.append({'title':x.get('title',''),'company':x.get('company_name',''),'location':x.get('location',''),'description':re.sub('<[^>]+>',' ',x.get('description','')),'url':x.get('url',''),'posted':x.get('created_at'),'source':'Arbeitnow'})
        except Exception as e: return out,[f'Arbeitnow: {e}']
    return out,[]
def search_adzuna(query,market):
    aid,akey=secret('ADZUNA_APP_ID'),secret('ADZUNA_APP_KEY')
    if not aid or not akey:return [],['Adzuna not configured: add ADZUNA_APP_ID and ADZUNA_APP_KEY in Streamlit Secrets.']
    country={'India':'in','Middle East':'ae','Africa':'za'}.get(market,'in')
    try:
        r=requests.get(f'https://api.adzuna.com/v1/api/jobs/{country}/search/1',params={'app_id':aid,'app_key':akey,'results_per_page':50,'what':query,'max_days_old':90,'content-type':'application/json'},timeout=18);r.raise_for_status()
        return [{'title':x.get('title',''),'company':(x.get('company') or {}).get('display_name',''),'location':(x.get('location') or {}).get('display_name',''),'description':x.get('description',''),'url':x.get('redirect_url',''),'posted':x.get('created'),'source':'Adzuna'} for x in r.json().get('results',[])],[]
    except Exception as e:return [],[f'Adzuna {market}: {e}']
def search_jooble(query,market):
    k=secret('JOOBLE_API_KEY')
    if not k:return [],['Jooble not configured: add JOOBLE_API_KEY in Streamlit Secrets.']
    try:
        r=requests.post(f'https://jooble.org/api/{k}',json={'keywords':query,'location':{'India':'India','Middle East':'United Arab Emirates','Africa':'South Africa'}.get(market,market)},timeout=18);r.raise_for_status()
        return [{'title':x.get('title',''),'company':x.get('company',''),'location':x.get('location',''),'description':x.get('snippet',''),'url':x.get('link',''),'posted':x.get('updated'),'source':'Jooble'} for x in r.json().get('jobs',[])],[]
    except Exception as e:return [],[f'Jooble {market}: {e}']
def queries_for(p):
    q=[x.replace(' / ',' ') for x in p['roles']]+[x.replace(' / ',' ') for x in p['industries'][:3]]+['business head P&L','COO operations','VP business growth','CEO managing director']
    return list(dict.fromkeys(q))[:8]
def scan(p):
    qs=queries_for(p); raw=[]; notes=[]
    # Public feed has limited geographic coverage; API providers broaden results.
    for q in qs[:4]:
        x,n=search_arbeitnow(q);raw+=x;notes+=n
    for m in p['markets']:
        for q in qs[:3]:
            x,n=search_adzuna(q,m);raw+=x;notes+=n
        for q in qs[:2]:
            x,n=search_jooble(q,m);raw+=x;notes+=n
    unique={}
    for j in raw: unique[key_for(j)]=j
    cutoff=datetime.now(timezone.utc)-timedelta(days=int(p['days'])); matched=[]
    for j in unique.values():
        d=parse_date(j.get('posted'))
        if not d or d<cutoff: continue
        loc=j.get('location',''); market=market_of(loc,j.get('description',''))
        if market not in p['markets']: continue
        yr=req_years(j.get('title','')+' '+j.get('description',''))
        if yr is not None and yr<int(p['min_required']): continue
        sc,why=score(j.get('title',''),j.get('description',''),market,p)
        if sc<28: continue
        j.update({'key':key_for(j),'market':market,'posted_date':d.date().isoformat(),'years':yr,'score':sc,'reasons':why})
        matched.append(j)
    for j in matched:
        run('''INSERT INTO jobs(job_key,company,role,location,market,description,url,source,posted,years,score,reasons,last_seen) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(job_key) DO UPDATE SET company=excluded.company,role=excluded.role,location=excluded.location,market=excluded.market,description=excluded.description,url=excluded.url,source=excluded.source,posted=excluded.posted,years=excluded.years,score=excluded.score,reasons=excluded.reasons,last_seen=excluded.last_seen''',
        (j['key'],j.get('company','Company not listed'),j.get('title',''),j.get('location',''),j['market'],j.get('description','')[:12000],j.get('url',''),j.get('source',''),j['posted_date'],j['years'],j['score'],j['reasons'],now()))
    # Expire old jobs but retain historical records.
    run('DELETE FROM jobs WHERE posted < ?',((datetime.now(timezone.utc)-timedelta(days=int(p['days']))).date().isoformat(),))
    run('INSERT INTO scans(at,sources,queries,count,notes) VALUES(?,?,?,?,?)',(now(),'Arbeitnow, Adzuna, Jooble',json.dumps(qs),len(matched),' | '.join(dict.fromkeys(notes))[:4000]))
    return len(matched),notes,qs

init()
st.title('🎯 Executive Job Screener')
st.caption('CV-driven automatic job discovery • India • Middle East • Africa • Vacancies up to 90 days old')
page=st.sidebar.radio('Navigation',['Dashboard & Scan','CV & Profile','Shortlist','Scan History','Setup'])
p=get_profile()
if page=='CV & Profile':
    st.subheader('Upload CV and extract search profile')
    f=st.file_uploader('CV file (PDF, DOCX, TXT)',type=['pdf','docx','txt']); label=st.text_input('CV version label',value=f'CV {date.today().isoformat()}')
    if st.button('Save CV and extract profile'):
        if not f: st.error('Choose a CV first.')
        else:
            raw=f.getvalue(); digest=hashlib.sha256(raw).hexdigest(); existing=df('SELECT id FROM cvs WHERE hash=?',(digest,))
            if existing.empty:
                safe=re.sub(r'[^A-Za-z0-9._-]+','_',f.name); path=DATA/'cv_versions'/f'{datetime.now().strftime("%Y%m%d_%H%M%S")}_{safe}';path.write_bytes(raw)
                text=extract(f.name,raw)
                run('INSERT INTO cvs(filename,path,label,uploaded,text,hash) VALUES(?,?,?,?,?,?)',(f.name,str(path),label,now(),text,digest))
            else: text=df('SELECT text FROM cvs WHERE id=?',(int(existing.iloc[0,0]),)).iloc[0,0]
            if not text.strip(): st.error('CV stored, but text extraction failed. Try a text-based PDF or DOCX.')
            else: save_profile(profile_from(text)); st.success('CV saved and search profile extracted. Review the profile below.'); st.rerun()
    cvs=df('SELECT id,filename,label,uploaded FROM cvs ORDER BY id DESC')
    if not cvs.empty:
        st.dataframe(cvs,use_container_width=True,hide_index=True)
        cid=st.selectbox('Download CV version',cvs.id.tolist()); row=df('SELECT path,filename FROM cvs WHERE id=?',(int(cid),)).iloc[0]
        if Path(row.path).exists(): st.download_button('Download CV',Path(row.path).read_bytes(),file_name=row.filename)
    if p:
        with st.form('profile_edit'):
            roles=st.multiselect('Positions',list(ROLE_TERMS),default=[x for x in p['roles'] if x in ROLE_TERMS])
            industries=st.multiselect('Industries',list(IND),default=[x for x in p['industries'] if x in IND])
            skills=st.multiselect('Capabilities',['P&L / Business Ownership','Sales & Business Development','Operations & Service Delivery','Team Leadership','Partner / Franchise Management','International Business','Business Growth / Transformation','Product / Content / Digital'],default=p['skills'])
            markets=st.multiselect('Markets',['India','Middle East','Africa'],default=p['markets'])
            exp=st.number_input('Your total experience (years)',15,50,int(max(15,min(50,p['experience_years']))))
            minreq=st.number_input('Minimum advertised experience requirement',15,40,int(p['min_required']))
            days=st.slider('Maximum vacancy age (days)',1,90,int(p['days']))
            ok=st.form_submit_button('Save profile')
        if ok:
            p.update(roles=roles,industries=industries,skills=skills,markets=markets,experience_years=exp,min_required=minreq,days=days);save_profile(p);st.success('Profile saved.');st.rerun()
    else: st.info('Upload your CV to begin.')
elif page=='Dashboard & Scan':
    if not p: st.warning('Open CV & Profile and upload your CV first.');st.stop()
    jobs=df('SELECT * FROM jobs ORDER BY score DESC,posted DESC')
    a,b,c,d=st.columns(4);a.metric('Matching jobs',len(jobs));b.metric('Markets',len(p['markets']));c.metric('Experience filter',f"{p['min_required']}+ years");d.metric('Posting window',f"{p['days']} days")
    st.write('Every scan searches configured sources, excludes postings older than the selected window, re-scores matches, and refreshes saved listings.')
    if st.button('🔄 Scan for new and refreshed jobs',type='primary',use_container_width=True):
        with st.spinner('Scanning available job sources and matching your CV profile…'): n,notes,qs=scan(p)
        st.success(f'Scan complete: {n} matching listings found or refreshed.');st.write('Search queries:',', '.join(qs))
        for note in dict.fromkeys(notes): st.caption(note)
        st.rerun()
    hist=df('SELECT at,count FROM scans ORDER BY id DESC LIMIT 1')
    if not hist.empty: st.caption(f"Last scan: {hist.iloc[0]['at']} • matches: {hist.iloc[0]['count']}")
    jobs=df('SELECT * FROM jobs ORDER BY score DESC,posted DESC')
    if jobs.empty: st.info('No scan has returned matching jobs yet. Configure Adzuna/Jooble keys in Setup to broaden coverage, then scan.')
    else:
        m=st.multiselect('Market filter',['India','Middle East','Africa'],default=p['markets']); minscore=st.slider('Minimum CV match score',0,100,30,5); src=st.multiselect('Source filter',sorted(jobs.source.dropna().unique()))
        v=jobs[jobs.market.isin(m)&(jobs.score>=minscore)]
        if src:v=v[v.source.isin(src)]
        st.caption(f'{len(v)} jobs displayed. Unknown or stale posting dates are excluded.')
        for _,r in v.iterrows():
            with st.container(border=True):
                left,right=st.columns([5,1]);left.markdown(f"**{r.role}** — {r.company}");left.caption(f"{r.location} • {r.market} • Posted {r.posted} • {r.source}");left.write(r.reasons)
                with left.expander('Description'): st.write((r.description or '')[:5000])
                right.metric('CV match',f'{r.score}%')
                if r.url: right.link_button('View job',r.url,use_container_width=True)
                if right.button('Shortlist',key=f'short-{r.id}'):
                    run('INSERT INTO shortlist(job_key,status,notes,updated) VALUES(?,?,?,?) ON CONFLICT(job_key) DO UPDATE SET status=excluded.status,updated=excluded.updated',(r.job_key,'Shortlisted','',now()));st.toast('Shortlisted')
        st.download_button('Export matching jobs CSV',v.to_csv(index=False).encode(),file_name='matching_jobs.csv',mime='text/csv')
elif page=='Shortlist':
    s=df('SELECT s.status,s.notes,s.updated,j.company,j.role,j.location,j.market,j.score,j.posted,j.url FROM shortlist s LEFT JOIN jobs j ON s.job_key=j.job_key ORDER BY s.updated DESC')
    st.subheader('Shortlisted jobs');st.dataframe(s,use_container_width=True,hide_index=True) if not s.empty else st.info('Shortlist jobs from the dashboard.')
    if not s.empty:
        st.download_button('Export shortlist CSV',s.to_csv(index=False).encode(),file_name='shortlist.csv',mime='text/csv')
elif page=='Scan History':
    h=df('SELECT * FROM scans ORDER BY id DESC LIMIT 100');st.dataframe(h,use_container_width=True,hide_index=True) if not h.empty else st.info('No scans yet.')
elif page=='Setup':
    st.subheader('Job source configuration')
    st.markdown('**Arbeitnow** is attempted without a key, but coverage in your target markets may be limited. Configure Adzuna and Jooble for broader discovery.')
    st.code('ADZUNA_APP_ID = "your_app_id"\nADZUNA_APP_KEY = "your_app_key"\nJOOBLE_API_KEY = "your_jooble_key"',language='toml')
    st.markdown('In Streamlit Cloud, open app menu → Settings → Secrets. Do not put API keys in GitHub code.')
    st.warning('This version searches when you click Scan. A Streamlit app does not run scans while asleep; scheduled scanning needs a separate scheduler. Local files/SQLite may be ephemeral on Streamlit Cloud. Use persistent private storage for long-term CV and application records.')
    st.caption('Adzuna maps India to India, Middle East to UAE, and Africa to South Africa as representative search locations; this is not full country-by-country coverage. Job match scores are heuristic, not guarantees.')
st.caption('Review job details, employer requirements and posting dates before applying. This app does not automatically submit third-party applications.')
