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
            return cfg["weight"], cfg["label"]
    for fam, cfg in profile["target_roles"].items():
        if _match_any(text, cfg["keywords"]):
            return cfg["weight"] - 15, cfg["label"]
    return (0, "")


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
    r"engineer|engineering)\b", re.I)


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
}

RANGE_RE = re.compile(r"(\d{2,3}(?:[.,]\d{3})*)\s*(?:-|–|to)\s*(\d{2,3}(?:[.,]\d{3})*)\s*(\w+)", re.I)
SINGLE_RE = re.compile(r"(?:up to|circa|about|~)?\s*(\d{2,3}(?:[.,]\d{3})*)\s*(\w+)(?:\s*(?:per|/)\s*(year|annum|yr|month|mo|k))?", re.I)


def _to_number(s):
    return float(s.replace(".", "").replace(",", "")) if s else 0


def _norm_currency(unit):
    u = unit.lower().rstrip("s")
    for cur, mult in CUR.items():
        if u == cur.lower().lstrip("\\"):
            return mult
    return None


def detect_salary(text):
    """Devuelve (min_eur_aprox, raw). No filtra, solo informa."""
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
        return None, ""
    lo = min(f[0] for f in found)
    hi = max(f[1] for f in found)
    return int(lo), f"{lo:,.0f}–{hi:,.0f} {unit}"


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
        role_w, role_label = _score_role(title, text, profile)
        domain_hits = _count_domain(text, profile)
        domain_w = min(domain_hits, 2) * 15
        skills_w = min(_score_skills(text, profile), 5) * 3
        loc_w = _score_location(j, profile)
        sen = _seniority_delta(text, profile)

        match = role_w + domain_w + skills_w + loc_w
        match = max(0, min(100, match))
        if sen < 0:
            match = max(0, match - 5)
        if ENGINEERING_ONLY.search(title) and not _match_any(title, role_keywords):
            match = max(0, match - 30)

        sal_eur, sal_raw = detect_salary(text)
        if sal_eur and sal_eur < 30000:
            match = max(0, match - 5)

        if match < args.min or match > args.max:
            continue

        reasons = []
        if role_label:
            reasons.append(role_label)
        if domain_hits:
            reasons.append(f"{domain_hits} dominios IA/Data")
        if skills_w:
            reasons.append("skills CV")

        j["match"] = match
        j["role_family"] = role_label or "otro"
        j["why"] = "; ".join(reasons)
        j["salary"] = sal_raw or ""
        j["salary_eur"] = sal_eur
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
