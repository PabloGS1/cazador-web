#!/usr/bin/env python3
"""
MATCHER — puntúa cada oferta (0-100) contra el perfil de Pablo.
Entrada: web/data/raw_jobs.json (scrape.py)
Salida:  web/data/jobs.json (con match%, summary, salario detectado, enlace)

Uso:
    python matcher.py [--min 40]
"""
import argparse
import html
import json
import re
import sys
from datetime import datetime
from pathlib import Path

import yaml

BASE = Path(__file__).parent
RAW = BASE / "web" / "data" / "raw_jobs.json"
OUT = BASE / "web" / "data" / "jobs.json"
FEATURES = BASE / "web" / "data" / "features.json"


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
    """Tier-based role taxonomy: match title against A/B/C tiers.
    Returns (weight, tier_label, 0) or (0, "", 0) if no match."""
    tax = profile.get("role_taxonomy", {})
    # Tier A first (direct match)
    tier_a = tax.get("tier_a", {})
    for t in tier_a.get("titles", []):
        if t.lower() in title_text:
            return tier_a.get("weight", 1.0), tier_a.get("label", "Target directo")
    # Tier B
    tier_b = tax.get("tier_b", {})
    for t in tier_b.get("titles", []):
        if t.lower() in title_text:
            return tier_b.get("weight", 0.6), tier_b.get("label", "Encaje parcial")
    # Tier C (data centre / AI infra)
    tier_c = tax.get("tier_c", {})
    for t in tier_c.get("titles", []):
        if t.lower() in title_text:
            return tier_c.get("weight", 0.4), tier_c.get("label", "DC/AI infra")
    return 0, ""



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
# Roles tecnicos DUROS que el usuario descarta explicitamente (no es ingeniero:
# su rol es ventas tecnico). MLOps/AIOps, programar con PyTorch, ML/DL engineering...
HARD_TECH = re.compile(
    r"\b(mlops|ml-?ops|aiops|ai-?ops|pytorch|tensorflow|keras|cuda|torchvision|ml engineer|machine learning engineer|deep learning engineer|llm engineer|computer vision engineer|model training|ml researcher|machine learning researcher|deep learning researcher|llm researcher|ai researcher|applied ai researcher|research engineer|applied scientist|post training)\b", re.I)
YEARS_RE = re.compile(r"(\d{1,2})\s*\+?\s*(?:-|–|to)?\s*\d{0,2}\s*years?\b", re.I)


def _domain_overlap(text, profile):
    """Returns overlap fraction (0-1): fraction of domain keyword groups matched."""
    groups = profile.get("domain_keywords", {}).get("keywords", [])
    if not groups:
        return 0.0
    hits = sum(1 for group in groups if _match_any(text, group))
    return hits / len(groups)


def _score_skills(text, profile):
    kws = profile.get("skills_keywords", {}).get("keywords", [])
    hits = sum(1 for k in kws if k.lower() in text)
    return hits


def _score_location(job, profile):
    """Geography weight from profile.yaml geo scoring. Default 0.3 for unmatched."""
    loc = (job.get("location") or "").lower()
    src = (job.get("source") or "").lower()
    blob = f"{loc} {src}"
    geo = profile.get("geography", {}).get("scoring", {})
    best = 0.3  # default for remote/unmatched
    for kw, w in geo.items():
        if kw.lower() in blob:
            best = max(best, w)
    return best


def _seniority_fit(text, profile):
    """Returns multiplier: 1.0 mid/senior IC, 0.3 director+, 0.0 junior/intern."""
    cfg = profile.get("seniority", {})
    # Check junior/intern first → 0.0
    for k in cfg.get("penalty", []):
        if k.lower() in text:
            # director/VP gets 0.3, others get 0.0
            if k.lower() in ("director", "vp", "vice president"):
                return cfg.get("director_penalty", 0.3)
            return cfg.get("junior_penalty", 0.0)
    # Check senior/lead/manager → 1.0
    for k in cfg.get("bonus", []):
        if k.lower() in text:
            return 1.0
    # Default: mid-level IC → 1.0
    return 1.0


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


