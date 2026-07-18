#!/bin/bash
# ============================================================
# deploy.sh — Football Pulse AI
# Run on a fresh Ubuntu 22.04 Google Cloud Free Tier VM (e2-micro)
# Usage: chmod +x deploy.sh && ./deploy.sh
# ============================================================
set -euo pipefail

APP_DIR="/home/ubuntu/football_pulse_ai"
SERVICE="football-pulse"

echo "======================================================"
echo "  Football Pulse AI — Deployment Script"
echo "======================================================"

# ── System update ──────────────────────────────────────────
echo "[1/8] Updating system packages…"
sudo apt-get update -y && sudo apt-get upgrade -y

# ── Install dependencies ───────────────────────────────────
echo "[2/8] Installing system dependencies…"
sudo apt-get install -y \
    python3 python3-pip python3-venv \
    git curl wget unzip \
    fonts-dejavu-core fonts-liberation \
    libjpeg-turbo8-dev zlib1g-dev \
    libfreetype6-dev

# ── Clone / upload project ─────────────────────────────────
echo "[3/8] Setting up project directory…"
if [ ! -d "$APP_DIR" ]; then
    # If you pushed to GitHub:
    # git clone https://github.com/YOUR_HANDLE/football_pulse_ai.git $APP_DIR
    # Otherwise the files are already here via gcloud scp
    mkdir -p "$APP_DIR"
fi
cd "$APP_DIR"

# ── Python virtualenv ──────────────────────────────────────
echo "[4/8] Creating Python virtual environment…"
python3 -m venv venv
source venv/bin/activate

# ── Install Python packages ────────────────────────────────
echo "[5/8] Installing Python requirements…"
pip install --upgrade pip
pip install -r requirements.txt

# ── .env setup ────────────────────────────────────────────
if [ ! -f ".env" ]; then
    echo "[6/8] Creating .env from template — EDIT THIS FILE!"
    cp .env.example .env
    echo ""
    echo "  ⚠️  IMPORTANT: Edit $APP_DIR/.env and add your API keys"
    echo "  Then run: sudo systemctl restart $SERVICE"
    echo ""
else
    echo "[6/8] .env already exists — skipping."
fi

# ── Systemd service ────────────────────────────────────────
echo "[7/8] Installing systemd service…"
sudo cp football-pulse.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE"
sudo systemctl start "$SERVICE"

# ── Status check ──────────────────────────────────────────
echo "[8/8] Checking service status…"
sleep 3
sudo systemctl status "$SERVICE" --no-pager || true

echo ""
echo "======================================================"
echo "  Deployment complete!"
echo ""
echo "  Useful commands:"
echo "    sudo systemctl status $SERVICE"
echo "    sudo systemctl restart $SERVICE"
echo "    sudo journalctl -u $SERVICE -f"
echo "    tail -f $APP_DIR/logs/football_pulse.log"
echo ""
echo "  Test poster generation:"
echo "    cd $APP_DIR && source venv/bin/activate"
echo "    python test_posters.py"
echo "======================================================"
