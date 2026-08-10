#!/usr/bin/env python3
"""
MATCHER — puntúa cada oferta (0-100) contra el perfil de Pablo.
Entrada: web/data/raw_jobs.json (scrape.py)
Salida:  web/data/jobs.json (con match%, summary, salario detectado, enlace)

Uso:
    python matcher.py [--min 40]
"""
import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

import yaml

BASE = Path(__file__).parent
RAW = BASE / "web" / "data" / "raw_jobs.json"
OUT = BASE / "web" / "data" / "jobs.json"


def load_profile():
    return yaml.safe_load((BASE / "profile.yaml").read_text(encoding="utf-8"))


def _text_of(job):
    return " ".join(filter(None, [
        job.get("title", ""),
        job.get("company", ""),
        job.get("location", ""),
        job.get("description", ""),
        job.get("summary", ""),
    ])).lower()


def _match_any(text, kws):
    for k in kws:
        if k.lower() in text:
            return True
    return False


def _score_role(title_text, text, profile):
    """Keyword de rol en el TÍTULO = peso completo; solo en la descripción
    se puntúa con menos (el título manda en ofertas de venta)."""
    for fam, cfg in profile["target_roles"].items():
        if _match_any(title_text, cfg["keywords"]):
            return cfg["weight"], cfg["label"], fam
    for fam, cfg in profile["target_roles"].items():
        if _match_any(text, cfg["keywords"]):
            return max(0, cfg["weight"] - 20), cfg["label"], fam
    return (0, "", "")


def _role_keywords(profile):
    kws = []
    for fam in profile["target_roles"].values():
        kws += fam["keywords"]
    return [k.lower() for k in kws]


# Títulos claramente de ingeniería/no-venta: bajan el match aunque la
# descripción suelte keywords sueltas (evita que el radar sea ruido dev).
ENGINEERING_ONLY = re.compile(
    r"\b(full-?stack|front-?end|back-?end|software engineer|data engineer|"
    r"data scientist|ml engineer|machine learning engineer|devops|sre|"
    r"site reliability|qa engineer|tester|product designer|ux designer|"
    r"technical recruiter|recruiter|talent acquisition|accountant|"
    r"legal counsel|marketing manager|content writer|social media|"
    r"counsel|legal|marketing|finance|recruiter|talent|hr|"
    r"engineer|engineering)\b", re.I)

# Roles de soporte (legal/HR/finanzas/marketing) que NO son venta: fuera
# aunque el título coincida con un keyword de rol (p.ej. "Commercial Counsel").
HARD_BLOCK = re.compile(
    r"\b(counsel|attorney|lawyer|compliance|paralegal|secretary|receptionist|"
    r"accountant|accounting|audit|auditor|payroll|"
    r"recruiter|talent acquisition|hr partner|hr business partner|"
    r"content writer|social media|marketing manager|marketing director|"
    r"community manager|support specialist|helpdesk)\b", re.I)

# Títulos de rol técnico-comercial: si piden muchos años, bajan el match
# (el usuario no quiere puestos "extremadamente demandantes" salvo en BD).
TECH_ROLE_KEYWORDS = [
    "sales engineer", "solutions engineer", "solution engineer", "presales",
    "pre-sales", "pre sales", "technical sales", "solutions consultant",
    "value engineer", "solutions architect", "technical account", "field engineer",
    "product engineer", "product owner", "product manager", "product specialist",
    "sales consultant", "technical consultant", "solutions advisor",
]
YEARS_RE = re.compile(r"(\d{1,2})\s*\+?\s*(?:-|–|to)?\s*\d{0,2}\s*years?\b", re.I)


def _count_domain(text, profile):
    hits = 0
    for group in profile["domain_keywords"]["keywords"]:
        if _match_any(text, group):
            hits += 1
    return hits


def _score_skills(text, profile):
    hits = sum(1 for k in profile["skills_from_cv"]["keywords"]
               if k.lower() in text)
    return hits


