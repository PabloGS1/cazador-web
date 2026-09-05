#!/usr/bin/env python3
"""Genera seed.sql para poblar la tabla D1 `jobs` desde web/data/features.json.

Uso:
    python make_seed_sql.py            # lee ../../web/data/features.json -> seed.sql
    wrangler d1 execute cazador --remote --file=seed.sql
"""
import json
import sys
from pathlib import Path

BASE = Path(__file__).parent
FEATURES = BASE.parent / "web" / "data" / "features.json"
OUT = BASE / "seed.sql"

BATCH = 400  # filas por sentencia INSERT


def esc(v):
    return (v or "").replace("'", "''")


def main():
    if not FEATURES.exists():
        sys.exit(f"No encuentro {FEATURES}. Ejecuta primero matcher.py")
    data = json.loads(FEATURES.read_text(encoding="utf-8"))
    jobs = data.get("jobs", []) if isinstance(data, dict) else data
    print(f"cargando {len(jobs)} ofertas desde {FEATURES}")

    cols = ("id,title,company,location,source,url,posted,salary_min_eur,salary_max_eur,"
            "salary_raw,lang,lang_req,years_min,eng_title,hard_block,hard_tech,"
            "title_lower,text_lower")
    lines = ["BEGIN TRANSACTION;"]
    for i in range(0, len(jobs), BATCH):
        chunk = jobs[i:i + BATCH]
        vals = []
        for j in chunk:
            v = (
                j["id"], j.get("title", ""), j.get("company", ""), j.get("location", ""),
                j.get("source", ""), j.get("url", ""), j.get("posted", ""),
                j.get("salary_min_eur"), j.get("salary_max_eur"), j.get("salary_raw", ""),
                j.get("lang", "en"), j.get("lang_req", ""), j.get("years_min", 0),
                1 if j.get("eng_title") else 0,
                1 if j.get("hard_block") else 0,
                1 if j.get("hard_tech") else 0,
                j.get("title_lower", ""), j.get("text_lower", ""),
            )
            vals.append("(" + ",".join(
                "'" + esc(x) + "'" if isinstance(x, str)
                else ("NULL" if x is None else str(int(x)))
                for x in v
            ) + ")")
        lines.append(f"INSERT OR REPLACE INTO jobs ({cols}) VALUES\n" + ",\n".join(vals) + ";")
    lines.append("COMMIT;")

    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"seed.sql generado ({len(jobs)} filas, {OUT.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
