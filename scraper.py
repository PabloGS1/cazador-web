#!/usr/bin/env python3
"""
CAZADOR SCRAPER — junta ofertas de fuentes públicas sin login.

Fuentes activas por defecto:
  - Adzuna          (NL / CH / SG)  API con app_id/app_key
  - Greenhouse      (boards públicos) — 49 empresas en companies.yaml
  - Ashby           (posting-api) — 25 empresas AI/startups en companies.yaml
  - Workday         (API CXS pública) — 16 empresas en companies.yaml
  - SmartRecruiters (API pública) — 7 empresas en companies.yaml
  - Lever           (api.lever.co) — Palantir (limitado a 100/empresa)
  - EPSO/EU-Careers (feed JSON público) — instituciones de la UE
  - Jobindex        (RSS público, sin token) — Dinamarca (100 ofertas)
  - SwissDevJobs    (RSS público) — Suiza (187 ofertas)
  - Amazon          (search.json API) — global (50 ofertas por query)
  - RemoteOk        (JSON público) — remote global
  - Arbeitnow       (JSON público) — Europa/remote
  - Remotive        (JSON público) — remote global
  - Microsoft/Google/Meta/Apple — HTML scraping (0 sin headless browser)
  - Jooble          (API key necesaria)
  - Careerjet       (affiliate API, en secrets.yaml; 403 hasta aprobar)
  - NVB             (API — 403 anti-bot)
  - WTTJ            (Algolia API) — Francia

Salida: web/data/raw_jobs.json  (alimenta a matcher.py)

Uso:
    python scraper.py                     # todas las fuentes por defecto
    python scraper.py --sources adzuna    # solo Adzuna
    python scraper.py --delay 0.5         # espera entre peticiones
"""
import argparse
import concurrent.futures
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
import yaml

BASE = Path(__file__).parent
RAW = BASE / "web" / "data" / "raw_jobs.json"
SECRETS = BASE / "secrets.yaml"
COMPANIES = BASE / "companies.yaml"

# Máximo de ofertas que se guardan por empresa (evita boards gigantes)
CAP_PER_COMPANY = 100

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
}

# Portales de Adzuna que cubren la estrategia: NL/CH/SG (núcleo) + EU/EMEA/MX
ADZUNA_COUNTRIES = [
    ("nl", "Netherlands"),
    ("ch", "Switzerland"),
    ("sg", "Singapore"),
    ("de", "Germany"),
    ("at", "Austria"),
    ("be", "Belgium"),
    ("fr", "France"),
    ("es", "Spain"),
    ("mx", "Mexico"),
]

# Límite de resultados por query y país: NL copa el grueso (80%),
# CH y SG se recortan para respetar la estrategia 15/5.
ADZUNA_CAP = {"nl": 60, "ch": 40, "sg": 20, "de": 30, "at": 15,
              "be": 15, "fr": 15, "es": 15, "mx": 15}
ADZUNA_RETRIES = 3

# Queries curadas para no quemar la cuota de la API (perfil.yaml)
ADZUNA_QUERIES = [
    "sales engineer", "solutions engineer", "presales",
    "business development", "account executive", "account manager",
    "product manager", "product engineer", "cloud sales", "SaaS",
    "artificial intelligence", "machine learning", "data engineer",
    "data center", "GPU", "HPC",
]
# Países extra: menos queries para no disparar la cuota (NL/CH/SG usan la lista completa)
ADZUNA_QUERIES_SHORT = [
    "sales engineer", "solutions engineer", "presales",
    "business development", "account manager", "key account",
    "data center", "artificial intelligence", "SaaS",
]

# Lever: el endpoint público responde 404 para la mayoría hoy; añade slugs
# que sí funcionen si quieres reactivarlo (slugs -> nombre).
LEVER_COMPANIES = {}

# Jooble: API gratuita, key por país (cada dominio necesita su propia key)
JOOBLE_KEYS = {}  # Rellena en secrets.yaml: jooble: { nl: "key", ch: "key", ... }
JOOBLE_COUNTRIES = {
    "nl": ("nl.jooble.org", "Netherlands"),
    "ch": ("ch.jooble.org", "Switzerland"),
    "de": ("de.jooble.org", "Germany"),
    "dk": ("dk.jooble.org", "Denmark"),
    "ae": ("ae.jooble.org", "UAE"),
    "sa": ("sa.jooble.org", "Saudi Arabia"),
    "gb": ("uk.jooble.org", "United Kingdom"),
}
JOOBLE_QUERIES = [
    "sales engineer", "solutions engineer", "presales",
    "business development", "account executive", "account manager",
    "key account", "cloud sales", "SaaS",
    "artificial intelligence", "machine learning",
    "data center", "technical account manager",
]

# Careerjet: API de afiliado, ID en secrets.yaml
CAREERJET_AFFID = ""  # Rellena en secrets.yaml: careerjet_affid: "tu-id"
CAREERJET_COUNTRIES = {
    "nl": "nl_NL", "ch": "de_CH", "de": "de_DE",
    "dk": "da_DK", "ae": "en_AE", "sa": "en_SA",
    "gb": "en_GB", "ie": "en_IE", "fr": "fr_FR",
    "es": "es_ES", "mx": "es_MX", "se": "sv_SE",
    "no": "no_NO", "pl": "pl_PL", "pt": "pt_PT",
}

# Nationale Vacaturebank: API interna no documentada (funciona sin auth)
NVB_QUERIES = [
    "sales engineer", "account manager", "business development",
    "technical account manager", "key account manager",
]

# Jobindex.dk: feeds RSS por búsqueda (sin auth)
JOBINDEX_QUERIES = [
    "sales engineer", "account manager", "business development",
    "technical account manager", "key account",
]

# Welcome to the Jungle: Algolia search (key pública embebida en JS)
WTTJ_APP_ID = "CSEKHVMS53"
WTTJ_QUERIES = [
    "sales engineer", "account executive", "business development",
    "account manager", "key account", "technical account manager",
]

# Fuentes remote-global sin API key (JSON públicos)
REMOTEOK_URL = "https://remoteok.com/api"
ARBEITNOW_URL = "https://www.arbeitnow.com/api/job-board-api"
REMOTIVE_URL = "https://remotive.com/api/remote-jobs"
REMOTEOK_TAGS = [
    "sales", "account", "business development", "presales", "customer success",
    "product", "data", "ai", "machine learning", "cloud",
]
ARBEITNOW_TAGS = [
    "sales", "account", "business development", "presales", "customer success",
    "product", "data engineer", "machine learning", "ai", "cloud",
]
REMOTIVE_CATEGORIES = ["sales", "customer success", "product", "data",
                       "software development", "machine learning"]
ARBEITNOW_REMOTE_KEYS = ["Berlin", "Remote", "Hybrid"]
REMOTIVE_REMOTE_GEO = re.compile(r"(?i)(worldwide|anywhere|remote|czech|poland|germany|spain|portugal|france|sweden|denmark|netherlands|uk|united kingdom|ireland|switzerland|austria|belgium)")