# Idioma local requerido pese a que la descripción esté en inglés.
# Búsqueda PREVENTIVA y amplia: cualquier mención de la lengua local en
# contexto de requisito (fluent, speaking, required, native, & English...).
# OJO: "english" queda fuera a propósito (no es penalizable) y los refs de
# mercado ("in Germany", "German market", "Dutch customers") no casan con
# estos patrones -> no se marcan.
LOCAL_LANG_WORDS = (
    "dutch|flemish|german|french|italian|spanish|danish|norwegian|swedish|finnish|"
    "portuguese|japanese|korean|thai|chinese|mandarin|cantonese|turkish|polish|czech|"
    "hungarian|greek|arabic|russian|hindi|tamil|indonesian|vietnamese|malay"
)
LANG_REQ_RE = re.compile(
    # fluencia directa: "fluent in German", "fluency in Dutch", "fluent German"
    r"fluen[ct](?:y)?\s+(?:in\s+)?(?:both\s+)?(?:" + LOCAL_LANG_WORDS + r")"
    # "<lang> speaking/speaker/fluent/language/fluency" o "<lang>-speaking"
    r"|(?:" + LOCAL_LANG_WORDS + r")\s*(?:-|–)?\s*(?:fluen[ct](?:y)?|speaking|speaker|language)"
    # "speak/must speak [nivel] <lang>", "you speak <lang>"
    r"|(?:you\s+)?(?:must\s+)?(?:speak|speaks)\s+(?:native-?level|native|fluent|business-?level|conversational|perfect|excellent|good)?\s+(?:" + LOCAL_LANG_WORDS + r")"
    # "<lang> required/mandatory/native/mother tongue/essential/a must"
    r"|(?:" + LOCAL_LANG_WORDS + r")\s+(?:required|mandatory|native|mother tongue|essential|a must|is a must|fluency)"
    # "native-level <lang>", "native speaker of <lang>", "proficient in <lang>"
    r"|(?:native-?level|native|fluent|proficient|perfect)\s+(?:speaker|fluency)?\s+(?:of|in)?\s*(?:" + LOCAL_LANG_WORDS + r")"
    # "exceptional/excellent/strong... [verbal and written] <lang>"
    r"|(?:exceptional|excellent|strong|perfect|good|very good|flawless|impeccable|business-?fluent)\s+(?:command of|written and spoken|written & spoken|verbal and written|written and verbal|verbal & written|oral and written|written and oral|spoken and written)\s+(?:" + LOCAL_LANG_WORDS + r")"
    # working/business/office/company language: <lang>
    r"|(?:working|business|office|company)\s+language[:\s]+(?:" + LOCAL_LANG_WORDS + r")"
    # bilingual <lang>
    r"|(?:bilingual|bi-lingual)\s+(?:in\s+)?(?:" + LOCAL_LANG_WORDS + r")"
    # "<lang> & English", "<lang>/English", "<lang> and English" (y al revés)
    r"|(?:" + LOCAL_LANG_WORDS + r")\s*(?:&|/)\s*english"
    r"|english\s*(?:&|/)\s*(?:" + LOCAL_LANG_WORDS + r")"
    r"|(?:" + LOCAL_LANG_WORDS + r")\s+and\s+english"
    r"|english\s+and\s+(?:" + LOCAL_LANG_WORDS + r")"
    # "communicate/communication [fluently] in <lang>"
    r"|(?:communicate|communication)\s+(?:fluently\s+)?(?:in\s+)?(?:both\s+)?(?:" + LOCAL_LANG_WORDS + r")"
    r"|(?:able|ability)\s+to\s+communicate\s+in\s+(?:" + LOCAL_LANG_WORDS + r")",
    re.I)
LANG_WORD_RE = re.compile(r"(?:" + LOCAL_LANG_WORDS + r")", re.I)


def detect_local_lang(text):
    """Devuelve p.ej. 'dutch, french' si el puesto exige idioma(s) local(es)."""
    if not text:
        return ""
    t = html.unescape(text)  # "German &amp; English" -> "German & English"
    langs = set()
    for mtxt in LANG_REQ_RE.findall(t):
        w = LANG_WORD_RE.search(mtxt)
        if w:
            langs.add(w.group(0).lower())
    return ", ".join(sorted(langs))