def _score_location(job, profile):
    loc = (job.get("location") or "").lower()
    # también mira país del portal (fuente)
    src = (job.get("source") or "").lower()
    blob = f"{loc} {src}"
    best = 0
    for kw, w in profile["location_prefs"]["scoring"].items():
        if kw.lower() in blob:
            best = max(best, w)
    return best


def _seniority_delta(text, profile):
    cfg = profile["seniority"]
    bonus = sum(1 for k in cfg["bonus"] if k in text)
    penalty = sum(1 for k in cfg["penalty"] if k in text)
    return min(bonus, 3) - min(penalty, 2)


# ---------------------------------------------------------------- salario

CUR = {
    "eur": 1.0, "€": 1.0, "euros": 1.0, "euro": 1.0,
    "usd": 0.92, "$": 0.92, "dollar": 0.92,
    "chf": 1.06, "sfr": 1.06,
    "sgd": 0.70, "s$": 0.70,
    "nok": 0.086, "kr": 0.086,
    "myr": 0.21, "rm": 0.21,
    "mxn": 0.047, "mx$": 0.047,
    "thb": 0.026, "baht": 0.026, "฿": 0.026,
    "gbp": 1.15, "£": 1.15,
    "sek": 0.087, "dkk": 0.134,
    "pln": 0.23, "czk": 0.041,
    "cad": 0.66, "aud": 0.60, "nzd": 0.55,
    "inr": 0.011, "brl": 0.18,
}

RANGE_RE = re.compile(r"(\d{2,3}(?:[.,]\d{3})*)\s*(?:-|–|to)\s*(\d{2,3}(?:[.,]\d{3})*)\s*(\w+)", re.I)
SINGLE_RE = re.compile(r"(?:up to|circa|about|~)?\s*(\d{2,3}(?:[.,]\d{3})*)\s*(\w+)(?:\s*(?:per|/)\s*(year|annum|yr|month|mo|k))?", re.I)


def _structured_salary(job):
    """Usa salary_min/max (Adzuna) si existen; convierte a EUR.
    Devuelve (min_eur, max_eur, raw). Valores anuales < 20k son basura
    (parses rotos tipo "€45" o "por hora/semana") -> se descartan."""
    lo = job.get("salary_min")
    if not lo:
        return None, None, ""
    hi = job.get("salary_max") or lo
    cur = (job.get("salary_currency") or "eur").lower()
    mult = _norm_currency(cur)
    if not mult:
        return None, None, ""
    a, b = sorted((lo * mult, hi * mult))
    if a < 20000:
        return None, None, ""
    return int(a), int(b), f"{a:,.0f}–{b:,.0f} {cur.upper()}"


def _to_number(s):
    return float(s.replace(".", "").replace(",", "")) if s else 0


def _norm_currency(unit):
    u = unit.lower().rstrip("s")
    for cur, mult in CUR.items():
        if u == cur.lower().lstrip("\\"):
            return mult
    return None


def detect_salary(text):
    """Devuelve (min_eur_aprox, max_eur, raw). No filtra, solo informa."""
    found = []
    for m in RANGE_RE.finditer(text):
        a, b, unit = m.groups()
        mult = _norm_currency(unit)
        if mult:
            found.append((min(_to_number(a), _to_number(b)) * mult,
                          max(_to_number(a), _to_number(b)) * mult, m.group(0)))
    for m in SINGLE_RE.finditer(text):
        val, unit, per = m.groups()
        mult = _norm_currency(unit)
        if mult and val and int(_to_number(val)) >= 30:
            amount = _to_number(val) * mult
            if per and per.lower().startswith("m"):  # per month
                amount *= 12
            found.append((amount, amount, m.group(0)))
    if not found:
        return None, None, ""
    lo = min(f[0] for f in found)
    hi = max(f[1] for f in found)
    if lo < 20000:  # descarta parses rotos (horas, semanas, €45...)
        return None, None, ""
    return int(lo), int(hi), found[0][2]


def _years_min(text):
    yrs = [int(m.group(1)) for m in YEARS_RE.finditer(text)]
    return min(yrs) if yrs else 0