GREENHOUSE_GEO = re.compile(
    r"(?i)\b(netherlands|holland|amsterdam|utrecht|rotterdam|eindhoven|hague|"
    r"switzerland|swiss|zurich|zürich|geneva|lausanne|basel|"
    r"singapore|emea|remote|europe|berlin|munich|frankfurt|"
    r"dublin|london|brussels|paris|oslo|stockholm|copenhagen|vienna|"
    r"warsaw|madrid|barcelona|lisbon|"
    r"norway|trondheim|stavanger|bergen|"
    r"denmark|copenhagen|aarhus|aalborg|odense|billund|"
    r"mexico|méxico|guadalajara|queretaro|querétaro|tijuana|monterrey|mexicali|"
    r"thailand|bangkok|chonburi|ayutthaya|"
    r"japan|tokyo|osaka|yokohama|tsukuba|"
    r"korea|seoul|suwon|hwaseong|icheon)\b")


def log(*a):
    print(f"[scraper] {' '.join(str(x) for x in a)}", flush=True)


def load_secrets():
    if SECRETS.exists():
        return yaml.safe_load(SECRETS.read_text(encoding="utf-8")) or {}
    return {}


def load_profile():
    return yaml.safe_load((BASE / "profile.yaml").read_text(encoding="utf-8"))


def load_companies():
    if not COMPANIES.exists():
        return {}
    return yaml.safe_load(COMPANIES.read_text(encoding="utf-8")) or {}


def strip_html(html):
    if not html:
        return ""
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def trunc(s, n=12000):
    return s[:n] if s else ""


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def get_json(url, label="", tries=ADZUNA_RETRIES, timeout=30):
    """GET con reintentos y backoff; devuelve dict/list o None."""
    for attempt in range(1, tries + 1):
        try:
            r = requests.get(url, headers=HEADERS, timeout=timeout)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            if attempt < tries:
                wait = 1.5 * attempt
                log(f"{label}: reintento {attempt}/{tries} en {wait:.1f}s "
                    f"({e.__class__.__name__})")
                time.sleep(wait)
            else:
                log(f"{label}: falló tras {tries} intentos ({e})")
    return None


# ------------------------------------------------------------------ Adzuna

def fetch_adzuna(secrets, delay):
    sid = secrets.get("adzuna_app_id") or os.environ.get("ADZUNA_APP_ID")
    key = secrets.get("adzuna_app_key") or os.environ.get("ADZUNA_APP_KEY")
    if not sid or not key:
        log("Adzuna: faltan app_id/app_key en secrets.yaml — saltando")
        return []

    jobs, seen = [], set()
    total_requests = 0
    for cc, country in ADZUNA_COUNTRIES:
        for q in ADZUNA_QUERIES:
            url = ("https://api.adzuna.com/v1/api/jobs/{cc}/search/1"
                   "?app_id={sid}&app_key={key}"
                   "&results_per_page=50&full_time=1&content-type=application/json"
                   "&what={q}").format(cc=cc, sid=sid, key=key,
                                       q=requests.utils.quote(q))
            data = get_json(url, label=f"Adzuna {cc}/{q}")
            if data is None:
                continue
            total_requests += 1
            for item in data.get("results", [])[:ADZUNA_CAP.get(cc, 50)]:
                jid = item.get("id")
                if not jid or jid in seen:
                    continue
                seen.add(jid)
                loc = item.get("location", {}) or {}
                loc_name = loc.get("display_name") or item.get("location") or ""
                sal_min, sal_max = item.get("salary_min"), item.get("salary_max")
                cur = (item.get("salary_currency") or "EUR").upper()
                sal_raw = ""
                if sal_min and sal_max:
                    sal_raw = f"{cur} {sal_min:,.0f} - {sal_max:,.0f} per year"
                elif sal_min:
                    sal_raw = f"from {cur} {sal_min:,.0f} per year"
                jobs.append({
                    "id": f"adzuna-{jid}",
                    "title": item.get("title") or "",
                    "company": (item.get("company") or {}).get("display_name") or "",
                    "location": loc_name,
                    "description": trunc(strip_html(item.get("description"))),
                    "summary": " · ".join(filter(None, [
                        item.get("title"), loc_name, sal_raw])),
                    "source": f"adzuna-{cc}",
                    "posted": (item.get("created") or "")[:10],
                    "url": item.get("redirect_url") or "",
                    "salary_raw": sal_raw,
                    "salary_min": sal_min,
                    "salary_max": sal_max,
                    "salary_currency": cur,
                    "contract": item.get("contract_type") or "",
                    "category": (item.get("category") or {}).get("label") or "",
                })
            time.sleep(delay)
    log(f"Adzuna: {len(jobs)} ofertas en {total_requests} peticiones")
    return jobs


# -------------------------------------------------------------- Greenhouse

def _keyword_sets(profile):
    """Devuelve (keywords_de_rol, keywords_de_dominio) en minúsculas."""
    role_kws = []
    # Nuevo schema: role_taxonomy con tiers
    if "role_taxonomy" in profile:
        for tier in profile["role_taxonomy"].values():
            if isinstance(tier, dict):
                role_kws += tier.get("titles", []) + tier.get("keywords", [])
    # Schema legacy: target_roles
    elif "target_roles" in profile:
        for fam in profile["target_roles"].values():
            role_kws += fam.get("keywords", [])
    domain_kws = []
    dk = profile.get("domain_keywords", {})
    if isinstance(dk, dict):
        for group in dk.get("keywords", []):
            if isinstance(group, list):
                domain_kws += group
            elif isinstance(group, str):
                domain_kws.append(group)
    return [k.lower() for k in role_kws], [k.lower() for k in domain_kws]


GREENHOUSE_US = re.compile(
    r"(?i)\b(united states|usa|u\.?s\.?|san francisco|california|new york|texas|"
    r"seattle|austin|chicago|atlanta|boston|denver|colorado|washington dc|"
    r"new jersey|virginia|georgia|washington state|florida|santa clara|"
    r"ca|ny|tx|wa|ma|il|ga|az|co|or|mn|nc|nj|va|md|ut|pa|oh|mi|wi)\b")


def _geo_relevant(loc):
    return bool(GREENHOUSE_GEO.search(loc or ""))


def _us_only(loc):
    loc = loc or ""
    if not GREENHOUSE_US.search(loc):
        return False
    geo = GREENHOUSE_GEO.search(loc)
    if not geo:
        return True
    # si el único "geo" es 'remote', la ubicación real es EE. UU.
    return geo.group(0).lower() == "remote"


def _relevant(title, loc, content, keywords):
    """Estrategia 80/15/5: prioriza EU (NL/CH/EMEA/remote) y descarta roles
    puramente de EE. UU. Entran roles con keyword de rol o de dominio IA/Data
    en el título, o con keyword en el contenido si la ubicación es EU/remote."""
    t = (title or "").lower()
    if _us_only(loc):
        return False
    if any(k in t for k in keywords):
        return True
    if not _geo_relevant(loc):
        return False
    blob = (t + " " + (content or "")[:2500]).lower()
    return any(k in blob for k in keywords)


def _build_job(source, jid, title, name, loc, content, url, posted):
    return {
        "id": jid,
        "title": title,
        "company": name,
        "location": loc,
        "description": trunc(content),
        "summary": " · ".join(filter(None, [title, name, loc])),
        "source": source,
        "posted": posted,
        "url": url or "",
        "salary_raw": "",
        "salary_min": None,
        "salary_max": None,
        "salary_currency": "",
    }


