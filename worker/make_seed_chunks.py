#!/usr/bin/env python3
"""Genera seed chunks (100 filas por INSERT) para poblar D1 remoto de forma fiable.

Uso:
    python make_seed_chunks.py         # lee features.json -> worker/seed/chunk-XXX.sql
    # luego, en worker/:
    #   for f in seed/chunk-*.sql; do wrangler d1 execute cazador --remote --file=$f; done
"""
import json
import sys
from pathlib import Path

BASE = Path(__file__).parent
FEATURES = BASE.parent / "web" / "data" / "features.json"
OUT_DIR = BASE / "seed"

# importa matcher.py del repo para calcular el score del perfil por defecto
sys.path.insert(0, str(BASE.parent))
import matcher  # noqa: E402

BATCH = 5           # filas por sentencia INSERT (miniflare local limita ~100KB por statement)
STMT_PER_FILE = 10  # sentencias por archivo chunk


def esc(v):
    return (v or "").replace("'", "''")


def main():
    if not FEATURES.exists():
        sys.exit(f"No encuentro {FEATURES}. Ejecuta primero matcher.py")
    data = json.loads(FEATURES.read_text(encoding="utf-8"))
    jobs = data.get("jobs", []) if isinstance(data, dict) else data
    print(f"cargando {len(jobs)} ofertas desde {FEATURES}")

    profile = matcher.load_profile()
    print("perfil por defecto:", len(profile["role_taxonomy"]), "tiers")

    OUT_DIR.mkdir(exist_ok=True)
    for old in OUT_DIR.glob("chunk-*.sql"):
        old.unlink()

    cols = ("id,title,company,location,source,url,posted,salary_min_eur,salary_max_eur,"
            "salary_raw,lang,lang_req,years_min,eng_title,hard_block,hard_tech,"
            "title_lower,text_lower,match,role_family,why")
    inserts = []
    for i in range(0, len(jobs), BATCH):
        chunk = jobs[i:i + BATCH]
        vals = []
        for j in chunk:
            match, role_label, why = matcher.score(j, profile)
            v = (
                j["id"], j.get("title", ""), j.get("company", ""), j.get("location", ""),
                j.get("source", ""), j.get("url", ""), j.get("posted", ""),
                j.get("salary_min_eur"), j.get("salary_max_eur"), j.get("salary_raw", ""),
                j.get("lang", "en"), j.get("lang_req", ""), j.get("years_min", 0),
                1 if j.get("eng_title") else 0,
                1 if j.get("hard_block") else 0,
                1 if j.get("hard_tech") else 0,
                j.get("title_lower", ""),
                (j.get("text_lower", "") or "")[:3000],
                int(match), role_label, why,
            )
            vals.append("(" + ",".join(
                "'" + esc(x) + "'" if isinstance(x, str)
                else ("NULL" if x is None else str(int(x)))
                for x in v
            ) + ")")
        inserts.append(f"INSERT OR REPLACE INTO jobs ({cols}) VALUES\n" + ",\n".join(vals) + ";")

    n = 0
    for i in range(0, len(inserts), STMT_PER_FILE):
        block = inserts[i:i + STMT_PER_FILE]
        out = OUT_DIR / f"chunk-{n:03d}.sql"
        out.write_text("\n".join(block), encoding="utf-8")
        n += 1
    print(f"{len(inserts)} statements en {n} archivos en {OUT_DIR}")

    first = next(OUT_DIR.glob("chunk-*.sql"))
    print(f"tamano max: {max(f.stat().st_size for f in OUT_DIR.glob('chunk-*.sql')) / 1e6:.2f} MB")
    print(f"ejemplo: {first.name} {first.stat().st_size / 1e3:.1f} KB")


if __name__ == "__main__":
    main()
