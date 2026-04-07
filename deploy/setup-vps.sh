#!/usr/bin/env bash
# First-time VPS setup for rpg-engine-basic
# Run as root on the Hostinger VPS
set -euo pipefail

APP_DIR="/var/www/rpg-engine"

echo "=== Backing up old app (if exists) ==="
if [ -d "$APP_DIR" ]; then
    mv "$APP_DIR" "${APP_DIR}-v1-backup-$(date +%Y%m%d)"
    echo "Old app backed up."
fi

echo "=== Cloning repo ==="
git clone https://github.com/mcgowee/rpg-engine-basic.git "$APP_DIR"
cd "$APP_DIR"

echo "=== Setting up Python venv ==="
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

echo "=== Setting up Node/SvelteKit ==="
cd web
npm ci
npm run build
cd ..

echo "=== Creating .env ==="
if [ ! -f .env ]; then
    cp deploy/.env.production .env
    echo ""
    echo "!!! IMPORTANT: Edit /var/www/rpg-engine/.env with your Azure API keys and SECRET_KEY !!!"
    echo ""
fi

echo "=== Installing systemd services ==="
cp deploy/rpg-flask.service /etc/systemd/system/
cp deploy/rpg-web.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable rpg-flask rpg-web

echo "=== Starting services ==="
systemctl start rpg-flask
systemctl start rpg-web

echo ""
echo "=== Setup complete ==="
echo "Flask: systemctl status rpg-flask"
echo "Web:   systemctl status rpg-web"
echo ""
echo "Don't forget to:"
echo "  1. Edit /var/www/rpg-engine/.env with your Azure keys and SECRET_KEY"
echo "  2. Update the GitHub webhook to point to this repo"
echo "  3. Verify: curl http://localhost:5051/graph-registry"
echo "  4. Verify: curl http://localhost:3002"
