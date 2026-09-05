#!/usr/bin/env bash
# Carga web/data/features.json -> seed/chunk-*.sql -> D1 remoto.
# Uso: CLOUDFLARE_API_TOKEN=... bash upload_d1.sh
set -euo pipefail
cd "$(dirname "$0")"

if [ -z "${CLOUDFLARE_API_TOKEN:-}" ]; then
  echo "Falta CLOUDFLARE_API_TOKEN" >&2
  exit 1
fi

python make_seed_chunks.py

npx wrangler d1 execute cazador --remote --command "DELETE FROM jobs;"
for f in seed/chunk-*.sql; do
  echo ">> ${f}"
  npx wrangler d1 execute cazador --remote --file="${f}"
done

echo "D1 actualizado OK"