# ------------------------------------------------------------------ idioma

# Stopwords por idioma: si la descripción está en el idioma local, es señal
# de que buscan gente local -> el puesto baja mucho de match (preferencia
# del usuario: solo ofertas en inglés). Se puntúa también el inglés para
# evitar falsos positivos con palabras comunes (p.ej. "a", "de", "at").
LANG_STOP = {
    "en": [" the ", " and ", " with ", " your ", " our ", " experience ",
           " opportunity ", " position ", " responsibilities ", " this role ",
           " you will ", " we are ", " team ", " company ", " applicant "],
    "nl": [" het ", " een ", " voor ", " met ", " wij ", " onze ", " jouw ",
           " van ", " niet ", " deze ", " zijn "],
    "de": [" der ", " die ", " das ", " und ", " mit ", " für ", " wir ", " sie ",
           " ihre ", " nicht ", " sowie ", " diesem "],
    "fr": [" le ", " la ", " les ", " des ", " pour ", " avec ", " vous ",
           " notre ", " nos ", " dans ", " également "],
    "es": [" el ", " los ", " las ", " para ", " con ", " nuestro ", " nuestra ",
           " entre ", " sobre ", " también "],
    "it": [" il ", " gli ", " per ", " con ", " della ", " delle ", " anche ",
           " sono ", " nostro "],
    "pt": [" são ", " você ", " nossa ", " nosso ", " também ", " experiência ",
           " suas ", " seus "],
    "da": [" og ", " det ", " er ", " ikke ", " vi ", " til ", " jeg "],
    "sv": [" och ", " att ", " det ", " som ", " på ", " för ", " inte ", " har "],
    "pl": [" oraz ", " dla ", " jest ", " są ", " się ", " nie ", " które "],
}

NON_LATIN_RE = re.compile(r"[\u3040-\u30ff\uac00-\ud7af\u0e00-\u0e7f\u4e00-\u9fff\u0600-\u06ff]")


def detect_language(text):
    if not text:
        return "en"
    t = " " + text.lower() + " "
    nol = len(NON_LATIN_RE.findall(t))
    if nol > 8:
        return "xx"
    best, bestn = "en", 0
    for lang, stops in LANG_STOP.items():
        n = sum(t.count(s) for s in stops)
        if n > bestn:
            best, bestn = lang, n
    return best if bestn > 2 else "en"


# Idiota local requerido pese a que la descripción esté en inglés:
# "fluent in Dutch", "Dutch speaking", "must speak German", "French required"...
# OJO: se excluye "english" a propósito (no es penalizable).
LOCAL_LANG_WORDS = (
    "dutch|flemish|german|french|italian|spanish|danish|norwegian|swedish|finnish|"
    "portuguese|japanese|korean|thai|chinese|mandarin|cantonese|turkish|polish|czech|"
    "hungarian|greek|arabic|russian|hindi|tamil|indonesian|vietnamese|malay"
)
LANG_REQ_RE = re.compile(
    r"fluen[ct](?:y)?\s+(?:in\s+)?(?:both\s+)?(?:" + LOCAL_LANG_WORDS + r")"
    r"|(?:" + LOCAL_LANG_WORDS + r")\s*(?:-|–)?\s*(?:fluen[ct](?:y)?|speaking|speaker|language)"
    r"|(?:speak|speaks|must speak|must be fluent in)\s+(?:" + LOCAL_LANG_WORDS + r")"
    r"|(?:" + LOCAL_LANG_WORDS + r")\s+(?:required|mandatory|native|mother tongue|essential|a must|is a must)"
    r"|(?:native|fluent|proficient)\s+(?:speaker|fluency)?\s+(?:of|in)?\s*(?:" + LOCAL_LANG_WORDS + r")"
    r"|(?:excellent|good|very good)\s+(?:command of|written and spoken|written & spoken|verbal and written)\s+(?:" + LOCAL_LANG_WORDS + r")"
    r"|(?:working|business|office|company)\s+language[:\s]+(?:" + LOCAL_LANG_WORDS + r")",
    re.I)