# ------------------------------------------------------------------ main

# ------------------------------------------------------- features + score

# Features por oferta: todo lo independiente del perfil se calcula UNA vez por
# scrape y se guarda en web/data/features.json. score() reutiliza esas features
# para puntuar contra CUALQUIER perfil (multi-usuario) sin re-scrapear.
# OJO: el texto de matching va COMPLETO (un cap a 3000 chars cambiaba el score
# de ~1/4 de las ofertas y movia el umbral 40). features.json pesa mas pero el
# resultado es identico al pipeline anterior.


def build_features(raw_jobs):
    feats = []
    for j in raw_jobs:
        title = (j.get("title") or "").lower()
        text = _text_of(j)
        sal_min_eur, sal_max_eur, sal_raw = _structured_salary(j)
        if not sal_min_eur:
            sal_min_eur, sal_max_eur, sal_raw = detect_salary(text)
        feat = {
            "id": j.get("id"),
            "title": j.get("title") or "",
            "company": j.get("company") or "",
            "location": j.get("location") or "",
            "source": j.get("source") or "",
            "url": j.get("url") or "",
            "posted": j.get("posted") or "",
            "summary": j.get("summary") or "",
            "description": j.get("description") or "",
            "title_lower": title,
            "text_lower": text,
            "salary_min_eur": sal_min_eur,
            "salary_max_eur": sal_max_eur,
            "salary_raw": sal_raw,
            "lang": detect_language((j.get("description") or "")[:2500]),
            "lang_req": detect_local_lang(text),
            "years_min": _years_min(text),
            "eng_title": bool(ENGINEERING_ONLY.search(title)),
            "hard_block": bool(HARD_BLOCK.search(title)),
            "hard_tech": bool(HARD_TECH.search(title)),
        }
        # campos extra de ciertas fuentes (Adzuna/EPSO) se conservan tal cual
        for k in ("contract", "category", "grade", "salary_currency"):
            if k in j:
                feat[k] = j[k]
        feats.append(feat)
    return feats


def _hard_rejects(feat, profile):
    """Check all hard reject conditions. Returns (reject: bool, reason: str)."""
    text = feat["text_lower"]
    title = feat["title_lower"]
    hr = profile.get("hard_reject", {})
    ai = profile.get("anti_identity", {})

    # 1. Anti-identity: reject title patterns (ML engineer, SDR, etc.)
    for pat in ai.get("reject_title_patterns", []):
        if pat.lower() in title:
            return True, f"anti-identity: {pat}"

    # 2. Restricted location
    for pat in hr.get("restricted_locations", []):
        if pat.lower() in text:
            return True, f"restricted location: {pat}"

    # 3. Forbidden certifications (mandatory)
    for cert in hr.get("forbidden_certs", []):
        if cert.lower() in text:
            return True, f"forbidden cert: {cert}"

    # 4. Hands-on production ownership
    for pat in hr.get("production_patterns", []):
        if pat.lower() in text:
            return True, f"production ownership: {pat}"

    # 5. Established network in specific market
    for pat in hr.get("established_network_patterns", []):
        if pat.lower() in text:
            return True, f"network required: {pat}"

    # 6. Language not in user's spoken languages
    if feat["lang"] != "en":
        return True, f"not english: {feat['lang']}"

    return False, ""


def _language_cap(feat, profile):
    """Techo de score si el puesto exige un idioma que el usuario no habla
    con fluidez. No descarta: limita para que nunca llegue a match >= 60."""
    lang_req = feat.get("lang_req") or ""
    if not lang_req:
        return None
    spoken = set(profile.get("hard_reject", {}).get("languages_spoken", []))
    req_langs = set(l.strip() for l in lang_req.split(",") if l.strip())
    if req_langs & spoken:
        return None
    return 45  # language barrier -> por debajo de 60


def _seniority_years_cap(feat, profile):
    """Techo de score según años mínimos pedidos. >9 años nunca llega a 60."""
    yrs = feat.get("years_min") or 0
    if yrs >= 13:
        return 35
    if yrs >= 10:
        return 50
    if yrs >= 9:
        return 55
    if yrs >= 8:
        return 70
    return None


