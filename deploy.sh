#!/usr/bin/env bash
# deploy.sh — called by webhook on git push
# Run from the app root: /var/www/rpg-engine/
set -euo pipefail

APP_DIR="/var/www/rpg-engine"
cd "$APP_DIR"

echo "=== Pulling latest code ==="
git fetch origin main
git reset --hard origin/main

echo "=== Installing Python deps ==="
source .venv/bin/activate
pip install -q -r requirements.txt

echo "=== Building SvelteKit ==="
cd web
npm ci --prefer-offline
npm run build
cd ..

echo "=== Restarting services ==="
systemctl restart rpg-flask
systemctl restart rpg-web

echo "=== Deploy complete ==="
date