LANG_WORD_RE = re.compile(r"(?:" + LOCAL_LANG_WORDS + r")", re.I)


def detect_local_lang(text):
    """Devuelve p.ej. 'dutch, french' si el puesto exige idioma(s) local(es)."""
    if not text:
        return ""
    langs = set()
    for mtxt in LANG_REQ_RE.findall(text):
        w = LANG_WORD_RE.search(mtxt)
        if w:
            langs.add(w.group(0).lower())
    return ", ".join(sorted(langs))


# ------------------------------------------------------------------ main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min", type=int, default=40)
    ap.add_argument("--max", type=int, default=200)
    args = ap.parse_args()

    if not RAW.exists():
        sys.exit(f"No encuentro {RAW}. Ejecuta primero scrape.py")
    data = json.loads(RAW.read_text(encoding="utf-8"))
    jobs = data.get("jobs", []) if isinstance(data, dict) else data
    profile = load_profile()
    role_keywords = _role_keywords(profile)

    out = []
    for j in jobs:
        title = (j.get("title") or "").lower()
        text = _text_of(j)
        role_w, role_label, role_fam = _score_role(title, text, profile)
        domain_hits = _count_domain(text, profile)
        domain_w = min(domain_hits, 3) * 8
        skills_w = min(_score_skills(text, profile), 4) * 2
        loc_w = _score_location(j, profile)
        sen = _seniority_delta(text, profile)

        match = role_w + domain_w + skills_w + loc_w
        match = max(0, min(90, match))
        if sen < 0:
            match = max(0, match - 4)
        if ENGINEERING_ONLY.search(title) and not _match_any(title, role_keywords):
            match = max(0, match - 40)
        if HARD_BLOCK.search(title):
            match = max(0, match - 60)
        # años de experiencia exigidos en roles técnico-comerciales
        if role_fam and role_fam in ("sales_engineering", "product_engineer", "key_account"):
            y = _years_min(text)
            if y >= 9:
                match = max(0, match - 10)
            elif y >= 6:
                match = max(0, match - 6)

        sal_min_eur, sal_max_eur, sal_raw = _structured_salary(j)
        if not sal_min_eur:
            sal_min_eur, sal_max_eur, sal_raw = detect_salary(text)
        if sal_min_eur and sal_min_eur < 30000:
            match = max(0, match - 5)

        # idioma: solo ofertas en inglés (local = buscan gente local)
        lang = detect_language((j.get("description") or "")[:2500])
        j["lang"] = lang
        if lang != "en":
            match = max(0, match - 30)

        # idioma local exigido pese a estar en inglés (p.ej. "Dutch fluency")
        lang_req = detect_local_lang(text)
        j["lang_req"] = lang_req
        if lang_req:
            match = max(0, match - 30)

        if match < args.min or match > args.max:
            continue

        reasons = []
        if role_label:
            reasons.append(role_label)
        if domain_hits:
            reasons.append(f"{domain_hits} dominios IA/Data")
        if skills_w:
            reasons.append("skills CV")
        if lang_req:
            reasons.append(f"requiere {lang_req}")

        j["match"] = match
        j["role_family"] = role_label or "otro"
        j["why"] = "; ".join(reasons)
        j["salary"] = sal_raw or ""
        j["salary_eur"] = sal_min_eur
        j["salary_max_eur"] = sal_max_eur
        j["summary"] = " · ".join(filter(None, [
            j.get("title"),
            j.get("company"),
            j.get("location"),
            sal_raw or "",
            j.get("source"),
        ]))
        slim = dict(j)
        slim["description"] = (j.get("description") or "")[:500]
        out.append(slim)

    out.sort(key=lambda x: (-x["match"], x.get("posted", "")), reverse=False)
    out.sort(key=lambda x: -x["match"])
    OUT.write_text(json.dumps({"generated": datetime.now().isoformat(), "count": len(out),
                               "jobs": out}, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"{len(out)} ofertas >= {args.min} match. -> {OUT}")


if __name__ == "__main__":
    main()