def fetch_greenhouse(delay, profile, companies):
    role_kws, domain_kws = _keyword_sets(profile)
    keywords = role_kws + domain_kws
    jobs, seen = [], set()
    for slug, name in companies.get("greenhouse", {}).items():
        url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"
        data = get_json(url, label=f"Greenhouse {slug}", timeout=40)
        if data is None:
            time.sleep(delay)
            continue
        kept = 0
        for item in data.get("jobs", []):
            jid = item.get("id")
            if not jid or jid in seen or kept >= CAP_PER_COMPANY:
                continue
            seen.add(jid)
            title = item.get("title") or ""
            loc = (item.get("location") or {}).get("name") or ""
            content = strip_html(item.get("content") or "")
            if not _relevant(title, loc, content, keywords):
                continue
            kept += 1
            jobs.append(_build_job(f"greenhouse-{slug}", f"greenhouse-{slug}-{jid}",
                                   title, name, loc, content,
                                   item.get("absolute_url"),
                                   (item.get("updated_at") or "")[:10]))
        log(f"Greenhouse {slug}: {len(data.get('jobs', []))} publicadas "
            f"-> {kept} relevantes")
        time.sleep(delay)
    log(f"Greenhouse: {len(jobs)} ofertas")
    return jobs


# -------------------------------------------------------------------- Ashby

def fetch_ashby(delay, profile, companies):
    role_kws, domain_kws = _keyword_sets(profile)
    keywords = role_kws + domain_kws
    jobs, seen = [], set()
    for slug, name in companies.get("ashby", {}).items():
        url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
        data = get_json(url, label=f"Ashby {slug}", timeout=40)
        if not isinstance(data, dict) or not data.get("jobs"):
            time.sleep(delay)
            continue
        kept = 0
        for item in data["jobs"]:
            jid = item.get("id")
            if not jid or jid in seen or kept >= CAP_PER_COMPANY:
                continue
            seen.add(jid)
            title = item.get("title") or ""
            loc = (item.get("location") or "") or ""
            sec = [x.get("location") for x in item.get("secondaryLocations") or []
                   if x.get("location")]
            if sec:
                loc = f"{loc}; {'; '.join(sec)}"
            remote = "Remote" if item.get("isRemote") else ""
            loc = " · ".join(filter(None, [loc, remote]))
            content = strip_html(item.get("descriptionHtml") or
                                 item.get("descriptionPlain") or "")
            if not _relevant(title, loc, content, keywords):
                continue
            kept += 1
            jobs.append(_build_job(f"ashby-{slug}", f"ashby-{slug}-{jid}",
                                   title, name, loc, content,
                                   item.get("jobUrl"),
                                   (item.get("publishedAt") or "")[:10]))
        log(f"Ashby {slug}: {len(data.get('jobs', []))} publicadas "
            f"-> {kept} relevantes")
        time.sleep(delay)
    log(f"Ashby: {len(jobs)} ofertas")
    return jobs


# ------------------------------------------------------------------ Workday

def _wd_url(tenant, pod, site, path):
    return f"https://{tenant}.{pod}.myworkdayjobs.com/en-US/{site}{path or ''}"


def _wd_date(posted):
    """Workday lista fechas relativas ('Posted Today', 'Posted N days ago')."""
    p = (posted or "").lower()
    today = datetime.now(timezone.utc).date()
    if "today" in p:
        return today.isoformat()
    if "yesterday" in p:
        return (today - timedelta(days=1)).isoformat()
    m = re.search(r"(\d+)\s*days?\s*ago", p)
    if m:
        return (today - timedelta(days=int(m.group(1)))).isoformat()
    return ""


def _fetch_workday_one(key, name, keywords, delay):
    parts = key.split("/")
    if len(parts) != 3:
        return []
    tenant, pod, site = parts
    base = (f"https://{tenant}.{pod}.myworkdayjobs.com"
            f"/wday/cxs/{tenant}/{site}/jobs")
    jobs, seen, total, kept = [], set(), None, 0
    offset = 0
    while kept < CAP_PER_COMPANY:
        try:
            r = requests.post(base,
                              headers={**HEADERS, "Accept": "application/json"},
                              json={"limit": 20, "offset": offset}, timeout=30)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            log(f"Workday {key}: error {e}")
            break
        if total is None:
            total = data.get("total", 0)
        page = data.get("jobPostings", [])
        for item in page:
            path = item.get("externalPath") or ""
            if not path or path in seen or kept >= CAP_PER_COMPANY:
                continue
            seen.add(path)
            title = item.get("title") or ""
            loc = " ".join(filter(None, [item.get("locationsText"), path]))
            if not _relevant(title, loc, "", keywords):
                continue
            kept += 1
            jobs.append(_build_job(f"workday-{tenant}", f"workday-{tenant}-{path}",
                                   title, name, loc, "",
                                   _wd_url(tenant, pod, site, path),
                                   _wd_date(item.get("postedOn"))))
        if not page or (total and offset + len(page) >= total):
            break
        offset += len(page)
    time.sleep(delay)
    log(f"Workday {key}: {total or 0} publicadas -> {kept} relevantes")
    return jobs


def fetch_workday(delay, profile, companies):
    role_kws, domain_kws = _keyword_sets(profile)
    keywords = role_kws + domain_kws
    jobs = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
        futs = [ex.submit(_fetch_workday_one, k, n, keywords, delay)
                for k, n in companies.get("workday", {}).items()]
        for f in concurrent.futures.as_completed(futs):
            jobs += f.result()
    log(f"Workday: {len(jobs)} ofertas")
    return jobs


# ----------------------------------------------------------- SmartRecruiters

def _fetch_sr_one(slug, name, keywords, delay):
    url = (f"https://api.smartrecruiters.com/v1/companies/{slug}"
           "/postings?limit=100&offset=0")
    data = get_json(url, label=f"SmartRecruiters {slug}", timeout=30)
    if not isinstance(data, dict) or not data.get("content"):
        time.sleep(delay)
        return []
    jobs, seen, kept = [], set(), 0
    for item in data["content"]:
        jid = item.get("id")
        if not jid or jid in seen or kept >= CAP_PER_COMPANY:
            continue
        seen.add(jid)
        title = item.get("name") or ""
        loc_data = item.get("location") or {}
        loc = (loc_data.get("fullLocation") or
               ", ".join(filter(None, [loc_data.get("city"),
                                       loc_data.get("region"),
                                       loc_data.get("country")])))
        if not _relevant(title, loc, "", keywords):
            continue
        kept += 1
        jobs.append(_build_job(f"smartrecruiters-{slug}", f"sr-{slug}-{jid}",
                               title, name, loc, "",
                               f"https://jobs.smartrecruiters.com/{slug}/{jid}",
                               (item.get("releasedDate") or "")[:10]))
    time.sleep(delay)
    log(f"SmartRecruiters {slug}: {data.get('totalFound', 0)} publicadas "
        f"-> {kept} relevantes")
    return jobs