def score(feat, profile):
    """New formula: 100 × role_weight × geo_weight × (0.5 + 0.5 × domain_overlap) × seniority_fit
    Hard rejects → score = 0 before formula. Role not in A/B/C → score = 0.
    Idiomas no hablados y años >9 limitan el max (nunca llegan a 60)."""
    title = feat["title_lower"]
    text = feat["text_lower"]

    # --- Hard rejects → 0 ---
    rejected, rej_reason = _hard_rejects(feat, profile)
    if rejected:
        return 0, "REJECTED", rej_reason

    # --- Role taxonomy filter ---
    role_w, role_label = _score_role(title, text, profile)
    if role_w == 0:
        return 0, "no role match", "title not in tier A/B/C"

    # --- Formula ---
    geo_w = _score_location(feat, profile)
    domain_ov = _domain_overlap(text, profile)
    domain_mod = 0.5 + 0.5 * domain_ov
    sen_fit = _seniority_fit(text, profile)

    match = 100 * role_w * geo_w * domain_mod * sen_fit
    match = max(0, min(90, round(match)))

    # --- Techo por idiomas / años ---
    caps = []
    lang_cap = _language_cap(feat, profile)
    years_cap = _seniority_years_cap(feat, profile)
    if lang_cap is not None:
        caps.append(lang_cap)
        match = min(match, lang_cap)
    if years_cap is not None:
        caps.append(years_cap)
        match = min(match, years_cap)

    # --- Build reasons ---
    reasons = []
    reasons.append(role_label)
    if geo_w < 0.3:
        reasons.append(f"geo {geo_w:.2f}")
    elif geo_w >= 0.8:
        reasons.append(f"geo {geo_w:.2f}")
    if domain_ov > 0:
        reasons.append(f"domain {domain_ov:.0%}")
    if sen_fit < 1.0:
        reasons.append(f"seniority ×{sen_fit}")
    if lang_cap is not None:
        reasons.append(f"idioma req cap {lang_cap}")
    if years_cap is not None:
        reasons.append(f"años cap {years_cap}")

    return match, role_label, "; ".join(reasons)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min", type=int, default=40)
    ap.add_argument("--max", type=int, default=200)
    ap.add_argument("--rebuild-features", action="store_true",
                    help="regenera features.json aunque ya exista")
    args = ap.parse_args()

    if not RAW.exists():
        sys.exit(f"No encuentro {RAW}. Ejecuta primero scrape.py")
    data = json.loads(RAW.read_text(encoding="utf-8"))
    jobs = data.get("jobs", []) if isinstance(data, dict) else data
    profile = load_profile()

    features = build_features(jobs)
    FEATURES.parent.mkdir(parents=True, exist_ok=True)
    FEATURES.write_text(json.dumps({"generated": datetime.now().isoformat(),
                                    "count": len(features), "jobs": features},
                                   ensure_ascii=False, indent=1),
                        encoding="utf-8")

    out = []
    for feat in features:
        match, role_label, why = score(feat, profile)
        if match < args.min or match > args.max:
            continue
        j = dict(feat)
        j["match"] = match
        j["role_family"] = role_label or "otro"
        j["why"] = why
        j["salary"] = feat["salary_raw"] or ""
        j["salary_eur"] = feat["salary_min_eur"]
        j["salary_max_eur"] = feat["salary_max_eur"]
        j["summary"] = " · ".join(filter(None, [
            feat["title"], feat["company"], feat["location"],
            feat["salary_raw"] or "", feat["source"]]))
        slim = dict(j)
        slim["description"] = (feat["description"] or "")[:500]
        for k in ("title_lower", "text_lower", "eng_title", "hard_block",
                  "hard_tech", "years_min"):
            slim.pop(k, None)
        out.append(slim)

    out.sort(key=lambda x: (-x["match"], x.get("posted", "")), reverse=False)
    out.sort(key=lambda x: -x["match"])
    OUT.write_text(json.dumps({"generated": datetime.now().isoformat(), "count": len(out),
                               "jobs": out}, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"{len(out)} ofertas >= {args.min} match. -> {OUT}")


if __name__ == "__main__":
    main()
