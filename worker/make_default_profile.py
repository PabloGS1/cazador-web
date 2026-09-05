#!/usr/bin/env python3
"""Genera worker/src/defaultProfile.ts desde profile.yaml.

El perfil por defecto es el de Pablo (profile.yaml), la referencia del producto.
Se usa para crear el perfil de cada usuario nuevo y para saber que los scores
precalculados de la tabla jobs (match/role_family/why) le corresponden.
"""
import json
import yaml
from pathlib import Path

BASE = Path(__file__).parent
YAML_PATH = BASE.parent / "profile.yaml"
OUT = BASE / "src" / "defaultProfile.ts"

cfg = yaml.safe_load(YAML_PATH.read_text(encoding="utf-8"))
sen = {k: cfg["seniority"][k] for k in ("bonus", "penalty")}
profile = {
    "target_roles": cfg["target_roles"],
    "domain_keywords": {"keywords": cfg["domain_keywords"]["keywords"]},
    "skills_keywords": cfg["skills_from_cv"]["keywords"],
    "location_scoring": cfg["location_prefs"]["scoring"],
    "seniority": sen,
    "spoken_languages": cfg.get("spoken_languages", ["english"]),
    "min_match": 40,
    "max_match": 200,
}

js = (
    "// GENERADO por make_default_profile.py desde profile.yaml - no editar a mano.\n"
    "export interface DefaultProfile {\n"
    "  target_roles: Record<string, { label: string; weight: number; keywords: string[] }>;\n"
    "  domain_keywords: { keywords: string[][] };\n"
    "  skills_keywords: string[];\n"
    "  location_scoring: Record<string, number>;\n"
    "  seniority: { bonus: string[]; penalty: string[] };\n"
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