def fetch_smartrecruiters(delay, profile, companies):
    role_kws, domain_kws = _keyword_sets(profile)
    keywords = role_kws + domain_kws
    jobs = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
        futs = [ex.submit(_fetch_sr_one, s, n, keywords, delay)
                for s, n in companies.get("smartrecruiters", {}).items()]
        for f in concurrent.futures.as_completed(futs):
            jobs += f.result()
    log(f"SmartRecruiters: {len(jobs)} ofertas")
    return jobs



# -------------------------------------------------------------------- EPSO

# Feed publico de ofertas de las instituciones de la UE (EPSO/EU-Careers).
# Devuelve JSON sin token ni login. El feed NO trae la descripcion completa,
# solo metadatos (dominio, grado, contrato, sede, deadline).
EPSO_URL = "https://epso.europa.eu/JSON-JOBS"


def fetch_epso(delay, profile):
    role_kws, domain_kws = _keyword_sets(profile)
    keywords = role_kws + domain_kws
    data = get_json(EPSO_URL, label="EPSO", timeout=40)
    if not isinstance(data, list):
        log(f"EPSO: respuesta inesperada ({type(data).__name__})")
        return []
    jobs, kept = [], 0
    for item in data:
        jid = item.get("ID")
        if not jid:
            continue
        title = item.get("TITLE") or ""
        company = (item.get("INSTITUTIONS") or "").strip()
        loc = item.get("LOCATIONS") or ""
        domain = item.get("DOMAIN") or ""
        grade = item.get("GRADE") or ""
        contract = item.get("CONTRACT") or ""
        content = " ".join(filter(None, [domain, grade, contract]))
        if not _relevant(title, loc, content, keywords):
            continue
        kept += 1
        jobs.append({
            "id": f"epso-{jid}",
            "title": title,
            "company": company,
            "location": loc,
            "description": trunc(content),
            "summary": " ".join(filter(None,
                                         [title, company, loc, grade, contract, domain])),
            "source": "epso",
            "posted": "",
            "url": item.get("URI") or "",
            "salary_raw": "",
            "salary_min": None,
            "salary_max": None,
            "salary_currency": "",
            "contract": contract,
            "category": domain,
            "grade": grade,
        })
    log(f"EPSO: {len(data)} publicadas -> {kept} relevantes")
    return jobs

# ------------------------------------------------------------------- Lever

def fetch_lever(delay, companies):
    jobs, seen = [], set()
    for slug, name in companies.get("lever", {}).items():
        url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
        try:
            r = requests.get(url, headers=HEADERS, timeout=120)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            log(f"Lever {slug}: error {e}")
            time.sleep(delay)
            continue
        kept = 0
        for item in data:
            if kept >= CAP_PER_COMPANY:
                break
            jid = item.get("id")
            if not jid or jid in seen:
                continue
            seen.add(jid)
            kept += 1
            jobs.append({
                "id": f"lever-{slug}-{jid}",
                "title": item.get("text") or "",
                "company": name,
                "location": item.get("categories", {}).get("location") or "",
                "description": trunc(strip_html(item.get("descriptionPlain") or
                                                item.get("description"))),
                "summary": " · ".join(filter(None, [item.get("text"), name])),
                "source": f"lever-{slug}",
                "posted": (datetime.fromtimestamp(item["createdAt"] / 1000, tz=timezone.utc).strftime("%Y-%m-%d") if item.get("createdAt") else ""),
                "url": item.get("hostedUrl") or "",
                "salary_raw": "",
                "salary_min": None,
                "salary_max": None,
                "salary_currency": "",
            })
        log(f"Lever {slug}: {kept} ofertas")
        time.sleep(delay)
    return jobs


# --------------------------------------------------------- Jooble (API free)

def fetch_jooble(delay, secrets):
    jobs = []
    jooble_keys = secrets.get("jooble", {})
    for country_code, (domain, country_name) in JOOBLE_COUNTRIES.items():
        key = jooble_keys.get(country_code)
        if not key:
            log(f"Jooble {country_code}: sin key, skip")
            continue
        for q in JOOBLE_QUERIES:
            url = f"https://{domain}/api/{key}"
            body = {"keywords": q, "location": country_name, "ResultOnPage": 20}
            try:
                r = requests.post(url, json=body, headers=HEADERS, timeout=30)
                r.raise_for_status()
                data = r.json()
            except Exception as e:
                log(f"Jooble {country_code}/{q}: error {e}")
                time.sleep(delay)
                continue
            for item in (data.get("jobs") or []):
                jid = item.get("id") or item.get("link") or ""
                if not jid:
                    continue
                loc = item.get("location") or ""
                jobs.append({
                    "id": f"jooble-{country_code}-{hash(jid) & 0xFFFFFFFF:08x}",
                    "title": item.get("title") or "",
                    "company": item.get("company") or "",
                    "location": loc if loc else country_name,
                    "description": trunc(item.get("snippet") or item.get("description") or ""),
                    "summary": " · ".join(filter(None, [item.get("title"), item.get("company")])),
                    "source": f"jooble-{country_code}",
                    "posted": (item.get("updated") or "")[:10],
                    "url": item.get("link") or "",
                    "salary_raw": "",
                    "salary_min": None,
                    "salary_max": None,
                    "salary_currency": "",
                })
            time.sleep(delay)
    log(f"Jooble: {len(jobs)} ofertas")
    return jobs


# ------------------------------------------------------- Careerjet (API free)

def fetch_careerjet(delay, secrets):
    jobs = []
    affid = secrets.get("careerjet_affid") or CAREERJET_AFFID
    if not affid:
        log("Careerjet: sin affidavit ID, skip")
        return jobs
    for country_code, locale in CAREERJET_COUNTRIES.items():
        for q in ADZUNA_QUERIES:
            params = {
                "keywords": q,
                "locale_code": locale,
                "results_on_page": 20,
                "sort": "date",
            }
            try:
                r = requests.get(
                    "https://search.api.careerjet.net/v4/query",
                    params=params,
                    auth=(affid, ""),
                    headers=HEADERS,
                    timeout=30,
                )
                r.raise_for_status()
                data = r.json()
            except Exception as e:
                log(f"Careerjet {country_code}/{q}: error {e}")
                time.sleep(delay)
                continue
            for item in (data.get("jobs") or []):
                if not item:
                    continue
                jobs.append({
                    "id": f"careerjet-{country_code}-{item.get('jobReference','')}",
                    "title": item.get("title") or "",
                    "company": item.get("company") or "",
                    "location": item.get("locations") or item.get("reference") or "",
                    "description": trunc(item.get("description_text") or item.get("description") or ""),
                    "summary": " · ".join(filter(None, [item.get("title"), item.get("company")])),
                    "source": f"careerjet-{country_code}",
                    "posted": (item.get("date") or "")[:10],
                    "url": item.get("url") or "",
                    "salary_raw": item.get("salary") or "",
                    "salary_min": None,
                    "salary_max": None,
                    "salary_currency": "",
                })
            time.sleep(delay)
    log(f"Careerjet: {len(jobs)} ofertas")
    return jobs


# ------------------------------------------- Nationale Vacaturebank (API interna)

