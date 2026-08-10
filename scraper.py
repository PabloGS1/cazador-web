#!/usr/bin/env python3
"""
CAZADOR SCRAPER — junta ofertas de fuentes públicas sin login.

Fuentes:
  - Adzuna          (NL / CH / SG)  API con app_id/app_key de secrets.yaml o env
  - Greenhouse      (boards públicos, sin token) — lista en companies.yaml
  - Ashby           (posting-api, sin token) — startups de IA, companies.yaml
  - Workday         (API CXS pública) — grandes empresas, companies.yaml
  - SmartRecruiters (API pública) — ASML, Renesas, WD, Statkraft, Grab...
  - Lever           (api.lever.co)  opcional y desactivado por defecto
                                    (a fecha de hoy responde 404 para casi todo)

Salida: web/data/raw_jobs.json  (alimenta a matcher.py)

Uso:
    python scraper.py                     # adzuna + greenhouse + ashby + workday + sr
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

# Portales de Adzuna que cubren la estrategia 80/15/5
ADZUNA_COUNTRIES = [
    ("nl", "Netherlands"),
    ("ch", "Switzerland"),
    ("sg", "Singapore"),
]

# Límite de resultados por query y país: NL copa el grueso (80%),
# CH y SG se recortan para respetar la estrategia 15/5.
ADZUNA_CAP = {"nl": 40, "ch": 20, "sg": 15}
ADZUNA_RETRIES = 3

# Queries curadas para no quemar la cuota de la API (perfil.yaml)
ADZUNA_QUERIES = [
    "sales engineer", "solutions engineer", "presales",
    "business development", "account executive", "account manager",
    "product manager", "product engineer", "cloud sales", "SaaS",
    "artificial intelligence", "machine learning", "data engineer",
    "data center", "GPU", "HPC",
]

# Lever: el endpoint público responde 404 para la mayoría hoy; añade slugs
# que sí funcionen si quieres reactivarlo (slugs -> nombre).
LEVER_COMPANIES = {}

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


def trunc(s, n=6000):
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
    for fam in profile["target_roles"].values():
        role_kws += fam["keywords"]
    domain_kws = []
    for group in profile["domain_keywords"]["keywords"]:
        domain_kws += group
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


# ------------------------------------------------------------------- Lever

def fetch_lever(delay):
    jobs, seen = [], set()
    for slug, name in LEVER_COMPANIES.items():
        url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            log(f"Lever {slug}: error {e}")
            time.sleep(delay)
            continue
        for item in data:
            jid = item.get("id")
            if not jid or jid in seen:
                continue
            seen.add(jid)
            jobs.append({
                "id": f"lever-{slug}-{jid}",
                "title": item.get("text") or "",
                "company": name,
                "location": item.get("categories", {}).get("location") or "",
                "description": trunc(strip_html(item.get("descriptionPlain") or
                                                item.get("description"))),
                "summary": " · ".join(filter(None, [item.get("text"), name])),
                "source": f"lever-{slug}",
                "posted": (item.get("createdAt") or "")[:10],
                "url": item.get("hostedUrl") or "",
                "salary_raw": "",
                "salary_min": None,
                "salary_max": None,
                "salary_currency": "",
            })
        time.sleep(delay)
    return jobs


# -------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sources",
                    default="adzuna,greenhouse,ashby,workday,smartrecruiters",
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
    if "lever" in sources:
        all_jobs += fetch_lever(args.delay)

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
