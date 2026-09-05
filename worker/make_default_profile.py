#!/usr/bin/env python3
"""Genera worker/src/defaultProfile.ts desde profile.yaml.

El perfil por defecto es el de Pablo (profile.yaml), la referencia del producto.
Se usa para crear el perfil de cada usuario nuevo y para puntuar server-side.
"""
import json
import yaml
from pathlib import Path

BASE = Path(__file__).parent
YAML_PATH = BASE.parent / "profile.yaml"
OUT = BASE / "src" / "defaultProfile.ts"

cfg = yaml.safe_load(YAML_PATH.read_text(encoding="utf-8"))

skills = cfg["skills_keywords"]["keywords"]
if skills and isinstance(skills[0], list):
    skills = [kw for grp in skills for kw in grp]

profile = {
    "role_taxonomy": cfg["role_taxonomy"],
    "anti_identity": cfg["anti_identity"],
    "hard_reject": cfg["hard_reject"],
    "geography": cfg["geography"],
    "domain_keywords": cfg["domain_keywords"],
    "skills_keywords": {"weight": cfg["skills_keywords"].get("weight", 1), "keywords": skills},
    "seniority": cfg["seniority"],
    "spoken_languages": cfg["hard_reject"]["languages_spoken"],
    "min_match": 40,
    "max_match": 200,
}

js = (
    "// GENERADO por make_default_profile.py desde profile.yaml - no editar a mano.\n"
    "export interface DefaultProfile {\n"
    "  role_taxonomy: {\n"
    "    tier_a: { weight: number; label: string; titles: string[] };\n"
    "    tier_b: { weight: number; label: string; titles: string[] };\n"
    "    tier_c: { weight: number; label: string; titles: string[] };\n"
    "  };\n"
    "  anti_identity: { reject_title_patterns: string[] };\n"
    "  hard_reject: {\n"
    "    languages_forbidden: string[];\n"
    "    languages_spoken: string[];\n"
    "    max_years_experience: number;\n"
    "    restricted_locations: string[];\n"
    "    forbidden_certs: string[];\n"
    "    production_patterns: string[];\n"
    "    established_network_patterns: string[];\n"
    "  };\n"
    "  geography: { weight: number; scoring: Record<string, number> };\n"
    "  domain_keywords: { weight: number; keywords: string[][] };\n"
    "  skills_keywords: { weight: number; keywords: string[] };\n"
    "  seniority: {\n"
    "    bonus: string[];\n"
    "    penalty: string[];\n"
    "    director_penalty: number;\n"
    "    junior_penalty: number;\n"
    "  };\n"
    "  spoken_languages: string[];\n"
    "  min_match: number;\n"
    "  max_match: number;\n"
    "}\n\n"
    "export const DEFAULT_PROFILE: DefaultProfile = "
    + json.dumps(profile, ensure_ascii=False, indent=2)
    + ";\n"
)
OUT.write_text(js, encoding="utf-8")
print(f"{OUT} ({OUT.stat().st_size / 1024:.1f} KB)")