def fetch_nationale_vacaturebank(delay):
    jobs = []
    nvb_headers = dict(HEADERS)
    nvb_headers["Accept"] = "application/json"
    nvb_headers["Referer"] = "https://www.nationalevacaturebank.nl/"
    nvb_headers["Origin"] = "https://www.nationalevacaturebank.nl"
    for q in NVB_QUERIES:
        page = 1
        while page <= 5:
            params = {"q": q, "page": page, "pageSize": 50, "sortBy": "date"}
            url = "https://api.nationalevacaturebank.nl/search/jobs"
            try:
                r = requests.get(url, params=params, headers=nvb_headers, timeout=30)
                if r.status_code == 404 or r.status_code == 403:
                    break
                r.raise_for_status()
                data = r.json()
            except Exception as e:
                log(f"NVB/{q}: error {e}")
                break
            items = data.get("jobs") or data.get("results") or []
            if not items:
                break
            for item in items:
                jid = item.get("id") or item.get("url") or ""
                if not jid:
                    continue
                jobs.append({
                    "id": f"nvb-{hash(str(jid)) & 0xFFFFFFFF:08x}",
                    "title": item.get("title") or item.get("name") or "",
                    "company": item.get("companyName") or item.get("company") or "",
                    "location": item.get("city") or item.get("location") or "",
                    "description": trunc(item.get("description") or item.get("content") or ""),
                    "summary": " · ".join(filter(None, [item.get("title"), item.get("companyName")])),
                    "source": "nvb-nl",
                    "posted": (item.get("publishDate") or item.get("date") or "")[:10],
                    "url": item.get("url") or item.get("applyUrl") or "",
                    "salary_raw": item.get("salary") or "",
                    "salary_min": None,
                    "salary_max": None,
                    "salary_currency": "",
                })
            page += 1
            time.sleep(delay)
    log(f"NVB: {len(jobs)} ofertas")
    return jobs


# ------------------------------------------------- Jobindex.dk (RSS feeds)

def fetch_jobindex_rss(delay):
    import xml.etree.ElementTree as ET
    jobs = []
    for q in JOBINDEX_QUERIES:
        rss_url = f"https://www.jobindex.dk/jobsoegning?q={requests.utils.quote(q)}&format=rss"
        try:
            r = requests.get(rss_url, headers=HEADERS, timeout=30)
            if r.status_code != 200:
                continue
            root = ET.fromstring(r.content)
        except Exception as e:
            log(f"Jobindex/{q}: error {e}")
            time.sleep(delay)
            continue
        for item in root.iter("item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            desc = (item.findtext("description") or "").strip()
            pub = (item.findtext("pubDate") or "")[:10]
            if not title or not link:
                continue
            jobs.append({
                "id": f"jobindex-{hash(link) & 0xFFFFFFFF:08x}",
                "title": title,
                "company": "",
                "location": "",
                "description": trunc(desc),
                "summary": title,
                "source": "jobindex-dk",
                "posted": pub,
                "url": link,
                "salary_raw": "",
                "salary_min": None,
                "salary_max": None,
                "salary_currency": "",
            })
        time.sleep(delay)
    log(f"Jobindex: {len(jobs)} ofertas")
    return jobs


# --------------------------------------- Welcome to the Jungle (Algolia search)

def fetch_wttj(delay, secrets):
    jobs = []
    algolia_key = secrets.get("wttj_algolia_key") or ""
    if not algolia_key:
        log("WTTJ: sin Algolia key, skip (añade wttj_algolia_key en secrets.yaml)")
        return jobs
    headers = dict(HEADERS)
    headers["x-algolia-application-id"] = WTTJ_APP_ID
    headers["x-algolia-api-key"] = algolia_key
    for q in WTTJ_QUERIES:
        body = {
            "requests": [{
                "indexName": "wk_cms_jobs_production",
                "params": f"query={requests.utils.quote(q)}&hitsPerPage=50&page=0",
            }]
        }
        try:
            r = requests.post(
                f"https://{WTTJ_APP_ID.lower()}-dsn.algolia.net/1/indexes/*/queries",
                json=body, headers=headers, timeout=30,
            )
            r.raise_for_status()
            results = r.json().get("results", [{}])[0]
        except Exception as e:
            log(f"WTTJ/{q}: error {e}")
            time.sleep(delay)
            continue
        for hit in results.get("hits", []):
            jid = hit.get("objectID") or ""
            if not jid:
                continue
            offices = hit.get("offices") or []
            loc = offices[0].get("city") or "" if offices else ""
            sal = hit.get("salary_min")
            sal_max = hit.get("salary_max")
            currency = hit.get("salary_currency") or "EUR"
            jobs.append({
                "id": f"wttj-{jid}",
                "title": hit.get("name") or "",
                "company": (hit.get("organization") or {}).get("name") or "",
                "location": loc,
                "description": trunc(hit.get("description") or hit.get("description_html") or ""),
                "summary": " · ".join(filter(None, [hit.get("name"), (hit.get("organization") or {}).get("name")])),
                "source": "wttj",
                "posted": (hit.get("published_at") or "")[:10],
                "url": f"https://www.welcometothejungle.com/fr/jobs/{jid}" if jid else "",
                "salary_raw": "",
                "salary_min": sal if sal else None,
                "salary_max": sal_max if sal_max else None,
                "salary_currency": currency,
            })
        time.sleep(delay)
    log(f"WTTJ: {len(jobs)} ofertas")
    return jobs


# ------------------------------------------------------------------ Bayt (UAE/SA)

def fetch_bayt(delay):
    jobs, seen = [], set()
    queries = ["sales engineer", "account executive", "business development",
               "solutions consultant", "technical account manager", "pre-sales"]
    for q in queries:
        for page in range(1, 6):
            url = f"https://www.bayt.com/en/international/jobs/{q.replace(' ', '-')}-jobs/?page={page}"
            try:
                r = requests.get(url, headers=HEADERS, timeout=30)
                if r.status_code != 200:
                    break
                # Extract job cards from HTML (bayt embeds JSON-LD)
                import re as _re
                for m in _re.finditer(r'"@type"\s*:\s*"JobPosting".*?"title"\s*:\s*"([^"]+)".*?"url"\s*:\s*"([^"]+)".*?"datePosted"\s*:\s*"([^"]*)"', r.text):
                    title, jurl, posted = m.group(1), m.group(2), m.group(3)[:10]
                    jid = jurl.rstrip("/").split("/")[-1]
                    if jid in seen:
                        continue
                    seen.add(jid)
                    jobs.append({
                        "id": f"bayt-{jid}",
                        "title": title,
                        "company": "",
                        "location": "",
                        "description": "",
                        "summary": title,
                        "source": "bayt",
                        "posted": posted,
                        "url": jurl if jurl.startswith("http") else f"https://www.bayt.com{jurl}",
                        "salary_raw": "",
                        "salary_min": None,
                        "salary_max": None,
                        "salary_currency": "",
                    })
            except Exception as e:
                log(f"Bayt/{q}: error {e}")
            time.sleep(delay)
    log(f"Bayt: {len(jobs)} ofertas")
    return jobs


# --------------------------------------------------------------- GulfTalent

def fetch_gulftalent(delay):
    jobs, seen = [], set()
    queries = ["sales engineer", "account executive", "business development",
               "solutions consultant", "pre-sales"]
    for q in queries:
        url = f"https://www.gulftalent.com/jobs/search?q={q.replace(' ', '+')}"
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            if r.status_code != 200:
                continue
            import re as _re
            for m in _re.finditer(r'<a[^>]*href="(/jobs/[^"]+)"[^>]*>([^<]+)</a>', r.text):
                jpath, title = m.group(1), m.group(2).strip()
                jid = jpath.rstrip("/").split("/")[-1]
                if jid in seen:
                    continue
                seen.add(jid)
                jobs.append({
                    "id": f"gt-{jid}",
                    "title": title,
                    "company": "",
                    "location": "",
                    "description": "",
                    "summary": title,
                    "source": "gulftalent",
                    "posted": "",
                    "url": f"https://www.gulftalent.com{jpath}",
                    "salary_raw": "",
                    "salary_min": None,
                    "salary_max": None,
                    "salary_currency": "",
                })
        except Exception as e:
            log(f"GulfTalent/{q}: error {e}")
        time.sleep(delay)
    log(f"GulfTalent: {len(jobs)} ofertas")
    return jobs


# ----------------------------------------------------------- SwissDevJobs.ch

def fetch_swissdevjobs(delay):
    jobs, seen = [], set()
    url = "https://www.swissdevjobs.ch/rss"
    try:
        r = requests.get(url, headers=HEADERS, timeout=30)
        if r.status_code != 200:
            log(f"SwissDevJobs: HTTP {r.status_code}")
            return jobs
        import re as _re
        import xml.etree.ElementTree as ET
        root = ET.fromstring(r.text)
        for item in root.iter("item"):
            title_el = item.find("title")
            link_el = item.find("link")
            title = title_el.text if title_el is not None else ""
            link = link_el.text if link_el is not None else ""
            if not link or link in seen:
                continue
            seen.add(link)
            jid = link.rstrip("/").split("/")[-1].split("?")[0]
            if not jid:
                continue
            # Extract salary from title if present: [CHF 85'000 - 115'000]
            sal_m = _re.search(r"\[([^\]]+)\]", title or "")
            sal_raw = sal_m.group(1) if sal_m else ""
            clean_title = _re.sub(r"\s*@\s*.*$", "", title or "")
            jobs.append({
                "id": f"swdev-{jid}",
                "title": clean_title,
                "company": "",
                "location": "Switzerland",
                "description": "",
                "summary": title,
                "source": "swissdevjobs",
                "posted": "",
                "url": link,
                "salary_raw": sal_raw,
                "salary_min": None,
                "salary_max": None,
                "salary_currency": "CHF",
            })
    except Exception as e:
        log(f"SwissDevJobs: error {e}")
    log(f"SwissDevJobs: {len(jobs)} ofertas")
    return jobs


# -------------------------------------------------------------- jobs.ch

def fetch_jobs_ch(delay):
    jobs, seen = [], set()
    queries = ["sales+engineer", "account+executive", "business+development",
               "solutions+consultant", "presales"]
    for q in queries:
        url = f"https://www.jobs.ch/en/vacancies/?q={q}&limit=50"
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            if r.status_code != 200:
                continue
            import re as _re
            for m in _re.finditer(r'"@type"\s*:\s*"JobPosting".*?"title"\s*:\s*"([^"]+)".*?"url"\s*:\s*"([^"]+)".*?"datePosted"\s*:\s*"([^"]*)"', r.text):
                title, jurl, posted = m.group(1), m.group(2), m.group(3)[:10]
                jid = jurl.rstrip("/").split("/")[-1]
                if jid in seen:
                    continue
                seen.add(jid)
                jobs.append({
                    "id": f"jobsch-{jid}",
                    "title": title,
                    "company": "",
                    "location": "Switzerland",
                    "description": "",
                    "summary": title,
                    "source": "jobsch",
                    "posted": posted,
                    "url": jurl if jurl.startswith("http") else f"https://www.jobs.ch{jurl}",
                    "salary_raw": "",
                    "salary_min": None,
                    "salary_max": None,
                    "salary_currency": "CHF",
                })
        except Exception as e:
            log(f"jobs.ch/{q}: error {e}")
        time.sleep(delay)
    log(f"jobs.ch: {len(jobs)} ofertas")
    return jobs


# ----------------------------------------------------- Fuentes remote sin key

def _remote_salary(sal_min, sal_max, currency=""):
    cur = (currency or "USD").upper()
    if sal_min and sal_max:
        return f"{cur} {int(sal_min):,} - {int(sal_max):,} per year"
    if sal_min:
        return f"from {cur} {int(sal_min):,} per year"
    return ""


def _iso_date(value):
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value / 1000 if value > 10_000_000_000 else value,
                                          tz=timezone.utc).strftime("%Y-%m-%d")
        except Exception:
            return ""
    s = str(value or "")
    return s[:10]


