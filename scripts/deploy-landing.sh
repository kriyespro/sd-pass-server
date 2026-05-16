#!/bin/sh
# Deploy landing page + templates (run on the server in ~/sd-pass-server)
set -e
cd "$(dirname "$0")/.."
COMPOSE="docker compose -f docker-compose.prod.yml --env-file .env.prod"

echo "=== 1. Pull latest ==="
git pull origin main

echo "=== 2. Check landing file on disk ==="
if grep -q "in Seconds with AI" templates/pages/home.jinja; then
  echo "OK: new landing page is in git checkout"
else
  echo "ERROR: templates/pages/home.jinja is still OLD — git pull failed?"
  exit 1
fi

echo "=== 3. Recreate web (applies templates volume + latest image) ==="
$COMPOSE up -d --build web

echo "=== 4. Wait for Gunicorn ==="
sleep 35

echo "=== 5. What the container sees ==="
$COMPOSE exec web head -3 /app/templates/pages/home.jinja

echo "=== 6. HTTP check from server ==="
curl -sS -H 'Host: crorepatinetwork.com' http://127.0.0.1:9898/ | grep -o 'in Seconds with AI\|Mini PaaS for institutes' | head -1 || true

echo ""
echo "Done. Purge Cloudflare cache if browser still shows old page."