def fetch_remoteok(delay):
    data = get_json(REMOTEOK_URL, label="RemoteOk", timeout=40)
    if not isinstance(data, list) or len(data) < 2:
        log(f"RemoteOk: respuesta inesperada ({type(data).__name__})")
        return []
    jobs, kept = [], 0
    for item in data[1:]:
        title = item.get("position") or ""
        loc = item.get("location") or "Remote"
        tags = " ".join(item.get("tags") or [])
        hay = f"{title} {tags} {loc}".lower()
        if not any(t in hay for t in REMOTEOK_TAGS):
            continue
        if not _geo_relevant(loc):
            continue
        kept += 1
        sal_min, sal_max = item.get("salary_min"), item.get("salary_max")
        content = f"{title} {tags} {item.get('description') or ''}"
        jobs.append({
            "id": f"remoteok-{item.get('id') or (item.get('slug') or '')}",
            "title": title,
            "company": item.get("company") or "",
            "location": loc,
            "description": trunc(strip_html(content)),
            "summary": " · ".join(filter(None, [title, "RemoteOk", loc])),
            "source": "remoteok",
            "posted": (item.get("date") or "")[:10],
            "url": item.get("url") or item.get("apply_url") or "",
            "salary_raw": _remote_salary(sal_min, sal_max),
            "salary_min": sal_min,
            "salary_max": sal_max,
            "salary_currency": "USD",
        })
        time.sleep(delay)
    log(f"RemoteOk: {len(data) - 1} descargadas -> {kept} relevantes")
    return jobs


def fetch_arbeitnow(delay):
    data = get_json(ARBEITNOW_URL, label="Arbeitnow", timeout=40)
    if not isinstance(data, dict) or not isinstance(data.get("data"), list):
        log(f"Arbeitnow: respuesta inesperada ({type(data).__name__})")
        return []
    jobs, kept = [], 0
    for item in data["data"]:
        title = item.get("title") or ""
        loc = item.get("location") or ""
        tags = " ".join(item.get("tags") or [])
        hay = f"{title} {tags} {loc} {item.get('job_types') or ''}".lower()
        if not any(t in hay for t in ARBEITNOW_TAGS):
            continue
        if not _geo_relevant(f"{loc} {item.get('remote') or ''}"):
            continue
        kept += 1
        content = f"{title} {tags} {item.get('description') or ''}"
        jobs.append({
            "id": f"arbeitnow-{item.get('slug') or ''}",
            "title": f"{title} ({loc})",
            "company": item.get("company_name") or "",
            "location": loc,
            "description": trunc(strip_html(content)),
            "summary": " · ".join(filter(None, [title, item.get("company_name") or "", loc])),
            "source": "arbeitnow",
            "posted": _iso_date(item.get("created_at")),
            "url": item.get("url") or "",
            "salary_raw": "",
            "salary_min": None,
            "salary_max": None,
            "salary_currency": "EUR",
        })
        time.sleep(delay)
    log(f"Arbeitnow: {len(data.get('data'))} descargadas -> {kept} relevantes")
    return jobs


def fetch_remotive(delay):
    jobs, kept = [], 0
    page = 0
    while len(jobs) < 200 and page < 6:
        data = get_json(f"{REMOTIVE_URL}?limit=100&page={page}",
                        label=f"Remotive p{page}", timeout=40)
        if not isinstance(data, dict) or not isinstance(data.get("jobs"), list):
            break
        page_items = data["jobs"]
        if not page_items:
            break
        for item in page_items:
            title = item.get("title") or ""
            cat = item.get("category") or ""
            tags = " ".join(item.get("tags") or [])
            loc = item.get("candidate_required_location") or "Remote"
            hay = f"{title} {cat} {tags}".lower()
            if not any(t in hay for t in REMOTIVE_CATEGORIES):
                continue
            if not (_geo_relevant(loc) or REMOTIVE_REMOTE_GEO.search(loc or "")):
                continue
            kept += 1
            content = f"{title} {cat} {tags} {item.get('description') or ''}"
            salary = item.get("salary") or ""
            jobs.append({
                "id": f"remotive-{item.get('id')}",
                "title": title,
                "company": item.get("company_name") or "",
                "location": loc,
                "description": trunc(strip_html(content)),
                "summary": " · ".join(filter(None, [title, cat, loc])),
                "source": "remotive",
                "posted": (item.get("publication_date") or "")[:10],
                "url": item.get("url") or "",
                "salary_raw": salary or "",
                "salary_min": None,
                "salary_max": None,
                "salary_currency": "",
            })
            time.sleep(delay)
        page += 1
    log(f"Remotive: {len(jobs) + 0} -> {kept} relevantes")
    return jobs


# ---------------------------------------------------------------- Google Jobs

def fetch_google_jobs(delay):
    jobs, seen = [], set()
    queries = ["sales+engineer", "account+executive", "business+development",
               "solutions+consultant", "technical+account+manager"]
    for q in queries:
        url = f"https://careers.google.com/jobs/results/?q={q}&hl=en&gl=us&num=50"
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            if r.status_code != 200:
                continue
            import re as _re
            # Google embeds structured data as JSON-LD
            for m in _re.finditer(r'"@type"\s*:\s*"JobPosting".*?"title"\s*:\s*"([^"]+)".*?"url"\s*:\s*"([^"]+)".*?"datePosted"\s*:\s*"([^"]*)"', r.text):
                title, jurl, posted = m.group(1), m.group(2), m.group(3)[:10]
                jid = jurl.rstrip("/").split("/")[-1]
                if jid in seen:
                    continue
                seen.add(jid)
                jobs.append({
                    "id": f"google-{jid}",
                    "title": title,
                    "company": "Google",
                    "location": "",
                    "description": "",
                    "summary": title,
                    "source": "google",
                    "posted": posted,
                    "url": jurl if jurl.startswith("http") else f"https://careers.google.com{jurl}",
                    "salary_raw": "",
                    "salary_min": None,
                    "salary_max": None,
                    "salary_currency": "USD",
                })
        except Exception as e:
            log(f"Google/{q}: error {e}")
        time.sleep(delay)
    log(f"Google: {len(jobs)} ofertas")
    return jobs


# --------------------------------------------------------------- Amazon Jobs

def fetch_amazon_jobs(delay):
    jobs, seen = [], set()
    queries = ["sales+engineer", "account+executive", "business+development",
               "solutions+consultant", "technical+account+manager"]
    for q in queries:
        url = f"https://www.amazon.jobs/en/search.json?q={q}&offset=0&result_limit=50&sort=recent"
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            r.raise_for_status()
            data = r.json()
            for item in data.get("jobs", []):
                jid = item.get("id_icims") or str(item.get("id", ""))
                title = item.get("title", "")
                if not jid or jid in seen:
                    continue
                seen.add(jid)
                loc = item.get("location", "")
                posted = (item.get("posted_date") or "")[:10]
                team = item.get("team", "")
                if isinstance(team, dict):
                    team = team.get("name", str(team))
                jobs.append({
                    "id": f"amazon-{jid}",
                    "title": title,
                    "company": "Amazon",
                    "location": loc,
                    "description": trunc(item.get("description", "")),
                    "summary": " · ".join(filter(None, [title, str(team)])),
                    "source": "amazon",
                    "posted": posted,
                    "url": f"https://www.amazon.jobs{item.get('job_path', '')}",
                    "salary_raw": "",
                    "salary_min": None,
                    "salary_max": None,
                    "salary_currency": "USD",
                })
        except Exception as e:
            log(f"Amazon/{q}: error {e}")
        time.sleep(delay)
    log(f"Amazon: {len(jobs)} ofertas")
    return jobs


# ------------------------------------------------------------- Microsoft Jobs

def fetch_microsoft_jobs(delay):
    jobs, seen = [], set()
    queries = ["sales+engineer", "account+executive", "business+development",
               "solutions+consultant", "technical+account+manager"]
    for q in queries:
        url = f"https://jobs.careers.microsoft.com/global/en/search?q={q}&pg=1&pgSz=50&o=Recent"
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            if r.status_code != 200:
                continue
            import re as _re
            # Microsoft/Eightfold renders client-side; try to find any embedded job data
            # Pattern: look for job-like URLs in href attributes
            for m in _re.finditer(r'href="(/global/en/job/\d+/[^"]+)"', r.text):
                jpath = m.group(1)
                jid = jpath.split("/job/")[1].split("/")[0] if "/job/" in jpath else ""
                title = ""
                # Try to get title from nearby text
                title_m = _re.search(r'title="([^"]+)"', r.text[max(0, m.start()-200):m.end()+200])
                if title_m:
                    title = title_m.group(1)
                if not jid or jid in seen:
                    continue
                seen.add(jid)
                jobs.append({
                    "id": f"ms-{jid}",
                    "title": title or f"Microsoft Job {jid}",
                    "company": "Microsoft",
                    "location": "",
                    "description": "",
                    "summary": title or f"Microsoft Job {jid}",
                    "source": "microsoft",
                    "posted": "",
                    "url": f"https://jobs.careers.microsoft.com{jpath}",
                    "salary_raw": "",
                    "salary_min": None,
                    "salary_max": None,
                    "salary_currency": "USD",
                })
        except Exception as e:
            log(f"Microsoft/{q}: error {e}")
        time.sleep(delay)
    log(f"Microsoft: {len(jobs)} ofertas")
    return jobs


# ----------------------------------------------------------------- Meta Jobs

def fetch_meta_jobs(delay):
    jobs, seen = [], set()
    queries = ["sales+engineer", "account+executive", "business+development",
               "solutions+consultant", "technical+account+manager"]
    for q in queries:
        url = f"https://www.metacareers.com/jobs?q={q}&limit=50"
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            if r.status_code != 200:
                continue
            import re as _re
            for m in _re.finditer(r'href="(/careers/jobs/[^"]+)"', r.text):
                jpath = m.group(1)
                jid = jpath.split("/")[-1]
                if not jid or jid in seen:
                    continue
                seen.add(jid)
                title_m = _re.search(r'title="([^"]+)"', r.text[max(0, m.start()-300):m.end()+300])
                title = title_m.group(1) if title_m else f"Meta Job {jid}"
                jobs.append({
                    "id": f"meta-{jid}",
                    "title": title,
                    "company": "Meta",
                    "location": "",
                    "description": "",
                    "summary": title,
                    "source": "meta",
                    "posted": "",
                    "url": f"https://www.metacareers.com{jpath}",
                    "salary_raw": "",
                    "salary_min": None,
                    "salary_max": None,
                    "salary_currency": "USD",
                })
        except Exception as e:
            log(f"Meta/{q}: error {e}")
        time.sleep(delay)
    log(f"Meta: {len(jobs)} ofertas")
    return jobs


# ----------------------------------------------------------------- Apple Jobs

def fetch_apple_jobs(delay):
    jobs, seen = [], set()
    queries = ["sales+engineer", "account+executive", "business+development",
               "solutions+consultant", "technical+account+manager"]
    for q in queries:
        # Apple jobs API
        url = f"https://jobs.apple.com/api/role/search?q={q}&limit=50&page=1"
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            if r.status_code != 200:
                # Try alternate HTML scraping
                url2 = f"https://jobs.apple.com/en-us/search?search={q.replace('+', ' ')}"
                r = requests.get(url2, headers=HEADERS, timeout=30)
                if r.status_code != 200:
                    continue
                import re as _re
                for m in _re.finditer(r'href="(/en-us/details/[^"]+)"', r.text):
                    jpath = m.group(1)
                    jid = jpath.split("/")[-1]
                    if not jid or jid in seen:
                        continue
                    seen.add(jid)
                    title_m = _re.search(r'title="([^"]+)"', r.text[max(0, m.start()-200):m.end()+200])
                    title = title_m.group(1) if title_m else f"Apple Job {jid}"
                    jobs.append({
                        "id": f"apple-{jid}",
                        "title": title,
                        "company": "Apple",
                        "location": "",
                        "description": "",
                        "summary": title,
                        "source": "apple",
                        "posted": "",
                        "url": f"https://jobs.apple.com{jpath}",
                        "salary_raw": "",
                        "salary_min": None,
                        "salary_max": None,
                        "salary_currency": "USD",
                    })
                continue
            data = r.json()
            for item in data.get("data", {}).get("rolesByStatics", {}).get("roleList", []):
                jid = item.get("id", "")
                title = item.get("name", "")
                if not jid or str(jid) in seen:
                    continue
                seen.add(str(jid))
                loc = ", ".join(item.get("location", [])) if isinstance(item.get("location"), list) else str(item.get("location", ""))
                jobs.append({
                    "id": f"apple-{jid}",
                    "title": title,
                    "company": "Apple",
                    "location": loc,
                    "description": trunc(item.get("description", "")),
                    "summary": title,
                    "source": "apple",
                    "posted": (item.get("datePosted") or "")[:10],
                    "url": f"https://jobs.apple.com/en-us/details/{jid}" if jid else "",
                    "salary_raw": "",
                    "salary_min": None,
                    "salary_max": None,
                    "salary_currency": "USD",
                })
        except Exception as e:
            log(f"Apple/{q}: error {e}")
        time.sleep(delay)
    log(f"Apple: {len(jobs)} ofertas")
    return jobs


# ----------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sources",
                    default="adzuna,greenhouse,ashby,workday,smartrecruiters,lever,epso,jooble,nvb,jobindex,wttj,swissdevjobs,amazon,microsoft,meta,apple,remoteok,arbeitnow,remotive",
                    help="fuentes separadas por coma")
    ap.add_argument("--delay", type=float, default=0.3,
                    help="segundos entre peticiones")
    args = ap.parse_args()

    sources = {s.strip() for s in args.sources.split(",")}
    secrets = load_secrets()
    profile = load_profile()
    companies = load_companies()

    all_jobs = []
    if "adzuna" in sources:
        all_jobs += fetch_adzuna(secrets, args.delay)
    if "greenhouse" in sources:
        all_jobs += fetch_greenhouse(args.delay, profile, companies)
    if "ashby" in sources:
        all_jobs += fetch_ashby(args.delay, profile, companies)
    if "workday" in sources:
        all_jobs += fetch_workday(args.delay, profile, companies)
    if "smartrecruiters" in sources:
        all_jobs += fetch_smartrecruiters(args.delay, profile, companies)
    if "epso" in sources:
        all_jobs += fetch_epso(args.delay, profile)
    if "lever" in sources:
        all_jobs += fetch_lever(args.delay, companies)
    if "jooble" in sources:
        all_jobs += fetch_jooble(args.delay, secrets)
    if "careerjet" in sources:
        all_jobs += fetch_careerjet(args.delay, secrets)
    if "nvb" in sources:
        all_jobs += fetch_nationale_vacaturebank(args.delay)
    if "jobindex" in sources:
        all_jobs += fetch_jobindex_rss(args.delay)
    if "wttj" in sources:
        all_jobs += fetch_wttj(args.delay, secrets)
    if "bayt" in sources:
        all_jobs += fetch_bayt(args.delay)
    if "gulftalent" in sources:
        all_jobs += fetch_gulftalent(args.delay)
    if "swissdevjobs" in sources:
        all_jobs += fetch_swissdevjobs(args.delay)
    if "jobsch" in sources:
        all_jobs += fetch_jobs_ch(args.delay)
    if "remoteok" in sources:
        all_jobs += fetch_remoteok(args.delay)
    if "arbeitnow" in sources:
        all_jobs += fetch_arbeitnow(args.delay)
    if "remotive" in sources:
        all_jobs += fetch_remotive(args.delay)
    if "google" in sources:
        all_jobs += fetch_google_jobs(args.delay)
    if "amazon" in sources:
        all_jobs += fetch_amazon_jobs(args.delay)
    if "microsoft" in sources:
        all_jobs += fetch_microsoft_jobs(args.delay)
    if "meta" in sources:
        all_jobs += fetch_meta_jobs(args.delay)
    if "apple" in sources:
        all_jobs += fetch_apple_jobs(args.delay)

    by_source = {}
    for j in all_jobs:
        by_source.setdefault(j["source"].split("-")[0], 0)
        by_source[j["source"].split("-")[0]] += 1

    RAW.parent.mkdir(parents=True, exist_ok=True)
    RAW.write_text(json.dumps({
        "generated": now_iso(),
        "count": len(all_jobs),
        "sources": by_source,
        "jobs": all_jobs,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"total {len(all_jobs)} ofertas -> {RAW}")
    for k, v in sorted(by_source.items()):
        log(f"  {k}: {v}")


if __name__ == "__main__":
    main()
